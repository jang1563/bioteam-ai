"""Research Digest API — topics CRUD, entries, reports, manual trigger.

POST   /api/v1/digest/topics              — create topic
GET    /api/v1/digest/topics              — list all topics
GET    /api/v1/digest/topics/{id}         — get topic
PUT    /api/v1/digest/topics/{id}         — update topic
DELETE /api/v1/digest/topics/{id}         — delete topic

GET    /api/v1/digest/entries              — list entries (filter by ?topic_id=&source=&days=)
GET    /api/v1/digest/entries/{id}         — get single entry

GET    /api/v1/digest/reports              — list reports (filter by ?topic_id=)
GET    /api/v1/digest/reports/{id}         — get single report

POST   /api/v1/digest/topics/{id}/run     — trigger immediate fetch
GET    /api/v1/digest/stats               — aggregate stats
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from app.db.database import engine as db_engine
from app.digest.scheduler import SCHEDULE_LOOKBACK_DAYS
from app.email.sender import is_email_configured, send_digest_email
from app.models.digest import DigestEntry, DigestReport, TopicProfile
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/digest", tags=["digest"])

# Module-level references (set during app startup via lifespan)
_pipeline = None
_scheduler = None
_running_topics: set[str] = set()


def set_pipeline(pipeline) -> None:
    """Wire up the digest pipeline (called from main.py lifespan)."""
    global _pipeline
    _pipeline = pipeline


def set_scheduler(scheduler) -> None:
    """Wire up the digest scheduler (called from main.py lifespan)."""
    global _scheduler
    _scheduler = scheduler


# === Request / Response Models ===


DigestSourceType = Literal["pubmed", "biorxiv", "arxiv", "github", "huggingface", "semantic_scholar"]


class CreateTopicRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    queries: list[str] = Field(min_length=1)
    sources: list[DigestSourceType] = Field(
        default_factory=lambda: ["pubmed", "biorxiv", "arxiv", "github", "huggingface", "semantic_scholar"],
    )
    categories: dict = Field(default_factory=dict)
    schedule: str = Field(default="daily", pattern=r"^(daily|weekly|manual)$")


class UpdateTopicRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    queries: list[str] | None = None
    sources: list[DigestSourceType] | None = None
    categories: dict | None = None
    schedule: str | None = Field(default=None, pattern=r"^(daily|weekly|manual)$")
    is_active: bool | None = None


class TopicResponse(BaseModel):
    id: str
    name: str
    queries: list[str]
    sources: list[str]
    categories: dict
    schedule: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class EntryResponse(BaseModel):
    id: str
    topic_id: str
    source: str
    external_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    url: str = ""
    metadata_extra: dict = Field(default_factory=dict)
    relevance_score: float = 0.0
    fetched_at: datetime
    published_at: str = ""


class ReportResponse(BaseModel):
    id: str
    topic_id: str
    period_start: datetime
    period_end: datetime
    entry_count: int
    summary: str
    highlights: list[dict] = Field(default_factory=list)
    source_breakdown: dict = Field(default_factory=dict)
    cost: float
    created_at: datetime


class StatsResponse(BaseModel):
    total_topics: int
    total_entries: int
    total_reports: int
    entries_by_source: dict = Field(default_factory=dict)


# === Topic CRUD ===


@router.post("/topics", response_model=TopicResponse, status_code=201)
async def create_topic(request: CreateTopicRequest) -> TopicResponse:
    """Create a new topic profile."""
    topic = TopicProfile(
        name=request.name,
        queries=request.queries,
        sources=request.sources,
        categories=request.categories,
        schedule=request.schedule,
    )
    with Session(db_engine) as session:
        session.add(topic)
        session.commit()
        session.refresh(topic)
        session.expunge(topic)
    return _topic_response(topic)


@router.get("/topics", response_model=list[TopicResponse])
async def list_topics() -> list[TopicResponse]:
    """List all topic profiles."""
    with Session(db_engine) as session:
        topics = session.exec(select(TopicProfile)).all()
        for t in topics:
            session.expunge(t)
    return [_topic_response(t) for t in topics]


@router.get("/topics/{topic_id}", response_model=TopicResponse)
async def get_topic(topic_id: str) -> TopicResponse:
    """Get a single topic profile."""
    with Session(db_engine) as session:
        topic = session.get(TopicProfile, topic_id)
        if topic is None:
            raise HTTPException(status_code=404, detail=f"Topic not found: {topic_id}")
        session.expunge(topic)
    return _topic_response(topic)


@router.put("/topics/{topic_id}", response_model=TopicResponse)
async def update_topic(topic_id: str, request: UpdateTopicRequest) -> TopicResponse:
    """Update an existing topic profile."""
    with Session(db_engine) as session:
        topic = session.get(TopicProfile, topic_id)
        if topic is None:
            raise HTTPException(status_code=404, detail=f"Topic not found: {topic_id}")

        update_data = request.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(topic, key, value)
        topic.updated_at = datetime.now(timezone.utc)

        session.add(topic)
        session.commit()
        session.refresh(topic)
        session.expunge(topic)
    return _topic_response(topic)


@router.delete("/topics/{topic_id}", status_code=204)
async def delete_topic(topic_id: str) -> None:
    """Delete a topic profile."""
    with Session(db_engine) as session:
        topic = session.get(TopicProfile, topic_id)
        if topic is None:
            raise HTTPException(status_code=404, detail=f"Topic not found: {topic_id}")
        session.delete(topic)
        session.commit()


# === Digest Entries ===


@router.get("/entries", response_model=list[EntryResponse])
async def list_entries(
    topic_id: str | None = Query(default=None),
    source: str | None = Query(default=None),
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="relevance", pattern=r"^(relevance|date)$"),
) -> list[EntryResponse]:
    """List digest entries with optional filters."""
    with Session(db_engine) as session:
        stmt = select(DigestEntry)
        if topic_id:
            stmt = stmt.where(DigestEntry.topic_id == topic_id)
        if source:
            stmt = stmt.where(DigestEntry.source == source)

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = stmt.where(DigestEntry.fetched_at >= cutoff)

        if sort_by == "date":
            stmt = stmt.order_by(DigestEntry.fetched_at.desc())
        else:
            stmt = stmt.order_by(DigestEntry.relevance_score.desc())

        stmt = stmt.offset(offset).limit(limit)

        entries = session.exec(stmt).all()
        for e in entries:
            session.expunge(e)
    return [_entry_response(e) for e in entries]


@router.get("/entries/{entry_id}", response_model=EntryResponse)
async def get_entry(entry_id: str) -> EntryResponse:
    """Get a single digest entry."""
    with Session(db_engine) as session:
        entry = session.get(DigestEntry, entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"Entry not found: {entry_id}")
        session.expunge(entry)
    return _entry_response(entry)


# === Digest Reports ===


@router.get("/reports", response_model=list[ReportResponse])
async def list_reports(
    topic_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ReportResponse]:
    """List digest reports, newest first."""
    with Session(db_engine) as session:
        stmt = select(DigestReport)
        if topic_id:
            stmt = stmt.where(DigestReport.topic_id == topic_id)
        stmt = stmt.order_by(DigestReport.created_at.desc()).limit(limit)

        reports = session.exec(stmt).all()
        for r in reports:
            session.expunge(r)
    return [_report_response(r) for r in reports]


@router.get("/reports/{report_id}", response_model=ReportResponse)
async def get_report(report_id: str) -> ReportResponse:
    """Get a single digest report."""
    with Session(db_engine) as session:
        report = session.get(DigestReport, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")
        session.expunge(report)
    return _report_response(report)


# === Manual Trigger ===


@router.post("/topics/{topic_id}/run", response_model=ReportResponse)
async def run_digest(topic_id: str) -> ReportResponse:
    """Trigger an immediate digest fetch for a topic."""
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Digest pipeline not initialized")

    with Session(db_engine) as session:
        topic = session.get(TopicProfile, topic_id)
        if topic is None:
            raise HTTPException(status_code=404, detail=f"Topic not found: {topic_id}")
        session.expunge(topic)

    if topic_id in _running_topics:
        raise HTTPException(
            status_code=409,
            detail=f"Digest is already running for topic '{topic.name}'",
        )

    _running_topics.add(topic_id)
    try:
        days = SCHEDULE_LOOKBACK_DAYS.get(topic.schedule, 7)
        report = await _pipeline.run(topic, days=days)

        # Fire-and-forget email delivery
        if is_email_configured():
            try:
                import asyncio
                with Session(db_engine) as session:
                    entries = session.exec(
                        select(DigestEntry)
                        .where(DigestEntry.topic_id == topic_id)
                        .order_by(DigestEntry.relevance_score.desc())
                        .limit(10)
                    ).all()
                asyncio.create_task(send_digest_email(report, topic, list(entries)))
            except Exception as e:
                logger.error("Failed to send digest email for topic %s: %s", topic_id, e)

        return _report_response(report)
    finally:
        _running_topics.discard(topic_id)


# === Scheduler Status ===


@router.get("/scheduler/status")
async def get_scheduler_status() -> dict:
    """Return global scheduler state and per-topic schedule visibility.

    Response schema:
        {
            "enabled": bool,
            "running": bool,
            "check_interval_minutes": float,
            "topics": [
                {
                    "topic_id": str, "name": str, "schedule": str,
                    "is_active": bool,
                    "last_run_at": str | null,   # ISO-8601 UTC
                    "next_run_at": str | null,   # ISO-8601 UTC
                    "minutes_until_next": int | null,
                    "overdue": bool,
                },
                ...
            ]
        }
    """
    if _scheduler is None:
        return {
            "enabled": False,
            "running": False,
            "check_interval_minutes": 0,
            "topics": [],
        }

    base = _scheduler.get_status()
    topics = _scheduler.get_topic_schedules()
    return {**base, "topics": topics}


# === Stats ===


@router.get("/stats", response_model=StatsResponse)
async def get_stats() -> StatsResponse:
    """Get aggregate digest statistics using SQL aggregates."""
    with Session(db_engine) as session:
        total_topics = session.exec(
            select(func.count()).select_from(TopicProfile)
        ).one()
        total_entries = session.exec(
            select(func.count()).select_from(DigestEntry)
        ).one()
        total_reports = session.exec(
            select(func.count()).select_from(DigestReport)
        ).one()

        rows = session.exec(
            select(DigestEntry.source, func.count(DigestEntry.id))
            .group_by(DigestEntry.source)
        ).all()
        entries_by_source = {row[0]: row[1] for row in rows}

    return StatsResponse(
        total_topics=total_topics,
        total_entries=total_entries,
        total_reports=total_reports,
        entries_by_source=entries_by_source,
    )


# === Helpers ===


def _topic_response(t: TopicProfile) -> TopicResponse:
    return TopicResponse(
        id=t.id, name=t.name, queries=t.queries, sources=t.sources,
        categories=t.categories, schedule=t.schedule, is_active=t.is_active,
        created_at=t.created_at, updated_at=t.updated_at,
    )


def _entry_response(e: DigestEntry) -> EntryResponse:
    return EntryResponse(
        id=e.id, topic_id=e.topic_id, source=e.source, external_id=e.external_id,
        title=e.title, authors=e.authors, abstract=e.abstract, url=e.url,
        metadata_extra=e.metadata_extra, relevance_score=e.relevance_score,
        fetched_at=e.fetched_at, published_at=e.published_at,
    )


def _report_response(r: DigestReport) -> ReportResponse:
    return ReportResponse(
        id=r.id, topic_id=r.topic_id, period_start=r.period_start,
        period_end=r.period_end, entry_count=r.entry_count, summary=r.summary,
        highlights=r.highlights, source_breakdown=r.source_breakdown,
        cost=r.cost, created_at=r.created_at,
    )
