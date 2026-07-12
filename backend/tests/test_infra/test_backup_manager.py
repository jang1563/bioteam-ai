"""Tests for BackupManager — create, rotate, list, restore."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from pathlib import Path

from app.backup.manager import BackupManager


def _make_manager(max_backups: int = 3):
    """Create a BackupManager with temp directories."""
    tmpdir = tempfile.mkdtemp()
    backup_dir = Path(tmpdir) / "backups"

    # Create fake SQLite DB
    sqlite_dir = Path(tmpdir) / "data"
    sqlite_dir.mkdir()
    sqlite_path = sqlite_dir / "bioteam.db"
    sqlite_path.write_text("fake sqlite data")

    # Create fake ChromaDB directory
    chromadb_dir = Path(tmpdir) / "chromadb"
    chromadb_dir.mkdir()
    (chromadb_dir / "collection1").mkdir()
    (chromadb_dir / "collection1" / "data.bin").write_text("fake chroma data")

    mgr = BackupManager(
        backup_dir=backup_dir,
        sqlite_path=sqlite_path,
        chromadb_dir=chromadb_dir,
        max_backups=max_backups,
    )
    return mgr, tmpdir


def test_create_backup():
    """create_backup should copy SQLite + ChromaDB to backup dir."""
    mgr, _ = _make_manager()
    backup_path = mgr.create_backup()

    assert backup_path.exists()
    assert backup_path.name.startswith("backup_")

    # SQLite file should be copied
    files = list(backup_path.iterdir())
    file_names = [f.name for f in files]
    assert "bioteam.db" in file_names

    # ChromaDB dir should be copied
    assert "chromadb" in file_names
    assert (backup_path / "chromadb" / "collection1" / "data.bin").exists()
    print("  PASS: create_backup")


def test_create_backup_with_label():
    """create_backup with label should include it in the name."""
    mgr, _ = _make_manager()
    backup_path = mgr.create_backup(label="pre_migration")

    assert "pre_migration" in backup_path.name
    print("  PASS: create_backup_with_label")


def test_list_backups():
    """list_backups should return backups sorted newest first."""
    mgr, _ = _make_manager()
    import time
    mgr.create_backup(label="first")
    time.sleep(0.01)
    mgr.create_backup(label="second")
    time.sleep(0.01)
    mgr.create_backup(label="third")

    backups = mgr.list_backups()
    assert len(backups) == 3
    # Newest first
    assert backups[0].name > backups[1].name > backups[2].name
    print("  PASS: list_backups")


def test_rotation():
    """Old backups beyond max_backups should be removed."""
    mgr, _ = _make_manager(max_backups=2)
    import time
    mgr.create_backup(label="a")
    time.sleep(0.01)
    mgr.create_backup(label="b")
    time.sleep(0.01)
    mgr.create_backup(label="c")

    backups = mgr.list_backups()
    assert len(backups) == 2
    # Oldest (a) should be removed
    names = [b.name for b in backups]
    assert not any("_a" in n for n in names)
    print("  PASS: rotation")


def test_restore():
    """restore should copy backup back to active locations."""
    mgr, tmpdir = _make_manager()

    # Create a backup
    backup_path = mgr.create_backup()

    # Modify the "active" data
    mgr.sqlite_path.write_text("modified sqlite data")
    (mgr.chromadb_dir / "collection1" / "data.bin").write_text("modified chroma data")

    # Restore from backup
    assert mgr.restore(backup_path) is True

    # Verify SQLite restored
    assert mgr.sqlite_path.read_text() == "fake sqlite data"

    # Verify ChromaDB restored
    assert (mgr.chromadb_dir / "collection1" / "data.bin").read_text() == "fake chroma data"
    print("  PASS: restore")


def test_restore_nonexistent():
    """restore with nonexistent path should return False."""
    mgr, _ = _make_manager()
    assert mgr.restore("/nonexistent/path") is False
    print("  PASS: restore_nonexistent")


if __name__ == "__main__":
    print("Testing Backup Manager:")
    test_create_backup()
    test_create_backup_with_label()
    test_list_backups()
    test_rotation()
    test_restore()
    test_restore_nonexistent()
    print("\nAll Backup Manager tests passed!")
