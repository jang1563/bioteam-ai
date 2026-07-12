"""Negative Results (Lab KB) API endpoints — CRUD for internal knowledge base.

GET  /api/v1/negative-results — list all (optional ?source= filter)
GET  /api/v1/negative-results/{id} — single result
POST /api/v1/negative-results — create new entry
PUT  /api/v1/negative-results/{id} — update existing entry
DELETE /api/v1/negative-results/{id} — delete entry
"""

from __future__ import annotations

from datetime import datetime

from app.db.database import engine as db_engine
from app.models.negative_result import NegativeResult
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

router = APIRouter(prefix="/api/v1", tags=["negative-results"])


# === Request / Response Models ===


class CreateNegativeResultRequest(BaseModel):
    """Request to create a negative result entry."""

    claim: str = Field(min_length=1, max_length=2000)
    outcome: str = Field(min_length=1, max_length=2000)
    source: str = Field(pattern=r"^(internal|clinical_trial|shadow|preprint_delta)$")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    failure_category: str = Field(
        default="",
        pattern=r"^(protocol|reagent|analysis|biological|)$",
    )
    conditions: dict = Field(default_factory=dict)
    implications: list[str] = Field(default_factory=list)
    organism: str | None = None
    source_id: str | None = None


class UpdateNegativeResultRequest(BaseModel):
    """Request to update a negative result entry. All fields optional."""

    claim: str | None = Field(default=None, max_length=2000)
    outcome: str | None = Field(default=None, max_length=2000)
    source: str | None = Field(
        default=None,
        pattern=r"^(internal|clinical_trial|shadow|preprint_delta)$",
    )
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    failure_category: str | None = Field(
        default=None,
        pattern=r"^(protocol|reagent|analysis|biological|)$",
    )
    conditions: dict | None = None
    implications: list[str] | None = None
    organism: str | None = None
    source_id: str | None = None
    verification_status: str | None = Field(
        default=None,
        pattern=r"^(unverified|confirmed|rejected|ambiguous)$",
    )
    verified_by: str | None = None


class NegativeResultResponse(BaseModel):
    """Response for a negative result entry."""

    id: str
    claim: str
    outcome: str
    source: str
    confidence: float
    failure_category: str
    conditions: dict = Field(default_factory=dict)
    implications: list[str] = Field(default_factory=list)
    organism: str | None = None
    source_id: str | None = None
    created_at: datetime
    created_by: str
    verified_by: str | None = None
    verification_status: str


def _to_response(nr: NegativeResult) -> NegativeResultResponse:
    return NegativeResultResponse(
        id=nr.id,
        claim=nr.claim,
        outcome=nr.outcome,
        source=nr.source,
        confidence=nr.confidence,
        failure_category=nr.failure_category,
        conditions=nr.conditions,
        implications=nr.implications,
        organism=nr.organism,
        source_id=nr.source_id,
        created_at=nr.created_at,
        created_by=nr.created_by,
        verified_by=nr.verified_by,
        verification_status=nr.verification_status,
    )


# === Endpoints ===


@router.get("/negative-results", response_model=list[NegativeResultResponse])
async def list_negative_results(
    source: str | None = Query(default=None, pattern=r"^(internal|clinical_trial|shadow|preprint_delta)$"),
) -> list[NegativeResultResponse]:
    """List all negative results, optionally filtered by source."""
    with Session(db_engine) as session:
        stmt = select(NegativeResult)
        if source:
            stmt = stmt.where(NegativeResult.source == source)
        results = session.exec(stmt).all()
        for r in results:
            session.expunge(r)
    return [_to_response(r) for r in results]


@router.get("/negative-results/{result_id}", response_model=NegativeResultResponse)
async def get_negative_result(result_id: str) -> NegativeResultResponse:
    """Get a single negative result by ID."""
    with Session(db_engine) as session:
        nr = session.get(NegativeResult, result_id)
        if nr is None:
            raise HTTPException(status_code=404, detail=f"Negative result not found: {result_id}")
        session.expunge(nr)
    return _to_response(nr)


@router.post("/negative-results", response_model=NegativeResultResponse, status_code=201)
async def create_negative_result(request: CreateNegativeResultRequest) -> NegativeResultResponse:
    """Create a new negative result entry."""
    nr = NegativeResult(
        claim=request.claim,
        outcome=request.outcome,
        source=request.source,
        confidence=request.confidence,
        failure_category=request.failure_category,
        conditions=request.conditions,
        implications=request.implications,
        organism=request.organism,
        source_id=request.source_id,
        created_by="human",
    )
    with Session(db_engine) as session:
        session.add(nr)
        session.commit()
        session.refresh(nr)
        session.expunge(nr)
    return _to_response(nr)


@router.put("/negative-results/{result_id}", response_model=NegativeResultResponse)
async def update_negative_result(result_id: str, request: UpdateNegativeResultRequest) -> NegativeResultResponse:
    """Update an existing negative result entry."""
    with Session(db_engine) as session:
        nr = session.get(NegativeResult, result_id)
        if nr is None:
            raise HTTPException(status_code=404, detail=f"Negative result not found: {result_id}")

        update_data = request.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(nr, key, value)

        session.add(nr)
        session.commit()
        session.refresh(nr)
        session.expunge(nr)
    return _to_response(nr)


@router.delete("/negative-results/{result_id}", status_code=204)
async def delete_negative_result(result_id: str) -> None:
    """Delete a negative result entry."""
    with Session(db_engine) as session:
        nr = session.get(NegativeResult, result_id)
        if nr is None:
            raise HTTPException(status_code=404, detail=f"Negative result not found: {result_id}")
        session.delete(nr)
        session.commit()
