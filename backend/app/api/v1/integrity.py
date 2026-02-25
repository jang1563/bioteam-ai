"""Data Integrity Audit API — CRUD for findings + audit trigger + runs.

GET    /api/v1/integrity/findings           — list findings (filter: severity, category, status)
GET    /api/v1/integrity/findings/{id}      — single finding
PUT    /api/v1/integrity/findings/{id}      — update status (acknowledge, resolve, false positive)
DELETE /api/v1/integrity/findings/{id}      — delete finding
POST   /api/v1/integrity/audit              — trigger ad-hoc audit
GET    /api/v1/integrity/runs               — list audit runs
GET    /api/v1/integrity/runs/{id}          — audit run detail
GET    /api/v1/integrity/stats              — aggregate stats
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.db.database import engine as db_engine
from app.models.integrity import AuditFinding, AuditRun
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrity", tags=["integrity"])

# Module-level dependency — set during app startup
_auditor_agent = None


def set_auditor_agent(agent) -> None:
    """Wire the DataIntegrityAuditorAgent during app startup."""
    global _auditor_agent
    _auditor_agent = agent


# === Request / Response Models ===


class FindingResponse(BaseModel):
    """Response for a single audit finding."""

    id: str
    category: str
    severity: str
    title: str
    description: str
    source_text: str = ""
    suggestion: str = ""
    confidence: float
    checker: str = ""
    finding_metadata: dict = Field(default_factory=dict)
    workflow_id: str | None = None
    paper_doi: str | None = None
    paper_pmid: str | None = None
    status: str
    resolved_by: str | None = None
    resolution_note: str | None = None
    created_at: datetime
    updated_at: datetime


class UpdateFindingRequest(BaseModel):
    """Request to update a finding's status."""

    status: str | None = Field(
        default=None,
        pattern=r"^(open|acknowledged|resolved|false_positive)$",
    )
    resolved_by: str | None = None
    resolution_note: str | None = Field(default=None, max_length=2000)


class TriggerAuditRequest(BaseModel):
    """Request to trigger an ad-hoc integrity audit."""

    text: str = Field(min_length=1, max_length=50000)
    dois: list[str] = Field(default_factory=list)
    use_llm: bool = False  # False = quick_check (deterministic), True = full audit


class AuditRunResponse(BaseModel):
    """Response for an audit run."""

    id: str
    workflow_id: str | None = None
    trigger: str
    total_findings: int
    findings_by_severity: dict = Field(default_factory=dict)
    findings_by_category: dict = Field(default_factory=dict)
    overall_level: str
    summary: str = ""
    cost: float = 0.0
    duration_ms: int = 0
    created_at: datetime


class IntegrityStats(BaseModel):
    """Aggregate statistics for integrity findings."""

    total_findings: int = 0
    findings_by_severity: dict = Field(default_factory=dict)
    findings_by_category: dict = Field(default_factory=dict)
    findings_by_status: dict = Field(default_factory=dict)
    total_runs: int = 0
    average_findings_per_run: float = 0.0


# === Helpers ===


def _to_finding_response(f: AuditFinding) -> FindingResponse:
    return FindingResponse(
        id=f.id,
        category=f.category,
        severity=f.severity,
        title=f.title,
        description=f.description,
        source_text=f.source_text,
        suggestion=f.suggestion,
        confidence=f.confidence,
        checker=f.checker,
        finding_metadata=f.finding_metadata,
        workflow_id=f.workflow_id,
        paper_doi=f.paper_doi,
        paper_pmid=f.paper_pmid,
        status=f.status,
        resolved_by=f.resolved_by,
        resolution_note=f.resolution_note,
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


def _to_run_response(r: AuditRun) -> AuditRunResponse:
    return AuditRunResponse(
        id=r.id,
        workflow_id=r.workflow_id,
        trigger=r.trigger,
        total_findings=r.total_findings,
        findings_by_severity=r.findings_by_severity,
        findings_by_category=r.findings_by_category,
        overall_level=r.overall_level,
        summary=r.summary,
        cost=r.cost,
        duration_ms=r.duration_ms,
        created_at=r.created_at,
    )


# === Findings Endpoints ===


@router.get("/findings", response_model=list[FindingResponse])
async def list_findings(
    severity: str | None = Query(
        default=None,
        pattern=r"^(info|warning|error|critical)$",
    ),
    category: str | None = Query(default=None, max_length=50),
    status: str | None = Query(
        default=None,
        pattern=r"^(open|acknowledged|resolved|false_positive)$",
    ),
    workflow_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[FindingResponse]:
    """List audit findings with optional filters."""
    with Session(db_engine) as session:
        stmt = select(AuditFinding).order_by(AuditFinding.created_at.desc())
        if severity:
            stmt = stmt.where(AuditFinding.severity == severity)
        if category:
            stmt = stmt.where(AuditFinding.category == category)
        if status:
            stmt = stmt.where(AuditFinding.status == status)
        if workflow_id:
            stmt = stmt.where(AuditFinding.workflow_id == workflow_id)
        stmt = stmt.offset(offset).limit(limit)
        results = session.exec(stmt).all()
        for r in results:
            session.expunge(r)
    return [_to_finding_response(r) for r in results]


@router.get("/findings/{finding_id}", response_model=FindingResponse)
async def get_finding(finding_id: str) -> FindingResponse:
    """Get a single audit finding by ID."""
    with Session(db_engine) as session:
        finding = session.get(AuditFinding, finding_id)
        if finding is None:
            raise HTTPException(status_code=404, detail=f"Finding not found: {finding_id}")
        session.expunge(finding)
    return _to_finding_response(finding)


@router.put("/findings/{finding_id}", response_model=FindingResponse)
async def update_finding(finding_id: str, request: UpdateFindingRequest) -> FindingResponse:
    """Update an audit finding's status (acknowledge, resolve, mark false positive)."""
    with Session(db_engine) as session:
        finding = session.get(AuditFinding, finding_id)
        if finding is None:
            raise HTTPException(status_code=404, detail=f"Finding not found: {finding_id}")

        update_data = request.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(finding, key, value)
        finding.updated_at = datetime.now(timezone.utc)

        session.add(finding)
        session.commit()
        session.refresh(finding)
        session.expunge(finding)
    return _to_finding_response(finding)


@router.delete("/findings/{finding_id}", status_code=204)
async def delete_finding(finding_id: str) -> None:
    """Delete an audit finding."""
    with Session(db_engine) as session:
        finding = session.get(AuditFinding, finding_id)
        if finding is None:
            raise HTTPException(status_code=404, detail=f"Finding not found: {finding_id}")
        session.delete(finding)
        session.commit()


# === Audit Trigger ===


@router.post("/audit", response_model=AuditRunResponse, status_code=201)
async def trigger_audit(request: TriggerAuditRequest) -> AuditRunResponse:
    """Trigger an ad-hoc integrity audit on provided text."""
    if _auditor_agent is None:
        raise HTTPException(status_code=503, detail="DataIntegrityAuditorAgent not available")

    start_time = time.time()

    try:
        if request.use_llm:
            from app.models.messages import ContextPackage

            context = ContextPackage(
                task_description=request.text,
                prior_step_outputs=[],
            )
            output = await _auditor_agent.audit(context)
        else:
            output = await _auditor_agent.quick_check(request.text, dois=request.dois or None)
    except Exception as e:
        logger.error("Ad-hoc audit failed: %s", e)
        raise HTTPException(status_code=500, detail="Audit failed due to an internal error")

    duration_ms = int((time.time() - start_time) * 1000)
    result = output.output or {}

    # Persist findings to database
    findings_list = result.get("findings", [])
    finding_ids = []
    with Session(db_engine) as session:
        for f in findings_list:
            db_finding = AuditFinding(
                category=f.get("category", "unknown"),
                severity=f.get("severity", "info"),
                title=f.get("title", ""),
                description=f.get("description", ""),
                source_text=f.get("source_text", ""),
                suggestion=f.get("suggestion", ""),
                confidence=f.get("confidence", 0.8),
                checker=f.get("checker", ""),
                finding_metadata=f.get("metadata", {}),
            )
            session.add(db_finding)
            finding_ids.append(db_finding.id)

        # Create audit run record
        run = AuditRun(
            trigger="manual",
            total_findings=result.get("total_findings", len(findings_list)),
            findings_by_severity=result.get("findings_by_severity", {}),
            findings_by_category=result.get("findings_by_category", {}),
            overall_level=result.get("overall_level", "clean"),
            summary=output.summary or "",
            cost=output.cost,
            duration_ms=duration_ms,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        session.expunge(run)

    return _to_run_response(run)


# === Audit Runs ===


@router.get("/runs", response_model=list[AuditRunResponse])
async def list_runs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[AuditRunResponse]:
    """List audit runs, newest first."""
    with Session(db_engine) as session:
        stmt = (
            select(AuditRun)
            .order_by(AuditRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        results = session.exec(stmt).all()
        for r in results:
            session.expunge(r)
    return [_to_run_response(r) for r in results]


@router.get("/runs/{run_id}", response_model=AuditRunResponse)
async def get_run(run_id: str) -> AuditRunResponse:
    """Get a single audit run by ID."""
    with Session(db_engine) as session:
        run = session.get(AuditRun, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Audit run not found: {run_id}")
        session.expunge(run)
    return _to_run_response(run)


# === Stats ===


@router.get("/stats", response_model=IntegrityStats)
async def get_stats() -> IntegrityStats:
    """Get aggregate integrity statistics."""
    with Session(db_engine) as session:
        # Total findings
        total_findings = session.exec(
            select(func.count(AuditFinding.id))
        ).one()

        # By severity
        severity_rows = session.exec(
            select(AuditFinding.severity, func.count(AuditFinding.id))
            .group_by(AuditFinding.severity)
        ).all()
        by_severity = {row[0]: row[1] for row in severity_rows}

        # By category
        category_rows = session.exec(
            select(AuditFinding.category, func.count(AuditFinding.id))
            .group_by(AuditFinding.category)
        ).all()
        by_category = {row[0]: row[1] for row in category_rows}

        # By status
        status_rows = session.exec(
            select(AuditFinding.status, func.count(AuditFinding.id))
            .group_by(AuditFinding.status)
        ).all()
        by_status = {row[0]: row[1] for row in status_rows}

        # Total runs
        total_runs = session.exec(
            select(func.count(AuditRun.id))
        ).one()

        avg_findings = total_findings / total_runs if total_runs > 0 else 0.0

    return IntegrityStats(
        total_findings=total_findings,
        findings_by_severity=by_severity,
        findings_by_category=by_category,
        findings_by_status=by_status,
        total_runs=total_runs,
        average_findings_per_run=avg_findings,
    )
