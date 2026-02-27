"""SessionCheckpoint — SQLite-backed checkpoint for long-term workflow recovery.

Unlike StepCheckpoint (in-memory, per-agent), SessionCheckpoint persists full
AgentOutput JSON to SQLite so that 20-step overnight workflows can resume
after server restarts or crashes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import JSON, Column, SQLModel
from sqlmodel import Field as SQLField


class SessionCheckpoint(SQLModel, table=True):
    """Persisted checkpoint for a single workflow step.

    One row per completed step per workflow instance. On resume, the runner
    loads all rows for the workflow and skips already-completed steps.
    """

    __tablename__ = "session_checkpoint"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    workflow_id: str = SQLField(index=True)
    step_id: str
    step_index: int = 0  # Position in the pipeline (0-based)
    agent_id: str = ""   # Primary agent that produced this result
    status: str = "completed"  # "completed" | "skipped" | "injected"
    # Full AgentOutput (or list thereof) as JSON
    agent_output: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    cost_incurred: float = 0.0
    idempotency_token: str = SQLField(default_factory=lambda: str(uuid4()))
    started_at: datetime | None = None
    completed_at: datetime | None = SQLField(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    # Error info (for skipped or injected steps)
    error: str | None = None
    # User-injected adjustment that influenced this step (from DC response)
    user_adjustment: str | None = None
