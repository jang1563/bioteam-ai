"""Manuscript Studio session models.

Persistent session state that aggregates outputs from W11, W8, W7, and
RCMXT-bearing workflows into one manuscript-defense surface.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlmodel import JSON, Column, SQLModel
from sqlmodel import Field as SQLField


class ManuscriptFallbackFlag(BaseModel):
    """Visible fallback or partial-failure note for a manuscript stage."""

    stage: str
    detail: str
    source_workflow_id: str | None = None
    provenance: str = ""


class ManuscriptClaimEvidence(BaseModel):
    """Claim-level evidence item derived from RCMXT and linked workflows."""

    claim_text: str
    composite_score: float | None = None
    axis_scores: dict[str, float | None] = Field(default_factory=dict)
    supporting_sources: list[str] = Field(default_factory=list)
    rcmxt_summary: str = ""
    risk_level: Literal["low", "medium", "high"] = "medium"
    integrity_notes: list[str] = Field(default_factory=list)
    reviewer_notes: list[str] = Field(default_factory=list)
    generated_by: str = ""


class ManuscriptReviewerRisk(BaseModel):
    """Reviewer-facing risk surfaced from W8 outputs."""

    title: str
    severity: Literal["low", "medium", "high"] = "medium"
    section: str = "General"
    detail: str = ""
    evidence_basis: str = ""
    generated_by: str = ""


class ManuscriptIntegrityFlag(BaseModel):
    """Submission blocker or integrity warning."""

    title: str
    severity: str = "warning"
    category: str = "unknown"
    detail: str = ""
    suggestion: str = ""
    status: str = "open"
    generated_by: str = ""


class ManuscriptReportRunMetadata(BaseModel):
    """Shared run metadata for reviewer-facing manuscript-defense reports."""

    workflow_id: str | None = None
    workflow_template: str = ""
    workflow_state: str = ""
    generated_at: datetime | None = None
    report_version: str = "v1"
    source_count: int = 0


class ReviewerRiskReport(BaseModel):
    """Versioned reviewer-risk report contract for W8-backed outputs."""

    report_type: Literal["ReviewerRiskReport"] = "ReviewerRiskReport"
    version: Literal["v1"] = "v1"
    maturity: Literal["validated_core"] = "validated_core"
    summary: str = ""
    findings: list[ManuscriptReviewerRisk] = Field(default_factory=list)
    evidence_provenance: list[str] = Field(default_factory=list)
    confidence_or_coverage: str = ""
    run_metadata: ManuscriptReportRunMetadata = Field(
        default_factory=lambda: ManuscriptReportRunMetadata(workflow_template="W8")
    )


class IntegrityAuditReport(BaseModel):
    """Versioned submission-check report contract for W7-backed outputs."""

    report_type: Literal["IntegrityAuditReport"] = "IntegrityAuditReport"
    version: Literal["v1"] = "v1"
    maturity: Literal["validated_core", "guided_support"] = "guided_support"
    summary: str = ""
    findings: list[ManuscriptIntegrityFlag] = Field(default_factory=list)
    evidence_provenance: list[str] = Field(default_factory=list)
    confidence_or_coverage: str = ""
    run_metadata: ManuscriptReportRunMetadata = Field(
        default_factory=lambda: ManuscriptReportRunMetadata(workflow_template="W7")
    )


class ManuscriptOutlineSection(BaseModel):
    """Derived outline section for the current manuscript story."""

    title: str
    bullets: list[str] = Field(default_factory=list)
    generated_by: str = ""


class ManuscriptSession(SQLModel, table=True):
    """Persistent Manuscript Studio session."""

    __tablename__ = "manuscript_session"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    title: str = ""
    query: str = ""
    notes: str = ""
    draft_text: str = ""
    target_journal: str | None = None
    key_papers: list[str] = SQLField(default_factory=list, sa_column=Column(JSON))

    phase: str = "collect_inputs"
    selected_frame_id: str | None = None
    completion_state: str = "empty"

    linked_workflows: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    fallback_flags: list[dict] = SQLField(default_factory=list, sa_column=Column(JSON))
    frame_options: list[dict] = SQLField(default_factory=list, sa_column=Column(JSON))
    selected_frame: dict | None = SQLField(default=None, sa_column=Column(JSON))
    claim_map: list[dict] = SQLField(default_factory=list, sa_column=Column(JSON))
    reviewer_risks: list[dict] = SQLField(default_factory=list, sa_column=Column(JSON))
    integrity_flags: list[dict] = SQLField(default_factory=list, sa_column=Column(JSON))
    outline: list[dict] = SQLField(default_factory=list, sa_column=Column(JSON))

    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
