"""Meta-Workflow API endpoints — create and manage DAG-based workflow chains.

POST /api/v1/meta-workflows — create from template or custom DAG
GET  /api/v1/meta-workflows/{id} — status + sub-workflow states
POST /api/v1/meta-workflows/{id}/intervene — meta-level pause/resume
GET  /api/v1/meta-workflows/{id}/graph — DAG for frontend visualization
"""

from __future__ import annotations

import logging

from app.config import settings
from app.db.database import engine as db_engine
from app.models.meta_workflow import MetaWorkflowDef, MetaWorkflowInstance, MetaWorkflowNode
from app.workflows.meta_orchestrator import MetaWorkflowOrchestrator
from app.workflows.meta_templates import META_TEMPLATES
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request/Response Models ──────────────────────────────────────────


class CreateMetaWorkflowRequest(BaseModel):
    """Request to create a meta-workflow."""

    template_id: str | None = None  # Use preset template
    custom_dag: dict | None = None  # Custom DAG definition
    query: str
    budget: float = 20.0


class MetaWorkflowStatusResponse(BaseModel):
    """Response for meta-workflow status."""

    id: str
    definition_id: str
    name: str
    state: str
    query: str
    budget_total: float
    budget_remaining: float
    node_states: dict[str, str]
    node_results: dict[str, dict]
    spawned_workflows: list[str]


class MetaIntervenRequest(BaseModel):
    """Request to intervene in a meta-workflow."""

    action: str  # "pause", "resume", "cancel"


class MetaGraphNode(BaseModel):
    """A node in the DAG graph for frontend visualization."""

    id: str
    template: str
    state: str = "pending"
    depends_on: list[str] = Field(default_factory=list)
    human_checkpoint: bool = False
    condition: str | None = None


class MetaGraphResponse(BaseModel):
    """DAG graph for frontend visualization."""

    meta_workflow_id: str
    nodes: list[MetaGraphNode]


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("/meta-workflows/templates")
async def list_templates() -> list[dict]:
    """List available meta-workflow templates."""
    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "node_count": len(t.nodes),
            "templates": [n.template for n in t.nodes],
        }
        for t in META_TEMPLATES.values()
    ]


@router.post("/meta-workflows")
async def create_meta_workflow(request: CreateMetaWorkflowRequest) -> MetaWorkflowStatusResponse:
    """Create and start a meta-workflow."""
    if not settings.routing_enabled:
        raise HTTPException(status_code=404, detail="Meta-workflows require routing_enabled=True")

    # Resolve definition
    if request.template_id:
        definition = META_TEMPLATES.get(request.template_id)
        if not definition:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown template: {request.template_id}. "
                f"Available: {list(META_TEMPLATES.keys())}",
            )
    elif request.custom_dag:
        try:
            definition = MetaWorkflowDef(**request.custom_dag)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid DAG: {e}")
    else:
        raise HTTPException(status_code=400, detail="Provide template_id or custom_dag")

    # Validate
    errors = definition.validate_dag()
    if errors:
        raise HTTPException(status_code=400, detail=f"DAG validation failed: {'; '.join(errors)}")

    # Create instance
    instance = MetaWorkflowInstance(
        definition_id=definition.id,
        name=definition.name,
        query=request.query,
        budget_total=request.budget,
        budget_remaining=request.budget,
        dag_nodes=[n.model_dump() for n in definition.nodes],
        node_states={n.id: "pending" for n in definition.nodes},
    )

    with Session(db_engine) as session:
        session.add(instance)
        session.commit()
        session.refresh(instance)

    # Dispatch execution in background
    import asyncio
    asyncio.create_task(_run_meta_background(instance.id, definition))

    return _build_status_response(instance)


@router.get("/meta-workflows/{meta_id}")
async def get_meta_workflow(meta_id: str) -> MetaWorkflowStatusResponse:
    """Get meta-workflow status."""
    with Session(db_engine) as session:
        instance = session.get(MetaWorkflowInstance, meta_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Meta-workflow not found")
        return _build_status_response(instance)


@router.post("/meta-workflows/{meta_id}/intervene")
async def intervene_meta(meta_id: str, request: MetaIntervenRequest) -> dict:
    """Pause, resume, or cancel a meta-workflow."""
    with Session(db_engine) as session:
        instance = session.get(MetaWorkflowInstance, meta_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Meta-workflow not found")

        if request.action == "pause":
            if instance.state != "RUNNING":
                raise HTTPException(status_code=409, detail=f"Cannot pause from {instance.state}")
            instance.state = "PAUSED"
            session.add(instance)
            session.commit()
            return {"meta_id": meta_id, "action": "pause", "new_state": "PAUSED"}

        elif request.action == "resume":
            if instance.state != "PAUSED":
                raise HTTPException(status_code=409, detail=f"Cannot resume from {instance.state}")
            instance.state = "RUNNING"
            session.add(instance)
            session.commit()

            # Reconstruct definition and resume
            definition = MetaWorkflowDef(
                id=instance.definition_id,
                name=instance.name,
                nodes=[MetaWorkflowNode(**n) for n in instance.dag_nodes],
            )
            import asyncio
            asyncio.create_task(_run_meta_background(instance.id, definition))

            return {"meta_id": meta_id, "action": "resume", "new_state": "RUNNING"}

        elif request.action == "cancel":
            instance.state = "FAILED"
            session.add(instance)
            session.commit()
            return {"meta_id": meta_id, "action": "cancel", "new_state": "FAILED"}

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")


@router.get("/meta-workflows/{meta_id}/graph")
async def get_meta_graph(meta_id: str) -> MetaGraphResponse:
    """Get DAG graph for frontend visualization."""
    with Session(db_engine) as session:
        instance = session.get(MetaWorkflowInstance, meta_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Meta-workflow not found")

        nodes = []
        for node_dict in instance.dag_nodes:
            node = MetaWorkflowNode(**node_dict)
            nodes.append(MetaGraphNode(
                id=node.id,
                template=node.template,
                state=instance.node_states.get(node.id, "pending"),
                depends_on=node.depends_on,
                human_checkpoint=node.human_checkpoint,
                condition=node.condition,
            ))

        return MetaGraphResponse(meta_workflow_id=meta_id, nodes=nodes)


# ── Background execution ────────────────────────────────────────────


async def _run_meta_background(meta_id: str, definition: MetaWorkflowDef) -> None:
    """Run meta-workflow in background task."""
    try:
        with Session(db_engine) as session:
            instance = session.get(MetaWorkflowInstance, meta_id)
            if not instance:
                logger.error("Meta-workflow %s not found for background execution", meta_id)
                return

            async def persist(inst: MetaWorkflowInstance) -> None:
                with Session(db_engine) as s:
                    s.add(inst)
                    s.commit()

            orchestrator = MetaWorkflowOrchestrator(
                persist_fn=persist,
            )

            await orchestrator.run(definition, instance.query, instance.budget_remaining, instance)

    except Exception as e:
        logger.error("Meta-workflow %s failed: %s", meta_id, e)
        try:
            with Session(db_engine) as session:
                instance = session.get(MetaWorkflowInstance, meta_id)
                if instance:
                    instance.state = "FAILED"
                    session.add(instance)
                    session.commit()
        except Exception:
            pass


# ── Helpers ──────────────────────────────────────────────────────────


def _build_status_response(instance: MetaWorkflowInstance) -> MetaWorkflowStatusResponse:
    return MetaWorkflowStatusResponse(
        id=instance.id,
        definition_id=instance.definition_id,
        name=instance.name,
        state=instance.state,
        query=instance.query,
        budget_total=instance.budget_total,
        budget_remaining=instance.budget_remaining,
        node_states=instance.node_states,
        node_results=instance.node_results,
        spawned_workflows=instance.spawned_workflows,
    )
