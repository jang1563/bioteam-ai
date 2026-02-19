"""Message and communication models.

Includes: AgentMessage (SQL), ContextPackage (Pydantic), SSEEvent (Pydantic).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlmodel import SQLModel, Field as SQLField, Column, JSON

from app.models.evidence import RCMXTScore
from app.models.negative_result import NegativeResult


class AgentMessage(SQLModel, table=True):
    """Message passed between agents via the workflow engine."""

    __tablename__ = "agent_message"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    from_agent: str
    to_agent: str
    workflow_id: str
    step: str
    payload: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    context_refs: list[str] = SQLField(default_factory=list, sa_column=Column(JSON))
    timestamp: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


# === Pydantic-only models (not persisted) ===


class MemoryItem(BaseModel):
    """A piece of relevant memory retrieved by Knowledge Manager."""

    id: str
    content: str
    source: str             # "literature" | "synthesis" | "lab_kb"
    relevance_score: float = 0.0
    metadata: dict = Field(default_factory=dict)


class ContextPackage(BaseModel):
    """Full context provided to an agent for a workflow step.

    Built by the workflow engine from prior step outputs,
    memory retrieval, and director notes.
    """

    task_description: str
    relevant_memory: list[MemoryItem] = Field(default_factory=list)
    prior_step_outputs: list[dict] = Field(default_factory=list)  # Serialized AgentOutput dicts
    negative_results: list[dict] = Field(default_factory=list)
    rcmxt_context: list[RCMXTScore] | None = None
    constraints: dict = Field(default_factory=dict)  # budget_remaining, deadline, director_notes, etc.


class SSEEvent(BaseModel):
    """Schema for all Server-Sent Events."""

    event_type: Literal[
        "workflow.started",
        "workflow.step_started",
        "workflow.step_completed",
        "workflow.step_failed",
        "workflow.paused",
        "workflow.waiting_human",
        "workflow.over_budget",
        "workflow.completed",
        "workflow.failed",
        "workflow.cancelled",
        "agent.token_stream",
        "system.health_changed",
        "system.cost_alert",
    ]
    workflow_id: str | None = None
    step_id: str | None = None
    agent_id: str | None = None
    payload: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
