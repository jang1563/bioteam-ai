"""Tests for Cold Start API endpoints.

Tests the orchestration endpoints: /run, /quick, /status.
Uses MockLLMLayer — no real API calls.
"""

import os
import sys
import asyncio
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry
from app.agents.research_director import ResearchDirectorAgent, QueryClassification
from app.agents.knowledge_manager import KnowledgeManagerAgent
from app.agents.project_manager import ProjectManagerAgent
from app.api.v1.cold_start import (
    router, set_dependencies, ColdStartResponse, ColdStartStatus,
)
from app.llm.mock_layer import MockLLMLayer
from app.memory.semantic import SemanticMemory


def _make_test_deps():
    """Create test dependencies with mock LLM."""
    classification = QueryClassification(
        type="simple_query",
        reasoning="test",
        target_agent="t02_transcriptomics",
    )
    mock = MockLLMLayer({"sonnet:QueryClassification": classification})

    tmpdir = tempfile.mkdtemp()
    memory = SemanticMemory(persist_dir=tmpdir)

    rd_spec = BaseAgent.load_spec("research_director")
    rd = ResearchDirectorAgent(spec=rd_spec, llm=mock)

    km_spec = BaseAgent.load_spec("knowledge_manager")
    km = KnowledgeManagerAgent(spec=km_spec, llm=mock, memory=memory)

    pm_spec = BaseAgent.load_spec("project_manager")
    pm = ProjectManagerAgent(spec=pm_spec, llm=mock)

    registry = AgentRegistry()
    registry.register(rd)
    registry.register(km)
    registry.register(pm)

    return registry, memory


def _make_app(registry, memory):
    """Create a test FastAPI app with cold start router."""
    set_dependencies(registry, memory)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_status_uninitialized():
    """Status should return is_initialized=False when deps not set."""
    set_dependencies(None, None)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/api/v1/cold-start/status")
    assert response.status_code == 200
    data = response.json()
    assert data["is_initialized"] is False
    print("  PASS: Status uninitialized")


def test_status_initialized():
    """Status should reflect registered agents and collections."""
    registry, memory = _make_test_deps()
    client = _make_app(registry, memory)

    response = client.get("/api/v1/cold-start/status")
    assert response.status_code == 200
    data = response.json()
    assert data["is_initialized"] is True
    assert data["agents_registered"] >= 2
    assert data["critical_agents_healthy"] is True
    assert isinstance(data["collection_counts"], dict)
    print(f"  PASS: Status initialized (agents: {data['agents_registered']})")


def test_quick_start():
    """Quick start should run smoke test only (no seeding)."""
    registry, memory = _make_test_deps()
    client = _make_app(registry, memory)

    response = client.post("/api/v1/cold-start/quick")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "quick"
    assert data["success"] is True
    assert len(data["smoke_checks"]) > 0
    assert len(data["seed_results"]) == 0
    assert data["duration_ms"] > 0
    print(f"  PASS: Quick start ({data['duration_ms']}ms, {len(data['smoke_checks'])} checks)")


def test_quick_start_without_registry():
    """Quick start should 503 without registry."""
    set_dependencies(None, None)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post("/api/v1/cold-start/quick")
    assert response.status_code == 503
    print("  PASS: Quick start 503 without registry")


def test_full_cold_start_without_registry():
    """Full cold start should 503 without registry."""
    set_dependencies(None, None)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/v1/cold-start/run",
        json={"seed_queries": ["test"], "run_smoke_test": False},
    )
    assert response.status_code == 503
    print("  PASS: Full cold start 503 without registry")


def test_full_cold_start_with_no_seeding():
    """Full cold start with empty queries should still succeed."""
    registry, memory = _make_test_deps()
    client = _make_app(registry, memory)

    response = client.post(
        "/api/v1/cold-start/run",
        json={"seed_queries": [], "run_smoke_test": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "full"
    assert data["total_papers_stored"] == 0
    assert len(data["smoke_checks"]) > 0
    print(f"  PASS: Full cold start with no seeding ({data['duration_ms']}ms)")


def test_cold_start_response_model():
    """ColdStartResponse should be valid Pydantic model."""
    resp = ColdStartResponse(
        mode="full",
        success=True,
        total_papers_stored=42,
        duration_ms=1000,
        message="Test",
    )
    assert resp.mode == "full"
    assert resp.success is True
    assert resp.total_papers_stored == 42
    print("  PASS: ColdStartResponse model")


def test_cold_start_status_model():
    """ColdStartStatus should be valid Pydantic model."""
    status = ColdStartStatus(
        is_initialized=True,
        agents_registered=5,
        critical_agents_healthy=True,
        total_documents=100,
        has_literature=True,
    )
    assert status.is_initialized is True
    assert status.total_documents == 100
    print("  PASS: ColdStartStatus model")


def test_request_validation():
    """Invalid request parameters should be rejected."""
    registry, memory = _make_test_deps()
    client = _make_app(registry, memory)

    # pubmed_max_results too high
    response = client.post(
        "/api/v1/cold-start/run",
        json={"pubmed_max_results": 999},
    )
    assert response.status_code == 422
    print("  PASS: Request validation (max_results > 200)")


if __name__ == "__main__":
    print("Testing Cold Start API:")
    test_status_uninitialized()
    test_status_initialized()
    test_quick_start()
    test_quick_start_without_registry()
    test_full_cold_start_without_registry()
    test_full_cold_start_with_no_seeding()
    test_cold_start_response_model()
    test_cold_start_status_model()
    test_request_validation()
    print("\nAll Cold Start API tests passed!")
