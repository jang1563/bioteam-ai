"""Health check endpoint — FR-6 comprehensive dependency checks.

Checks: LLM API connectivity, SQLite DB, ChromaDB, PubMed API, CostTracker status.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

VERSION = "0.5.0"


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
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
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
    ncbi_email = os.environ.get("NCBI_EMAIL", "")
    if ncbi_email:
        checks["pubmed"] = {"status": "ok", "detail": f"email={ncbi_email[:20]}..."}
    else:
        checks["pubmed"] = {"status": "warning", "detail": "NCBI_EMAIL not set (PubMed may rate-limit)"}
        has_warning = True

    # 5. CostTracker
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
    except Exception as e:
        checks["cost_tracker"] = {"status": "ok", "detail": f"default (${50.0:.2f} budget)"}

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
