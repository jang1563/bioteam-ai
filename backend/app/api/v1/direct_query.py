"""Direct Query API endpoint.

POST /api/v1/direct-query
GET  /api/v1/direct-query/stream (SSE)

Accepts a research question, routes through Research Director,
retrieves context from Knowledge Manager, and returns a structured response.

v5: Registry-backed handler replaces 503 stub.
v6: Full answer pipeline — classify → retrieve → generate answer.
    Added 30s timeout, $0.50 cost cap per PRD requirements.
v7: Specialist routing + SSE streaming endpoint.
v8: Citation post-validation (hallucination guard), seed_papers prioritization.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from app.agents.registry import AgentRegistry
from app.models.messages import ContextPackage
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["direct-query"])

# PRD performance targets (FR-1)
DIRECT_QUERY_TIMEOUT = 30.0  # seconds
DIRECT_QUERY_COST_CAP = 0.50  # USD

# Module-level registry reference, set by main.py at startup
_registry: AgentRegistry | None = None


def set_registry(registry: AgentRegistry | None) -> None:
    """Wire up the agent registry (called from main.py lifespan)."""
    global _registry
    _registry = registry


# === Request / Response models ===


class DirectQueryRequest(BaseModel):
    """Incoming direct query from the dashboard."""

    query: str = Field(min_length=1, max_length=2000, description="Research question")
    conversation_id: str | None = Field(default=None, description="Continue existing conversation")
    seed_papers: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="Optional DOI/PMID identifiers to prioritize in context",
    )


class DirectQueryResponse(BaseModel):
    """Response from Direct Query pipeline."""

    query: str
    classification_type: str  # "simple_query" | "needs_workflow"
    classification_reasoning: str = ""
    target_agent: str | None = None
    workflow_type: str | None = None
    routed_agent: str | None = None  # Agent actually used for answer generation
    conversation_id: str | None = None  # Created or continued conversation ID

    # Populated for simple_query
    answer: str | None = None
    sources: list[dict] = Field(default_factory=list)
    memory_context: list[dict] = Field(default_factory=list)
    ungrounded_citations: list[str] = Field(
        default_factory=list,
        description="DOI/PMID patterns in the answer not found in retrieved sources",
    )

    # Metadata
    total_cost: float = 0.0
    total_tokens: int = 0
    model_versions: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# === Helper functions ===


def _resolve_specialist(
    registry: AgentRegistry | None,
    target_agent: str | None,
) -> tuple[str | None, str]:
    """Resolve specialist agent's system prompt for answer generation.

    Returns (agent_id, system_prompt_text).
    Falls back to generic prompt if agent unavailable.
    """
    if not registry or not target_agent:
        return None, ""

    agent = registry.get(target_agent)
    if agent is None or not registry.is_available(target_agent):
        logger.info("Specialist %s unavailable, using generic prompt", target_agent)
        return None, ""

    return agent.agent_id, agent.system_prompt


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
        if metadata.get("pmid"):
            source_entry["pmid"] = str(metadata["pmid"])
        if metadata.get("year"):
            source_entry["year"] = metadata["year"]
        if metadata.get("title"):
            source_entry["title"] = metadata["title"]
        if metadata.get("authors"):
            source_entry["authors"] = metadata["authors"]
        if metadata.get("journal"):
            source_entry["journal"] = metadata["journal"]
        sources.append(source_entry)
    return sources


# Patterns for extracting citation identifiers from LLM answers
_DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[^\s,;)\]>\"']+", re.IGNORECASE)
_PMID_PATTERN = re.compile(r"\bPMID[:\s]+(\d{5,9})\b", re.IGNORECASE)
_AUTHOR_YEAR_PATTERN = re.compile(
    r"\b([A-Z][a-zA-Z\-']{1,40})\s+et al\.,?\s*\(?((?:19|20)\d{2})\)?"
)


def _normalize_doi(doi: str) -> str:
    """Normalize DOI string for matching."""
    value = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if value.startswith(prefix):
            value = value[len(prefix):]
    return value


def _normalize_pmid(value: str | int) -> str:
    """Normalize PMID to digit-only string."""
    text = str(value).strip()
    if text.lower().startswith("pmid:"):
        text = text[5:].strip()
    return text


def _validate_answer_citations(answer: str, sources: list[dict]) -> tuple[str, list[str]]:
    """Post-validate citations in LLM answer against retrieved sources.

    Extracts DOI/PMID patterns from the answer and checks each against the
    known sources list.  Returns the (possibly annotated) answer and a list
    of any ungrounded citation strings found.

    The answer text is not modified; ungrounded citations are reported so
    the caller can decide how to surface them (warning log, response field).
    """
    if not answer:
        return answer, []

    # Build lookup tables from retrieved sources for grounding checks.
    source_dois: set[str] = set()
    source_pmids: set[str] = set()
    source_author_surnames: set[str] = set()
    for src in sources:
        doi = src.get("doi", "")
        if doi:
            source_dois.add(_normalize_doi(doi))
        pmid = src.get("pmid", "")
        if pmid:
            source_pmids.add(_normalize_pmid(pmid))
        authors = src.get("authors", [])
        if isinstance(authors, list):
            for author in authors:
                if not author:
                    continue
                surname = str(author).strip().split()[-1].lower()
                if surname:
                    source_author_surnames.add(surname)

    ungrounded: list[str] = []
    seen_ungrounded: set[str] = set()

    for doi in _DOI_PATTERN.findall(answer):
        normalized = _normalize_doi(doi)
        if normalized not in source_dois:
            key = f"DOI:{doi}"
            if key not in seen_ungrounded:
                seen_ungrounded.add(key)
                ungrounded.append(key)

    # PMIDs are validated against retrieved sources regardless of source count.
    for pmid in _PMID_PATTERN.findall(answer):
        normalized = _normalize_pmid(pmid)
        if normalized not in source_pmids:
            key = f"PMID:{pmid}"
            if key not in seen_ungrounded:
                seen_ungrounded.add(key)
                ungrounded.append(key)

    # Validate "Surname et al. (YEAR)" style mentions against retrieved author list.
    for surname, year in _AUTHOR_YEAR_PATTERN.findall(answer):
        key = f"AUTHOR_YEAR:{surname} et al. ({year})"
        if surname.lower() not in source_author_surnames and key not in seen_ungrounded:
            seen_ungrounded.add(key)
            ungrounded.append(key)

    if ungrounded:
        logger.warning(
            "Citation post-validation: %d ungrounded citation(s) detected: %s",
            len(ungrounded),
            ", ".join(ungrounded[:5]),
        )

    return answer, ungrounded


def _prioritize_context_by_seed_papers(
    memory_context: list[dict],
    seed_papers: list[str],
) -> list[dict]:
    """Reorder memory context so seed_paper DOIs appear first.

    seed_papers are DOIs/PMIDs the user explicitly wants included.
    Matching items are moved to the front; the rest retain their order.
    """
    if not seed_papers or not memory_context:
        return memory_context

    seed_dois = set()
    seed_pmids = set()
    for seed in seed_papers:
        raw = seed.strip()
        if not raw:
            continue
        if raw.lower().startswith("10.") or "doi:" in raw.lower() or "doi.org/" in raw.lower():
            seed_dois.add(_normalize_doi(raw))
            continue
        normalized_pmid = _normalize_pmid(raw)
        if normalized_pmid.isdigit():
            seed_pmids.add(normalized_pmid)

    prioritized = []
    rest = []
    for item in memory_context:
        metadata = item.get("metadata", {})
        doi = metadata.get("doi", "")
        pmid = metadata.get("pmid", "")
        doi_match = bool(doi) and _normalize_doi(str(doi)) in seed_dois
        pmid_match = bool(pmid) and _normalize_pmid(pmid) in seed_pmids
        if doi_match or pmid_match:
            prioritized.append(item)
        else:
            rest.append(item)

    return prioritized + rest


# === Pipeline function (decoupled from FastAPI for testing) ===


def _load_conversation_history(conversation_id: str | None) -> list[dict]:
    """Load prior turns as LLM message pairs. Returns last 10 turns max."""
    if not conversation_id:
        return []
    try:
        from app.db.database import engine
        from app.models.messages import ConversationTurn
        from sqlmodel import Session, select

        with Session(engine) as session:
            stmt = (
                select(ConversationTurn)
                .where(ConversationTurn.conversation_id == conversation_id)
                .order_by(ConversationTurn.turn_number.desc())  # type: ignore[union-attr]
                .limit(10)
            )
            turns = list(reversed(session.exec(stmt).all()))

        messages = []
        for turn in turns:
            messages.append({"role": "user", "content": turn.query})
            if turn.answer:
                messages.append({"role": "assistant", "content": turn.answer})
        return messages
    except Exception as e:
        logger.warning("Failed to load conversation history: %s", e)
        return []


def _save_conversation_turn(
    conversation_id: str | None,
    query: str,
    classification_type: str,
    routed_agent: str | None,
    answer: str | None,
    sources: list[dict],
    cost: float,
    duration_ms: int,
) -> str | None:
    """Save a turn. Creates conversation if needed. Returns conversation_id."""
    if classification_type != "simple_query":
        return None
    try:
        from app.db.database import engine
        from app.models.messages import Conversation, ConversationTurn
        from sqlmodel import Session

        with Session(engine) as session:
            if conversation_id:
                conv = session.get(Conversation, conversation_id)
                if conv is None:
                    conversation_id = None  # Fall through to create

            if not conversation_id:
                conv = Conversation(
                    title=query[:60],
                    total_cost=0.0,
                    turn_count=0,
                )
                session.add(conv)
                session.flush()
                conversation_id = conv.id
            else:
                conv = session.get(Conversation, conversation_id)

            if conv is not None:
                conv.turn_count += 1
                conv.total_cost += cost
                conv.updated_at = datetime.now(timezone.utc)

                turn = ConversationTurn(
                    conversation_id=conversation_id,
                    turn_number=conv.turn_count,
                    query=query,
                    classification_type=classification_type,
                    routed_agent=routed_agent,
                    answer=answer,
                    sources=sources,
                    cost=cost,
                    duration_ms=duration_ms,
                )
                session.add(turn)
                session.commit()

            return conversation_id
    except Exception as e:
        logger.warning("Failed to save conversation turn: %s", e)
        return conversation_id


async def run_direct_query(
    query: str,
    research_director: Any,
    knowledge_manager: Any,
    registry: AgentRegistry | None = None,
    seed_papers: list[str] | None = None,
    conversation_id: str | None = None,
) -> DirectQueryResponse:
    """Execute the Direct Query pipeline.

    Pipeline:
      1. Research Director classifies query (Sonnet)
      2. Knowledge Manager retrieves memory context
      3. Generate answer using LLM with memory grounding (Sonnet)
      4. Save conversation turn

    Args:
        query: Research question.
        research_director: ResearchDirectorAgent instance.
        knowledge_manager: KnowledgeManagerAgent instance.
        registry: Optional AgentRegistry for specialist routing.
        seed_papers: Optional DOIs to prioritize.
        conversation_id: Optional ID to continue a conversation.

    Returns:
        DirectQueryResponse with classification and answer.
    """
    start = time.time()

    total_cost = 0.0
    total_tokens = 0
    model_versions: list[str] = []

    # Load conversation history for context
    conversation_history = _load_conversation_history(conversation_id)

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
    routed_agent: str | None = None
    ungrounded_citations: list[str] = []

    if classification_type == "simple_query":
        # 2a: Resolve specialist agent for domain-grounded answers
        routed_agent, specialist_prompt = _resolve_specialist(registry, target_agent)

        # 2b: Retrieve relevant memory
        memory_output = await knowledge_manager.execute(context)
        if memory_output.is_success and memory_output.output:
            memory_context = memory_output.output.get("results", [])
            total_cost += memory_output.cost
            total_tokens += memory_output.input_tokens + memory_output.output_tokens
            if memory_output.model_version:
                model_versions.append(memory_output.model_version)

        # Prioritize seed papers (user-specified DOIs) in context ordering
        if seed_papers:
            memory_context = _prioritize_context_by_seed_papers(memory_context, seed_papers)

        # Cost cap check before answer generation
        if total_cost >= DIRECT_QUERY_COST_CAP:
            logger.warning("Cost cap reached ($%.4f >= $%.2f), skipping answer generation",
                           total_cost, DIRECT_QUERY_COST_CAP)
        else:
            # 2c: Generate answer using LLM with memory grounding
            llm = research_director.llm
            context_text = _build_context_text(memory_context)

            # Grounding instructions depend on whether context is available
            if memory_context:
                grounding = (
                    "Cite specific sources using [N] notation when available. "
                    "CRITICAL: Only cite papers, DOIs, and facts that appear in the "
                    "knowledge base context above. Do not fabricate citations, "
                    "author names, or experimental results."
                )
            else:
                grounding = (
                    "No papers were found in the knowledge base for this topic. "
                    "You may provide a general answer based on your training knowledge, "
                    "but you MUST clearly label it as "
                    "'Based on general knowledge (not retrieved evidence)' "
                    "at the top of your answer. "
                    "Do NOT cite specific DOIs, PMIDs, or author names. "
                    "Recommend the user run a W1 Literature Review for "
                    "evidence-backed answers."
                )

            # Build messages with conversation history for context
            answer_messages = list(conversation_history)  # Prior turns
            answer_messages.append({
                "role": "user",
                "content": (
                    f"Research question: {query}\n\n"
                    f"Relevant knowledge base context:\n{context_text}\n\n"
                    f"Provide a concise, evidence-based answer to the research question. "
                    f"{grounding} "
                    f"If the context is insufficient, clearly state what is known "
                    f"and what knowledge gaps remain rather than guessing."
                ),
            })

            # Use specialist system prompt if available for domain expertise
            system_prompt = specialist_prompt if specialist_prompt else None

            try:
                raw_response, answer_meta = await llm.complete_raw(
                    messages=answer_messages,
                    model_tier="sonnet",
                    max_tokens=2048,
                    system=system_prompt,
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

        # Post-validate citations in the answer against retrieved sources
        if answer:
            answer, ungrounded_citations = _validate_answer_citations(answer, sources)
        else:
            ungrounded_citations: list[str] = []

    duration_ms = int((time.time() - start) * 1000)

    # Save conversation turn
    result_conversation_id = _save_conversation_turn(
        conversation_id=conversation_id,
        query=query,
        classification_type=classification_type,
        routed_agent=routed_agent,
        answer=answer,
        sources=sources,
        cost=total_cost,
        duration_ms=duration_ms,
    )

    return DirectQueryResponse(
        query=query,
        classification_type=classification_type,
        classification_reasoning=classification.get("reasoning", ""),
        target_agent=target_agent,
        workflow_type=workflow_type,
        routed_agent=routed_agent,
        conversation_id=result_conversation_id,
        answer=answer,
        sources=sources,
        memory_context=memory_context,
        ungrounded_citations=ungrounded_citations if classification_type == "simple_query" else [],
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
                conversation_id=request.conversation_id,
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


# === SSE Streaming endpoint ===


def _sse_event(event: str, data: dict) -> str:
    """Format a named SSE event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/direct-query/stream")
async def direct_query_stream(
    query: str = Query(min_length=1, max_length=2000, description="Research question"),
    conversation_id: str | None = Query(default=None, description="Continue existing conversation"),
    target_agent: str | None = Query(default=None, description="Skip RD classification and route directly to this agent"),
    seed_papers: list[str] = Query(default_factory=list, description="Optional DOI/PMID identifiers to prioritize in context"),
) -> StreamingResponse:
    """SSE endpoint for streaming Direct Query responses.

    Uses GET because EventSource API only supports GET.
    Emits named events: classification, memory, token, done, error.
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

    async def event_generator():
        start = time.time()
        total_cost = 0.0
        total_tokens = 0
        model_versions: list[str] = []

        # Load conversation history for context
        conv_history = _load_conversation_history(conversation_id)

        try:
            context = ContextPackage(task_description=query)

            if target_agent:
                # Fast path: skip Research Director classification, route directly
                classification_type = "simple_query"
                resolved_target = target_agent
                yield _sse_event("classification", {
                    "type": "simple_query",
                    "reasoning": f"Direct agent chat with {target_agent}",
                    "target_agent": target_agent,
                    "workflow_type": None,
                })
            else:
                # Standard path: Step 1 — classify via Research Director
                classification_output = await rd.execute(context)

                if not classification_output.is_success:
                    yield _sse_event("error", {"detail": f"Classification failed: {classification_output.error}"})
                    return

                total_cost += classification_output.cost
                total_tokens += classification_output.input_tokens + classification_output.output_tokens
                if classification_output.model_version:
                    model_versions.append(classification_output.model_version)

                classification = classification_output.output
                classification_type = classification.get("type", "simple_query")
                resolved_target = classification.get("target_agent")

                yield _sse_event("classification", {
                    "type": classification_type,
                    "reasoning": classification.get("reasoning", ""),
                    "target_agent": resolved_target,
                    "workflow_type": classification.get("workflow_type"),
                })

                # If needs_workflow, no streaming — send done immediately
                if classification_type != "simple_query":
                    duration_ms = int((time.time() - start) * 1000)
                    yield _sse_event("done", {
                        "classification_type": classification_type,
                        "target_agent": resolved_target,
                        "routed_agent": None,
                        "workflow_type": classification.get("workflow_type"),
                        "total_cost": total_cost,
                        "total_tokens": total_tokens,
                        "model_versions": model_versions,
                        "duration_ms": duration_ms,
                        "sources": [],
                    })
                    return

            # Step 2: Resolve specialist
            routed_agent, specialist_prompt = _resolve_specialist(_registry, resolved_target)

            # Step 3: Retrieve memory
            memory_output = await km.execute(context)
            memory_context: list[dict] = []
            if memory_output.is_success and memory_output.output:
                memory_context = memory_output.output.get("results", [])
                total_cost += memory_output.cost
                total_tokens += memory_output.input_tokens + memory_output.output_tokens
                if memory_output.model_version:
                    model_versions.append(memory_output.model_version)

            if seed_papers:
                memory_context = _prioritize_context_by_seed_papers(memory_context, seed_papers)

            sources = _extract_sources(memory_context)
            yield _sse_event("memory", {
                "results_count": len(memory_context),
                "sources": sources,
            })

            # Cost cap check
            if total_cost >= DIRECT_QUERY_COST_CAP:
                yield _sse_event("error", {"detail": "Cost cap reached before answer generation."})
                return

            # Step 4: Stream answer
            llm = rd.llm
            context_text = _build_context_text(memory_context)

            # Grounding instructions depend on whether context is available
            if memory_context:
                sse_grounding = (
                    "Cite specific sources using [N] notation when available. "
                    "CRITICAL: Only cite papers, DOIs, and facts that appear in the "
                    "knowledge base context above. Do not fabricate citations, "
                    "author names, or experimental results."
                )
            else:
                sse_grounding = (
                    "No papers were found in the knowledge base for this topic. "
                    "You may provide a general answer based on your training knowledge, "
                    "but you MUST clearly label it as "
                    "'Based on general knowledge (not retrieved evidence)' "
                    "at the top of your answer. "
                    "Do NOT cite specific DOIs, PMIDs, or author names. "
                    "Recommend the user run a W1 Literature Review for "
                    "evidence-backed answers."
                )

            answer_messages = list(conv_history)  # Prior turns for context
            answer_messages.append({
                "role": "user",
                "content": (
                    f"Research question: {query}\n\n"
                    f"Relevant knowledge base context:\n{context_text}\n\n"
                    f"Provide a concise, evidence-based answer to the research question. "
                    f"{sse_grounding} "
                    f"If the context is insufficient, clearly state what is known "
                    f"and what knowledge gaps remain rather than guessing."
                ),
            })
            system_prompt = specialist_prompt if specialist_prompt else None

            answer_chunks: list[str] = []
            async for chunk, meta in llm.complete_stream(
                messages=answer_messages,
                model_tier="sonnet",
                max_tokens=2048,
                system=system_prompt,
            ):
                if meta is None:
                    answer_chunks.append(chunk)
                    yield _sse_event("token", {"text": chunk})
                else:
                    total_cost += meta.cost
                    total_tokens += meta.input_tokens + meta.output_tokens
                    if meta.model_version:
                        model_versions.append(meta.model_version)

            duration_ms = int((time.time() - start) * 1000)

            # Save conversation turn
            full_answer = "".join(answer_chunks) or None
            ungrounded_citations: list[str] = []
            if full_answer:
                full_answer, ungrounded_citations = _validate_answer_citations(full_answer, sources)
            result_conv_id = _save_conversation_turn(
                conversation_id=conversation_id,
                query=query,
                classification_type=classification_type,
                routed_agent=routed_agent,
                answer=full_answer,
                sources=sources,
                cost=total_cost,
                duration_ms=duration_ms,
            )

            yield _sse_event("done", {
                "classification_type": classification_type,
                "target_agent": resolved_target,
                "workflow_type": None,
                "routed_agent": routed_agent,
                "conversation_id": result_conv_id,
                "answer": full_answer,
                "total_cost": total_cost,
                "total_tokens": total_tokens,
                "model_versions": model_versions,
                "duration_ms": duration_ms,
                "sources": sources,
                "ungrounded_citations": ungrounded_citations,
            })

        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error("Stream error: %s", e)
            yield _sse_event("error", {"detail": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
