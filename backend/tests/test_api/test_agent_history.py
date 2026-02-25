"""Tests for Agent History endpoint — GET /agents/{id}/history."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from datetime import datetime, timezone

from app.agents.registry import create_registry
from app.api.v1.agents import set_registry
from app.db.database import create_db_and_tables
from app.db.database import engine as db_engine
from app.llm.mock_layer import MockLLMLayer
from app.main import app
from app.models.cost import CostRecord
from app.models.workflow import StepCheckpoint
from fastapi.testclient import TestClient
from sqlmodel import Session


def _setup():
    """Wire up dependencies for testing."""
    create_db_and_tables()
    mock = MockLLMLayer()
    registry = create_registry(mock)
    set_registry(registry)
    return TestClient(app)


def test_history_empty():
    """GET /agents/{id}/history with no executions returns empty list."""
    client = _setup()
    response = client.get("/api/v1/agents/research_director/history")
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "research_director"
    assert isinstance(data["entries"], list)
    assert data["total_count"] >= 0
    print("  PASS: history_empty")


def test_history_with_checkpoints():
    """GET /agents/{id}/history returns entries from step checkpoints."""
    client = _setup()

    # Insert test checkpoint data
    with Session(db_engine) as session:
        cp = StepCheckpoint(
            workflow_id="wf-test-1",
            step_id="SEARCH",
            agent_id="research_director",
            status="completed",
            result={"summary": "Found 15 papers on spaceflight anemia"},
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        session.add(cp)
        session.commit()

    response = client.get("/api/v1/agents/research_director/history")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] >= 1
    # Find the entry we inserted
    found = any(
        e["workflow_id"] == "wf-test-1" and e["step_id"] == "SEARCH"
        for e in data["entries"]
    )
    assert found, "Expected checkpoint entry not found"
    print("  PASS: history_with_checkpoints")


def test_history_pagination():
    """GET /agents/{id}/history supports limit and offset pagination."""
    client = _setup()
    response = client.get("/api/v1/agents/research_director/history?limit=5&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["entries"]) <= 5
    print("  PASS: history_pagination")


def test_history_not_found():
    """GET /agents/nonexistent/history returns 404."""
    client = _setup()
    response = client.get("/api/v1/agents/nonexistent/history")
    assert response.status_code == 404
    print("  PASS: history_not_found")


if __name__ == "__main__":
    print("Testing Agent History API:")
    test_history_empty()
    test_history_with_checkpoints()
    test_history_pagination()
    test_history_not_found()
    print("\nAll Agent History tests passed!")
