"""Agent API endpoints — list, inspect, query, and get history for agents.

GET  /api/v1/agents — list all registered agents
GET  /api/v1/agents/{agent_id} — full spec + runtime status
POST /api/v1/agents/{agent_id}/query — ask an agent a question directly
GET  /api/v1/agents/{agent_id}/history — execution history for an agent
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.agents.registry import AgentRegistry
from app.db.database import engine as db_engine
from app.models.messages import ContextPackage
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["agents"])

# Module-level registry reference, set by main.py at startup
_registry: AgentRegistry | None = None


def set_registry(registry: AgentRegistry) -> None:
    """Wire up the agent registry (called from main.py lifespan)."""
    global _registry
    _registry = registry


def _get_registry() -> AgentRegistry:
    if _registry is None:
        raise HTTPException(status_code=503, detail="Agent registry not initialized.")
    return _registry


# === Response Models ===


class AgentListItem(BaseModel):
    """Summary of an agent for list view."""

    id: str
    name: str
    tier: str
    model_tier: str
    criticality: str = "optional"
    state: str = "idle"
    total_calls: int = 0
    total_cost: float = 0.0
    consecutive_failures: int = 0


class AgentDetail(BaseModel):
    """Full agent spec + runtime status."""

    id: str
    name: str
    tier: str
    model_tier: str
    model_tier_secondary: str | None = None
    division: str | None = None
    criticality: str = "optional"
    tools: list[str] = Field(default_factory=list)
    mcp_access: list[str] = Field(default_factory=list)
    literature_access: bool = False
    version: str = ""

    # Runtime status
    state: str = "idle"
    total_calls: int = 0
    total_cost: float = 0.0
    consecutive_failures: int = 0


class AgentQueryRequest(BaseModel):
    """Request to query an agent directly."""

    query: str = Field(min_length=1, max_length=5000)
    context: str = Field(default="", max_length=10000)


class AgentQueryResponse(BaseModel):
    """Response from an agent query."""

    agent_id: str
    answer: str
    cost: float
    duration_ms: int


class AgentHistoryEntry(BaseModel):
    """A single execution record for an agent."""

    timestamp: datetime
    workflow_id: str | None = None
    step_id: str | None = None
    cost: float = 0.0
    duration_ms: int = 0
    success: bool = True
    summary: str = ""


class AgentHistoryResponse(BaseModel):
    """Execution history for an agent."""

    agent_id: str
    entries: list[AgentHistoryEntry] = Field(default_factory=list)
    total_count: int = 0
    total_cost: float = 0.0


# === Endpoints ===


@router.get("/agents", response_model=list[AgentListItem])
async def list_agents() -> list[AgentListItem]:
    """List all registered agents with summary status."""
    registry = _get_registry()
    agents = registry.list_agents()
    statuses = {s.agent_id: s for s in registry.list_statuses()}

    items = []
    for spec in agents:
        status = statuses.get(spec.id)
        items.append(AgentListItem(
            id=spec.id,
            name=spec.name,
            tier=spec.tier,
            model_tier=spec.model_tier,
            criticality=spec.criticality,
            state=status.state if status else "unknown",
            total_calls=status.total_calls if status else 0,
            total_cost=status.total_cost if status else 0.0,
            consecutive_failures=status.consecutive_failures if status else 0,
        ))
    return items


@router.get("/agents/{agent_id}", response_model=AgentDetail)
async def get_agent(agent_id: str) -> AgentDetail:
    """Get full agent detail by ID."""
    registry = _get_registry()
    agent = registry.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    spec = agent.spec
    status = agent.status

    return AgentDetail(
        id=spec.id,
        name=spec.name,
        tier=spec.tier,
        model_tier=spec.model_tier,
        model_tier_secondary=spec.model_tier_secondary,
        division=spec.division,
        criticality=spec.criticality,
        tools=spec.tools,
        mcp_access=spec.mcp_access,
        literature_access=spec.literature_access,
        version=spec.version,
        state=status.state,
        total_calls=status.total_calls,
        total_cost=status.total_cost,
        consecutive_failures=status.consecutive_failures,
    )


@router.post("/agents/{agent_id}/query", response_model=AgentQueryResponse)
async def query_agent(agent_id: str, request: AgentQueryRequest) -> AgentQueryResponse:
    """Ask a specific agent a question directly (outside workflow context).

    Uses the agent's execute() flow with a $0.50 cost cap.
    """
    registry = _get_registry()
    agent = registry.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    context = ContextPackage(
        task_description=request.query,
        constraints={"budget_remaining": 0.50, "mode": "direct_query"},
    )
    if request.context:
        context.prior_step_outputs.append({
            "type": "user_context",
            "content": request.context,
        })

    start_time = time.time()
    output = await agent.execute(context)
    duration_ms = int((time.time() - start_time) * 1000)

    if not output.is_success:
        raise HTTPException(status_code=502, detail=output.error or "Agent execution failed")

    answer = output.summary or ""
    if not answer and isinstance(output.output, dict):
        answer = output.output.get("summary", str(output.output)[:2000])
    elif not answer and output.output is not None:
        answer = str(output.output)[:2000]

    return AgentQueryResponse(
        agent_id=agent_id,
        answer=answer,
        cost=output.cost,
        duration_ms=duration_ms,
    )


@router.get("/agents/{agent_id}/history", response_model=AgentHistoryResponse)
async def agent_history(
    agent_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AgentHistoryResponse:
    """Get execution history for an agent from step checkpoints and cost records."""
    registry = _get_registry()
    if registry.get(agent_id) is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    from app.models.cost import CostRecord
    from app.models.workflow import StepCheckpoint

    entries: list[AgentHistoryEntry] = []
    total_cost = 0.0

    with Session(db_engine) as session:
        # Query step checkpoints for this agent
        stmt = (
            select(StepCheckpoint)
            .where(StepCheckpoint.agent_id == agent_id)
            .order_by(StepCheckpoint.started_at.desc())  # type: ignore[union-attr]
        )
        checkpoints = session.exec(stmt).all()

        # Build a cost lookup from CostRecord
        cost_stmt = (
            select(CostRecord)
            .where(CostRecord.agent_id == agent_id)
            .order_by(CostRecord.timestamp.desc())  # type: ignore[union-attr]
        )
        cost_records = session.exec(cost_stmt).all()
        # Map by (workflow_id, step_id) for joining
        cost_map: dict[tuple[str | None, str | None], float] = {}
        for cr in cost_records:
            key = (cr.workflow_id, cr.step_id)
            cost_map[key] = cost_map.get(key, 0.0) + cr.cost_usd
            total_cost += cr.cost_usd

        for cp in checkpoints:
            cost = cost_map.get((cp.workflow_id, cp.step_id), 0.0)
            result_data = cp.result or {}
            summary = ""
            if isinstance(result_data, dict):
                summary = result_data.get("summary", "")[:200]

            entries.append(AgentHistoryEntry(
                timestamp=cp.started_at or cp.completed_at or datetime.now(timezone.utc),
                workflow_id=cp.workflow_id,
                step_id=cp.step_id,
                cost=cost,
                duration_ms=0,
                success=cp.status == "completed",
                summary=summary,
            ))

    # Apply pagination
    total_count = len(entries)
    entries = entries[offset:offset + limit]

    return AgentHistoryResponse(
        agent_id=agent_id,
        entries=entries,
        total_count=total_count,
        total_cost=total_cost,
    )
