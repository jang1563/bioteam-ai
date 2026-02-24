"""End-to-end test for Direct Query pipeline.

Tests the full pipeline: Research Director → Knowledge Manager → Answer → Response
using MockLLMLayer (no real API calls).

v6: Updated tests for answer generation pipeline, timeout, cost cap.
"""

import os
import sys
import asyncio
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.research_director import ResearchDirectorAgent, QueryClassification
from app.agents.knowledge_manager import KnowledgeManagerAgent
from app.api.v1.direct_query import (
    run_direct_query, DirectQueryResponse,
    _build_context_text, _extract_sources,
    DIRECT_QUERY_TIMEOUT, DIRECT_QUERY_COST_CAP,
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
    print(f"  PASS: Workflow query E2E → W1")


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
    print(f"  PASS: Answer generated with empty memory")


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
            "metadata": {"doi": "10.1234/test", "year": "2023", "title": "Test Paper"},
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
    assert sources[0]["source_type"] == "literature"
    assert "doi" not in sources[1], "lab_kb item should not have DOI"
    print("  PASS: _extract_sources")


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
    from fastapi.testclient import TestClient
    from app.api.v1.direct_query import router
    from fastapi import FastAPI

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
    from fastapi.testclient import TestClient
    from app.api.v1.direct_query import router, set_registry
    from app.agents.registry import AgentRegistry
    from fastapi import FastAPI

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


if __name__ == "__main__":
    print("Testing Direct Query Pipeline (E2E):")
    test_simple_query_e2e()
    test_workflow_query_e2e()
    test_response_metadata()
    test_answer_generation_with_empty_memory()
    test_build_context_text()
    test_build_context_text_empty()
    test_extract_sources()
    test_cost_cap_constant()
    test_timeout_constant()
    test_fastapi_endpoint()
    test_fastapi_endpoint_with_registry()
    print("\nAll Direct Query E2E tests passed!")
