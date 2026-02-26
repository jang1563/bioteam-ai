"""Message and communication models.

Includes: AgentMessage (SQL), Conversation (SQL), ConversationTurn (SQL),
ContextPackage (Pydantic), SSEEvent (Pydantic).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from app.models.evidence import RCMXTScore
from pydantic import BaseModel, Field
from sqlmodel import JSON, Column, SQLModel
from sqlmodel import Field as SQLField


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


class Conversation(SQLModel, table=True):
    """A conversation thread in Direct Query."""

    __tablename__ = "conversation"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    title: str = ""
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    total_cost: float = 0.0
    turn_count: int = 0


class ConversationTurn(SQLModel, table=True):
    """A single Q&A turn within a conversation."""

    __tablename__ = "conversation_turn"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    conversation_id: str = SQLField(index=True)
    turn_number: int = 0
    query: str = ""
    classification_type: str = ""
    routed_agent: str | None = None
    answer: str | None = None
    sources: list[dict] = SQLField(default_factory=list, sa_column=Column(JSON))
    cost: float = 0.0
    duration_ms: int = 0
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


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
    metadata: dict = Field(default_factory=dict)  # Pass-through data: available_papers, etc.


class SSEEvent(BaseModel):
    """Schema for all Server-Sent Events."""

    event_type: Literal[
        "workflow.started",
        "workflow.resumed",
        "workflow.step_started",
        "workflow.step_completed",
        "workflow.step_failed",
        "workflow.paused",
        "workflow.waiting_human",
        "workflow.over_budget",
        "workflow.completed",
        "workflow.failed",
        "workflow.cancelled",
        "workflow.note_injected",
        "workflow.intervention",
        "agent.token_stream",
        "system.health_changed",
        "system.cost_alert",
    ]
    workflow_id: str | None = None
    step_id: str | None = None
    agent_id: str | None = None
    payload: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
