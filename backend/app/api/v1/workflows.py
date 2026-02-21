"""Workflow API endpoints — create, inspect, and intervene in workflows.

GET /api/v1/workflows — list all workflow instances
GET /api/v1/workflows/{id} — full WorkflowInstance
GET /api/v1/workflows/{id}/steps/{step_id} — step checkpoint result
POST /api/v1/workflows — create + start a workflow
POST /api/v1/workflows/{id}/intervene — pause/resume/cancel/inject_note

v5.1: SQLite persistence for workflow state (survives server restarts).
v5.2: Added list endpoint for dashboard.
v5.3: Auto-execute W1 pipeline on creation via asyncio.create_task.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select

from app.agents.registry import AgentRegistry
from app.db.database import engine as db_engine
from app.models.workflow import WorkflowInstance, DirectorNote
from app.workflows.engine import WorkflowEngine, IllegalTransitionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["workflows"])

# Module-level references, set by main.py at startup
_registry: AgentRegistry | None = None
_engine: WorkflowEngine | None = None
_sse_hub = None  # SSEHub, set by main.py
_lock = asyncio.Lock()  # Protects DB writes from concurrent access


def set_dependencies(
    registry: AgentRegistry,
    engine: WorkflowEngine,
    sse_hub=None,
) -> None:
    """Wire up dependencies (called from main.py lifespan)."""
    global _registry, _engine, _sse_hub
    _registry = registry
    _engine = engine
    _sse_hub = sse_hub


def _get_engine() -> WorkflowEngine:
    if _engine is None:
        raise HTTPException(status_code=503, detail="Workflow engine not initialized.")
    return _engine


def _get_instance(workflow_id: str) -> WorkflowInstance:
    """Load a WorkflowInstance from SQLite by ID."""
    with Session(db_engine) as session:
        instance = session.get(WorkflowInstance, workflow_id)
        if instance is None:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
        session.expunge(instance)
        return instance


def _save_instance(instance: WorkflowInstance) -> None:
    """Persist a WorkflowInstance to SQLite."""
    instance.updated_at = datetime.now(timezone.utc)
    with Session(db_engine) as session:
        session.merge(instance)
        session.commit()


# === Request / Response Models ===


class CreateWorkflowRequest(BaseModel):
    """Request to create a new workflow."""

    template: str = Field(pattern=r"^W[1-6]$")  # "W1" through "W6"
    query: str = Field(min_length=1, max_length=2000)
    budget: float = Field(default=5.0, ge=0.1, le=100.0)
    seed_papers: list[str] = Field(default_factory=list, max_length=50)


class CreateWorkflowResponse(BaseModel):
    """Response after creating a workflow."""

    workflow_id: str
    template: str
    state: str
    query: str


class WorkflowStatusResponse(BaseModel):
    """Full workflow status."""

    id: str
    template: str
    query: str = ""
    state: str
    current_step: str
    step_history: list[dict] = Field(default_factory=list)
    budget_total: float = 5.0
    budget_remaining: float = 5.0
    loop_count: dict[str, int] = Field(default_factory=dict)
    # Tier 1: reproducibility, citation validation, evidence scoring
    session_manifest: dict = Field(default_factory=dict)
    citation_report: dict = Field(default_factory=dict)
    rcmxt_scores: list[dict] = Field(default_factory=list)


class StepCheckpointResponse(BaseModel):
    """Checkpoint data for a workflow step."""

    step_id: str
    status: str
    agent_results: list[dict] = Field(default_factory=list)


class InterveneRequest(BaseModel):
    """Request to intervene in a running workflow."""

    action: Literal["pause", "resume", "cancel", "inject_note"]
    note: str | None = Field(default=None, max_length=2000)
    note_action: str | None = Field(
        default=None,
        pattern=r"^(ADD_PAPER|EXCLUDE_PAPER|MODIFY_QUERY|EDIT_TEXT|FREE_TEXT)$",
    )


class InterveneResponse(BaseModel):
    """Response after intervention."""

    workflow_id: str
    action: str
    new_state: str
    detail: str = ""


# === Endpoints ===


@router.get("/workflows", response_model=list[WorkflowStatusResponse])
async def list_workflows() -> list[WorkflowStatusResponse]:
    """List all workflow instances."""
    with Session(db_engine) as session:
        instances = session.exec(select(WorkflowInstance)).all()
        # Expunge all before session closes
        for inst in instances:
            session.expunge(inst)

    return [
        WorkflowStatusResponse(
            id=inst.id,
            template=inst.template,
            query=inst.query,
            state=inst.state,
            current_step=inst.current_step,
            step_history=inst.step_history,
            budget_total=inst.budget_total,
            budget_remaining=inst.budget_remaining,
            loop_count=inst.loop_count,
            session_manifest=inst.session_manifest,
            citation_report=inst.citation_report,
            rcmxt_scores=inst.rcmxt_scores,
        )
        for inst in instances
    ]


@router.post("/workflows", response_model=CreateWorkflowResponse)
async def create_workflow(request: CreateWorkflowRequest) -> CreateWorkflowResponse:
    """Create a new workflow instance and auto-start execution."""
    engine = _get_engine()

    instance = WorkflowInstance(
        template=request.template,
        query=request.query,
        budget_total=request.budget,
        budget_remaining=request.budget,
        seed_papers=request.seed_papers,
    )

    async with _lock:
        _save_instance(instance)

    # Auto-start W1 pipeline in background
    if request.template == "W1" and _registry is not None:
        logger.info("Starting W1 background task for %s", instance.id)
        task = asyncio.create_task(
            _run_w1_background(instance.id, request.query, request.budget)
        )
        # Log unhandled exceptions from background task
        task.add_done_callback(
            lambda t: logger.error("W1 task exception: %s", t.exception())
            if t.exception() else None
        )
    elif request.template == "W1":
        logger.warning("W1 created but _registry is None — cannot auto-start")

    return CreateWorkflowResponse(
        workflow_id=instance.id,
        template=instance.template,
        state=instance.state,
        query=request.query,
    )


async def _run_w1_background(
    workflow_id: str,
    query: str,
    budget: float,
) -> None:
    """Execute W1 pipeline as a background task with SSE updates."""
    from app.workflows.runners.w1_literature import W1LiteratureReviewRunner

    try:
        instance = _get_instance(workflow_id)

        async def _persist(inst: WorkflowInstance) -> None:
            async with _lock:
                _save_instance(inst)

        runner = W1LiteratureReviewRunner(
            registry=_registry,
            engine=_engine,
            sse_hub=_sse_hub,
            persist_fn=_persist,
        )

        # Broadcast start event
        if _sse_hub:
            await _sse_hub.broadcast_dict(
                event_type="workflow.started",
                workflow_id=workflow_id,
                payload={"template": "W1", "query": query[:200]},
            )

        result = await runner.run(
            query=query,
            instance=instance,
            budget=budget,
        )

        # Persist final state after run
        async with _lock:
            _save_instance(instance)

        # Broadcast completion/pause event
        if _sse_hub:
            if instance.state == "WAITING_HUMAN":
                await _sse_hub.broadcast_dict(
                    event_type="workflow.paused",
                    workflow_id=workflow_id,
                    payload={
                        "state": instance.state,
                        "paused_at": instance.current_step,
                        "steps_completed": len(instance.step_history),
                        "budget_remaining": instance.budget_remaining,
                    },
                )
            elif instance.state == "COMPLETED":
                await _sse_hub.broadcast_dict(
                    event_type="workflow.completed",
                    workflow_id=workflow_id,
                    payload={
                        "steps_completed": len(instance.step_history),
                        "budget_used": instance.budget_total - instance.budget_remaining,
                    },
                )

        # Store step results in step_history for frontend display
        step_results = result.get("step_results", {})
        if step_results:
            history = list(instance.step_history)
            for entry in history:
                step_id = entry.get("step_id")
                if step_id and step_id in step_results:
                    sr = step_results[step_id]
                    if isinstance(sr, dict):
                        entry["result_data"] = _truncate_result(sr)
            instance.step_history = history
            async with _lock:
                _save_instance(instance)

        logger.info(
            "W1 workflow %s reached state %s (%d steps)",
            workflow_id, instance.state, len(instance.step_history),
        )

    except Exception as e:
        logger.error("W1 background task failed for %s: %s", workflow_id, e, exc_info=True)
        try:
            instance = _get_instance(workflow_id)
            if instance.state not in ("FAILED", "CANCELLED", "COMPLETED"):
                # Must be in RUNNING to fail; if still PENDING, start first
                if instance.state == "PENDING":
                    _engine.start(instance)
                _engine.fail(instance, str(e))
                async with _lock:
                    _save_instance(instance)
            if _sse_hub:
                await _sse_hub.broadcast_dict(
                    event_type="workflow.failed",
                    workflow_id=workflow_id,
                    payload={"error": str(e)[:500]},
                )
        except Exception:
            logger.error("Failed to mark workflow %s as FAILED", workflow_id, exc_info=True)


async def _resume_w1_background(workflow_id: str, query: str) -> None:
    """Resume W1 pipeline after human approval (NOVELTY_CHECK + REPORT)."""
    from app.workflows.runners.w1_literature import W1LiteratureReviewRunner

    try:
        instance = _get_instance(workflow_id)

        async def _persist(inst: WorkflowInstance) -> None:
            async with _lock:
                _save_instance(inst)

        runner = W1LiteratureReviewRunner(
            registry=_registry,
            engine=_engine,
            sse_hub=_sse_hub,
            persist_fn=_persist,
        )

        if _sse_hub:
            await _sse_hub.broadcast_dict(
                event_type="workflow.resumed",
                workflow_id=workflow_id,
                payload={"state": instance.state},
            )

        result = await runner.resume_after_human(instance, query)

        async with _lock:
            _save_instance(instance)

        if _sse_hub and instance.state == "COMPLETED":
            await _sse_hub.broadcast_dict(
                event_type="workflow.completed",
                workflow_id=workflow_id,
                payload={
                    "steps_completed": len(instance.step_history),
                    "budget_used": instance.budget_total - instance.budget_remaining,
                },
            )

        logger.info("W1 workflow %s resumed → %s", workflow_id, instance.state)

    except Exception as e:
        logger.error("W1 resume failed for %s: %s", workflow_id, e, exc_info=True)
        try:
            instance = _get_instance(workflow_id)
            if instance.state not in ("FAILED", "CANCELLED", "COMPLETED"):
                _engine.fail(instance, str(e))
                async with _lock:
                    _save_instance(instance)
        except Exception:
            logger.error("Failed to mark workflow %s as FAILED", workflow_id, exc_info=True)


def _truncate_result(data: dict, max_len: int = 2000) -> dict:
    """Truncate large result values for storage in step_history."""
    truncated = {}
    for k, v in data.items():
        if isinstance(v, str) and len(v) > max_len:
            truncated[k] = v[:max_len] + "..."
        elif isinstance(v, dict):
            truncated[k] = _truncate_result(v, max_len)
        elif isinstance(v, list) and len(v) > 20:
            truncated[k] = v[:20]
        else:
            truncated[k] = v
    return truncated


@router.get("/workflows/{workflow_id}", response_model=WorkflowStatusResponse)
async def get_workflow(workflow_id: str) -> WorkflowStatusResponse:
    """Get full workflow status."""
    instance = _get_instance(workflow_id)

    return WorkflowStatusResponse(
        id=instance.id,
        template=instance.template,
        query=instance.query,
        state=instance.state,
        current_step=instance.current_step,
        step_history=instance.step_history,
        budget_total=instance.budget_total,
        budget_remaining=instance.budget_remaining,
        loop_count=instance.loop_count,
        session_manifest=instance.session_manifest,
        citation_report=instance.citation_report,
        rcmxt_scores=instance.rcmxt_scores,
    )


@router.get("/workflows/{workflow_id}/steps/{step_id}", response_model=StepCheckpointResponse)
async def get_step(workflow_id: str, step_id: str) -> StepCheckpointResponse:
    """Get checkpoint data for a specific workflow step."""
    instance = _get_instance(workflow_id)

    # Find step in history
    for entry in instance.step_history:
        if entry.get("step_id") == step_id:
            return StepCheckpointResponse(
                step_id=step_id,
                status="completed",
                agent_results=[entry],
            )

    # Step not yet completed
    if instance.current_step == step_id:
        return StepCheckpointResponse(step_id=step_id, status="running")

    return StepCheckpointResponse(step_id=step_id, status="pending")


@router.post("/workflows/{workflow_id}/intervene", response_model=InterveneResponse)
async def intervene(workflow_id: str, request: InterveneRequest) -> InterveneResponse:
    """Pause, resume, cancel, or inject a note into a workflow."""
    engine = _get_engine()

    async with _lock:
        instance = _get_instance(workflow_id)

        try:
            if request.action == "pause":
                engine.pause(instance)
                detail = "Workflow paused"
            elif request.action == "resume":
                engine.resume(instance)
                detail = "Workflow resumed"
                # If resuming from WAITING_HUMAN, continue W1 pipeline
                if instance.template == "W1" and _registry is not None:
                    _save_instance(instance)
                    asyncio.create_task(
                        _resume_w1_background(workflow_id, instance.query)
                    )
            elif request.action == "cancel":
                engine.cancel(instance)
                detail = "Workflow cancelled"
            elif request.action == "inject_note":
                if not request.note:
                    raise HTTPException(status_code=400, detail="Note text required for inject_note")
                note = DirectorNote(
                    text=request.note,
                    action=request.note_action or "FREE_TEXT",
                )
                notes = list(instance.injected_notes)
                notes.append(note.model_dump(mode="json"))
                instance.injected_notes = notes
                detail = f"Note injected: {request.note[:80]}"
            else:
                raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")

            _save_instance(instance)

        except IllegalTransitionError as e:
            raise HTTPException(status_code=409, detail=str(e))

    return InterveneResponse(
        workflow_id=workflow_id,
        action=request.action,
        new_state=instance.state,
        detail=detail,
    )
