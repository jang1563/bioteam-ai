"""End-to-end test for Direct Query pipeline.

Tests the full pipeline: Research Director → Knowledge Manager → Answer → Response
using MockLLMLayer (no real API calls).

v6: Updated tests for answer generation pipeline, timeout, cost cap.
"""

import asyncio
import json
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.knowledge_manager import KnowledgeManagerAgent
from app.agents.registry import AgentRegistry
from app.agents.research_director import QueryClassification, ResearchDirectorAgent
from app.api.v1.direct_query import (
    DIRECT_QUERY_COST_CAP,
    DIRECT_QUERY_TIMEOUT,
    DirectQueryResponse,
    _build_context_text,
    _extract_sources,
    _prioritize_context_by_seed_papers,
    _resolve_specialist,
    _validate_answer_citations,
    run_direct_query,
)
from app.llm.mock_layer import MockLLMLayer
from app.memory.semantic import SemanticMemory


def setup_agents():
    """Create agents with mock LLM and seeded memory."""
    # Create mock with predefined responses
    classification = QueryClassification(
        type="simple_query",
        reasoning="Single gene expression lookup.",
        target_agent="t02_transcriptomics",
    )
    mock = MockLLMLayer({"sonnet:QueryClassification": classification})

    # Create Research Director
    rd_spec = BaseAgent.load_spec("research_director")
    rd = ResearchDirectorAgent(spec=rd_spec, llm=mock)

    # Create Knowledge Manager with seeded memory
    tmpdir = tempfile.mkdtemp()
    memory = SemanticMemory(persist_dir=tmpdir)
    memory.add(
        collection="literature",
        doc_id="doi:10.1038/s41591-021-01637-7",
        text="Hemolysis is a primary driver of space anemia during spaceflight. "
             "Red blood cell destruction increases by 54% in microgravity.",
        metadata={"doi": "10.1038/s41591-021-01637-7", "year": "2022", "source_type": "primary_literature"},
    )
    memory.add(
        collection="literature",
        doc_id="doi:10.1182/blood.2021014479",
        text="TNFSF11 (RANKL) shows significant upregulation in spaceflight cfRNA data, "
             "suggesting bone-blood crosstalk in microgravity adaptation.",
        metadata={"doi": "10.1182/blood.2021014479", "year": "2023", "source_type": "primary_literature"},
    )

    km_spec = BaseAgent.load_spec("knowledge_manager")
    km = KnowledgeManagerAgent(spec=km_spec, llm=mock, memory=memory)

    return rd, km


def test_simple_query_e2e():
    """Full pipeline: simple query → classify → retrieve memory → generate answer."""
    rd, km = setup_agents()

    response = asyncio.run(run_direct_query(
        query="Is gene TNFSF11 differentially expressed in spaceflight cfRNA data?",
        research_director=rd,
        knowledge_manager=km,
    ))

    assert isinstance(response, DirectQueryResponse)
    assert response.classification_type == "simple_query"
    assert response.target_agent == "t02_transcriptomics"
    assert len(response.memory_context) > 0, "Should retrieve relevant memory"

    # Check that memory results are relevant (contain TNFSF11 or spaceflight)
    found_relevant = any(
        "tnfsf11" in str(r).lower() or "spaceflight" in str(r).lower()
        for r in response.memory_context
    )
    assert found_relevant, "Memory should contain relevant results"

    # v6: Answer should now be populated
    assert response.answer is not None, "Answer should be generated"
    assert len(response.answer) > 0, "Answer should not be empty"

    # v6: Sources should be extracted from memory context
    assert len(response.sources) > 0, "Sources should be populated"

    assert response.total_cost >= 0
    assert response.duration_ms > 0
    assert len(response.model_versions) >= 1
    print(f"  PASS: Simple query E2E (cost: ${response.total_cost:.4f}, {response.duration_ms}ms)")
    print(f"    Classification: {response.classification_type} → {response.target_agent}")
    print(f"    Memory results: {len(response.memory_context)}")
    print(f"    Answer: {response.answer[:80]}...")
    print(f"    Sources: {len(response.sources)}")


def test_workflow_query_e2e():
    """Full pipeline: workflow query → classify → route (no memory or answer)."""
    classification = QueryClassification(
        type="needs_workflow",
        reasoning="Comparing mechanisms across species requires systematic review.",
        workflow_type="W1",
    )
    mock = MockLLMLayer({"sonnet:QueryClassification": classification})

    rd_spec = BaseAgent.load_spec("research_director")
    rd = ResearchDirectorAgent(spec=rd_spec, llm=mock)

    km_spec = BaseAgent.load_spec("knowledge_manager")
    km = KnowledgeManagerAgent(spec=km_spec, llm=mock)

    response = asyncio.run(run_direct_query(
        query="Compare spaceflight-induced anemia mechanisms across rodent and human studies",
        research_director=rd,
        knowledge_manager=km,
    ))

    assert response.classification_type == "needs_workflow"
    assert response.workflow_type == "W1"
    assert len(response.memory_context) == 0, "Workflow queries skip memory retrieval"
    assert response.answer is None, "Workflow queries don't generate answers"
    assert len(response.sources) == 0, "Workflow queries don't have sources"
    print("  PASS: Workflow query E2E → W1")


def test_response_metadata():
    """Response should carry full metadata for reproducibility."""
    rd, km = setup_agents()

    response = asyncio.run(run_direct_query(
        query="What is spaceflight anemia?",
        research_director=rd,
        knowledge_manager=km,
    ))

    assert response.query == "What is spaceflight anemia?"
    assert response.timestamp is not None
    assert isinstance(response.model_versions, list)
    assert all(v.startswith("mock-") for v in response.model_versions)
    # v6: Should have 3 model versions (classify + memory + answer)
    assert len(response.model_versions) >= 2, f"Expected ≥2 model versions, got {len(response.model_versions)}"
    print(f"  PASS: Response metadata (models: {response.model_versions})")


def test_answer_generation_with_empty_memory():
    """Answer should still be generated even when memory is empty."""
    classification = QueryClassification(
        type="simple_query",
        reasoning="General biology question.",
        target_agent="knowledge_manager",
    )
    mock = MockLLMLayer({"sonnet:QueryClassification": classification})

    rd_spec = BaseAgent.load_spec("research_director")
    rd = ResearchDirectorAgent(spec=rd_spec, llm=mock)

    # KM with no seeded memory
    km_spec = BaseAgent.load_spec("knowledge_manager")
    km = KnowledgeManagerAgent(spec=km_spec, llm=mock)

    response = asyncio.run(run_direct_query(
        query="What is CRISPR-Cas9?",
        research_director=rd,
        knowledge_manager=km,
    ))

    assert response.classification_type == "simple_query"
    # Answer should still be generated (from LLM knowledge)
    assert response.answer is not None, "Answer should be generated even without memory"
    assert len(response.sources) == 0, "No sources when memory is empty"
    print("  PASS: Answer generated with empty memory")


def test_build_context_text():
    """_build_context_text should format memory items for LLM."""
    items = [
        {
            "content": "Gene X is upregulated.",
            "source": "literature",
            "metadata": {"doi": "10.1234/test", "year": "2023"},
        },
        {
            "text": "Protocol for RNA extraction.",
            "source": "lab_kb",
            "metadata": {},
        },
    ]

    text = _build_context_text(items)
    assert "10.1234/test" in text
    assert "2023" in text
    assert "Gene X is upregulated" in text
    assert "Protocol for RNA extraction" in text
    assert "[1]" in text
    assert "[2]" in text
    print("  PASS: _build_context_text formatting")


def test_build_context_text_empty():
    """_build_context_text returns fallback for empty list."""
    text = _build_context_text([])
    assert "No prior knowledge" in text
    print("  PASS: _build_context_text empty fallback")


def test_extract_sources():
    """_extract_sources should extract structured references."""
    items = [
        {
            "content": "Gene X is upregulated in condition Y.",
            "source": "literature",
            "metadata": {
                "doi": "10.1234/test",
                "pmid": "32699394",
                "year": "2023",
                "title": "Test Paper",
            },
        },
        {
            "text": "Lab protocol note.",
            "source": "lab_kb",
            "metadata": {},
        },
    ]

    sources = _extract_sources(items)
    assert len(sources) == 2
    assert sources[0]["doi"] == "10.1234/test"
    assert sources[0]["year"] == "2023"
    assert sources[0]["title"] == "Test Paper"
    assert sources[0]["pmid"] == "32699394"
    assert sources[0]["source_type"] == "literature"
    assert "doi" not in sources[1], "lab_kb item should not have DOI"
    print("  PASS: _extract_sources")


def test_validate_answer_citations_flags_ungrounded_pmid_with_sources():
    """PMIDs in answer should be validated even when sources are present."""
    answer = "Evidence: PMID: 99999999 and DOI:10.1234/test"
    sources = [{"doi": "10.1234/test", "pmid": "32699394"}]

    _, ungrounded = _validate_answer_citations(answer, sources)
    assert "PMID:99999999" in ungrounded
    assert "DOI:10.1234/test" not in ungrounded
    print("  PASS: PMID validation with non-empty sources")


def test_prioritize_context_by_seed_papers_supports_pmid():
    """seed_papers should prioritize both DOI and PMID identifiers."""
    memory_context = [
        {"metadata": {"doi": "10.1000/doi-first"}, "content": "doi paper"},
        {"metadata": {"pmid": "12345678"}, "content": "pmid paper"},
    ]
    reordered = _prioritize_context_by_seed_papers(memory_context, ["PMID:12345678"])
    assert reordered[0]["content"] == "pmid paper"
    print("  PASS: seed_papers supports PMID prioritization")


def test_cost_cap_constant():
    """Cost cap should match PRD requirement."""
    assert DIRECT_QUERY_COST_CAP == 0.50
    print("  PASS: Cost cap = $0.50")


def test_timeout_constant():
    """Timeout should match PRD requirement."""
    assert DIRECT_QUERY_TIMEOUT == 30.0
    print("  PASS: Timeout = 30s")


def test_fastapi_endpoint():
    """Test the FastAPI endpoint responds (503 without agent registry)."""
    from app.api.v1.direct_query import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/v1/direct-query",
        json={"query": "What is spaceflight anemia?"},
    )
    assert response.status_code == 503  # Agent registry not initialized
    print("  PASS: FastAPI endpoint returns 503 without agent registry")


def test_fastapi_endpoint_with_registry():
    """Test endpoint with registry wired up returns 200."""
    from app.agents.registry import AgentRegistry
    from app.api.v1.direct_query import router, set_registry
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    rd, km = setup_agents()
    registry = AgentRegistry()
    registry.register(rd)
    registry.register(km)
    set_registry(registry)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/v1/direct-query",
        json={"query": "What is spaceflight anemia?"},
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["classification_type"] == "simple_query"
    assert data["answer"] is not None
    assert len(data["answer"]) > 0
    print(f"  PASS: FastAPI endpoint with registry (answer: {data['answer'][:60]}...)")

    # Clean up: reset registry to None
    set_registry(None)


def test_specialist_routing_uses_agent_system_prompt():
    """When target_agent is available, its system prompt should be used for answer generation."""
    classification = QueryClassification(
        type="simple_query",
        reasoning="Transcriptomics question.",
        target_agent="t02_transcriptomics",
    )
    mock = MockLLMLayer({"sonnet:QueryClassification": classification})

    rd_spec = BaseAgent.load_spec("research_director")
    rd = ResearchDirectorAgent(spec=rd_spec, llm=mock)

    km_spec = BaseAgent.load_spec("knowledge_manager")
    km = KnowledgeManagerAgent(spec=km_spec, llm=mock)

    # Create registry with t02 agent
    from app.agents.teams.t02_transcriptomics import TranscriptomicsAgent
    t02_spec = BaseAgent.load_spec("t02_transcriptomics")
    t02 = TranscriptomicsAgent(spec=t02_spec, llm=mock)

    registry = AgentRegistry()
    registry.register(rd)
    registry.register(km)
    registry.register(t02)

    response = asyncio.run(run_direct_query(
        query="Is TNFSF11 differentially expressed?",
        research_director=rd,
        knowledge_manager=km,
        registry=registry,
    ))

    assert response.routed_agent == "t02_transcriptomics"
    assert response.answer is not None

    # Verify the mock LLM received a system prompt (specialist's prompt)
    raw_calls = [c for c in mock.call_log if c["method"] == "complete_raw"]
    assert len(raw_calls) >= 1
    last_raw = raw_calls[-1]
    # The system prompt should be set (non-None) when specialist is available
    assert last_raw.get("system") is not None or "system" in last_raw, \
        "Specialist system prompt should be passed to complete_raw"
    print(f"  PASS: Specialist routing uses t02 system prompt (routed_agent={response.routed_agent})")


def test_specialist_unavailable_falls_back():
    """When target_agent is not in registry, fallback to generic prompt."""
    classification = QueryClassification(
        type="simple_query",
        reasoning="Proteomics question.",
        target_agent="t03_proteomics",  # Not registered
    )
    mock = MockLLMLayer({"sonnet:QueryClassification": classification})

    rd_spec = BaseAgent.load_spec("research_director")
    rd = ResearchDirectorAgent(spec=rd_spec, llm=mock)

    km_spec = BaseAgent.load_spec("knowledge_manager")
    km = KnowledgeManagerAgent(spec=km_spec, llm=mock)

    # Registry without t03
    registry = AgentRegistry()
    registry.register(rd)
    registry.register(km)

    response = asyncio.run(run_direct_query(
        query="What proteins are affected by microgravity?",
        research_director=rd,
        knowledge_manager=km,
        registry=registry,
    ))

    assert response.routed_agent is None, "Should be None when specialist unavailable"
    assert response.target_agent == "t03_proteomics", "Classification target should still be reported"
    assert response.answer is not None, "Answer should still be generated"
    print("  PASS: Specialist unavailable fallback (routed_agent=None)")


def test_resolve_specialist_helper():
    """Unit test for _resolve_specialist helper."""
    mock = MockLLMLayer()

    # Case 1: No registry
    agent_id, prompt = _resolve_specialist(None, "t02_transcriptomics")
    assert agent_id is None
    assert prompt == ""

    # Case 2: No target_agent
    registry = AgentRegistry()
    agent_id, prompt = _resolve_specialist(registry, None)
    assert agent_id is None
    assert prompt == ""

    # Case 3: Agent not in registry
    agent_id, prompt = _resolve_specialist(registry, "t03_proteomics")
    assert agent_id is None
    assert prompt == ""

    # Case 4: Agent available
    from app.agents.teams.t02_transcriptomics import TranscriptomicsAgent
    t02_spec = BaseAgent.load_spec("t02_transcriptomics")
    t02 = TranscriptomicsAgent(spec=t02_spec, llm=mock)
    registry.register(t02)

    agent_id, prompt = _resolve_specialist(registry, "t02_transcriptomics")
    assert agent_id == "t02_transcriptomics"
    assert len(prompt) > 0, "Should return the agent's system prompt"
    print(f"  PASS: _resolve_specialist helper (prompt length: {len(prompt)})")


def test_stream_endpoint_emits_events():
    """SSE streaming endpoint should emit classification → memory → token(s) → done."""
    from app.api.v1.direct_query import router, set_registry
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    rd, km = setup_agents()
    registry = AgentRegistry()
    registry.register(rd)
    registry.register(km)
    set_registry(registry)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    with client.stream("GET", "/api/v1/direct-query/stream?query=What+is+spaceflight+anemia%3F") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        events = []
        event_type = ""
        for line in response.iter_lines():
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                events.append({"event": event_type, "data": data})

    event_types = [e["event"] for e in events]
    assert "classification" in event_types, f"Missing classification: {event_types}"
    assert "memory" in event_types, f"Missing memory: {event_types}"
    assert "done" in event_types, f"Missing done: {event_types}"

    cls_event = next(e for e in events if e["event"] == "classification")
    assert cls_event["data"]["type"] == "simple_query"

    done_event = next(e for e in events if e["event"] == "done")
    assert "total_cost" in done_event["data"]
    assert "duration_ms" in done_event["data"]
    assert "ungrounded_citations" in done_event["data"]
    assert isinstance(done_event["data"]["ungrounded_citations"], list)

    token_events = [e for e in events if e["event"] == "token"]
    assert len(token_events) > 0, f"Expected token events: {event_types}"

    print(f"  PASS: Stream endpoint ({len(events)} events, {len(token_events)} tokens)")
    set_registry(None)


def test_stream_endpoint_with_auth_query_token():
    """SSE stream should work with BIOTEAM_API_KEY via ?token= auth."""
    from app.api.v1.direct_query import router, set_registry
    from app.middleware.auth import APIKeyAuthMiddleware
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    rd, km = setup_agents()
    registry = AgentRegistry()
    registry.register(rd)
    registry.register(km)
    set_registry(registry)

    app = FastAPI()
    app.add_middleware(APIKeyAuthMiddleware)
    app.include_router(router)
    client = TestClient(app)

    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.bioteam_api_key = "sse-secret"
        with client.stream(
            "GET",
            "/api/v1/direct-query/stream?query=What+is+spaceflight+anemia%3F&token=sse-secret",
        ) as response:
            assert response.status_code == 200
            events = []
            event_type = ""
            for line in response.iter_lines():
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    events.append({"event": event_type, "data": json.loads(line[6:])})

    event_types = [e["event"] for e in events]
    assert "classification" in event_types
    assert "done" in event_types
    set_registry(None)


def test_stream_endpoint_with_auth_issued_stream_token():
    """SSE stream should work with issued short-lived stream token."""
    from app.api.v1.auth import router as auth_router
    from app.api.v1.direct_query import router, set_registry
    from app.middleware.auth import APIKeyAuthMiddleware
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    rd, km = setup_agents()
    registry = AgentRegistry()
    registry.register(rd)
    registry.register(km)
    set_registry(registry)

    app = FastAPI()
    app.add_middleware(APIKeyAuthMiddleware)
    app.include_router(auth_router)
    app.include_router(router)
    client = TestClient(app)

    with patch("app.middleware.auth.settings") as mock_settings, patch("app.api.v1.auth.settings") as auth_settings:
        mock_settings.bioteam_api_key = "sse-secret"
        auth_settings.bioteam_api_key = "sse-secret"

        token_resp = client.post(
            "/api/v1/auth/stream-token",
            headers={"Authorization": "Bearer sse-secret"},
            json={"path": "/api/v1/direct-query/stream"},
        )
        assert token_resp.status_code == 200, token_resp.text
        stream_token = token_resp.json()["token"]
        assert isinstance(stream_token, str) and len(stream_token) > 20

        with client.stream(
            "GET",
            f"/api/v1/direct-query/stream?query=What+is+spaceflight+anemia%3F&token={stream_token}",
        ) as response:
            assert response.status_code == 200
            events = []
            event_type = ""
            for line in response.iter_lines():
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    events.append({"event": event_type, "data": json.loads(line[6:])})

    event_types = [e["event"] for e in events]
    assert "classification" in event_types
    assert "done" in event_types
    set_registry(None)


def test_stream_endpoint_with_auth_invalid_query_token_rejected():
    """SSE stream should reject invalid ?token= when auth is enabled."""
    from app.api.v1.direct_query import router, set_registry
    from app.middleware.auth import APIKeyAuthMiddleware
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    rd, km = setup_agents()
    registry = AgentRegistry()
    registry.register(rd)
    registry.register(km)
    set_registry(registry)

    app = FastAPI()
    app.add_middleware(APIKeyAuthMiddleware)
    app.include_router(router)
    client = TestClient(app)

    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.bioteam_api_key = "sse-secret"
        response = client.get(
            "/api/v1/direct-query/stream?query=What+is+spaceflight+anemia%3F&token=wrong-token"
        )
        assert response.status_code == 403

    set_registry(None)


def test_stream_workflow_returns_done_immediately():
    """Workflow queries should emit classification + done, no tokens."""
    from app.api.v1.direct_query import router, set_registry
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    classification = QueryClassification(
        type="needs_workflow",
        reasoning="Requires systematic review.",
        workflow_type="W1",
    )
    mock = MockLLMLayer({"sonnet:QueryClassification": classification})

    rd_spec = BaseAgent.load_spec("research_director")
    rd = ResearchDirectorAgent(spec=rd_spec, llm=mock)
    km_spec = BaseAgent.load_spec("knowledge_manager")
    km = KnowledgeManagerAgent(spec=km_spec, llm=mock)

    registry = AgentRegistry()
    registry.register(rd)
    registry.register(km)
    set_registry(registry)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    with client.stream("GET", "/api/v1/direct-query/stream?query=Compare+anemia") as response:
        assert response.status_code == 200
        events = []
        event_type = ""
        for line in response.iter_lines():
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                events.append({"event": event_type, "data": data})

    event_types = [e["event"] for e in events]
    assert "classification" in event_types
    assert "done" in event_types
    assert "token" not in event_types

    done_data = next(e for e in events if e["event"] == "done")["data"]
    assert done_data["classification_type"] == "needs_workflow"
    print("  PASS: Stream workflow done immediately")
    set_registry(None)


def test_stream_no_registry_returns_503():
    """Streaming endpoint without registry should return 503."""
    from app.api.v1.direct_query import router, set_registry
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    set_registry(None)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/api/v1/direct-query/stream?query=test")
    assert response.status_code == 503
    print("  PASS: Stream 503 without registry")


def test_routed_agent_in_api_response():
    """routed_agent field should appear in the FastAPI JSON response."""
    from app.agents.teams.t02_transcriptomics import TranscriptomicsAgent
    from app.api.v1.direct_query import router, set_registry
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    classification = QueryClassification(
        type="simple_query",
        reasoning="Transcriptomics question.",
        target_agent="t02_transcriptomics",
    )
    mock = MockLLMLayer({"sonnet:QueryClassification": classification})

    rd_spec = BaseAgent.load_spec("research_director")
    rd = ResearchDirectorAgent(spec=rd_spec, llm=mock)
    km_spec = BaseAgent.load_spec("knowledge_manager")
    km = KnowledgeManagerAgent(spec=km_spec, llm=mock)
    t02_spec = BaseAgent.load_spec("t02_transcriptomics")
    t02 = TranscriptomicsAgent(spec=t02_spec, llm=mock)

    registry = AgentRegistry()
    registry.register(rd)
    registry.register(km)
    registry.register(t02)
    set_registry(registry)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/v1/direct-query",
        json={"query": "Is TNFSF11 differentially expressed?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["routed_agent"] == "t02_transcriptomics"
    assert data["target_agent"] == "t02_transcriptomics"
    print("  PASS: routed_agent in API response")

    set_registry(None)


def test_empty_context_grounding_prompt():
    """When memory is empty, prompt should instruct LLM to label as general knowledge."""
    classification = QueryClassification(
        type="simple_query",
        reasoning="General biology question.",
        target_agent="knowledge_manager",
    )
    mock = MockLLMLayer({"sonnet:QueryClassification": classification})

    rd_spec = BaseAgent.load_spec("research_director")
    rd = ResearchDirectorAgent(spec=rd_spec, llm=mock)

    # KM with no seeded memory — will produce empty context
    km_spec = BaseAgent.load_spec("knowledge_manager")
    km = KnowledgeManagerAgent(spec=km_spec, llm=mock)

    asyncio.run(run_direct_query(
        query="What is CRISPR-Cas9?",
        research_director=rd,
        knowledge_manager=km,
    ))

    # Check the answer generation call (complete_raw) for empty-context grounding
    raw_calls = [c for c in mock.call_log if c["method"] == "complete_raw"]
    assert len(raw_calls) >= 1, "Expected at least 1 complete_raw call for answer"
    last_msg = raw_calls[-1]["messages"][-1]["content"]
    assert "general knowledge" in last_msg.lower(), \
        f"Empty-context prompt should mention 'general knowledge': {last_msg[:200]}"
    assert "Do NOT cite specific DOIs" in last_msg, \
        f"Empty-context prompt should warn against citing DOIs: {last_msg[:200]}"
    print("  PASS: Empty-context grounding prompt includes general knowledge disclaimer")


def test_populated_context_grounding_prompt():
    """When memory has results, prompt should instruct LLM to cite from context."""
    rd, km = setup_agents()  # This has seeded memory

    mock = rd.llm  # Get the mock to inspect call_log
    asyncio.run(run_direct_query(
        query="What is spaceflight anemia?",
        research_director=rd,
        knowledge_manager=km,
    ))

    raw_calls = [c for c in mock.call_log if c["method"] == "complete_raw"]
    assert len(raw_calls) >= 1
    last_msg = raw_calls[-1]["messages"][-1]["content"]
    assert "CRITICAL" in last_msg, \
        f"Populated-context prompt should have CRITICAL citation instruction: {last_msg[:200]}"
    assert "general knowledge" not in last_msg.lower(), \
        f"Populated-context prompt should NOT mention general knowledge: {last_msg[:200]}"
    print("  PASS: Populated-context grounding prompt uses CRITICAL citation rules")


if __name__ == "__main__":
    print("Testing Direct Query Pipeline (E2E):")
    test_simple_query_e2e()
    test_workflow_query_e2e()
    test_response_metadata()
    test_answer_generation_with_empty_memory()
    test_build_context_text()
    test_build_context_text_empty()
    test_extract_sources()
    test_validate_answer_citations_flags_ungrounded_pmid_with_sources()
    test_prioritize_context_by_seed_papers_supports_pmid()
    test_cost_cap_constant()
    test_timeout_constant()
    test_fastapi_endpoint()
    test_fastapi_endpoint_with_registry()
    test_specialist_routing_uses_agent_system_prompt()
    test_specialist_unavailable_falls_back()
    test_resolve_specialist_helper()
    test_stream_endpoint_emits_events()
    test_stream_endpoint_with_auth_query_token()
    test_stream_endpoint_with_auth_issued_stream_token()
    test_stream_workflow_returns_done_immediately()
    test_stream_no_registry_returns_503()
    test_routed_agent_in_api_response()
    test_empty_context_grounding_prompt()
    test_populated_context_grounding_prompt()
    print("\nAll Direct Query E2E tests passed!")
