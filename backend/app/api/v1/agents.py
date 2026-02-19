"""Agent API endpoints — list and inspect agents.

GET /api/v1/agents — list all registered agents
GET /api/v1/agents/{agent_id} — full spec + runtime status
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from app.agents.registry import AgentRegistry

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
