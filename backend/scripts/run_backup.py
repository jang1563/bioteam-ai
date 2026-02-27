#!/usr/bin/env python3
"""Create a manual local backup of SQLite and ChromaDB data."""

from __future__ import annotations

from pathlib import Path

from app.backup.manager import BackupManager
from app.config import settings


def main() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    project_root = backend_dir.parent

    db_url = settings.database_url
    sqlite_path: Path | None = None
    if db_url.startswith("sqlite:///"):
        sqlite_path = project_root / db_url.replace("sqlite:///", "")

    manager = BackupManager(
        backup_dir=project_root / "data" / "backups",
        sqlite_path=sqlite_path,
        chromadb_dir=project_root / "data" / "chroma",
    )
    backup_path = manager.create_backup(label="manual")
    print(backup_path)


if __name__ == "__main__":
    main()
