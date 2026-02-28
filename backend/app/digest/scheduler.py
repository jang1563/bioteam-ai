"""Digest Scheduler — automated periodic digest fetching using asyncio.

Follows the BackupScheduler pattern exactly. Checks every `check_interval_minutes`
for TopicProfiles that are due for a fetch, and runs the DigestPipeline for each.

Phase 1 implementation: asyncio background task.
Phase 2+: migrate to Celery periodic task.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.db.database import engine as db_engine
from app.digest.pipeline import DigestPipeline
from app.email.sender import is_email_configured, send_digest_email
from app.models.digest import DigestEntry, DigestReport, TopicProfile
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

# Schedule intervals in hours
SCHEDULE_HOURS = {
    "daily": 24.0,
    "weekly": 168.0,
    "manual": 0.0,  # Never auto-run
}

# Lookback window in days for each schedule type
SCHEDULE_LOOKBACK_DAYS = {
    "daily": 7,   # Daily digest: show last 7 days to catch up
    "weekly": 30, # Weekly digest: show last 30 days
}


class DigestScheduler:
    """Runs periodic digest fetching on a configurable interval.

    Usage:
        scheduler = DigestScheduler(pipeline=pipeline, check_interval_minutes=60)
        await scheduler.start()
        # ... app runs ...
        scheduler.stop()
    """

    def __init__(
        self,
        pipeline: DigestPipeline,
        check_interval_minutes: float = 60.0,
        enabled: bool = True,
    ) -> None:
        self.pipeline = pipeline
        self.check_interval_seconds = check_interval_minutes * 60
        self.enabled = enabled
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the digest scheduler as a background task."""
        if not self.enabled:
            logger.info("Digest scheduler disabled")
            return

        if self._running:
            logger.warning("Digest scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "Digest scheduler started (check interval: %.1f min)",
            self.check_interval_seconds / 60,
        )

    def stop(self) -> None:
        """Stop the digest scheduler."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Digest scheduler stopped")

    async def _loop(self) -> None:
        """Main scheduling loop.

        Runs an initial check after a short startup delay (60s), then on the
        configured interval. This avoids a 60-minute blind spot after server restart.
        """
        # Short initial delay to let app fully start up
        await asyncio.sleep(60)
        while self._running:
            try:
                await self._check_and_run()
                await asyncio.sleep(self.check_interval_seconds)
                if not self._running:
                    break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Digest scheduler error: %s", e, exc_info=True)
                await asyncio.sleep(60)

    async def _check_and_run(self) -> None:
        """Check for topics that are due and run pipeline for each."""
        now = datetime.now(timezone.utc)

        # Prune stale entries older than 90 days to prevent unbounded DB growth
        self._prune_old_entries(now)

        with Session(db_engine) as session:
            topics = session.exec(
                select(TopicProfile).where(TopicProfile.is_active)
            ).all()

        for topic in topics:
            schedule_hours = SCHEDULE_HOURS.get(topic.schedule, 0.0)
            if schedule_hours <= 0:
                continue  # "manual" — skip auto-runs

            # Check if there's a recent enough report
            if self._is_due(topic, schedule_hours, now):
                logger.info("Running digest for topic '%s'", topic.name)
                try:
                    days = SCHEDULE_LOOKBACK_DAYS.get(topic.schedule, 7)
                    report = await self.pipeline.run(topic, days=days)

                    # Send email notification (fire-and-forget)
                    if is_email_configured():
                        try:
                            with Session(db_engine) as session:
                                entries = session.exec(
                                    select(DigestEntry)
                                    .where(DigestEntry.topic_id == topic.id)
                                    .order_by(DigestEntry.relevance_score.desc())
                                    .limit(10)
                                ).all()
                                for entry in entries:
                                    session.expunge(entry)
                            await send_digest_email(report, topic, list(entries))
                        except Exception as email_err:
                            logger.warning("Email send failed for '%s': %s", topic.name, email_err)
                except Exception as e:
                    logger.error("Digest pipeline failed for '%s': %s", topic.name, e)

    def _prune_old_entries(self, now: datetime, retention_days: int = 90) -> None:
        """Delete DigestEntry records older than retention_days to prevent DB bloat."""
        cutoff = now - timedelta(days=retention_days)
        cutoff_naive = cutoff.replace(tzinfo=None)  # SQLite stores naive datetimes
        try:
            with Session(db_engine) as session:
                old_entries = session.exec(
                    select(DigestEntry).where(DigestEntry.fetched_at < cutoff_naive)
                ).all()
                if old_entries:
                    for entry in old_entries:
                        session.delete(entry)
                    session.commit()
                    logger.info("Pruned %d digest entries older than %d days", len(old_entries), retention_days)
        except Exception as e:
            logger.warning("Failed to prune old digest entries: %s", e)

    def _is_due(self, topic: TopicProfile, schedule_hours: float, now: datetime) -> bool:
        """Check if a topic is due for a digest run."""
        with Session(db_engine) as session:
            latest_report = session.exec(
                select(DigestReport)
                .where(DigestReport.topic_id == topic.id)
                .order_by(DigestReport.created_at.desc())
                .limit(1)
            ).first()

        if latest_report is None:
            return True  # Never run before

        cutoff = now - timedelta(hours=schedule_hours)
        # SQLite returns naive datetimes — make timezone-aware before comparing
        created_at = latest_report.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return created_at < cutoff

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def get_status(self) -> dict:
        """Get scheduler status for health checks."""
        return {
            "enabled": self.enabled,
            "running": self.is_running,
            "check_interval_minutes": self.check_interval_seconds / 60,
        }
