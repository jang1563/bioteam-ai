"""BioTeam-AI FastAPI Application.

Entry point for the backend server.

v5: Added agent registry initialization, all API routers wired up.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from app.api.health import router as health_router
from app.api.v1.agents import router as agents_router
from app.api.v1.auth import router as auth_router
from app.api.v1.backup import router as backup_router
from app.api.v1.cold_start import router as cold_start_router
from app.api.v1.contradictions import router as contradictions_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.digest import router as digest_router
from app.api.v1.direct_query import router as dq_router
from app.api.v1.integrity import router as integrity_router
from app.api.v1.negative_results import router as nr_router
from app.api.v1.resume import router as resume_router
from app.api.v1.sse import router as sse_router
from app.api.v1.workflows import router as workflows_router
from app.db.database import create_db_and_tables
from app.middleware.auth import APIKeyAuthMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.models.cost import CostRecord  # noqa: F401
from app.models.digest import DigestEntry, DigestReport, TopicProfile  # noqa: F401

# Import all SQL models so SQLModel metadata registers them
from app.models.evidence import ContradictionEntry, DataRegistry, Evidence  # noqa: F401
from app.models.integrity import AuditFinding, AuditRun  # noqa: F401
from app.models.memory import EpisodicEvent  # noqa: F401
from app.models.messages import AgentMessage, Conversation, ConversationTurn  # noqa: F401
from app.models.negative_result import NegativeResult  # noqa: F401
from app.models.session_checkpoint import SessionCheckpoint  # noqa: F401
from app.models.task import Project, Task  # noqa: F401
from app.models.workflow import StepCheckpoint, WorkflowInstance  # noqa: F401
from app.workflows.engine import WorkflowEngine
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _configure_langfuse() -> bool:
    """Initialize Langfuse tracing if configured. Returns True if enabled."""
    from app.config import settings as _s

    if not _s.langfuse_public_key or not _s.langfuse_secret_key:
        logger.info("Langfuse not configured (no keys). Tracing disabled.")
        return False

    try:
        from langfuse.decorators import langfuse_context

        langfuse_context.configure(
            public_key=_s.langfuse_public_key,
            secret_key=_s.langfuse_secret_key,
            host=_s.langfuse_host,
        )
        logger.info("Langfuse tracing enabled → %s", _s.langfuse_host)
        return True
    except ImportError:
        logger.info("langfuse package not installed. Tracing disabled.")
        return False
    except Exception as e:
        logger.warning("Langfuse init failed (non-fatal): %s", e)
        return False


def _shutdown_langfuse() -> None:
    """Flush pending Langfuse events on shutdown."""
    try:
        from langfuse.decorators import langfuse_context

        langfuse_context.flush()
        logger.info("Langfuse flushed on shutdown.")
    except Exception:
        pass  # Best-effort


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    # Startup: create tables
    create_db_and_tables()

    # Initialize Langfuse observability
    langfuse_enabled = _configure_langfuse()

    # Initialize agent registry (graceful — doesn't fail if API key is test/missing)
    backup_scheduler = None
    digest_scheduler = None
    integrity_scheduler = None
    digest_pipeline = None
    try:
        from app.agents.registry import create_registry
        from app.api.v1.agents import set_registry as set_agents_registry
        from app.api.v1.backup import set_backup_manager
        from app.api.v1.direct_query import set_registry as set_dq_registry
        from app.api.v1.workflows import set_dependencies as set_workflow_deps
        from app.backup.manager import BackupManager
        from app.config import settings
        from app.llm.layer import LLMLayer
        from app.memory.semantic import SemanticMemory

        llm = LLMLayer()
        memory = SemanticMemory()
        registry = create_registry(llm, memory)
        engine = WorkflowEngine()

        from app.api.v1.cold_start import set_dependencies as set_cold_start_deps
        from app.api.v1.sse import sse_hub

        # Wire up API modules
        set_agents_registry(registry)
        set_dq_registry(registry)
        set_workflow_deps(registry, engine, sse_hub=sse_hub)
        set_cold_start_deps(registry, memory)

        # Wire up resume API
        from app.api.v1.resume import set_dependencies as set_resume_deps
        set_resume_deps(registry, engine, sse_hub=sse_hub)

        # Wire up backup manager
        db_url = settings.database_url
        sqlite_path = db_url.replace("sqlite:///", "") if db_url.startswith("sqlite:///") else None
        backup_mgr = BackupManager(
            backup_dir="data/backups",
            sqlite_path=sqlite_path,
            chromadb_dir="data/chroma",
        )
        set_backup_manager(backup_mgr)

        # Start automated backup scheduler
        from app.backup.scheduler import BackupScheduler
        backup_scheduler = BackupScheduler(
            manager=backup_mgr,
            interval_hours=settings.backup_interval_hours,
            enabled=settings.backup_enabled,
        )
        await backup_scheduler.start()

        # Wire up digest pipeline + scheduler
        from app.api.v1.digest import set_pipeline as set_digest_pipeline
        from app.api.v1.digest import set_scheduler as set_digest_scheduler
        from app.digest.pipeline import DigestPipeline
        from app.digest.scheduler import DigestScheduler

        digest_agent = registry.get("digest_agent")
        digest_pipeline = DigestPipeline(digest_agent=digest_agent)
        set_digest_pipeline(digest_pipeline)

        # Wire up integrity auditor agent
        from app.api.v1.integrity import set_auditor_agent
        auditor_agent = registry.get("data_integrity_auditor")
        if auditor_agent:
            set_auditor_agent(auditor_agent)

        digest_scheduler = DigestScheduler(
            pipeline=digest_pipeline,
            check_interval_minutes=settings.digest_check_interval_minutes,
            enabled=settings.digest_enabled,
        )
        set_digest_scheduler(digest_scheduler)
        await digest_scheduler.start()

        # Start integrity audit scheduler
        from app.engines.integrity.scheduler import IntegrityScheduler

        integrity_scheduler = IntegrityScheduler(
            auditor_agent=auditor_agent,
            interval_hours=settings.integrity_audit_interval_hours,
            enabled=settings.integrity_audit_enabled,
        )
        await integrity_scheduler.start()

        logger.info("Agent registry initialized with %d agents", len(registry.list_agents()))
    except Exception as e:
        logger.warning("Registry init skipped (non-fatal): %s", e)

    yield

    # Shutdown: stop schedulers and flush observability
    if backup_scheduler is not None:
        backup_scheduler.stop()
    if digest_scheduler is not None:
        digest_scheduler.stop()
    if integrity_scheduler is not None:
        integrity_scheduler.stop()
    if digest_pipeline is not None:
        digest_pipeline.shutdown()
    if langfuse_enabled:
        _shutdown_langfuse()


app = FastAPI(
    title="BioTeam-AI",
    description="Personal AI Science Team for Biology Research",
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware (order matters: first added = outermost)
from app.config import settings as _settings

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(APIKeyAuthMiddleware)
app.add_middleware(RateLimitMiddleware, global_rpm=60, expensive_rpm=10)

# Global exception handler — prevent internal details from leaking
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Let FastAPI handle HTTPExceptions normally (preserves status codes like 404, 503)
    if isinstance(exc, HTTPException):
        raise exc
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )


# Routes
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(dq_router)
app.include_router(sse_router)
app.include_router(agents_router)
app.include_router(workflows_router)
app.include_router(backup_router)
app.include_router(nr_router)
app.include_router(cold_start_router)
app.include_router(conversations_router)
app.include_router(contradictions_router)
app.include_router(digest_router)
app.include_router(integrity_router)
app.include_router(resume_router)


@app.get("/")
async def root():
    return {"name": "BioTeam-AI", "version": "0.1.0", "status": "running"}
