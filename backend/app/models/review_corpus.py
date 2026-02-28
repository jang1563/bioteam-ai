"""SQLModel + Pydantic models for the Open Peer Review Corpus (Phase 6).

OpenPeerReviewEntry stores one article's review data (decision letter + author response).
ReviewerConcern is a Pydantic model for structured concerns extracted from review text.

Sources: eLife (primary), PLOS, Nature Portfolio, EMBO Press.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field
from sqlmodel import Column, SQLModel, String, Text
from sqlmodel import Field as SField

# ---------------------------------------------------------------------------
# ReviewerConcern — Pydantic (stored as JSON in OpenPeerReviewEntry)
# ---------------------------------------------------------------------------


class ReviewerConcern(BaseModel):
    """A single structured concern raised by a reviewer."""

    concern_id: str = Field(description="e.g. 'R1C3' = Reviewer 1, Concern 3")
    concern_text: str
    category: Literal[
        "methodology", "statistics", "citation", "interpretation",
        "novelty", "presentation", "reproducibility", "other",
    ] = "other"
    severity: Literal["major", "minor", "question"] = "minor"
    author_response_text: str = ""
    resolution: Literal[
        "conceded", "rebutted", "partially_addressed", "unclear"
    ] = "unclear"
    was_valid: bool | None = Field(
        default=None,
        description="Ground truth: True if author conceded and paper was revised",
    )
    raised_by_multiple: bool = False


class ReviewConcernBatch(BaseModel):
    """Batch of concerns extracted from one review."""

    article_id: str
    concerns: list[ReviewerConcern] = Field(default_factory=list)
    total_reviewers: int = 0
    extraction_model: str = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# W8BenchmarkResult — used by the harness
# ---------------------------------------------------------------------------


class W8BenchmarkResult(BaseModel):
    """Result of running W8 on one article and comparing to human reviewers."""

    article_id: str
    source: str
    w8_workflow_id: str | None = None

    # Per-article metrics
    major_concern_recall: float | None = None
    overall_concern_recall: float | None = None
    concern_precision: float | None = None
    decision_accuracy: bool | None = None

    # Raw overlap data
    w8_concerns_raised: list[str] = Field(default_factory=list)
    human_concerns_matched: list[str] = Field(default_factory=list)
    human_concerns_missed: list[str] = Field(default_factory=list)

    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# OpenPeerReviewEntry — SQLModel table
# ---------------------------------------------------------------------------


class OpenPeerReviewEntry(SQLModel, table=True):
    """One article's peer review data from an open review journal.

    Primary key: "{source}:{article_id}" (e.g. "elife:12345").
    """

    __tablename__ = "open_peer_review_entry"

    id: str = SField(primary_key=True, description="{source}:{article_id}")
    source: str = SField(sa_column=Column(String(20), nullable=False))
    doi: str = SField(sa_column=Column(String(200), nullable=False, index=True))
    title: str = SField(default="", sa_column=Column(Text, nullable=False))
    journal: str = SField(default="", sa_column=Column(String(100), nullable=False))
    published_year: int | None = SField(default=None)

    # Raw review text
    decision_letter: str = SField(default="", sa_column=Column(Text, nullable=False))
    author_response: str = SField(default="", sa_column=Column(Text, nullable=False))
    editorial_decision: str = SField(
        default="",
        sa_column=Column(String(30), nullable=False),
        description="accept | major_revision | minor_revision | reject",
    )

    # Extracted structured data (JSON)
    parsed_concerns_json: str = SField(
        default="[]",
        sa_column=Column(Text, nullable=False),
        description="JSON: list[ReviewerConcern]",
    )

    # W8 run linkage
    w8_workflow_id: Optional[str] = SField(default=None, sa_column=Column(String(36)))
    w8_benchmark_json: str = SField(
        default="{}",
        sa_column=Column(Text, nullable=False),
        description="JSON: W8BenchmarkResult",
    )

    collected_at: datetime = SField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SField(default_factory=lambda: datetime.now(timezone.utc))

    # ── Helpers ──────────────────────────────────────────────────────────────

    def get_concerns(self) -> list[ReviewerConcern]:
        raw = json.loads(self.parsed_concerns_json or "[]")
        return [ReviewerConcern(**c) for c in raw]

    def set_concerns(self, concerns: list[ReviewerConcern]) -> None:
        self.parsed_concerns_json = json.dumps([c.model_dump() for c in concerns])

    def get_benchmark(self) -> W8BenchmarkResult | None:
        raw = json.loads(self.w8_benchmark_json or "{}")
        if not raw:
            return None
        return W8BenchmarkResult(**raw)

    def set_benchmark(self, result: W8BenchmarkResult) -> None:
        self.w8_benchmark_json = result.model_dump_json()
