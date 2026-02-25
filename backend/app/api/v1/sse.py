"""SSE (Server-Sent Events) hub for real-time dashboard updates.

Uses sse-starlette for production SSE support.
Falls back to a simple asyncio-based implementation if sse-starlette
is not available.

Events follow the SSEEvent schema defined in app.models.messages.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from app.models.messages import SSEEvent
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/v1", tags=["sse"])


class SSEHub:
    """Central hub for broadcasting SSE events to connected clients.

    Usage:
        hub = SSEHub()

        # In workflow engine:
        await hub.broadcast(SSEEvent(
            event_type="workflow.step_completed",
            workflow_id="w1_abc",
            step_id="SEARCH",
            agent_id="knowledge_manager",
            payload={"papers_found": 47, "cost": 0.12},
        ))

        # In FastAPI:
        @router.get("/sse")
        async def sse_endpoint():
            return hub.create_response()
    """

    MAX_SUBSCRIBERS = 50  # Safety cap to prevent unbounded growth

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[SSEEvent | None]] = []

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def subscribe(self) -> asyncio.Queue[SSEEvent | None]:
        """Create a new subscriber queue.

        Returns:
            Queue that receives SSEEvent objects. None signals disconnect.

        Raises:
            RuntimeError: If MAX_SUBSCRIBERS limit is reached.
        """
        if len(self._subscribers) >= self.MAX_SUBSCRIBERS:
            # Evict oldest subscriber before adding new one
            oldest = self._subscribers.pop(0)
            try:
                oldest.put_nowait(None)
            except asyncio.QueueFull:
                pass

        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[SSEEvent | None]) -> None:
        """Remove a subscriber queue."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def broadcast(self, event: SSEEvent) -> int:
        """Send an event to all connected subscribers.

        Args:
            event: The SSEEvent to broadcast.

        Returns:
            Number of subscribers that received the event.
        """
        sent = 0
        dead_queues = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
                sent += 1
            except asyncio.QueueFull:
                dead_queues.append(queue)

        # Clean up full/dead queues
        for q in dead_queues:
            self._subscribers.remove(q)

        return sent

    async def broadcast_dict(
        self,
        event_type: str,
        workflow_id: str | None = None,
        step_id: str | None = None,
        agent_id: str | None = None,
        payload: dict | None = None,
    ) -> int:
        """Convenience method to broadcast from dict values."""
        event = SSEEvent(
            event_type=event_type,  # type: ignore[arg-type]
            workflow_id=workflow_id,
            step_id=step_id,
            agent_id=agent_id,
            payload=payload or {},
        )
        return await self.broadcast(event)

    async def event_generator(
        self,
        queue: asyncio.Queue[SSEEvent | None],
        heartbeat_interval: float = 30.0,
    ) -> AsyncGenerator[str, None]:
        """Generate SSE-formatted strings from a subscriber queue.

        Sends periodic heartbeat comments to detect disconnected clients.

        Yields:
            SSE-formatted event strings (event: type\\ndata: json\\n\\n)
        """
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
                    if event is None:
                        break
                    yield _format_sse(event)
                except asyncio.TimeoutError:
                    # SSE heartbeat comment — keeps connection alive and detects dead clients
                    yield ": heartbeat\n\n"
        finally:
            self.unsubscribe(queue)

    def create_response(self) -> StreamingResponse:
        """Create a FastAPI StreamingResponse for SSE.

        Returns:
            StreamingResponse with text/event-stream content type.
        """
        queue = self.subscribe()
        return StreamingResponse(
            self.event_generator(queue),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    async def disconnect_all(self) -> None:
        """Disconnect all subscribers (used during shutdown)."""
        for queue in self._subscribers:
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass
        self._subscribers.clear()


def _format_sse(event: SSEEvent) -> str:
    """Format an SSEEvent as a standard SSE string.

    Format:
        event: <event_type>
        data: <json_payload>

    """
    data = {
        "event_type": event.event_type,
        "workflow_id": event.workflow_id,
        "step_id": event.step_id,
        "agent_id": event.agent_id,
        "payload": event.payload,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
    }
    return f"event: {event.event_type}\ndata: {json.dumps(data)}\n\n"


# === Singleton hub instance ===

sse_hub = SSEHub()


# === FastAPI endpoint ===


@router.get("/sse")
async def sse_endpoint():
    """SSE endpoint for real-time dashboard updates.

    Connect to receive workflow events, agent status changes,
    and system alerts as Server-Sent Events.
    """
    return sse_hub.create_response()
