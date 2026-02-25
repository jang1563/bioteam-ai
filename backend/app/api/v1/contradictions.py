"""Contradictions API — read-only endpoints for detected contradictions.

Contradictions are created by the Ambiguity Engine agent, not by humans.
This API provides read-only access for the dashboard.

GET  /api/v1/contradictions — list all (newest first, paginated)
GET  /api/v1/contradictions/{id} — get by ID
GET  /api/v1/contradictions/by-workflow/{workflow_id} — filter by workflow
"""

from __future__ import annotations

from datetime import datetime

from app.db.database import engine as db_engine
from app.models.evidence import ContradictionEntry
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

router = APIRouter(prefix="/api/v1", tags=["contradictions"])


# === Response Models ===


class ContradictionResponse(BaseModel):
    """Response for a single contradiction entry."""

    id: str
    claim_a: str
    claim_b: str
    types: list[str] = Field(default_factory=list)
    resolution_hypotheses: list[str] = Field(default_factory=list)
    rcmxt_a: dict = Field(default_factory=dict)
    rcmxt_b: dict = Field(default_factory=dict)
    discriminating_experiment: str | None = None
    detected_at: datetime
    detected_by: str
    workflow_id: str | None = None


def _to_response(entry: ContradictionEntry) -> ContradictionResponse:
    return ContradictionResponse(
        id=entry.id,
        claim_a=entry.claim_a,
        claim_b=entry.claim_b,
        types=entry.types,
        resolution_hypotheses=entry.resolution_hypotheses,
        rcmxt_a=entry.rcmxt_a,
        rcmxt_b=entry.rcmxt_b,
        discriminating_experiment=entry.discriminating_experiment,
        detected_at=entry.detected_at,
        detected_by=entry.detected_by,
        workflow_id=entry.workflow_id,
    )


# === Endpoints ===


@router.get("/contradictions", response_model=list[ContradictionResponse])
async def list_contradictions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ContradictionResponse]:
    """List all contradictions, newest first."""
    with Session(db_engine) as session:
        stmt = (
            select(ContradictionEntry)
            .order_by(ContradictionEntry.detected_at.desc())
            .offset(offset)
            .limit(limit)
        )
        results = session.exec(stmt).all()
        for r in results:
            session.expunge(r)
    return [_to_response(r) for r in results]


@router.get("/contradictions/{entry_id}", response_model=ContradictionResponse)
async def get_contradiction(entry_id: str) -> ContradictionResponse:
    """Get a single contradiction by ID."""
    with Session(db_engine) as session:
        entry = session.get(ContradictionEntry, entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"Contradiction not found: {entry_id}")
        session.expunge(entry)
    return _to_response(entry)


@router.get("/contradictions/by-workflow/{workflow_id}", response_model=list[ContradictionResponse])
async def get_contradictions_by_workflow(workflow_id: str) -> list[ContradictionResponse]:
    """Get all contradictions for a specific workflow."""
    with Session(db_engine) as session:
        stmt = (
            select(ContradictionEntry)
            .where(ContradictionEntry.workflow_id == workflow_id)
            .order_by(ContradictionEntry.detected_at.desc())
        )
        results = session.exec(stmt).all()
        for r in results:
            session.expunge(r)
    return [_to_response(r) for r in results]
