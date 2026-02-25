"""Celery tasks for workflow execution.

These tasks wrap the async workflow runners inside synchronous Celery tasks
using asyncio.run(). Each task gets its own event loop.

When Celery is not configured, the workflow API falls back to
asyncio.create_task() (Phase 1 behavior).

v6.0: W1-only tasks.
v6.1: Generic run_workflow / resume_workflow for all templates (W1-W6).
"""

from __future__ import annotations

import asyncio
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


# === Generic tasks (W1-W6) ===


@celery_app.task(
    name="app.tasks.workflow_tasks.run_workflow",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def run_workflow(self, workflow_id: str, template: str, query: str, budget: float) -> dict:
    """Execute any workflow pipeline as a Celery task.

    Wraps the async _run_workflow_background() in asyncio.run().
    """
    logger.info("Celery task started: %s workflow %s (task_id=%s)", template, workflow_id, self.request.id)

    try:
        asyncio.run(_execute_workflow(workflow_id, template, query, budget))
        logger.info("Celery task completed: %s workflow %s", template, workflow_id)
        return {"workflow_id": workflow_id, "template": template, "status": "completed"}
    except Exception as exc:
        logger.error("Celery task failed: %s workflow %s: %s", template, workflow_id, exc, exc_info=True)
        raise


@celery_app.task(
    name="app.tasks.workflow_tasks.resume_workflow",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def resume_workflow(self, workflow_id: str, template: str, query: str) -> dict:
    """Resume any workflow pipeline after human approval as a Celery task."""
    logger.info("Celery task started: resume %s %s (task_id=%s)", template, workflow_id, self.request.id)

    try:
        asyncio.run(_execute_workflow_resume(workflow_id, template, query))
        logger.info("Celery task completed: resume %s %s", template, workflow_id)
        return {"workflow_id": workflow_id, "template": template, "status": "resumed"}
    except Exception as exc:
        logger.error("Celery task failed: resume %s %s: %s", template, workflow_id, exc, exc_info=True)
        raise


async def _execute_workflow(workflow_id: str, template: str, query: str, budget: float) -> None:
    """Async workflow execution (called from within Celery task's event loop)."""
    from app.api.v1.workflows import _run_workflow_background

    await _run_workflow_background(workflow_id, template, query, budget)


async def _execute_workflow_resume(workflow_id: str, template: str, query: str) -> None:
    """Async workflow resume (called from within Celery task's event loop)."""
    from app.api.v1.workflows import _resume_workflow_background

    await _resume_workflow_background(workflow_id, template, query)


# === Backward-compatible W1-specific tasks (existing Celery task names) ===


@celery_app.task(
    name="app.tasks.workflow_tasks.run_w1_workflow",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def run_w1_workflow(self, workflow_id: str, query: str, budget: float) -> dict:
    """Execute W1 Literature Review pipeline as a Celery task (backward-compatible)."""
    return run_workflow(workflow_id, "W1", query, budget)


@celery_app.task(
    name="app.tasks.workflow_tasks.resume_w1_workflow",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def resume_w1_workflow(self, workflow_id: str, query: str) -> dict:
    """Resume W1 pipeline after human approval (backward-compatible)."""
    return resume_workflow(workflow_id, "W1", query)
