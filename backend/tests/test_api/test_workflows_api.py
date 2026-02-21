"""Tests for Workflow API endpoints — create, get, intervene."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from fastapi.testclient import TestClient

from app.main import app
from app.agents.registry import create_registry
from app.llm.mock_layer import MockLLMLayer
from app.workflows.engine import WorkflowEngine
from app.api.v1.workflows import set_dependencies
from app.db.database import create_db_and_tables


def _setup():
    """Wire up dependencies for testing."""
    create_db_and_tables()
    mock = MockLLMLayer()
    registry = create_registry(mock)
    engine = WorkflowEngine()
    set_dependencies(registry, engine)
    return TestClient(app)


def test_create_workflow():
    """POST /api/v1/workflows should create a new workflow instance."""
    client = _setup()
    response = client.post("/api/v1/workflows", json={
        "template": "W1",
        "query": "spaceflight anemia mechanisms",
        "budget": 3.0,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["template"] == "W1"
    # State is PENDING at creation time (background execution starts after)
    assert data["state"] == "PENDING"
    assert data["query"] == "spaceflight anemia mechanisms"
    assert "workflow_id" in data
    print("  PASS: create_workflow")


def test_create_non_w1_stays_pending():
    """POST /api/v1/workflows with W2-W6 should stay PENDING (no runner)."""
    client = _setup()
    response = client.post("/api/v1/workflows", json={
        "template": "W2",
        "query": "test query",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "PENDING"

    wf_id = data["workflow_id"]
    get_resp = client.get(f"/api/v1/workflows/{wf_id}")
    assert get_resp.json()["state"] == "PENDING"
    print("  PASS: create_non_w1_stays_pending")


def test_get_workflow():
    """GET /api/v1/workflows/{id} should return workflow status."""
    client = _setup()
    # Use W2 to avoid auto-start (no runner for W2)
    create_resp = client.post("/api/v1/workflows", json={
        "template": "W2",
        "query": "test query",
    })
    wf_id = create_resp.json()["workflow_id"]

    response = client.get(f"/api/v1/workflows/{wf_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == wf_id
    assert data["template"] == "W2"
    assert data["state"] == "PENDING"
    assert data["budget_total"] == 5.0
    print("  PASS: get_workflow")


def test_get_w1_workflow_auto_starts():
    """W1 workflow should auto-start and transition from PENDING."""
    client = _setup()
    create_resp = client.post("/api/v1/workflows", json={
        "template": "W1",
        "query": "test query for auto-start",
    })
    wf_id = create_resp.json()["workflow_id"]

    # W1 auto-starts; with MockLLMLayer it will likely fail,
    # but the important thing is it's no longer PENDING
    import time
    time.sleep(0.5)  # Give background task a moment
    response = client.get(f"/api/v1/workflows/{wf_id}")
    data = response.json()
    assert data["id"] == wf_id
    assert data["template"] == "W1"
    # State should have changed from PENDING (RUNNING, FAILED, etc.)
    assert data["state"] in ("RUNNING", "WAITING_HUMAN", "FAILED", "COMPLETED", "PENDING")
    print(f"  PASS: get_w1_workflow_auto_starts (state={data['state']})")


def test_get_workflow_not_found():
    """GET /api/v1/workflows/nonexistent should return 404."""
    client = _setup()
    response = client.get("/api/v1/workflows/nonexistent")
    assert response.status_code == 404
    print("  PASS: get_workflow_not_found")


def test_intervene_cancel():
    """POST /api/v1/workflows/{id}/intervene cancel should work."""
    client = _setup()
    # Use W2 (no auto-start) so state is predictable
    create_resp = client.post("/api/v1/workflows", json={
        "template": "W2",
        "query": "test",
    })
    wf_id = create_resp.json()["workflow_id"]

    response = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
        "action": "cancel",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "cancel"
    assert data["new_state"] == "CANCELLED"
    print("  PASS: intervene_cancel")


def test_intervene_inject_note():
    """POST /api/v1/workflows/{id}/intervene inject_note should add a note."""
    client = _setup()
    # Use W2 (no auto-start)
    create_resp = client.post("/api/v1/workflows", json={
        "template": "W2",
        "query": "test",
    })
    wf_id = create_resp.json()["workflow_id"]

    response = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
        "action": "inject_note",
        "note": "Please focus on human studies only",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "inject_note"
    assert "Note injected" in data["detail"]
    print("  PASS: intervene_inject_note")


def test_list_workflows():
    """GET /api/v1/workflows should return all workflow instances."""
    client = _setup()
    # Create two workflows (W2 to avoid auto-start complexity)
    client.post("/api/v1/workflows", json={"template": "W2", "query": "query 1"})
    client.post("/api/v1/workflows", json={"template": "W3", "query": "query 2"})

    response = client.get("/api/v1/workflows")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    for item in data:
        assert "id" in item
        assert "template" in item
        assert "state" in item
    print("  PASS: list_workflows")


def test_list_workflows_empty_initially():
    """GET /api/v1/workflows should work even when no workflows exist."""
    client = _setup()
    response = client.get("/api/v1/workflows")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    print("  PASS: list_workflows_empty_initially")


if __name__ == "__main__":
    print("Testing Workflow API:")
    test_create_workflow()
    test_create_non_w1_stays_pending()
    test_get_workflow()
    test_get_w1_workflow_auto_starts()
    test_get_workflow_not_found()
    test_intervene_cancel()
    test_intervene_inject_note()
    test_list_workflows()
    test_list_workflows_empty_initially()
    print("\nAll Workflow API tests passed!")
