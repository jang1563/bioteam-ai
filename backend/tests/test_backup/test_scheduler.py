"""Tests for BackupScheduler — automated periodic backups."""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.backup.manager import BackupManager
from app.backup.scheduler import BackupScheduler


def _make_manager():
    """Create a BackupManager with temp directories."""
    tmpdir = tempfile.mkdtemp()
    backup_dir = os.path.join(tmpdir, "backups")
    return BackupManager(backup_dir=backup_dir)


def test_scheduler_init():
    """Scheduler should initialize with correct defaults."""
    mgr = _make_manager()
    scheduler = BackupScheduler(manager=mgr)
    assert scheduler.interval_seconds == 24 * 3600
    assert scheduler.enabled is True
    assert scheduler.is_running is False
    print("  PASS: Scheduler init")


def test_scheduler_disabled():
    """Disabled scheduler should not start."""
    mgr = _make_manager()
    scheduler = BackupScheduler(manager=mgr, enabled=False)

    asyncio.run(scheduler.start())
    assert scheduler.is_running is False
    print("  PASS: Scheduler disabled")


def test_scheduler_start_stop():
    """Scheduler should start and stop cleanly."""
    mgr = _make_manager()
    scheduler = BackupScheduler(manager=mgr, interval_hours=0.001)

    async def _test():
        await scheduler.start()
        assert scheduler.is_running is True
        await asyncio.sleep(0.05)
        scheduler.stop()
        assert scheduler.is_running is False

    asyncio.run(_test())
    print("  PASS: Scheduler start/stop")


def test_scheduler_creates_backup():
    """Scheduler should create a backup when triggered."""
    mgr = _make_manager()
    scheduler = BackupScheduler(manager=mgr, interval_hours=0.0001)  # ~0.36s

    async def _test():
        await scheduler.start()
        # Wait enough for one backup cycle
        await asyncio.sleep(1.0)
        scheduler.stop()

    asyncio.run(_test())

    backups = mgr.list_backups()
    assert len(backups) >= 1, f"Expected at least 1 backup, got {len(backups)}"
    assert "scheduled" in backups[0].name
    print(f"  PASS: Scheduler created {len(backups)} backup(s)")


def test_scheduler_double_start():
    """Starting scheduler twice should not create duplicate tasks."""
    mgr = _make_manager()
    scheduler = BackupScheduler(manager=mgr, interval_hours=1.0)

    async def _test():
        await scheduler.start()
        await scheduler.start()  # Second start should be no-op
        assert scheduler.is_running is True
        scheduler.stop()

    asyncio.run(_test())
    print("  PASS: Double start idempotent")


def test_scheduler_get_status():
    """get_status() should return correct scheduler state."""
    mgr = _make_manager()
    scheduler = BackupScheduler(manager=mgr, interval_hours=12)

    status = scheduler.get_status()
    assert status["enabled"] is True
    assert status["running"] is False
    assert status["interval_hours"] == 12.0
    assert isinstance(status["backups_available"], int)
    print("  PASS: get_status()")


def test_scheduler_custom_interval():
    """Scheduler should respect custom interval."""
    mgr = _make_manager()
    scheduler = BackupScheduler(manager=mgr, interval_hours=6.0)
    assert scheduler.interval_seconds == 6 * 3600
    print("  PASS: Custom interval (6h)")


if __name__ == "__main__":
    print("Testing Backup Scheduler:")
    test_scheduler_init()
    test_scheduler_disabled()
    test_scheduler_start_stop()
    test_scheduler_creates_backup()
    test_scheduler_double_start()
    test_scheduler_get_status()
    test_scheduler_custom_interval()
    print("\nAll Backup Scheduler tests passed!")
