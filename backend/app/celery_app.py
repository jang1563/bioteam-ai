"""BioTeam-AI Celery application.

Phase 2 task queue for long-running workflow execution.
When CELERY_BROKER_URL is empty, Celery is disabled and the app falls back
to asyncio.create_task() (Phase 1 behavior).

Usage:
    celery -A app.celery_app worker --loglevel=info --concurrency=4
"""

from __future__ import annotations

import logging

from app.config import settings
from celery import Celery

logger = logging.getLogger(__name__)


def is_celery_enabled() -> bool:
    """Check if Celery is configured (broker URL set)."""
    return bool(settings.celery_broker_url)


def create_celery_app() -> Celery:
    """Create and configure the Celery application."""
    broker = settings.celery_broker_url or "memory://"
    backend = settings.celery_result_backend or "rpc://"

    app = Celery(
        "bioteam",
        broker=broker,
        backend=backend,
    )

    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_time_limit=settings.celery_task_time_limit,
        task_soft_time_limit=settings.celery_task_time_limit - 60,
        task_track_started=True,
        worker_concurrency=settings.celery_worker_concurrency,
        # Route workflow tasks to dedicated queue
        task_routes={
            "app.tasks.workflow_tasks.*": {"queue": "workflows"},
        },
        task_default_queue="default",
    )

    # Auto-discover task modules
    app.autodiscover_tasks(["app.tasks"])

    return app


celery_app = create_celery_app()
