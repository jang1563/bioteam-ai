"""CostTracker — budget enforcement and cost analytics.

Tracks per-workflow and per-session costs, enforces budgets,
and generates accuracy reports comparing estimated vs actual.

Storage: SQLite (cost_record table) via CostRecord model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.models.cost import CostAccuracyReport, CostRecord
from sqlmodel import Session, select

# Default budget per workflow template
WORKFLOW_BUDGETS: dict[str, float] = {
    "direct_query": 1.0,
    "W1": 5.0,
    "W2": 15.0,
    "W3": 10.0,
    "W4": 25.0,
    "W5": 30.0,
    "W6": 5.0,
}

# Estimated cost per call by model tier (used for pre-call estimation)
COST_PER_1K_INPUT: dict[str, float] = {
    "opus": 0.015,
    "sonnet": 0.003,
    "haiku": 0.001,
}

COST_PER_1K_OUTPUT: dict[str, float] = {
    "opus": 0.075,
    "sonnet": 0.015,
    "haiku": 0.005,
}


class CostTracker:
    """Tracks and enforces cost budgets for workflows and sessions.

    Usage:
        tracker = CostTracker(session)

        # Pre-step: check budget
        if not tracker.check_budget("workflow_123", estimated_cost=0.15):
            raise OverBudgetError(...)

        # Post-step: record actual cost
        tracker.record_actual(
            workflow_id="workflow_123",
            step_id="SEARCH",
            agent_id="knowledge_manager",
            model_tier="sonnet",
            model_version="claude-sonnet-4-6",
            input_tokens=1500,
            output_tokens=800,
            cost_usd=0.057,
        )
    """

    def __init__(self, db_session: Session) -> None:
        self.db = db_session
        self.session_budget = settings.session_budget
        self.alert_threshold = settings.budget_alert_threshold

    def check_budget(
        self,
        workflow_id: str,
        estimated_cost: float,
        template: str = "direct_query",
    ) -> bool:
        """Check if a workflow has sufficient budget for the next step.

        Args:
            workflow_id: The workflow instance ID.
            estimated_cost: Estimated cost of the next step.
            template: Workflow template name for budget lookup.

        Returns:
            True if budget is sufficient, False if over budget.
        """
        workflow_budget = WORKFLOW_BUDGETS.get(template, 5.0)
        spent = self.get_workflow_cost(workflow_id)
        remaining = workflow_budget - spent

        if remaining < estimated_cost:
            return False

        # Also check session budget
        session_spent = self.get_session_cost()
        if (session_spent + estimated_cost) > self.session_budget:
            return False

        return True

    def get_budget_status(
        self,
        workflow_id: str,
        template: str = "direct_query",
    ) -> dict[str, Any]:
        """Get budget status for a workflow.

        Returns:
            Dict with budget, spent, remaining, percentage, alert flag.
        """
        workflow_budget = WORKFLOW_BUDGETS.get(template, 5.0)
        spent = self.get_workflow_cost(workflow_id)
        remaining = workflow_budget - spent
        pct = spent / workflow_budget if workflow_budget > 0 else 0.0

        return {
            "workflow_id": workflow_id,
            "template": template,
            "budget": workflow_budget,
            "spent": round(spent, 4),
            "remaining": round(remaining, 4),
            "percentage": round(pct, 4),
            "alert": pct >= self.alert_threshold,
        }

    def record_actual(
        self,
        workflow_id: str | None,
        step_id: str | None,
        agent_id: str,
        model_tier: str,
        model_version: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_input_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> CostRecord:
        """Record an actual cost from an agent call.

        Args:
            workflow_id: Workflow instance ID (None for direct queries).
            step_id: Workflow step ID (None for direct queries).
            agent_id: The agent that made the call.
            model_tier: "opus", "sonnet", or "haiku".
            model_version: Full model ID string.
            input_tokens: Actual input tokens used.
            output_tokens: Actual output tokens used.
            cached_input_tokens: Tokens served from cache.
            cost_usd: Actual cost in USD.

        Returns:
            The persisted CostRecord.
        """
        record = CostRecord(
            workflow_id=workflow_id,
            step_id=step_id,
            agent_id=agent_id,
            model_tier=model_tier,
            model_version=model_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            cost_usd=cost_usd,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_workflow_cost(self, workflow_id: str) -> float:
        """Get total cost for a workflow."""
        stmt = select(CostRecord).where(CostRecord.workflow_id == workflow_id)
        records = self.db.exec(stmt).all()
        return sum(r.cost_usd for r in records)

    def get_session_cost(self) -> float:
        """Get total cost for the current session (all records)."""
        stmt = select(CostRecord)
        records = self.db.exec(stmt).all()
        return sum(r.cost_usd for r in records)

    def get_workflow_breakdown(self, workflow_id: str) -> list[dict]:
        """Get per-step cost breakdown for a workflow."""
        stmt = (
            select(CostRecord)
            .where(CostRecord.workflow_id == workflow_id)
            .order_by(CostRecord.timestamp)
        )
        records = self.db.exec(stmt).all()

        breakdown = []
        for r in records:
            breakdown.append({
                "step_id": r.step_id,
                "agent_id": r.agent_id,
                "model_tier": r.model_tier,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cached_input_tokens": r.cached_input_tokens,
                "cost_usd": r.cost_usd,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            })
        return breakdown

    def get_accuracy_report(
        self,
        workflow_id: str,
        template: str,
        estimated_cost: float,
    ) -> CostAccuracyReport:
        """Compare estimated vs actual cost for a workflow.

        Used at phase milestones for cost validation gates.
        """
        actual = self.get_workflow_cost(workflow_id)
        ratio = actual / estimated_cost if estimated_cost > 0 else 0.0

        return CostAccuracyReport(
            workflow_id=workflow_id,
            template=template,
            estimated_cost=estimated_cost,
            actual_cost=actual,
            ratio=round(ratio, 3),
            per_step_breakdown=self.get_workflow_breakdown(workflow_id),
            generated_at=datetime.now(timezone.utc),
        )

    def get_model_tier_summary(self) -> dict[str, dict]:
        """Get aggregated cost summary by model tier."""
        stmt = select(CostRecord)
        records = self.db.exec(stmt).all()

        summary: dict[str, dict] = {}
        for r in records:
            tier = r.model_tier
            if tier not in summary:
                summary[tier] = {
                    "calls": 0,
                    "total_cost": 0.0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                }
            summary[tier]["calls"] += 1
            summary[tier]["total_cost"] += r.cost_usd
            summary[tier]["total_input_tokens"] += r.input_tokens
            summary[tier]["total_output_tokens"] += r.output_tokens

        return summary
