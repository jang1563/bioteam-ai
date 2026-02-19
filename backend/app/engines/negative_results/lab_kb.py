"""Lab KB Engine — CRUD + search for internal negative results.

Operates on the NegativeResult SQL model using SQLModel sessions.
Used by W1 NEGATIVE_CHECK step and the Negative Results module.
Search uses SQL LIKE for simplicity (no LLM needed).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
from uuid import uuid4

from sqlmodel import Session, select

from app.models.negative_result import NegativeResult


class LabKBEngine:
    """CRUD and search engine for internal negative results."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        claim: str,
        outcome: str,
        source: str = "internal",
        organism: str | None = None,
        confidence: float = 0.5,
        failure_category: str = "",
        implications: list[str] | None = None,
        conditions: dict | None = None,
        created_by: str = "human",
    ) -> NegativeResult:
        """Create a new negative result entry."""
        entry = NegativeResult(
            id=str(uuid4()),
            claim=claim,
            outcome=outcome,
            source=source,
            organism=organism,
            confidence=confidence,
            failure_category=failure_category,
            implications=implications or [],
            conditions=conditions or {},
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(entry)
        self.session.commit()
        self.session.refresh(entry)
        return entry

    def get(self, entry_id: str) -> NegativeResult | None:
        """Get a negative result by ID."""
        return self.session.get(NegativeResult, entry_id)

    def list_all(self, limit: int = 100, offset: int = 0) -> Sequence[NegativeResult]:
        """List all negative results with pagination."""
        statement = (
            select(NegativeResult)
            .order_by(NegativeResult.created_at.desc())  # type: ignore[union-attr]
            .offset(offset)
            .limit(limit)
        )
        return self.session.exec(statement).all()

    def update(self, entry_id: str, **kwargs) -> NegativeResult | None:
        """Update fields on a negative result."""
        entry = self.session.get(NegativeResult, entry_id)
        if entry is None:
            return None
        for key, value in kwargs.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        self.session.add(entry)
        self.session.commit()
        self.session.refresh(entry)
        return entry

    def delete(self, entry_id: str) -> bool:
        """Delete a negative result. Returns True if deleted."""
        entry = self.session.get(NegativeResult, entry_id)
        if entry is None:
            return False
        self.session.delete(entry)
        self.session.commit()
        return True

    def search(self, query: str, limit: int = 20) -> Sequence[NegativeResult]:
        """Search negative results by claim or outcome text (SQL LIKE)."""
        pattern = f"%{query}%"
        statement = (
            select(NegativeResult)
            .where(
                (NegativeResult.claim.contains(query))  # type: ignore[union-attr]
                | (NegativeResult.outcome.contains(query))  # type: ignore[union-attr]
            )
            .limit(limit)
        )
        return self.session.exec(statement).all()

    def search_by_organism(self, organism: str, limit: int = 20) -> Sequence[NegativeResult]:
        """Search negative results by organism."""
        statement = (
            select(NegativeResult)
            .where(NegativeResult.organism == organism)
            .limit(limit)
        )
        return self.session.exec(statement).all()

    def search_by_category(self, category: str, limit: int = 20) -> Sequence[NegativeResult]:
        """Search negative results by failure category."""
        statement = (
            select(NegativeResult)
            .where(NegativeResult.failure_category == category)
            .limit(limit)
        )
        return self.session.exec(statement).all()

    def verify(
        self, entry_id: str, verified_by: str, status: str = "confirmed"
    ) -> NegativeResult | None:
        """Mark a negative result as verified by a human."""
        return self.update(
            entry_id,
            verified_by=verified_by,
            verification_status=status,
        )
