"""Celery tasks for workflow execution.

These tasks wrap the async workflow runners inside synchronous Celery tasks
using asyncio.run(). Each task gets its own event loop.

When Celery is not configured, the workflow API falls back to
asyncio.create_task() (Phase 1 behavior).
"""

from __future__ import annotations

import asyncio
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.workflow_tasks.run_w1_workflow",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def run_w1_workflow(self, workflow_id: str, query: str, budget: float) -> dict:
    """Execute W1 Literature Review pipeline as a Celery task.

    Wraps the async _run_w1_background() in asyncio.run().
    """
    logger.info("Celery task started: W1 workflow %s (task_id=%s)", workflow_id, self.request.id)

    try:
        result = asyncio.run(_execute_w1(workflow_id, query, budget))
        logger.info("Celery task completed: W1 workflow %s", workflow_id)
        return {"workflow_id": workflow_id, "status": "completed", **result}
    except Exception as exc:
        logger.error("Celery task failed: W1 workflow %s: %s", workflow_id, exc, exc_info=True)
        raise


@celery_app.task(
    name="app.tasks.workflow_tasks.resume_w1_workflow",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def resume_w1_workflow(self, workflow_id: str, query: str) -> dict:
    """Resume W1 pipeline after human approval as a Celery task."""
    logger.info("Celery task started: resume W1 %s (task_id=%s)", workflow_id, self.request.id)

    try:
        asyncio.run(_execute_w1_resume(workflow_id, query))
        logger.info("Celery task completed: resume W1 %s", workflow_id)
        return {"workflow_id": workflow_id, "status": "resumed"}
    except Exception as exc:
        logger.error("Celery task failed: resume W1 %s: %s", workflow_id, exc, exc_info=True)
        raise


async def _execute_w1(workflow_id: str, query: str, budget: float) -> dict:
    """Async W1 execution (called from within Celery task's event loop)."""
    # Lazy imports to avoid circular dependencies at module load time
    from app.api.v1.workflows import _run_w1_background

    await _run_w1_background(workflow_id, query, budget)
    return {"workflow_id": workflow_id}


async def _execute_w1_resume(workflow_id: str, query: str) -> None:
    """Async W1 resume (called from within Celery task's event loop)."""
    from app.api.v1.workflows import _resume_w1_background

    await _resume_w1_background(workflow_id, query)
