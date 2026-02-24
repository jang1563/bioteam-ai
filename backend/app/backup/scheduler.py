"""Backup Scheduler — automated periodic backups using asyncio.

Phase 1 implementation: asyncio background task with configurable interval.
Phase 2+: migrate to Celery periodic task.

Usage:
    scheduler = BackupScheduler(manager=backup_manager, interval_hours=24)
    await scheduler.start()
    # ... app runs ...
    scheduler.stop()
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.backup.manager import BackupManager

logger = logging.getLogger(__name__)


class BackupScheduler:
    """Runs periodic backups on a configurable interval.

    Uses asyncio.create_task for Phase 1 (single-process).
    """

    def __init__(
        self,
        manager: BackupManager,
        interval_hours: float = 24.0,
        enabled: bool = True,
    ) -> None:
        self.manager = manager
        self.interval_seconds = interval_hours * 3600
        self.enabled = enabled
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the backup scheduler as a background task."""
        if not self.enabled:
            logger.info("Backup scheduler disabled")
            return

        if self._running:
            logger.warning("Backup scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "Backup scheduler started (interval: %.1f hours)",
            self.interval_seconds / 3600,
        )

    def stop(self) -> None:
        """Stop the backup scheduler."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Backup scheduler stopped")

    async def _loop(self) -> None:
        """Main scheduling loop."""
        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)
                if not self._running:
                    break
                await self._run_backup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Backup scheduler error: %s", e, exc_info=True)
                # Continue the loop — don't let one failure kill the scheduler
                await asyncio.sleep(60)  # Wait a minute before retrying

    async def _run_backup(self) -> None:
        """Execute a scheduled backup."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        label = f"scheduled_{timestamp}"

        try:
            # Run in executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            path = await loop.run_in_executor(
                None, self.manager.create_backup, label
            )
            logger.info("Scheduled backup created: %s", path)
        except Exception as e:
            logger.error("Scheduled backup failed: %s", e, exc_info=True)

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def get_status(self) -> dict:
        """Get scheduler status for health checks."""
        return {
            "enabled": self.enabled,
            "running": self.is_running,
            "interval_hours": self.interval_seconds / 3600,
            "backups_available": len(self.manager.list_backups()),
        }
