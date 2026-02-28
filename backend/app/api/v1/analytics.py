"""Analytics API — workflow metrics, cost tracking, agent usage.

GET /api/v1/analytics/summary     — overview stats (runs, cost, tokens)
GET /api/v1/analytics/workflows   — breakdown by template and state
GET /api/v1/analytics/cost-by-day — daily cost time series (last N days)
GET /api/v1/analytics/agents      — top agents by cost and token usage
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.db.database import get_session
from app.models.cost import CostRecord
from app.models.workflow import WorkflowInstance
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session, select

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


# === Response models ===


class AnalyticsSummary(BaseModel):
    total_workflows: int
    completed_workflows: int
    failed_workflows: int
    running_workflows: int
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    avg_cost_per_workflow: float


class TemplateStats(BaseModel):
    template: str
    total: int
    completed: int
    failed: int
    total_cost_usd: float


class WorkflowBreakdownResponse(BaseModel):
    by_template: list[TemplateStats]
    by_state: dict[str, int]


class DailyCostEntry(BaseModel):
    date: str          # YYYY-MM-DD
    cost_usd: float
    workflow_count: int


class CostByDayResponse(BaseModel):
    days: int
    entries: list[DailyCostEntry]
    total_cost_usd: float


class AgentStats(BaseModel):
    agent_id: str
    call_count: int
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int


class AgentsResponse(BaseModel):
    agents: list[AgentStats]
    total_agents_used: int


# === Endpoints ===


@router.get("/summary", response_model=AnalyticsSummary)
def get_summary(session: Session = Depends(get_session)) -> AnalyticsSummary:
    """Return high-level analytics summary."""
    workflows = session.exec(select(WorkflowInstance)).all()
    cost_records = session.exec(select(CostRecord)).all()

    total = len(workflows)
    completed = sum(1 for w in workflows if w.state == "COMPLETED")
    failed = sum(1 for w in workflows if w.state == "FAILED")
    running = sum(1 for w in workflows if w.state in ("RUNNING", "WAITING_HUMAN", "PAUSED"))

    total_cost = sum(r.cost_usd for r in cost_records)
    total_input = sum(r.input_tokens for r in cost_records)
    total_output = sum(r.output_tokens for r in cost_records)
    avg_cost = total_cost / completed if completed > 0 else 0.0

    return AnalyticsSummary(
        total_workflows=total,
        completed_workflows=completed,
        failed_workflows=failed,
        running_workflows=running,
        total_cost_usd=round(total_cost, 4),
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        avg_cost_per_workflow=round(avg_cost, 4),
    )


@router.get("/workflows", response_model=WorkflowBreakdownResponse)
def get_workflow_breakdown(session: Session = Depends(get_session)) -> WorkflowBreakdownResponse:
    """Return workflow counts broken down by template and state."""
    workflows = session.exec(select(WorkflowInstance)).all()

    # Group by template
    by_tmpl: dict[str, dict] = defaultdict(lambda: {"total": 0, "completed": 0, "failed": 0})
    cost_by_wid: dict[str, float] = defaultdict(float)

    cost_records = session.exec(select(CostRecord)).all()
    for r in cost_records:
        if r.workflow_id:
            cost_by_wid[r.workflow_id] += r.cost_usd

    by_state: dict[str, int] = defaultdict(int)
    for w in workflows:
        tmpl = w.template or "unknown"
        by_tmpl[tmpl]["total"] += 1
        if w.state == "COMPLETED":
            by_tmpl[tmpl]["completed"] += 1
        elif w.state == "FAILED":
            by_tmpl[tmpl]["failed"] += 1
        by_state[w.state] += 1

    template_stats = [
        TemplateStats(
            template=tmpl,
            total=v["total"],
            completed=v["completed"],
            failed=v["failed"],
            total_cost_usd=round(
                sum(cost_by_wid[w.id] for w in workflows if (w.template or "unknown") == tmpl),
                4,
            ),
        )
        for tmpl, v in sorted(by_tmpl.items())
    ]

    return WorkflowBreakdownResponse(
        by_template=template_stats,
        by_state=dict(by_state),
    )


@router.get("/cost-by-day", response_model=CostByDayResponse)
def get_cost_by_day(
    days: int = Query(default=30, ge=1, le=365),
    session: Session = Depends(get_session),
) -> CostByDayResponse:
    """Return daily cost aggregated for the last N days."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    records = session.exec(select(CostRecord)).all()
    workflows = session.exec(select(WorkflowInstance)).all()

    # Build lookup: date → {cost, workflow_ids}
    daily_cost: dict[str, float] = defaultdict(float)
    daily_wids: dict[str, set] = defaultdict(set)

    for r in records:
        ts = r.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts >= since:
            day = ts.strftime("%Y-%m-%d")
            daily_cost[day] += r.cost_usd
            if r.workflow_id:
                daily_wids[day].add(r.workflow_id)

    # Also count workflows by creation date (even if no cost records)
    workflow_day_count: dict[str, set] = defaultdict(set)
    for w in workflows:
        ts = w.created_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts >= since:
            day = ts.strftime("%Y-%m-%d")
            workflow_day_count[day].add(w.id)

    # Fill all days in range (even zeros)
    entries = []
    for i in range(days):
        day = (datetime.now(timezone.utc) - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        wid_set = daily_wids.get(day, set()) | workflow_day_count.get(day, set())
        entries.append(
            DailyCostEntry(
                date=day,
                cost_usd=round(daily_cost.get(day, 0.0), 4),
                workflow_count=len(wid_set),
            )
        )

    total = round(sum(e.cost_usd for e in entries), 4)
    return CostByDayResponse(days=days, entries=entries, total_cost_usd=total)


@router.get("/agents", response_model=AgentsResponse)
def get_agent_stats(session: Session = Depends(get_session)) -> AgentsResponse:
    """Return per-agent cost and token usage stats."""
    records = session.exec(select(CostRecord)).all()

    agg: dict[str, dict] = defaultdict(
        lambda: {"call_count": 0, "cost": 0.0, "input_tokens": 0, "output_tokens": 0}
    )
    for r in records:
        agg[r.agent_id]["call_count"] += 1
        agg[r.agent_id]["cost"] += r.cost_usd
        agg[r.agent_id]["input_tokens"] += r.input_tokens
        agg[r.agent_id]["output_tokens"] += r.output_tokens

    agents = sorted(
        [
            AgentStats(
                agent_id=aid,
                call_count=v["call_count"],
                total_cost_usd=round(v["cost"], 4),
                total_input_tokens=v["input_tokens"],
                total_output_tokens=v["output_tokens"],
            )
            for aid, v in agg.items()
        ],
        key=lambda a: a.total_cost_usd,
        reverse=True,
    )

    return AgentsResponse(agents=agents, total_agents_used=len(agents))
