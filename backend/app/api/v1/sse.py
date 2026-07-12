"""SSE (Server-Sent Events) hub for real-time dashboard updates.

Uses sse-starlette for production SSE support.
Falls back to a simple asyncio-based implementation if sse-starlette
is not available.

Events follow the SSEEvent schema defined in app.models.messages.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from app.models.messages import SSEEvent
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

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
        # Per-workflow queues: workflow_id -> list of subscriber queues
        self._workflow_queues: dict[str, list[asyncio.Queue[SSEEvent | None]]] = {}

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
            logger.warning(
                "SSE hub at capacity (%d/%d), evicting oldest subscriber",
                len(self._subscribers), self.MAX_SUBSCRIBERS,
            )
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

    def subscribe_workflow(self, workflow_id: str) -> asyncio.Queue[SSEEvent | None]:
        """Create a workflow-specific subscriber queue.

        Only receives events where event.workflow_id == workflow_id.

        Args:
            workflow_id: The workflow ID to filter events for.

        Returns:
            Queue that receives matching SSEEvent objects. None signals disconnect.
        """
        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue(maxsize=200)
        if workflow_id not in self._workflow_queues:
            self._workflow_queues[workflow_id] = []
        self._workflow_queues[workflow_id].append(queue)
        return queue

    def unsubscribe_workflow(self, workflow_id: str, queue: asyncio.Queue[SSEEvent | None]) -> None:
        """Remove a workflow-specific subscriber queue."""
        queues = self._workflow_queues.get(workflow_id, [])
        if queue in queues:
            queues.remove(queue)
        if not queues:
            self._workflow_queues.pop(workflow_id, None)

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

        # Also fan out to workflow-specific queues
        if event.workflow_id and event.workflow_id in self._workflow_queues:
            dead_workflow = []
            for q in self._workflow_queues[event.workflow_id]:
                try:
                    q.put_nowait(event)
                    sent += 1
                except asyncio.QueueFull:
                    dead_workflow.append(q)
            for q in dead_workflow:
                self._workflow_queues[event.workflow_id].remove(q)

        return sent

    async def broadcast_dict(
        self,
        event_type: str,
        workflow_id: str | None = None,
        step_id: str | None = None,
        agent_id: str | list[str] | None = None,
        payload: dict | None = None,
    ) -> int:
        """Convenience method to broadcast from dict values."""
        # Normalize list agent_ids (from parallel steps) to comma-separated string
        if isinstance(agent_id, list):
            agent_id = ",".join(agent_id)
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

    def create_workflow_response(self, workflow_id: str) -> StreamingResponse:
        """Create a workflow-filtered SSE StreamingResponse.

        Only events matching workflow_id are delivered.

        Args:
            workflow_id: Workflow ID to filter events for.

        Returns:
            StreamingResponse with text/event-stream content type.
        """
        queue = self.subscribe_workflow(workflow_id)

        async def _gen():
            try:
                async for chunk in self.event_generator(queue):
                    yield chunk
            finally:
                self.unsubscribe_workflow(workflow_id, queue)

        return StreamingResponse(
            _gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
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
        # Also disconnect workflow-specific queues
        for queues in self._workflow_queues.values():
            for q in queues:
                try:
                    q.put_nowait(None)
                except asyncio.QueueFull:
                    pass
        self._workflow_queues.clear()


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
    return f"event: {event.event_type}\ndata: {json.dumps(data, default=str)}\n\n"


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


@router.get("/sse/workflow/{workflow_id}")
async def sse_workflow_endpoint(workflow_id: str):
    """Workflow-specific SSE endpoint.

    Delivers only events matching the given workflow_id.
    Used by the Peer Review page and other workflow-specific UIs.

    Connect via EventSource:
        new EventSource('/api/v1/sse/workflow/w8_abc?token=...')
    """
    return sse_hub.create_workflow_response(workflow_id)
