"""Task and Project models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from sqlmodel import SQLModel, Field as SQLField


class Project(SQLModel, table=True):
    """A research project grouping workflows and tasks."""

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str
    description: str = ""
    status: str = "active"  # "active" | "archived"
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class Task(SQLModel, table=True):
    """A task within a project, tracked by Project Manager."""

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    project_id: str | None = None
    title: str
    description: str = ""
    status: str = "todo"  # "todo" | "in_progress" | "done" | "blocked"
    assigned_to: str | None = None  # Agent ID
    priority: int = 0  # 0=normal, 1=high, 2=urgent
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
