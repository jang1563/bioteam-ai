"""CheckpointManager — SQLite-backed persistence for long-term workflow steps.

Saves each completed step as a SessionCheckpoint row so that W9 (or any
multi-step workflow) can resume after crashes, restarts, or budget pauses.

Also manages progress.json files under data/runs/{workflow_id}/ for
real-time progress monitoring without DB queries.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.models.agent import AgentOutput
from app.models.session_checkpoint import SessionCheckpoint
from app.models.step_error import StepErrorReport
from sqlmodel import Session, select

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages per-step SQLite checkpoints for long-term workflow recovery.

    Usage:
        mgr = CheckpointManager(db_session)
        await mgr.save_step(instance, step_id=1, step_name="GENOMIC_ANALYSIS",
                            agent_id="t01_genomics", output=agent_output)
        prior = mgr.load_completed_steps(workflow_id)
        # prior = {"SCOPE": AgentOutput(...), "GENOMIC_ANALYSIS": AgentOutput(...)}
    """

    def __init__(self, db_session: Session) -> None:
        self._db = db_session

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_step(
        self,
        workflow_id: str,
        step_id: str,
        step_index: int,
        agent_id: str,
        output: AgentOutput | list[AgentOutput],
        cost: float = 0.0,
        status: str = "completed",
        error: str | None = None,
        user_adjustment: str | None = None,
    ) -> SessionCheckpoint:
        """Atomically save a completed step to SQLite.

        If a checkpoint for (workflow_id, step_id) already exists it is
        overwritten (for step re-runs).
        """
        if not settings.checkpoint_enabled:
            return self._make_transient(workflow_id, step_id, step_index, agent_id, output, cost)

        # Serialize output
        if isinstance(output, list):
            output_json = {"outputs": [o.model_dump(mode="json") for o in output]}
        else:
            output_json = output.model_dump(mode="json")

        # Upsert
        existing = self._db.exec(
            select(SessionCheckpoint).where(
                SessionCheckpoint.workflow_id == workflow_id,
                SessionCheckpoint.step_id == step_id,
            )
        ).first()

        if existing:
            existing.agent_output = output_json
            existing.cost_incurred = cost
            existing.status = status
            existing.error = error
            existing.user_adjustment = user_adjustment
            existing.completed_at = datetime.now(timezone.utc)
            existing.idempotency_token = existing.idempotency_token  # keep token
            self._db.add(existing)
            self._db.commit()
            self._db.refresh(existing)
            return existing

        cp = SessionCheckpoint(
            workflow_id=workflow_id,
            step_id=step_id,
            step_index=step_index,
            agent_id=agent_id,
            status=status,
            agent_output=output_json,
            cost_incurred=cost,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            error=error,
            user_adjustment=user_adjustment,
        )
        self._db.add(cp)
        self._db.commit()
        self._db.refresh(cp)
        logger.debug("Checkpoint saved: %s / %s", workflow_id[:8], step_id)
        return cp

    def save_error_report(
        self,
        workflow_id: str,
        step_id: str,
        report: StepErrorReport,
    ) -> None:
        """Persist an error report as a 'failed' checkpoint row."""
        if not settings.checkpoint_enabled:
            return
        try:
            cp = SessionCheckpoint(
                workflow_id=workflow_id,
                step_id=step_id,
                step_index=0,
                agent_id=report.agent_id,
                status="failed",
                agent_output=report.model_dump(mode="json"),
                error=report.error_message,
            )
            self._db.add(cp)
            self._db.commit()
        except Exception as e:
            logger.warning("Failed to persist error report: %s", e)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load_completed_steps(
        self, workflow_id: str,
    ) -> dict[str, AgentOutput | list[AgentOutput]]:
        """Load all completed step results for a workflow.

        Returns:
            Dict mapping step_id → AgentOutput (single) or list[AgentOutput]
            (parallel steps).
        """
        if not settings.checkpoint_enabled:
            return {}

        rows = self._db.exec(
            select(SessionCheckpoint)
            .where(
                SessionCheckpoint.workflow_id == workflow_id,
                SessionCheckpoint.status.in_(["completed", "skipped", "injected"]),
            )
            .order_by(SessionCheckpoint.step_index)
        ).all()

        result: dict[str, AgentOutput | list[AgentOutput]] = {}
        for row in rows:
            try:
                payload = row.agent_output
                if "outputs" in payload:
                    outputs = [AgentOutput(**o) for o in payload["outputs"]]
                    # Return full list for parallel steps (not just first)
                    result[row.step_id] = outputs if outputs else [AgentOutput(agent_id=row.agent_id)]
                else:
                    result[row.step_id] = AgentOutput(**payload)
            except Exception as e:
                logger.warning("Failed to restore checkpoint %s/%s: %s", workflow_id[:8], row.step_id, e)
        return result

    def get_cost_total(self, workflow_id: str) -> float:
        """Sum of all checkpoint costs for a workflow (for resume budget calc)."""
        rows = self._db.exec(
            select(SessionCheckpoint).where(
                SessionCheckpoint.workflow_id == workflow_id,
                SessionCheckpoint.status == "completed",
            )
        ).all()
        return sum(r.cost_incurred for r in rows)

    # ------------------------------------------------------------------
    # Progress File
    # ------------------------------------------------------------------

    def write_progress_file(
        self,
        workflow_id: str,
        template: str,
        state: str,
        current_step: str,
        step_index: int,
        total_steps: int,
        cost_used: float,
        budget_total: float,
    ) -> None:
        """Write a human-readable progress.json under data/runs/{workflow_id}/."""
        if not settings.checkpoint_enabled:
            return
        run_dir = Path(settings.checkpoint_dir) / workflow_id
        run_dir.mkdir(parents=True, exist_ok=True)
        pct = round(step_index / max(total_steps, 1) * 100)
        progress = {
            "workflow_id": workflow_id,
            "template": template,
            "state": state,
            "current_step": current_step,
            "step_index": step_index,
            "total_steps": total_steps,
            "pct_complete": pct,
            "cost_used": round(cost_used, 4),
            "cost_remaining": round(max(0, budget_total - cost_used), 4),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        path = run_dir / "progress.json"
        path.write_text(json.dumps(progress, indent=2))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_transient(
        workflow_id: str,
        step_id: str,
        step_index: int,
        agent_id: str,
        output: AgentOutput | list[AgentOutput],
        cost: float,
    ) -> SessionCheckpoint:
        """Return a transient (unsaved) checkpoint when disabled."""
        if isinstance(output, list):
            output_json = {"outputs": [o.model_dump(mode="json") for o in output]}
        else:
            output_json = output.model_dump(mode="json")
        return SessionCheckpoint(
            workflow_id=workflow_id,
            step_id=step_id,
            step_index=step_index,
            agent_id=agent_id,
            agent_output=output_json,
            cost_incurred=cost,
        )
