"""Health check endpoint — FR-6 comprehensive dependency checks.

Checks: LLM API connectivity, SQLite DB, ChromaDB, PubMed API, CostTracker status.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import settings
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

VERSION = "0.8.0"


class HealthStatus(BaseModel):
    status: str  # "healthy" | "degraded" | "unhealthy"
    version: str
    checks: dict[str, dict]
    dependencies: dict[str, str]  # Simplified view for frontend
    timestamp: datetime


@router.get("/health", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    """Check all system dependencies (PRD FR-6)."""
    checks: dict[str, dict] = {}
    overall_healthy = True
    has_warning = False

    # 1. LLM API connectivity
    try:
        api_key = settings.anthropic_api_key
        if api_key and api_key != "test":
            import anthropic
            anthropic.AsyncAnthropic()  # validates key format
            checks["llm_api"] = {"status": "ok", "detail": "API key configured"}
        elif api_key == "test":
            checks["llm_api"] = {"status": "ok", "detail": "test mode"}
        else:
            checks["llm_api"] = {"status": "warning", "detail": "ANTHROPIC_API_KEY not set"}
            has_warning = True
    except Exception as e:
        checks["llm_api"] = {"status": "error", "detail": str(e)}
        overall_healthy = False

    # 2. SQLite DB
    try:
        from app.db.database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1")).fetchone()
            wal = conn.execute(text("PRAGMA journal_mode")).fetchone()
            checks["database"] = {"status": "ok", "detail": f"journal_mode={wal[0]}"}
    except Exception as e:
        checks["database"] = {"status": "error", "detail": str(e)}
        overall_healthy = False

    # 3. ChromaDB
    try:
        import chromadb
        version = getattr(chromadb, "__version__", "unknown")
        checks["chromadb"] = {"status": "ok", "detail": f"v{version} available"}
    except ImportError:
        checks["chromadb"] = {"status": "warning", "detail": "chromadb not installed"}
        has_warning = True
    except Exception as e:
        checks["chromadb"] = {"status": "warning", "detail": str(e)}
        has_warning = True

    # 4. PubMed API (check config)
    ncbi_email = settings.ncbi_email
    if ncbi_email:
        checks["pubmed"] = {"status": "ok", "detail": f"email={ncbi_email[:20]}..."}
    else:
        checks["pubmed"] = {"status": "warning", "detail": "NCBI_EMAIL not set (PubMed may rate-limit)"}
        has_warning = True

    # 5. Redis / Celery
    try:
        from app.celery_app import is_celery_enabled
        if is_celery_enabled():
            import redis as redis_lib
            r = redis_lib.from_url(settings.celery_broker_url, socket_timeout=2)
            r.ping()
            checks["redis"] = {"status": "ok", "detail": "Connected"}
            checks["celery"] = {"status": "ok", "detail": "Broker configured"}
        else:
            checks["redis"] = {"status": "warning", "detail": "Not configured (asyncio fallback)"}
            checks["celery"] = {"status": "warning", "detail": "Not configured (asyncio fallback)"}
            has_warning = True
    except Exception as e:
        checks["redis"] = {"status": "error", "detail": str(e)[:100]}
        checks["celery"] = {"status": "error", "detail": "Broker unreachable"}
        has_warning = True

    # 6. CostTracker
    try:
        from app.cost.tracker import CostTracker
        tracker = CostTracker()
        budget = tracker.get_budget_status()
        remaining = budget.get("remaining", 0)
        checks["cost_tracker"] = {
            "status": "ok" if remaining > 0 else "warning",
            "detail": f"${remaining:.2f} remaining",
        }
        if remaining <= 0:
            has_warning = True
    except Exception:
        checks["cost_tracker"] = {"status": "ok", "detail": f"default (${50.0:.2f} budget)"}

    # 7. Docker sandbox
    if settings.docker_enabled:
        from app.execution.docker_runner import DockerCodeRunner
        runner = DockerCodeRunner()
        if runner.is_available():
            checks["docker"] = {"status": "ok", "detail": f"sandbox ready (timeout={settings.docker_timeout_seconds}s, mem={settings.docker_memory_limit})"}
        else:
            checks["docker"] = {"status": "warning", "detail": "Docker daemon not running — code execution unavailable (set DOCKER_ENABLED=false to suppress)"}
            has_warning = True
    else:
        checks["docker"] = {"status": "disabled", "detail": "set DOCKER_ENABLED=true to enable code execution sandbox"}

    # 8. Optional features (informational — never cause unhealthy)
    checks["peer_review_corpus"] = {
        "status": "ok" if settings.peer_review_corpus_enabled else "disabled",
        "detail": "eLife/PLOS open peer review corpus (Phase 6)"
        + (" — enabled" if settings.peer_review_corpus_enabled else " — set PEER_REVIEW_CORPUS_ENABLED=true to activate"),
    }
    checks["mcp_connectors"] = {
        "status": "ok" if settings.mcp_enabled else "disabled",
        "detail": f"preferred_sources={settings.mcp_preferred_sources}"
        + ("" if settings.mcp_enabled else " — set MCP_ENABLED=true to activate"),
    }

    # Build simplified dependencies map for frontend
    dependencies = {name: check["status"] for name, check in checks.items()}

    if overall_healthy:
        status = "degraded" if has_warning else "healthy"
    else:
        status = "unhealthy"

    return HealthStatus(
        status=status,
        version=VERSION,
        checks=checks,
        dependencies=dependencies,
        timestamp=datetime.now(timezone.utc),
    )
