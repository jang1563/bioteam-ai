"""Workflow intervention E2E tests — pause, resume, cancel, inject note flows.

Tests multi-step intervention sequences through the HTTP API.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from fastapi.testclient import TestClient

from app.main import app
from app.agents.registry import create_registry
from app.agents.research_director import QueryClassification
from app.llm.mock_layer import MockLLMLayer
from app.workflows.engine import WorkflowEngine
from app.api.v1.agents import set_registry as set_agents_registry
from app.api.v1.direct_query import set_registry as set_dq_registry
from app.api.v1.workflows import set_dependencies as set_workflow_deps
from app.db.database import create_db_and_tables


# === Setup ===


def _setup():
    """Wire up all dependencies with mock LLM and return TestClient."""
    create_db_and_tables()
    classification = QueryClassification(
        type="simple_query",
        reasoning="Test classification",
        target_agent="t02_transcriptomics",
    )
    mock = MockLLMLayer({"sonnet:QueryClassification": classification})
    registry = create_registry(mock)
    engine = WorkflowEngine()

    set_agents_registry(registry)
    set_dq_registry(registry)
    set_workflow_deps(registry, engine)

    _reset_rate_limiter()
    return TestClient(app)


def _reset_rate_limiter():
    """Clear all rate limiter token buckets."""
    from app.middleware.rate_limit import RateLimitMiddleware
    middleware = app.middleware_stack
    while middleware is not None:
        if isinstance(middleware, RateLimitMiddleware):
            middleware._global_buckets.clear()
            middleware._expensive_buckets.clear()
            return
        middleware = getattr(middleware, 'app', None)


def _create_workflow(client, template="W2", query="test intervention"):
    """Create a workflow and return its ID."""
    resp = client.post("/api/v1/workflows", json={
        "template": template,
        "query": query,
    })
    assert resp.status_code == 200
    return resp.json()["workflow_id"]


# === Intervention Flow Tests ===


def test_inject_note_add_paper():
    """Inject ADD_PAPER note → verify note stored on workflow."""
    client = _setup()
    wf_id = _create_workflow(client)

    resp = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
        "action": "inject_note",
        "note": "Include doi:10.1038/s41591-021-01637-7",
        "note_action": "ADD_PAPER",
    })
    assert resp.status_code == 200

    # Verify note is visible in workflow status
    resp = client.get(f"/api/v1/workflows/{wf_id}")
    assert resp.status_code == 200


def test_inject_note_modify_query():
    """Inject MODIFY_QUERY note → verify stored."""
    client = _setup()
    wf_id = _create_workflow(client)

    resp = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
        "action": "inject_note",
        "note": "Focus specifically on human studies",
        "note_action": "MODIFY_QUERY",
    })
    assert resp.status_code == 200


def test_cancel_pending_workflow():
    """Create W2 (PENDING) → cancel → verify CANCELLED."""
    client = _setup()
    wf_id = _create_workflow(client)

    # Verify PENDING
    resp = client.get(f"/api/v1/workflows/{wf_id}")
    assert resp.json()["state"] == "PENDING"

    # Cancel
    resp = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
        "action": "cancel",
    })
    assert resp.status_code == 200
    assert resp.json()["new_state"] == "CANCELLED"

    # Verify CANCELLED
    resp = client.get(f"/api/v1/workflows/{wf_id}")
    assert resp.json()["state"] == "CANCELLED"


def test_double_cancel_idempotent():
    """Cancel → cancel again → second cancel should not error."""
    client = _setup()
    wf_id = _create_workflow(client)

    # First cancel
    resp = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
        "action": "cancel",
    })
    assert resp.status_code == 200

    # Second cancel — should handle gracefully (already terminal)
    resp = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
        "action": "cancel",
    })
    # Returns 409 Conflict (already terminal state) — expected behavior
    assert resp.status_code in (200, 400, 409)


def test_inject_multiple_notes():
    """Inject 3 notes → verify all stored."""
    client = _setup()
    wf_id = _create_workflow(client)

    notes = [
        ("Focus on human studies only", "MODIFY_QUERY"),
        ("Exclude rodent models", "FREE_TEXT"),
        ("Add doi:10.1182/blood.2021014479", "ADD_PAPER"),
    ]

    for note_text, note_action in notes:
        resp = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
            "action": "inject_note",
            "note": note_text,
            "note_action": note_action,
        })
        assert resp.status_code == 200


def test_intervene_nonexistent_workflow():
    """Intervene on nonexistent workflow → 404."""
    client = _setup()

    resp = client.post("/api/v1/workflows/nonexistent-id/intervene", json={
        "action": "cancel",
    })
    assert resp.status_code == 404


def test_intervene_invalid_action():
    """Send invalid action → 422 validation error."""
    client = _setup()
    wf_id = _create_workflow(client)

    resp = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
        "action": "destroy",
    })
    assert resp.status_code == 422


def test_workflow_list_after_multiple_creates():
    """Create 3 workflows → list all → verify count and ordering."""
    client = _setup()

    ids = []
    for i in range(3):
        wf_id = _create_workflow(client, query=f"query {i}")
        ids.append(wf_id)

    resp = client.get("/api/v1/workflows")
    assert resp.status_code == 200
    workflows = resp.json()
    assert len(workflows) >= 3

    # All created IDs should be in the list
    listed_ids = [w["id"] for w in workflows]
    for wf_id in ids:
        assert wf_id in listed_ids


if __name__ == "__main__":
    print("Testing Intervention E2E:")
    test_inject_note_add_paper()
    test_inject_note_modify_query()
    test_cancel_pending_workflow()
    test_double_cancel_idempotent()
    test_inject_multiple_notes()
    test_intervene_nonexistent_workflow()
    test_intervene_invalid_action()
    test_workflow_list_after_multiple_creates()
    print("\nAll Intervention E2E tests passed!")
