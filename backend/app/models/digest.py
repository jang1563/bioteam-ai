"""Digest models for research monitoring.

Includes:
- TopicProfile: User-defined search topic configuration
- DigestEntry: A single discovered paper/repo
- DigestReport: LLM-generated summary report
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import SQLModel, Field as SQLField, Column, JSON


class TopicProfile(SQLModel, table=True):
    """User-defined search topic for digest monitoring."""

    __tablename__ = "topic_profile"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str  # "AI in Biology"
    queries: list[str] = SQLField(default_factory=list, sa_column=Column(JSON))
    sources: list[str] = SQLField(
        default_factory=lambda: ["pubmed", "biorxiv", "arxiv", "github", "huggingface", "semantic_scholar"],
        sa_column=Column(JSON),
    )
    categories: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    schedule: str = "daily"  # "daily" | "weekly" | "manual"
    is_active: bool = True
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class DigestEntry(SQLModel, table=True):
    """A single paper/repo discovered by the digest pipeline."""

    __tablename__ = "digest_entry"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    topic_id: str  # FK to TopicProfile.id
    source: str  # "pubmed" | "biorxiv" | "arxiv" | "github" | "huggingface" | "semantic_scholar"
    external_id: str  # DOI, arXiv ID, repo full_name, etc.
    title: str
    authors: list[str] = SQLField(default_factory=list, sa_column=Column(JSON))
    abstract: str = ""
    url: str = ""
    metadata_extra: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    relevance_score: float = 0.0  # 0.0-1.0, computed by pipeline
    fetched_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    published_at: str = ""  # Original publication date string


class DigestReport(SQLModel, table=True):
    """A generated summary report for a topic."""

    __tablename__ = "digest_report"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    topic_id: str  # FK to TopicProfile.id
    period_start: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    period_end: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    entry_count: int = 0
    summary: str = ""  # LLM-generated digest summary
    highlights: list[dict] = SQLField(default_factory=list, sa_column=Column(JSON))
    source_breakdown: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    cost: float = 0.0  # LLM cost for generating this digest
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
