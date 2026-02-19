"""BioTeam-AI FastAPI Application.

Entry point for the backend server.

v5: Added agent registry initialization, all API routers wired up.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1.direct_query import router as dq_router
from app.api.v1.sse import router as sse_router
from app.api.v1.agents import router as agents_router
from app.api.v1.workflows import router as workflows_router
from app.api.v1.backup import router as backup_router
from app.db.database import create_db_and_tables
from app.workflows.engine import WorkflowEngine

# Import all SQL models so SQLModel metadata registers them
from app.models.evidence import Evidence, ContradictionEntry, DataRegistry  # noqa: F401
from app.models.negative_result import NegativeResult  # noqa: F401
from app.models.workflow import WorkflowInstance, StepCheckpoint  # noqa: F401
from app.models.messages import AgentMessage  # noqa: F401
from app.models.task import Project, Task  # noqa: F401
from app.models.memory import EpisodicEvent  # noqa: F401
from app.models.cost import CostRecord  # noqa: F401

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    # Startup: create tables
    create_db_and_tables()

    # Initialize agent registry (graceful — doesn't fail if API key is test/missing)
    try:
        from app.config import settings
        from app.llm.layer import LLMLayer
        from app.memory.semantic import SemanticMemory
        from app.agents.registry import create_registry
        from app.api.v1.agents import set_registry as set_agents_registry
        from app.api.v1.direct_query import set_registry as set_dq_registry
        from app.api.v1.workflows import set_dependencies as set_workflow_deps
        from app.api.v1.backup import set_backup_manager
        from app.backup.manager import BackupManager

        llm = LLMLayer()
        memory = SemanticMemory()
        registry = create_registry(llm, memory)
        engine = WorkflowEngine()

        # Wire up API modules
        set_agents_registry(registry)
        set_dq_registry(registry)
        set_workflow_deps(registry, engine)

        # Wire up backup manager
        db_url = settings.database_url
        sqlite_path = db_url.replace("sqlite:///", "") if db_url.startswith("sqlite:///") else None
        backup_mgr = BackupManager(
            backup_dir="data/backups",
            sqlite_path=sqlite_path,
            chromadb_dir="data/chroma",
        )
        set_backup_manager(backup_mgr)

        logger.info("Agent registry initialized with %d agents", len(registry.list_agents()))
    except Exception as e:
        logger.warning("Registry init skipped (non-fatal): %s", e)

    yield
    # Shutdown: cleanup if needed


app = FastAPI(
    title="BioTeam-AI",
    description="Personal AI Science Team for Biology Research",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(health_router)
app.include_router(dq_router)
app.include_router(sse_router)
app.include_router(agents_router)
app.include_router(workflows_router)
app.include_router(backup_router)


@app.get("/")
async def root():
    return {"name": "BioTeam-AI", "version": "0.1.0", "status": "running"}
