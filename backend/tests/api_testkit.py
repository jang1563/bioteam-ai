"""Shared helpers for router-scoped API tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient


def make_temp_sqlite_url(prefix: str) -> tuple[str, Path]:
    """Return a unique SQLite URL/path pair for an isolated test database."""
    db_path = Path(tempfile.gettempdir()) / f"{prefix}_{uuid4().hex}.db"
    cleanup_sqlite_path(db_path)
    return f"sqlite:///{db_path}", db_path


def cleanup_sqlite_path(db_path: Path) -> None:
    """Remove SQLite db and WAL sidecars if they exist."""
    for suffix in ("", "-wal", "-shm"):
        try:
            Path(f"{db_path}{suffix}").unlink()
        except FileNotFoundError:
            pass


def build_router_client(*routers) -> TestClient:
    """Create a FastAPI app that mounts only the requested routers."""
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    return TestClient(app)
