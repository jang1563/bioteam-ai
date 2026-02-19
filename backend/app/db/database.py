"""Database setup — SQLite with WAL mode via SQLModel/SQLAlchemy.

Design decisions (Day 0):
- SQLModel chosen: combines Pydantic v2 + SQLAlchemy in one model class
- SQLite WAL mode: enables concurrent reads during workflow execution
- Alembic for migrations: autogenerate from SQLModel table definitions
- ChromaDB handles vector storage (literature, synthesis, lab_kb collections)
- SQLite handles structured state (workflows, checkpoints, costs, evidence, etc.)

What goes where:
- SQLite: WorkflowInstance, StepCheckpoint, Evidence, NegativeResult, AgentMessage,
          Project, Task, CostRecord, EpisodicEvent
- ChromaDB: Literature embeddings, synthesis text, lab KB text (vector-searchable)
"""

from __future__ import annotations

import os
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.config import settings


def get_database_url() -> str:
    """Get database URL, ensuring the data directory exists."""
    url = settings.database_url
    if url.startswith("sqlite:///"):
        db_path = url.replace("sqlite:///", "")
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    return url


# Enable WAL mode for all SQLite connections
@event.listens_for(Engine, "connect")
def set_sqlite_wal(dbapi_connection, connection_record):
    """Enable WAL mode for concurrent reads during workflow execution."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")  # Safe with WAL
    cursor.execute("PRAGMA busy_timeout=5000")    # 5s wait on lock
    cursor.close()


engine = create_engine(
    get_database_url(),
    echo=False,
    connect_args={"check_same_thread": False},  # Required for SQLite + async
)


def create_db_and_tables():
    """Create all tables defined by SQLModel metadata."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Dependency for FastAPI endpoints."""
    with Session(engine) as session:
        yield session
