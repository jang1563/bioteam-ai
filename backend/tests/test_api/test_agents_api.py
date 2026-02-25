"""Tests for Agent API endpoints — GET /agents, GET /agents/{id}."""

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


def test_list_agents():
    """GET /api/v1/agents should return all registered agents."""
    client = _setup()
    response = client.get("/api/v1/agents")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 7
    ids = [a["id"] for a in data]
    assert "research_director" in ids
    assert "knowledge_manager" in ids
    assert "project_manager" in ids
    assert "ambiguity_engine" in ids
    assert "digest_agent" in ids
    assert "t02_transcriptomics" in ids
    assert "t10_data_eng" in ids
    # Check structure
    for agent in data:
        assert "id" in agent
        assert "name" in agent
        assert "tier" in agent
        assert "model_tier" in agent
        assert "state" in agent
    print("  PASS: list_agents")


def test_get_agent_exists():
    """GET /api/v1/agents/research_director should return full detail."""
    client = _setup()
    response = client.get("/api/v1/agents/research_director")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "research_director"
    assert data["name"] == "Research Director"
    assert data["tier"] == "strategic"
    assert data["model_tier"] == "sonnet"
    assert data["model_tier_secondary"] == "opus"
    assert data["criticality"] == "critical"
    assert data["state"] == "idle"
    assert isinstance(data["tools"], list)
    print("  PASS: get_agent_exists")


def test_get_agent_not_found():
    """GET /api/v1/agents/nonexistent should return 404."""
    client = _setup()
    response = client.get("/api/v1/agents/nonexistent")
    assert response.status_code == 404
    print("  PASS: get_agent_not_found")


def test_agent_fields():
    """T02 agent detail should have correct specialist fields."""
    client = _setup()
    response = client.get("/api/v1/agents/t02_transcriptomics")
    assert response.status_code == 200
    data = response.json()
    assert data["tier"] == "domain_expert"
    assert data["model_tier"] == "sonnet"
    assert data["criticality"] == "optional"
    assert data["division"] == "wet_to_dry"
    print("  PASS: agent_fields")


if __name__ == "__main__":
    print("Testing Agent API:")
    test_list_agents()
    test_get_agent_exists()
    test_get_agent_not_found()
    test_agent_fields()
    print("\nAll Agent API tests passed!")
