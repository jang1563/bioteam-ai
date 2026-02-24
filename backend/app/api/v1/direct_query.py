"""Direct Query API endpoint.

POST /api/v1/direct-query
Accepts a research question, routes through Research Director,
retrieves context from Knowledge Manager, and returns a structured response.

v5: Registry-backed handler replaces 503 stub.
v6: Full answer pipeline — classify → retrieve → generate answer.
    Added 30s timeout, $0.50 cost cap per PRD requirements.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from app.agents.registry import AgentRegistry
from app.models.messages import ContextPackage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["direct-query"])

# PRD performance targets (FR-1)
DIRECT_QUERY_TIMEOUT = 30.0  # seconds
DIRECT_QUERY_COST_CAP = 0.50  # USD

# Module-level registry reference, set by main.py at startup
_registry: AgentRegistry | None = None


def set_registry(registry: AgentRegistry) -> None:
    """Wire up the agent registry (called from main.py lifespan)."""
    global _registry
    _registry = registry


# === Request / Response models ===


class DirectQueryRequest(BaseModel):
    """Incoming direct query from the dashboard."""

    query: str = Field(min_length=1, max_length=2000, description="Research question")
    seed_papers: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="Optional DOIs to include",
    )


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


# === Helper functions ===


def _build_context_text(memory_context: list[dict]) -> str:
    """Format memory context into a text block for LLM grounding."""
    if not memory_context:
        return "(No prior knowledge available.)"

    parts = []
    for i, item in enumerate(memory_context, 1):
        content = item.get("content", item.get("text", ""))
        source = item.get("source", "unknown")
        metadata = item.get("metadata", {})
        doi = metadata.get("doi", "")
        year = metadata.get("year", "")

        ref = f"[{i}]"
        if doi:
            ref += f" DOI:{doi}"
        if year:
            ref += f" ({year})"
        ref += f" [{source}]"
        parts.append(f"{ref}\n{content}")

    return "\n\n".join(parts)


def _extract_sources(memory_context: list[dict]) -> list[dict]:
    """Extract structured source references from memory context."""
    sources = []
    for item in memory_context:
        metadata = item.get("metadata", {})
        source_entry = {
            "content_snippet": (item.get("content", item.get("text", "")))[:200],
            "source_type": item.get("source", "unknown"),
        }
        if metadata.get("doi"):
            source_entry["doi"] = metadata["doi"]
        if metadata.get("year"):
            source_entry["year"] = metadata["year"]
        if metadata.get("title"):
            source_entry["title"] = metadata["title"]
        sources.append(source_entry)
    return sources


# === Pipeline function (decoupled from FastAPI for testing) ===


async def run_direct_query(
    query: str,
    research_director: Any,
    knowledge_manager: Any,
    registry: AgentRegistry | None = None,
    seed_papers: list[str] | None = None,
) -> DirectQueryResponse:
    """Execute the Direct Query pipeline.

    Pipeline:
      1. Research Director classifies query (Sonnet)
      2. Knowledge Manager retrieves memory context
      3. Generate answer using LLM with memory grounding (Sonnet)

    Args:
        query: Research question.
        research_director: ResearchDirectorAgent instance.
        knowledge_manager: KnowledgeManagerAgent instance.
        registry: Optional AgentRegistry for specialist routing.
        seed_papers: Optional DOIs to prioritize.

    Returns:
        DirectQueryResponse with classification and answer.
    """
    import time
    start = time.time()

    total_cost = 0.0
    total_tokens = 0
    model_versions: list[str] = []

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

    # Step 2: If simple_query, retrieve memory context + generate answer
    memory_context: list[dict] = []
    answer: str | None = None
    sources: list[dict] = []

    if classification_type == "simple_query":
        # 2a: Retrieve relevant memory
        memory_output = await knowledge_manager.execute(context)
        if memory_output.is_success and memory_output.output:
            memory_context = memory_output.output.get("results", [])
            total_cost += memory_output.cost
            total_tokens += memory_output.input_tokens + memory_output.output_tokens
            if memory_output.model_version:
                model_versions.append(memory_output.model_version)

        # Cost cap check before answer generation
        if total_cost >= DIRECT_QUERY_COST_CAP:
            logger.warning("Cost cap reached ($%.4f >= $%.2f), skipping answer generation",
                           total_cost, DIRECT_QUERY_COST_CAP)
        else:
            # 2b: Generate answer using LLM with memory grounding
            llm = research_director.llm
            context_text = _build_context_text(memory_context)

            answer_messages = [
                {
                    "role": "user",
                    "content": (
                        f"Research question: {query}\n\n"
                        f"Relevant knowledge base context:\n{context_text}\n\n"
                        f"Provide a concise, evidence-based answer to the research question. "
                        f"Cite specific sources using [N] notation when available. "
                        f"If the context is insufficient, clearly state what is known "
                        f"and what knowledge gaps remain."
                    ),
                }
            ]

            try:
                raw_response, answer_meta = await llm.complete_raw(
                    messages=answer_messages,
                    model_tier="sonnet",
                    max_tokens=2048,
                )

                # Extract text from response
                answer_parts = []
                for block in raw_response.content:
                    if hasattr(block, "text"):
                        answer_parts.append(block.text)
                answer = "".join(answer_parts) if answer_parts else None

                total_cost += answer_meta.cost
                total_tokens += answer_meta.input_tokens + answer_meta.output_tokens
                if answer_meta.model_version:
                    model_versions.append(answer_meta.model_version)
            except Exception as e:
                logger.error("Answer generation failed: %s", e)
                # Pipeline still returns classification + memory even if answer fails

        # Extract structured sources from memory context
        sources = _extract_sources(memory_context)

    duration_ms = int((time.time() - start) * 1000)

    return DirectQueryResponse(
        query=query,
        classification_type=classification_type,
        classification_reasoning=classification.get("reasoning", ""),
        target_agent=target_agent,
        workflow_type=workflow_type,
        answer=answer,
        sources=sources,
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

    Routes through Research Director for classification, retrieves
    context from Knowledge Manager, and generates an answer.
    Enforces 30s timeout and $0.50 cost cap per PRD FR-1.
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
        return await asyncio.wait_for(
            run_direct_query(
                query=request.query,
                research_director=rd,
                knowledge_manager=km,
                registry=_registry,
                seed_papers=request.seed_papers,
            ),
            timeout=DIRECT_QUERY_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Direct query timed out after {int(DIRECT_QUERY_TIMEOUT)}s.",
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
