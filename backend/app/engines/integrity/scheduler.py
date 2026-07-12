"""Integrity Audit Scheduler — periodic background auditing of completed W1 workflows.

Follows the DigestScheduler pattern. Checks on a configurable interval for
completed W1 workflows that haven't been integrity-audited yet and runs
the DataIntegrityAuditorAgent's quick_check on their synthesis output.

Phase 1 implementation: asyncio background task.
Phase 2+: migrate to Celery periodic task.
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.db.database import engine as db_engine
from app.models.integrity import AuditFinding, AuditRun
from app.models.workflow import WorkflowInstance
from sqlmodel import Session, select

logger = logging.getLogger(__name__)


class IntegrityScheduler:
    """Runs periodic integrity audits on completed workflows.

    Scans for W1 workflows in COMPLETED state that don't have an associated
    AuditRun record, then runs deterministic checks (quick_check) on each.

    Usage:
        scheduler = IntegrityScheduler(
            auditor_agent=agent,
            interval_hours=24.0,
            enabled=True,
        )
        await scheduler.start()
        # ... app runs ...
        scheduler.stop()
    """

    def __init__(
        self,
        auditor_agent,
        interval_hours: float = 24.0,
        enabled: bool = True,
    ) -> None:
        self._auditor = auditor_agent
        self._interval_seconds = interval_hours * 3600
        self._enabled = enabled
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the scheduler as a background task."""
        if not self._enabled:
            logger.info("Integrity scheduler disabled")
            return
        if self._auditor is None:
            logger.warning("Integrity scheduler: no auditor agent, disabled")
            return
        if self._running:
            logger.warning("Integrity scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "Integrity scheduler started (interval: %.1f hours)",
            self._interval_seconds / 3600,
        )

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Integrity scheduler stopped")

    async def _loop(self) -> None:
        """Main scheduling loop."""
        while self._running:
            try:
                await asyncio.sleep(self._interval_seconds)
                if not self._running:
                    break
                await self._check_and_audit()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Integrity scheduler error: %s", e, exc_info=True)
                await asyncio.sleep(300)  # Back off 5 min on error

    async def _check_and_audit(self) -> None:
        """Find un-audited completed W1 workflows and run quick_check."""
        # Get completed W1 workflow IDs
        with Session(db_engine) as session:
            completed = session.exec(
                select(WorkflowInstance)
                .where(WorkflowInstance.template == "W1")
                .where(WorkflowInstance.state == "COMPLETED")
            ).all()

            # Get already-audited workflow IDs
            audited_ids = set(
                session.exec(
                    select(AuditRun.workflow_id).where(AuditRun.workflow_id.isnot(None))
                ).all()
            )

        # Filter to un-audited
        to_audit = [w for w in completed if w.id not in audited_ids]
        if not to_audit:
            return

        logger.info("Integrity scheduler: %d un-audited W1 workflows found", len(to_audit))

        for wf in to_audit:
            try:
                await self._audit_workflow(wf)
            except Exception as e:
                logger.error("Scheduled audit failed for workflow %s: %s", wf.id, e)

    async def _audit_workflow(self, wf: WorkflowInstance) -> None:
        """Run quick_check on a single workflow's synthesis output."""
        # Extract text from session_manifest
        text_parts = []
        manifest = wf.session_manifest or {}

        # Try synthesis, report, or any text content
        for key in ("synthesis", "report", "summary", "final_report"):
            val = manifest.get(key)
            if val and isinstance(val, str):
                text_parts.append(val)
            elif val and isinstance(val, dict):
                for subkey in ("summary", "text", "content"):
                    sub = val.get(subkey)
                    if sub and isinstance(sub, str):
                        text_parts.append(sub)

        text = "\n\n".join(text_parts) if text_parts else ""
        if not text:
            logger.debug("No text to audit in workflow %s", wf.id)
            # Still record the run so we don't retry
            self._record_run(wf.id, 0, {}, {}, "clean", "", 0.0, 0)
            return

        start_time = time.time()
        output = await self._auditor.quick_check(text)
        duration_ms = int((time.time() - start_time) * 1000)

        result = output.output or {}
        findings_list = result.get("findings", [])

        # Persist findings
        with Session(db_engine) as session:
            for f in findings_list:
                db_finding = AuditFinding(
                    category=f.get("category", "unknown"),
                    severity=f.get("severity", "info"),
                    title=f.get("title", ""),
                    description=f.get("description", ""),
                    source_text=f.get("source_text", ""),
                    suggestion=f.get("suggestion", ""),
                    confidence=f.get("confidence", 0.8),
                    checker=f.get("checker", ""),
                    finding_metadata=f.get("metadata", {}),
                    workflow_id=wf.id,
                )
                session.add(db_finding)
            session.commit()

        self._record_run(
            workflow_id=wf.id,
            total_findings=result.get("total_findings", len(findings_list)),
            by_severity=result.get("findings_by_severity", {}),
            by_category=result.get("findings_by_category", {}),
            overall_level=result.get("overall_level", "clean"),
            summary=output.summary or "",
            cost=output.cost,
            duration_ms=duration_ms,
        )

        logger.info(
            "Scheduled audit for workflow %s: %d findings (%s)",
            wf.id, len(findings_list), result.get("overall_level", "clean"),
        )

    def _record_run(
        self,
        workflow_id: str,
        total_findings: int,
        by_severity: dict,
        by_category: dict,
        overall_level: str,
        summary: str,
        cost: float,
        duration_ms: int,
    ) -> None:
        """Persist an AuditRun record."""
        with Session(db_engine) as session:
            run = AuditRun(
                workflow_id=workflow_id,
                trigger="scheduled",
                total_findings=total_findings,
                findings_by_severity=by_severity,
                findings_by_category=by_category,
                overall_level=overall_level,
                summary=summary,
                cost=cost,
                duration_ms=duration_ms,
            )
            session.add(run)
            session.commit()

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def get_status(self) -> dict:
        """Get scheduler status for health checks."""
        return {
            "enabled": self._enabled,
            "running": self.is_running,
            "interval_hours": self._interval_seconds / 3600,
        }
