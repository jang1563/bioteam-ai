"""Tests for SSE hub."""

import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.models.messages import SSEEvent
from app.api.v1.sse import SSEHub, _format_sse


def test_subscribe_unsubscribe():
    """Hub should track subscribers."""
    hub = SSEHub()
    assert hub.subscriber_count == 0

    q1 = hub.subscribe()
    assert hub.subscriber_count == 1

    q2 = hub.subscribe()
    assert hub.subscriber_count == 2

    hub.unsubscribe(q1)
    assert hub.subscriber_count == 1

    hub.unsubscribe(q2)
    assert hub.subscriber_count == 0
    print("  PASS: subscribe_unsubscribe")


def test_broadcast():
    """Should deliver events to all subscribers."""
    hub = SSEHub()
    q1 = hub.subscribe()
    q2 = hub.subscribe()

    event = SSEEvent(
        event_type="workflow.started",
        workflow_id="w1_abc",
        payload={"template": "W1"},
    )

    sent = asyncio.run(hub.broadcast(event))
    assert sent == 2

    # Both queues should have the event
    assert q1.qsize() == 1
    assert q2.qsize() == 1
    assert q1.get_nowait().event_type == "workflow.started"
    assert q2.get_nowait().workflow_id == "w1_abc"
    print("  PASS: broadcast")


def test_broadcast_dict():
    """Should broadcast from dict values."""
    hub = SSEHub()
    q = hub.subscribe()

    sent = asyncio.run(hub.broadcast_dict(
        event_type="workflow.step_completed",
        workflow_id="w1_abc",
        step_id="SEARCH",
        agent_id="knowledge_manager",
        payload={"papers_found": 47},
    ))

    assert sent == 1
    event = q.get_nowait()
    assert event.event_type == "workflow.step_completed"
    assert event.step_id == "SEARCH"
    assert event.payload["papers_found"] == 47
    print("  PASS: broadcast_dict")


def test_format_sse():
    """SSE format should follow standard spec."""
    event = SSEEvent(
        event_type="workflow.completed",
        workflow_id="w1_done",
        payload={"total_cost": 1.23},
    )

    formatted = _format_sse(event)
    assert formatted.startswith("event: workflow.completed\n")
    assert '"workflow_id": "w1_done"' in formatted
    assert formatted.endswith("\n\n")
    print("  PASS: format_sse")


def test_full_queue_cleanup():
    """Should remove subscribers with full queues."""
    hub = SSEHub()
    q = hub.subscribe()

    # Fill the queue (maxsize=100)
    for i in range(100):
        q.put_nowait(SSEEvent(
            event_type="workflow.started",
            payload={"i": i},
        ))

    # Next broadcast should remove the full queue
    event = SSEEvent(event_type="system.health_changed", payload={})
    sent = asyncio.run(hub.broadcast(event))
    assert sent == 0  # Queue was full, event not delivered
    assert hub.subscriber_count == 0  # Dead queue cleaned up
    print("  PASS: full_queue_cleanup")


def test_event_generator():
    """Event generator should yield SSE-formatted strings."""
    hub = SSEHub()
    q = hub.subscribe()

    # Put two events and a terminator
    q.put_nowait(SSEEvent(event_type="workflow.started", payload={}))
    q.put_nowait(SSEEvent(event_type="workflow.completed", payload={}))
    q.put_nowait(None)  # Terminator

    async def collect():
        results = []
        async for msg in hub.event_generator(q):
            results.append(msg)
        return results

    results = asyncio.run(collect())
    assert len(results) == 2
    assert "workflow.started" in results[0]
    assert "workflow.completed" in results[1]
    print("  PASS: event_generator")


def test_disconnect_all():
    """Should disconnect all subscribers."""
    hub = SSEHub()
    q1 = hub.subscribe()
    q2 = hub.subscribe()

    asyncio.run(hub.disconnect_all())
    assert hub.subscriber_count == 0

    # Queues should have None terminator
    assert q1.get_nowait() is None
    assert q2.get_nowait() is None
    print("  PASS: disconnect_all")


def test_fastapi_endpoint():
    """SSE endpoint should be registered and return StreamingResponse."""
    from fastapi import FastAPI
    from app.api.v1.sse import router

    app = FastAPI()
    app.include_router(router)

    # Verify the route is registered
    routes = [r.path for r in app.routes]
    assert "/api/v1/sse" in routes
    print("  PASS: fastapi_endpoint (route registered)")


if __name__ == "__main__":
    print("Testing SSE Hub:")
    test_subscribe_unsubscribe()
    test_broadcast()
    test_broadcast_dict()
    test_format_sse()
    test_full_queue_cleanup()
    test_event_generator()
    test_disconnect_all()
    test_fastapi_endpoint()
    print("\nAll SSE Hub tests passed!")
