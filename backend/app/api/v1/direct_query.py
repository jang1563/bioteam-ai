"""Direct Query API endpoint.

POST /api/v1/direct-query
Accepts a research question, routes through Research Director,
retrieves context from Knowledge Manager, and returns a structured response.

v5: Registry-backed handler replaces 503 stub.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from app.agents.registry import AgentRegistry
from app.models.messages import ContextPackage

router = APIRouter(prefix="/api/v1", tags=["direct-query"])

# Module-level registry reference, set by main.py at startup
_registry: AgentRegistry | None = None


def set_registry(registry: AgentRegistry) -> None:
    """Wire up the agent registry (called from main.py lifespan)."""
    global _registry
    _registry = registry


# === Request / Response models ===


class DirectQueryRequest(BaseModel):
    """Incoming direct query from the dashboard."""

    query: str = Field(min_length=1, description="Research question")
    seed_papers: list[str] = Field(default_factory=list, description="Optional DOIs to include")


class DirectQueryResponse(BaseModel):
    """Response from Direct Query pipeline."""

    query: str
    classification_type: str  # "simple_query" | "needs_workflow"
    classification_reasoning: str = ""
    target_agent: str | None = None
    workflow_type: str | None = None

    # Populated for simple_query
    answer: str | None = None
    sources: list[dict] = Field(default_factory=list)
    memory_context: list[dict] = Field(default_factory=list)

    # Metadata
    total_cost: float = 0.0
    total_tokens: int = 0
    model_versions: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# === Pipeline function (decoupled from FastAPI for testing) ===


async def run_direct_query(
    query: str,
    research_director: Any,
    knowledge_manager: Any,
    seed_papers: list[str] | None = None,
) -> DirectQueryResponse:
    """Execute the Direct Query pipeline.

    Pipeline: Research Director classifies → Knowledge Manager retrieves → Response

    Args:
        query: Research question.
        research_director: ResearchDirectorAgent instance.
        knowledge_manager: KnowledgeManagerAgent instance.
        seed_papers: Optional DOIs to prioritize.

    Returns:
        DirectQueryResponse with classification and optional answer.
    """
    import time
    start = time.time()

    total_cost = 0.0
    total_tokens = 0
    model_versions = []

    # Step 1: Classify query
    context = ContextPackage(task_description=query)
    classification_output = await research_director.execute(context)

    if not classification_output.is_success:
        raise RuntimeError(f"Research Director failed: {classification_output.error}")

    total_cost += classification_output.cost
    total_tokens += classification_output.input_tokens + classification_output.output_tokens
    if classification_output.model_version:
        model_versions.append(classification_output.model_version)

    classification = classification_output.output
    classification_type = classification.get("type", "simple_query")
    target_agent = classification.get("target_agent")
    workflow_type = classification.get("workflow_type")

    # Step 2: If simple_query, retrieve memory context
    memory_context = []
    if classification_type == "simple_query":
        memory_output = await knowledge_manager.execute(context)
        if memory_output.is_success and memory_output.output:
            memory_context = memory_output.output.get("results", [])
            total_cost += memory_output.cost
            total_tokens += memory_output.input_tokens + memory_output.output_tokens
            if memory_output.model_version:
                model_versions.append(memory_output.model_version)

    duration_ms = int((time.time() - start) * 1000)

    return DirectQueryResponse(
        query=query,
        classification_type=classification_type,
        classification_reasoning=classification.get("reasoning", ""),
        target_agent=target_agent,
        workflow_type=workflow_type,
        memory_context=memory_context,
        total_cost=total_cost,
        total_tokens=total_tokens,
        model_versions=model_versions,
        duration_ms=duration_ms,
    )


# === FastAPI endpoint ===


@router.post("/direct-query", response_model=DirectQueryResponse)
async def direct_query_endpoint(request: DirectQueryRequest) -> DirectQueryResponse:
    """Handle a direct research query.

    Routes through Research Director for classification, then
    retrieves context from Knowledge Manager for simple queries.
    """
    if _registry is None:
        raise HTTPException(
            status_code=503,
            detail="Agent registry not initialized. Run Cold Start first.",
        )

    rd = _registry.get("research_director")
    km = _registry.get("knowledge_manager")

    if rd is None or km is None:
        raise HTTPException(
            status_code=503,
            detail="Required agents (research_director, knowledge_manager) not available.",
        )

    try:
        return await run_direct_query(
            query=request.query,
            research_director=rd,
            knowledge_manager=km,
            seed_papers=request.seed_papers,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
