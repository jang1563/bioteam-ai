"""Workflow Resume & Step-Control API.

Endpoints:
  POST /api/v1/workflows/{id}/resume
      Resume an OVER_BUDGET or PAUSED workflow with optional budget top-up.

  POST /api/v1/workflows/{id}/direction_response
      User response to a DC (Direction Check) event — continue / focus / adjust.

  POST /api/v1/workflows/{id}/steps/{step_id}/rerun
      Re-execute a single step (clears its checkpoint and re-queues).

  POST /api/v1/workflows/{id}/steps/{step_id}/skip
      Skip a step (saves an empty result and advances).

  POST /api/v1/workflows/{id}/steps/{step_id}/inject
      Inject a manual result for a step without re-executing it.

These endpoints require step_rerun_enabled=True in settings.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.db.database import engine as db_engine
from app.models.session_checkpoint import SessionCheckpoint
from app.models.workflow import WorkflowInstance
from app.workflows.engine import WorkflowEngine
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["resume"])

# Module-level refs set by main.py
_registry = None
_engine: WorkflowEngine | None = None
_sse_hub = None


def set_dependencies(registry, engine: WorkflowEngine, sse_hub=None) -> None:
    global _registry, _engine, _sse_hub
    _registry = registry
    _engine = engine
    _sse_hub = sse_hub


# === Request / Response Models ===


class ResumeRequest(BaseModel):
    budget_top_up: float = Field(default=0.0, ge=0.0, le=500.0)


class ResumeResponse(BaseModel):
    workflow_id: str
    new_state: str
    budget_remaining: float
    detail: str = ""


class DirectionResponseRequest(BaseModel):
    """User response to a DC (Direction Check) event."""
    response: str = Field(min_length=1, max_length=1000)
    # e.g. "continue" | "focus:BRCA1,TP53" | "skip_network_analysis" | "adjust:<free text>"


class StepInjectRequest(BaseModel):
    """Manual result injection for a workflow step."""
    result: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="Manual injection by user", max_length=500)


class StepControlResponse(BaseModel):
    workflow_id: str
    step_id: str
    action: str
    detail: str = ""


# === Helpers ===


def _require_step_control():
    if not settings.step_rerun_enabled:
        raise HTTPException(status_code=403, detail="Step re-run is disabled (step_rerun_enabled=False).")


def _get_instance(workflow_id: str) -> WorkflowInstance:
    with Session(db_engine) as session:
        instance = session.get(WorkflowInstance, workflow_id)
        if instance is None:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")
        session.expunge(instance)
    return instance


def _save_instance(instance: WorkflowInstance) -> None:
    instance.updated_at = datetime.now(timezone.utc)
    with Session(db_engine) as session:
        session.merge(instance)
        session.commit()


# === Endpoints ===


@router.post("/workflows/{workflow_id}/resume", response_model=ResumeResponse)
async def resume_workflow(workflow_id: str, request: ResumeRequest) -> ResumeResponse:
    """Resume an OVER_BUDGET, PAUSED, or WAITING_DIRECTION workflow.

    Optionally add budget (budget_top_up > 0) before resuming.
    """
    instance = _get_instance(workflow_id)

    resumable = {"OVER_BUDGET", "PAUSED", "WAITING_HUMAN", "WAITING_DIRECTION", "FAILED"}
    if instance.state not in resumable:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot resume workflow in state {instance.state!r}. Must be one of {resumable}.",
        )

    if _engine is None:
        raise HTTPException(status_code=503, detail="Workflow engine not initialized.")

    # Apply budget top-up
    if request.budget_top_up > 0:
        instance.budget_remaining = instance.budget_remaining + request.budget_top_up
        instance.budget_total = instance.budget_total + request.budget_top_up
        logger.info("Budget top-up %.2f for workflow %s", request.budget_top_up, workflow_id)

    _engine.resume(instance)
    _save_instance(instance)

    # Re-dispatch execution
    _dispatch_resume(workflow_id, instance.template, instance.query)

    return ResumeResponse(
        workflow_id=workflow_id,
        new_state=instance.state,
        budget_remaining=instance.budget_remaining,
        detail=f"Workflow resumed. Budget: ${instance.budget_remaining:.2f} remaining.",
    )


@router.post("/workflows/{workflow_id}/direction_response", response_model=StepControlResponse)
async def submit_direction_response(
    workflow_id: str, request: DirectionResponseRequest
) -> StepControlResponse:
    """Submit user response to a Direction Check (DC) event.

    Response format:
      "continue"                    → proceed with all steps unchanged
      "focus:BRCA1,TP53"           → narrow focus to specific genes
      "skip_network_analysis"       → skip a specific step
      "adjust:<free-form text>"     → inject a user adjustment note
    """
    instance = _get_instance(workflow_id)

    if instance.state != "WAITING_DIRECTION":
        raise HTTPException(
            status_code=409,
            detail=f"No pending Direction Check. Current state: {instance.state!r}.",
        )

    if _engine is None:
        raise HTTPException(status_code=503, detail="Workflow engine not initialized.")

    # Store the direction response in session_manifest
    manifest = dict(instance.session_manifest)
    dc_responses = manifest.get("direction_responses", [])
    dc_responses.append({
        "response": request.response,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "step": instance.current_step,
    })
    manifest["direction_responses"] = dc_responses
    manifest["pending_user_adjustment"] = request.response
    instance.session_manifest = manifest

    # Transition back to RUNNING
    _engine.resume(instance)
    _save_instance(instance)

    # Re-dispatch
    _dispatch_resume(workflow_id, instance.template, instance.query)

    return StepControlResponse(
        workflow_id=workflow_id,
        step_id=instance.current_step,
        action="direction_response",
        detail=f"Direction response recorded. Resuming with: {request.response[:100]}",
    )


@router.post("/workflows/{workflow_id}/steps/{step_id}/rerun", response_model=StepControlResponse)
async def rerun_step(workflow_id: str, step_id: str) -> StepControlResponse:
    """Re-execute a specific step by clearing its checkpoint.

    The workflow must be PAUSED, WAITING_DIRECTION, OVER_BUDGET, or FAILED.
    """
    _require_step_control()
    instance = _get_instance(workflow_id)

    rerunable_states = {"PAUSED", "WAITING_DIRECTION", "OVER_BUDGET", "FAILED", "WAITING_HUMAN"}
    if instance.state not in rerunable_states:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot re-run step in state {instance.state!r}.",
        )

    # Delete existing checkpoint for this step
    with Session(db_engine) as session:
        existing = session.exec(
            select(SessionCheckpoint).where(
                SessionCheckpoint.workflow_id == workflow_id,
                SessionCheckpoint.step_id == step_id,
            )
        ).first()
        if existing:
            session.delete(existing)
            session.commit()
            logger.info("Cleared checkpoint for step %s in workflow %s", step_id, workflow_id)

    # Set current_step to this step so resume picks up from here
    instance.current_step = step_id
    if _engine:
        _engine.resume(instance)
    _save_instance(instance)

    _dispatch_resume(workflow_id, instance.template, instance.query)

    return StepControlResponse(
        workflow_id=workflow_id,
        step_id=step_id,
        action="rerun",
        detail=f"Step {step_id} checkpoint cleared. Workflow will re-execute from this step.",
    )


@router.post("/workflows/{workflow_id}/steps/{step_id}/skip", response_model=StepControlResponse)
async def skip_step(workflow_id: str, step_id: str) -> StepControlResponse:
    """Skip a step by saving an empty result (workflow continues past it)."""
    _require_step_control()
    _get_instance(workflow_id)

    # Save a "skipped" checkpoint
    with Session(db_engine) as session:
        existing = session.exec(
            select(SessionCheckpoint).where(
                SessionCheckpoint.workflow_id == workflow_id,
                SessionCheckpoint.step_id == step_id,
            )
        ).first()
        cp = existing or SessionCheckpoint(
            workflow_id=workflow_id,
            step_id=step_id,
            step_index=0,
            agent_id="skip",
        )
        cp.status = "skipped"
        cp.agent_output = {"output": {}, "summary": f"Skipped by user at {datetime.now(timezone.utc).isoformat()}"}
        cp.error = None
        session.add(cp)
        session.commit()

    logger.info("Step %s skipped in workflow %s", step_id, workflow_id)

    return StepControlResponse(
        workflow_id=workflow_id,
        step_id=step_id,
        action="skip",
        detail=f"Step {step_id} marked as skipped. Resume the workflow to continue.",
    )


@router.post("/workflows/{workflow_id}/steps/{step_id}/inject", response_model=StepControlResponse)
async def inject_step_result(
    workflow_id: str, step_id: str, request: StepInjectRequest
) -> StepControlResponse:
    """Inject a manual result for a step without re-executing the agent."""
    _require_step_control()

    with Session(db_engine) as session:
        existing = session.exec(
            select(SessionCheckpoint).where(
                SessionCheckpoint.workflow_id == workflow_id,
                SessionCheckpoint.step_id == step_id,
            )
        ).first()
        cp = existing or SessionCheckpoint(
            workflow_id=workflow_id,
            step_id=step_id,
            step_index=0,
            agent_id="injected",
        )
        cp.status = "injected"
        cp.agent_output = {
            "output": request.result,
            "summary": request.reason,
            "agent_id": "injected",
        }
        cp.user_adjustment = request.reason
        session.add(cp)
        session.commit()

    logger.info("Step %s injected in workflow %s", step_id, workflow_id)

    return StepControlResponse(
        workflow_id=workflow_id,
        step_id=step_id,
        action="inject",
        detail=f"Manual result injected for step {step_id}.",
    )


# === Dispatch Helper ===


def _dispatch_resume(workflow_id: str, template: str, query: str) -> None:
    """Re-dispatch a workflow from its current step via Celery or asyncio."""
    from app.celery_app import is_celery_enabled

    if is_celery_enabled():
        try:
            from app.tasks.workflow_tasks import resume_workflow as celery_resume
            celery_resume.delay(workflow_id, template, query)
            return
        except Exception as e:
            logger.warning("Celery resume failed, falling back to asyncio: %s", e)

    asyncio.create_task(_resume_background(workflow_id, template, query))


async def _resume_background(workflow_id: str, template: str, query: str) -> None:
    """Background resume execution (asyncio fallback)."""
    from app.api.v1.workflows import _resume_workflow_background
    try:
        await _resume_workflow_background(workflow_id, template, query)
    except Exception as e:
        logger.error("Resume background error for %s: %s", workflow_id, e)
