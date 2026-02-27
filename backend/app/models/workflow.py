"""Workflow models.

Includes: WorkflowInstance (SQL), StepCheckpoint (SQL),
          WorkflowStep (Pydantic), DirectorNote (Pydantic).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlmodel import JSON, Column, SQLModel
from sqlmodel import Field as SQLField

# === Workflow States ===

WorkflowState = Literal[
    "PENDING", "RUNNING", "PAUSED", "WAITING_HUMAN",
    "COMPLETED", "FAILED", "CANCELLED", "OVER_BUDGET",
]

WorkflowTemplate = Literal["direct_query", "W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8"]


# === SQL Tables ===


class WorkflowInstance(SQLModel, table=True):
    """A running or completed workflow instance."""

    __tablename__ = "workflow_instance"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    template: str  # WorkflowTemplate
    query: str = ""  # Original research query
    state: str = "PENDING"  # WorkflowState
    current_step: str = ""
    step_history: list[dict] = SQLField(default_factory=list, sa_column=Column(JSON))
    loop_count: dict[str, int] = SQLField(default_factory=dict, sa_column=Column(JSON))
    max_loops: int = 3
    budget_total: float = 5.0
    budget_remaining: float = 5.0
    injected_notes: list[dict] = SQLField(default_factory=list, sa_column=Column(JSON))
    # v4.2: seed papers for researcher-directed literature review
    seed_papers: list[str] = SQLField(default_factory=list, sa_column=Column(JSON))  # DOIs provided by Director
    # v5.2: Tier 1 feature data (reproducibility, citation validation, evidence scoring)
    session_manifest: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    citation_report: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    rcmxt_scores: list[dict] = SQLField(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))

    # W8: path to paper PDF for peer review
    pdf_path: str | None = None

    # project_id for future multi-project support
    project_id: str | None = None


class StepCheckpoint(SQLModel, table=True):
    """Checkpoint for resuming parallel steps after crash."""

    __tablename__ = "step_checkpoint"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    workflow_id: str
    step_id: str
    agent_id: str
    status: str = "pending"  # "pending" | "running" | "completed" | "failed"
    result: dict | None = SQLField(default=None, sa_column=Column(JSON))
    idempotency_token: str = SQLField(default_factory=lambda: str(uuid4()))
    started_at: datetime | None = None
    completed_at: datetime | None = None


# === Pydantic-only models ===


DirectorNoteAction = Literal[
    "ADD_PAPER",        # Add a seed paper/DOI
    "EXCLUDE_PAPER",    # Exclude a specific paper
    "MODIFY_QUERY",     # Change search terms
    "EDIT_TEXT",        # Modify synthesis text
    "FREE_TEXT",        # Free-form instruction
]


class DirectorNote(BaseModel):
    """A note injected by the Director into a workflow.

    v4.2: Structured action types replace free-text-only notes.
    """

    text: str
    action: DirectorNoteAction = "FREE_TEXT"
    target_step: str | None = None  # None = next step
    metadata: dict = {}             # Action-specific data (e.g., {"doi": "10.1234/..."})
    injected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkflowStepDef(BaseModel):
    """Definition of a workflow step (template, not instance).

    Note: input_mapper and loop_condition are referenced by name
    and resolved at runtime by the workflow engine.
    """

    id: str
    agent_id: str | list[str]  # Single or parallel
    output_schema: str  # Pydantic model class name
    next_step: str | None = None  # Static next step (or None for conditional)
    is_parallel: bool = False
    is_human_checkpoint: bool = False
    is_loop_point: bool = False
    estimated_cost: float = 0.10
