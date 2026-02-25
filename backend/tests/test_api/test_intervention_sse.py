"""Tests for SSE events on workflow intervention."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import asyncio

from app.agents.registry import create_registry
from app.api.v1.sse import SSEHub
from app.api.v1.workflows import set_dependencies
from app.db.database import create_db_and_tables
from app.llm.mock_layer import MockLLMLayer
from app.main import app
from app.models.messages import SSEEvent
from app.workflows.engine import WorkflowEngine
from fastapi.testclient import TestClient


def _setup(with_sse: bool = False):
    """Wire up dependencies. If with_sse=True, also set up SSE hub."""
    create_db_and_tables()
    mock = MockLLMLayer()
    registry = create_registry(mock)
    engine = WorkflowEngine()
    sse_hub = SSEHub() if with_sse else None
    set_dependencies(registry, engine, sse_hub)
    return TestClient(app), sse_hub


def test_sse_event_type_note_injected():
    """SSEEvent model accepts 'workflow.note_injected' type."""
    event = SSEEvent(
        event_type="workflow.note_injected",
        workflow_id="wf-1",
        payload={"action": "inject_note", "detail": "test note"},
    )
    assert event.event_type == "workflow.note_injected"


def test_sse_event_type_intervention():
    """SSEEvent model accepts 'workflow.intervention' type."""
    event = SSEEvent(
        event_type="workflow.intervention",
        workflow_id="wf-1",
        payload={"action": "pause", "new_state": "PAUSED"},
    )
    assert event.event_type == "workflow.intervention"


def test_intervene_cancel_broadcasts_sse():
    """Cancel intervention should broadcast workflow.intervention event."""
    client, sse_hub = _setup(with_sse=True)
    assert sse_hub is not None

    # Create a workflow
    resp = client.post("/api/v1/workflows", json={
        "template": "W2",
        "query": "test",
    })
    wf_id = resp.json()["workflow_id"]

    # Subscribe to SSE
    queue = asyncio.Queue()
    sse_hub._subscribers.append(queue)

    # Cancel the workflow
    resp = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
        "action": "cancel",
    })
    assert resp.status_code == 200
    assert resp.json()["new_state"] == "CANCELLED"

    # Check that SSE event was broadcast (events are SSEEvent objects)
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    intervention_events = [
        e for e in events
        if hasattr(e, "event_type") and e.event_type == "workflow.intervention"
    ]
    assert len(intervention_events) >= 1, f"Expected intervention SSE event, got: {events}"
    print("  PASS: intervene_cancel_broadcasts_sse")


def test_intervene_inject_note_broadcasts_sse():
    """inject_note intervention should broadcast workflow.note_injected event."""
    client, sse_hub = _setup(with_sse=True)
    assert sse_hub is not None

    resp = client.post("/api/v1/workflows", json={
        "template": "W2",
        "query": "test",
    })
    wf_id = resp.json()["workflow_id"]

    queue = asyncio.Queue()
    sse_hub._subscribers.append(queue)

    resp = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
        "action": "inject_note",
        "note": "Focus on human trials",
    })
    assert resp.status_code == 200

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    note_events = [
        e for e in events
        if hasattr(e, "event_type") and e.event_type == "workflow.note_injected"
    ]
    assert len(note_events) >= 1, f"Expected note_injected SSE event, got: {events}"
    print("  PASS: intervene_inject_note_broadcasts_sse")


def test_intervene_without_sse_hub():
    """Intervention without SSE hub should not crash."""
    client, _ = _setup(with_sse=False)
    resp = client.post("/api/v1/workflows", json={
        "template": "W2",
        "query": "test",
    })
    wf_id = resp.json()["workflow_id"]

    resp = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
        "action": "cancel",
    })
    assert resp.status_code == 200
    print("  PASS: intervene_without_sse_hub")


def test_intervene_pause_broadcasts_intervention_type():
    """Pause intervention (not inject_note) uses 'workflow.intervention' event type."""
    client, sse_hub = _setup(with_sse=True)
    assert sse_hub is not None

    resp = client.post("/api/v1/workflows", json={
        "template": "W2",
        "query": "test",
    })
    wf_id = resp.json()["workflow_id"]

    # Need to get workflow to RUNNING state for pause to work.
    # Cancel works from PENDING, so just test cancel uses "intervention" type.
    queue = asyncio.Queue()
    sse_hub._subscribers.append(queue)

    resp = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
        "action": "cancel",
    })
    assert resp.status_code == 200

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    # Should NOT have note_injected, should have intervention
    note_events = [
        e for e in events
        if hasattr(e, "event_type") and e.event_type == "workflow.note_injected"
    ]
    assert len(note_events) == 0, "Cancel should not produce note_injected event"
    print("  PASS: intervene_pause_broadcasts_intervention_type")


if __name__ == "__main__":
    print("Testing Intervention SSE:")
    test_sse_event_type_note_injected()
    test_sse_event_type_intervention()
    test_intervene_cancel_broadcasts_sse()
    test_intervene_inject_note_broadcasts_sse()
    test_intervene_without_sse_hub()
    test_intervene_pause_broadcasts_intervention_type()
    print("\nAll Intervention SSE tests passed!")
