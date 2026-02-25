"""Data Integrity Audit models.

Includes: AuditFinding (SQL table), AuditRun (SQL table).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from sqlmodel import JSON, Column, SQLModel
from sqlmodel import Field as SQLField

FindingStatus = Literal["open", "acknowledged", "resolved", "false_positive"]


class AuditFinding(SQLModel, table=True):
    """A data integrity finding persisted to the database."""

    __tablename__ = "audit_finding"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    category: str           # IntegrityCategory value
    severity: str           # IntegritySeverity value
    title: str = ""
    description: str = ""
    source_text: str = ""
    suggestion: str = ""
    confidence: float = 0.8
    checker: str = ""
    finding_metadata: dict = SQLField(default_factory=dict, sa_column=Column(JSON))

    # Context
    workflow_id: str | None = None
    paper_doi: str | None = None
    paper_pmid: str | None = None

    # Status tracking
    status: str = "open"  # FindingStatus
    resolved_by: str | None = None
    resolution_note: str | None = None

    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "data_integrity_auditor"
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class AuditRun(SQLModel, table=True):
    """A single integrity audit execution."""

    __tablename__ = "audit_run"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    workflow_id: str | None = None
    trigger: str = "manual"  # "manual" | "w1_step" | "scheduled" | "w7_workflow"
    total_findings: int = 0
    findings_by_severity: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    findings_by_category: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    overall_level: str = "clean"
    summary: str = ""
    cost: float = 0.0
    duration_ms: int = 0
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
