"""Tests for input validation on API endpoints.

Uses a separate FastAPI app without rate limiting to test validation in isolation.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.registry import create_registry
from app.api.v1.direct_query import router as dq_router
from app.api.v1.direct_query import set_registry as set_dq_registry
from app.api.v1.workflows import router as wf_router
from app.api.v1.workflows import set_dependencies
from app.db.database import create_db_and_tables
from app.llm.mock_layer import MockLLMLayer
from app.workflows.engine import WorkflowEngine
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client():
    """Create a test app WITHOUT rate limiting middleware."""
    create_db_and_tables()

    # Build a minimal FastAPI with just the routers under test
    test_app = FastAPI()
    test_app.include_router(wf_router)
    test_app.include_router(dq_router)

    mock = MockLLMLayer()
    registry = create_registry(mock)
    engine = WorkflowEngine()
    set_dependencies(registry, engine)
    set_dq_registry(registry)

    return TestClient(test_app)


# === Workflow validation ===


def test_workflow_template_invalid():
    """Invalid template should be rejected."""
    client = _client()
    resp = client.post("/api/v1/workflows", json={
        "template": "INVALID",
        "query": "test",
    })
    assert resp.status_code == 422


def test_workflow_template_valid_w1_to_w6():
    """W1 through W6 should be accepted."""
    client = _client()
    for template in ["W1", "W2", "W3", "W4", "W5", "W6"]:
        resp = client.post("/api/v1/workflows", json={
            "template": template,
            "query": "test query",
        })
        assert resp.status_code == 200, f"Template {template} rejected"


def test_workflow_query_too_long():
    """Query longer than 2000 chars should be rejected."""
    client = _client()
    resp = client.post("/api/v1/workflows", json={
        "template": "W1",
        "query": "x" * 2001,
    })
    assert resp.status_code == 422


def test_workflow_query_empty():
    """Empty query should be rejected."""
    client = _client()
    resp = client.post("/api/v1/workflows", json={
        "template": "W1",
        "query": "",
    })
    assert resp.status_code == 422


def test_workflow_budget_too_low():
    """Budget below 0.1 should be rejected."""
    client = _client()
    resp = client.post("/api/v1/workflows", json={
        "template": "W1",
        "query": "test",
        "budget": 0.01,
    })
    assert resp.status_code == 422


def test_workflow_budget_too_high():
    """Budget above 100 should be rejected."""
    client = _client()
    resp = client.post("/api/v1/workflows", json={
        "template": "W1",
        "query": "test",
        "budget": 200.0,
    })
    assert resp.status_code == 422


def test_workflow_budget_valid():
    """Budget in range [0.1, 100] should be accepted."""
    client = _client()
    resp = client.post("/api/v1/workflows", json={
        "template": "W1",
        "query": "test",
        "budget": 10.0,
    })
    assert resp.status_code == 200


def test_intervene_invalid_note_action():
    """Invalid note_action should be rejected."""
    client = _client()
    # Create workflow first
    resp = client.post("/api/v1/workflows", json={
        "template": "W1", "query": "test",
    })
    wf_id = resp.json()["workflow_id"]

    resp = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
        "action": "inject_note",
        "note": "test note",
        "note_action": "INVALID_ACTION",
    })
    assert resp.status_code == 422


def test_intervene_valid_note_actions():
    """Valid note_action values should be accepted."""
    client = _client()
    for action in ["ADD_PAPER", "EXCLUDE_PAPER", "MODIFY_QUERY", "EDIT_TEXT", "FREE_TEXT"]:
        resp = client.post("/api/v1/workflows", json={
            "template": "W1", "query": "test",
        })
        wf_id = resp.json()["workflow_id"]

        resp = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
            "action": "inject_note",
            "note": "test note",
            "note_action": action,
        })
        assert resp.status_code == 200, f"note_action {action} rejected"


# === Direct Query validation ===


def test_direct_query_empty_query():
    """Empty query should be rejected."""
    client = _client()
    resp = client.post("/api/v1/direct-query", json={"query": ""})
    assert resp.status_code == 422


def test_direct_query_too_long():
    """Query over 2000 chars should be rejected."""
    client = _client()
    resp = client.post("/api/v1/direct-query", json={"query": "x" * 2001})
    assert resp.status_code == 422


if __name__ == "__main__":
    print("Testing Input Validation:")
    test_workflow_template_invalid()
    test_workflow_template_valid_w1_to_w6()
    test_workflow_query_too_long()
    test_workflow_query_empty()
    test_workflow_budget_too_low()
    test_workflow_budget_too_high()
    test_workflow_budget_valid()
    test_intervene_invalid_note_action()
    test_intervene_valid_note_actions()
    test_direct_query_empty_query()
    test_direct_query_too_long()
    print("\nAll Input Validation tests passed!")
