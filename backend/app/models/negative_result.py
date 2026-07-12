"""Negative Result models.

Includes: NegativeResult (SQL table), FailedProtocol (Pydantic).

v4.2 changes:
- NegativeResult: added verified_by + verification_status for human verification tracking
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel
from sqlmodel import JSON, Column, SQLModel
from sqlmodel import Field as SQLField


class NegativeResult(SQLModel, table=True):
    """A negative result from any of the 4 data sources."""

    __tablename__ = "negative_result"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    claim: str                      # What was expected
    outcome: str                    # What actually happened
    conditions: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    source: str  # "internal" | "clinical_trial" | "shadow" | "preprint_delta"
    confidence: float = 0.5
    failure_category: str = ""  # "protocol" | "reagent" | "analysis" | "biological"
    implications: list[str] = SQLField(default_factory=list, sa_column=Column(JSON))
    source_id: str | None = None    # DOI, trial ID, or Lab KB entry ID
    organism: str | None = None
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "human"       # Agent ID or "human"
    # v4.2: human verification tracking
    verified_by: str | None = None  # human ID who verified, or None if unverified
    verification_status: str = "unverified"  # "unverified" | "confirmed" | "rejected" | "ambiguous"


NegativeResultSource = Literal["internal", "clinical_trial", "shadow", "preprint_delta"]
FailureCategory = Literal["protocol", "reagent", "analysis", "biological"]
VerificationStatus = Literal["unverified", "confirmed", "rejected", "ambiguous"]


class FailedProtocol(BaseModel):
    """A failed experimental protocol from internal Lab KB."""

    protocol_name: str
    target: str
    expected_result: str
    actual_result: str
    conditions: dict
    failure_reason: str
    suggested_modifications: list[str]
