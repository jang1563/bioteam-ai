"""Memory models — semantic and episodic memory.

ChromaDB stores vector-searchable content in 3 collections:
- literature: Published papers, preprints (source of truth)
- synthesis: Agent-generated interpretations (clearly labeled)
- lab_kb: Manually entered lab knowledge (human-verified)

SQLite stores structured episodic events for history/audit.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlmodel import JSON, Column, SQLModel
from sqlmodel import Field as SQLField


class SemanticEntry(BaseModel):
    """An entry in ChromaDB vector store.

    Not a SQL table — stored in ChromaDB with embeddings.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    collection: str  # "literature" | "synthesis" | "lab_kb"
    text: str
    metadata: dict = Field(default_factory=dict)
    # metadata includes: doi, pmid, source_type, organism, date, agent_id, etc.


class EpisodicEvent(SQLModel, table=True):
    """An episodic memory event stored in SQLite.

    Tracks what happened, when, and by whom — for audit trail and
    Knowledge Manager's contextual memory.
    """

    __tablename__ = "episodic_event"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    event_type: str  # "query", "workflow_started", "paper_found", "contradiction_detected", etc.
    agent_id: str | None = None
    workflow_id: str | None = None
    summary: str = ""
    details: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    timestamp: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
