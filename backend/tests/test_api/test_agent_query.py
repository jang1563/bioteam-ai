"""Tests for Agent Query endpoint — POST /agents/{id}/query."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.registry import create_registry
from app.api.v1.agents import set_registry
from app.llm.mock_layer import MockLLMLayer
from app.main import app
from fastapi.testclient import TestClient


def _setup():
    """Wire up a mock registry for testing."""
    mock = MockLLMLayer()
    registry = create_registry(mock)
    set_registry(registry)
    return TestClient(app)


def test_query_agent_success():
    """POST /agents/{id}/query should return an answer from the agent."""
    client = _setup()
    response = client.post("/api/v1/agents/research_director/query", json={
        "query": "What are the key mechanisms of spaceflight anemia?",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "research_director"
    assert isinstance(data["answer"], str)
    assert data["cost"] >= 0.0
    assert data["duration_ms"] >= 0
    print("  PASS: query_agent_success")


def test_query_agent_with_context():
    """POST /agents/{id}/query with optional context should succeed."""
    client = _setup()
    response = client.post("/api/v1/agents/knowledge_manager/query", json={
        "query": "Summarize prior findings on VEGF",
        "context": "Previous research showed VEGF increases during microgravity exposure.",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "knowledge_manager"
    print("  PASS: query_agent_with_context")


def test_query_agent_not_found():
    """POST /agents/nonexistent/query should return 404."""
    client = _setup()
    response = client.post("/api/v1/agents/nonexistent/query", json={
        "query": "test",
    })
    assert response.status_code == 404
    print("  PASS: query_agent_not_found")


def test_query_agent_empty_query():
    """POST /agents/{id}/query with empty query should return 422."""
    client = _setup()
    response = client.post("/api/v1/agents/research_director/query", json={
        "query": "",
    })
    assert response.status_code == 422
    print("  PASS: query_agent_empty_query")


def test_query_agent_too_long():
    """POST /agents/{id}/query with query exceeding max_length should return 422."""
    client = _setup()
    response = client.post("/api/v1/agents/research_director/query", json={
        "query": "x" * 5001,
    })
    assert response.status_code == 422
    print("  PASS: query_agent_too_long")


if __name__ == "__main__":
    print("Testing Agent Query API:")
    test_query_agent_success()
    test_query_agent_with_context()
    test_query_agent_not_found()
    test_query_agent_empty_query()
    test_query_agent_too_long()
    print("\nAll Agent Query tests passed!")
