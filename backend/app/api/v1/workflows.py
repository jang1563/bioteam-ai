"""Workflow API endpoints — create, inspect, and intervene in workflows.

GET /api/v1/workflows/{id} — full WorkflowInstance
GET /api/v1/workflows/{id}/steps/{step_id} — step checkpoint result
POST /api/v1/workflows — create + start a workflow
POST /api/v1/workflows/{id}/intervene — pause/resume/cancel/inject_note
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from app.agents.registry import AgentRegistry
from app.models.workflow import WorkflowInstance, DirectorNote
from app.workflows.engine import WorkflowEngine, IllegalTransitionError

router = APIRouter(prefix="/api/v1", tags=["workflows"])

# Module-level references, set by main.py at startup
_registry: AgentRegistry | None = None
_engine: WorkflowEngine | None = None
_instances: dict[str, WorkflowInstance] = {}  # In-memory store (Phase 1)


def set_dependencies(registry: AgentRegistry, engine: WorkflowEngine) -> None:
    """Wire up dependencies (called from main.py lifespan)."""
    global _registry, _engine
    _registry = registry
    _engine = engine


def _get_engine() -> WorkflowEngine:
    if _engine is None:
        raise HTTPException(status_code=503, detail="Workflow engine not initialized.")
    return _engine


# === Request / Response Models ===


class CreateWorkflowRequest(BaseModel):
    """Request to create a new workflow."""

    template: str  # "W1", "W2", etc.
    query: str
    budget: float = 5.0
    seed_papers: list[str] = Field(default_factory=list)


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
    state: str
    current_step: str
    step_history: list[dict] = Field(default_factory=list)
    budget_total: float = 5.0
    budget_remaining: float = 5.0
    loop_count: dict[str, int] = Field(default_factory=dict)


class StepCheckpointResponse(BaseModel):
    """Checkpoint data for a workflow step."""

    step_id: str
    status: str
    agent_results: list[dict] = Field(default_factory=list)


class InterveneRequest(BaseModel):
    """Request to intervene in a running workflow."""

    action: Literal["pause", "resume", "cancel", "inject_note"]
    note: str | None = None
    note_action: str | None = None  # DirectorNoteAction


class InterveneResponse(BaseModel):
    """Response after intervention."""

    workflow_id: str
    action: str
    new_state: str
    detail: str = ""


# === Endpoints ===


@router.post("/workflows", response_model=CreateWorkflowResponse)
async def create_workflow(request: CreateWorkflowRequest) -> CreateWorkflowResponse:
    """Create a new workflow instance."""
    engine = _get_engine()

    instance = WorkflowInstance(
        template=request.template,
        budget_total=request.budget,
        budget_remaining=request.budget,
        seed_papers=request.seed_papers,
    )

    # Store in-memory
    _instances[instance.id] = instance

    return CreateWorkflowResponse(
        workflow_id=instance.id,
        template=instance.template,
        state=instance.state,
        query=request.query,
    )


@router.get("/workflows/{workflow_id}", response_model=WorkflowStatusResponse)
async def get_workflow(workflow_id: str) -> WorkflowStatusResponse:
    """Get full workflow status."""
    instance = _instances.get(workflow_id)
    if instance is None:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

    return WorkflowStatusResponse(
        id=instance.id,
        template=instance.template,
        state=instance.state,
        current_step=instance.current_step,
        step_history=instance.step_history,
        budget_total=instance.budget_total,
        budget_remaining=instance.budget_remaining,
        loop_count=instance.loop_count,
    )


@router.get("/workflows/{workflow_id}/steps/{step_id}", response_model=StepCheckpointResponse)
async def get_step(workflow_id: str, step_id: str) -> StepCheckpointResponse:
    """Get checkpoint data for a specific workflow step."""
    instance = _instances.get(workflow_id)
    if instance is None:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

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
    instance = _instances.get(workflow_id)
    if instance is None:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

    try:
        if request.action == "pause":
            engine.pause(instance)
            detail = "Workflow paused"
        elif request.action == "resume":
            engine.resume(instance)
            detail = "Workflow resumed"
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
            notes.append(note.model_dump())
            instance.injected_notes = notes
            detail = f"Note injected: {request.note[:80]}"
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")
    except IllegalTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return InterveneResponse(
        workflow_id=workflow_id,
        action=request.action,
        new_state=instance.state,
        detail=detail,
    )
