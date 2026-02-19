"""Backup API endpoints — manual trigger for SQLite + ChromaDB backup.

POST /api/v1/backup — create a new backup snapshot
GET /api/v1/backups — list available backups
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.backup.manager import BackupManager

router = APIRouter(prefix="/api/v1", tags=["backup"])

# Module-level reference, set by main.py at startup
_manager: BackupManager | None = None


def set_backup_manager(manager: BackupManager) -> None:
    """Wire up the backup manager (called from main.py lifespan)."""
    global _manager
    _manager = manager


# === Response Models ===


class BackupResponse(BaseModel):
    status: str
    backup_path: str
    backups_available: int


class BackupListResponse(BaseModel):
    backups: list[str]
    total: int


# === Endpoints ===


@router.post("/backup", response_model=BackupResponse)
async def create_backup(label: str = "") -> BackupResponse:
    """Create a new backup snapshot of SQLite + ChromaDB."""
    if _manager is None:
        raise HTTPException(status_code=503, detail="Backup manager not initialized.")

    path = _manager.create_backup(label=label)
    return BackupResponse(
        status="ok",
        backup_path=str(path),
        backups_available=len(_manager.list_backups()),
    )


@router.get("/backups", response_model=BackupListResponse)
async def list_backups() -> BackupListResponse:
    """List all available backup snapshots."""
    if _manager is None:
        raise HTTPException(status_code=503, detail="Backup manager not initialized.")

    backups = _manager.list_backups()
    return BackupListResponse(
        backups=[str(p) for p in backups],
        total=len(backups),
    )
