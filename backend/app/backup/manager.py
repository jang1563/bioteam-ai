"""Backup Manager — snapshot and restore SQLite + ChromaDB data.

Design:
- create_backup() copies SQLite DB file + ChromaDB persist directory
  to a timestamped backup folder
- _rotate() keeps last N backups (default 5)
- list_backups() returns available backups sorted by timestamp
- restore() copies a backup back to the active locations
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


class BackupManager:
    """Manages backups of SQLite database and ChromaDB persist directory."""

    def __init__(
        self,
        backup_dir: str | Path,
        sqlite_path: str | Path | None = None,
        chromadb_dir: str | Path | None = None,
        max_backups: int = 5,
    ) -> None:
        self.backup_dir = Path(backup_dir)
        self.sqlite_path = Path(sqlite_path) if sqlite_path else None
        self.chromadb_dir = Path(chromadb_dir) if chromadb_dir else None
        self.max_backups = max_backups
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, label: str = "") -> Path:
        """Create a timestamped backup of SQLite + ChromaDB.

        Returns the path to the backup directory.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        name = f"backup_{timestamp}"
        if label:
            name = f"backup_{timestamp}_{label}"

        backup_path = self.backup_dir / name
        backup_path.mkdir(parents=True, exist_ok=True)

        # Copy SQLite database
        if self.sqlite_path and self.sqlite_path.exists():
            shutil.copy2(self.sqlite_path, backup_path / self.sqlite_path.name)
            # Also copy WAL and SHM files if they exist
            for suffix in ["-wal", "-shm"]:
                wal_path = self.sqlite_path.parent / (self.sqlite_path.name + suffix)
                if wal_path.exists():
                    shutil.copy2(wal_path, backup_path / wal_path.name)

        # Copy ChromaDB directory
        if self.chromadb_dir and self.chromadb_dir.exists():
            shutil.copytree(
                self.chromadb_dir,
                backup_path / "chromadb",
                dirs_exist_ok=True,
            )

        # Rotate old backups
        self._rotate()

        return backup_path

    def _rotate(self) -> None:
        """Remove oldest backups beyond max_backups limit."""
        backups = self.list_backups()
        if len(backups) > self.max_backups:
            for old_backup in backups[self.max_backups:]:
                shutil.rmtree(old_backup, ignore_errors=True)

    def list_backups(self) -> list[Path]:
        """List all backup directories sorted by name (newest first)."""
        if not self.backup_dir.exists():
            return []
        backups = [
            p for p in self.backup_dir.iterdir()
            if p.is_dir() and p.name.startswith("backup_")
        ]
        backups.sort(key=lambda p: p.name, reverse=True)
        return backups

    def restore(self, backup_path: str | Path) -> bool:
        """Restore from a backup directory.

        Returns True if restore succeeded, False if backup not found.
        """
        backup_path = Path(backup_path)
        if not backup_path.exists():
            return False

        # Restore SQLite
        if self.sqlite_path:
            for f in backup_path.iterdir():
                if f.is_file() and f.suffix in (".db", ""):
                    # Check if it matches the sqlite filename
                    if f.name == self.sqlite_path.name or f.name.startswith(self.sqlite_path.name):
                        shutil.copy2(f, self.sqlite_path.parent / f.name)

        # Restore ChromaDB
        chromadb_backup = backup_path / "chromadb"
        if self.chromadb_dir and chromadb_backup.exists():
            if self.chromadb_dir.exists():
                shutil.rmtree(self.chromadb_dir)
            shutil.copytree(chromadb_backup, self.chromadb_dir)

        return True
