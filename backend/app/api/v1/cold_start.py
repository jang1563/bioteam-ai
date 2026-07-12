"""Cold Start API — orchestrates first-run setup protocol.

POST /api/v1/cold-start/run     — Execute Cold Start (seed + smoke test)
POST /api/v1/cold-start/quick   — Quick Start (skip seeding, verify agents only)
GET  /api/v1/cold-start/status  — Current Cold Start status

PRD FR-5: Cold Start Protocol
Plan v4.2: Quick Start mode + Full Cold Start (4 steps)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.agents.registry import AgentRegistry
from app.memory.semantic import SemanticMemory
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cold-start", tags=["cold-start"])

# Module-level dependencies, set by main.py lifespan
_registry: AgentRegistry | None = None
_memory: SemanticMemory | None = None


def set_dependencies(
    registry: AgentRegistry,
    memory: SemanticMemory,
) -> None:
    """Wire up dependencies (called from main.py lifespan)."""
    global _registry, _memory
    _registry = registry
    _memory = memory


# === Request / Response models ===


class ColdStartRequest(BaseModel):
    """Configuration for Cold Start run."""

    seed_queries: list[str] = Field(
        default_factory=lambda: ["spaceflight biology", "space anemia"],
        description="PubMed/S2 search queries for knowledge seeding",
        max_length=10,
    )
    pubmed_max_results: int = Field(default=50, ge=1, le=200)
    s2_limit: int = Field(default=50, ge=1, le=200)
    run_smoke_test: bool = Field(default=True)


class SeedStepResult(BaseModel):
    """Result from a single seeding step."""

    source: str
    query: str
    papers_fetched: int = 0
    papers_stored: int = 0
    papers_skipped: int = 0
    errors: list[str] = Field(default_factory=list)


class SmokeCheckResult(BaseModel):
    """Result of a smoke test check."""

    name: str
    passed: bool
    detail: str = ""


class ColdStartResponse(BaseModel):
    """Full Cold Start result."""

    mode: str  # "full" | "quick"
    success: bool
    seed_results: list[SeedStepResult] = Field(default_factory=list)
    smoke_checks: list[SmokeCheckResult] = Field(default_factory=list)
    collection_counts: dict[str, int] = Field(default_factory=dict)
    total_papers_stored: int = 0
    duration_ms: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message: str = ""


class ColdStartStatus(BaseModel):
    """Current status of the system's Cold Start state."""

    is_initialized: bool
    agents_registered: int = 0
    critical_agents_healthy: bool = False
    collection_counts: dict[str, int] = Field(default_factory=dict)
    total_documents: int = 0
    has_literature: bool = False
    has_lab_kb: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# === Endpoints ===


@router.post("/run", response_model=ColdStartResponse)
async def run_cold_start(request: ColdStartRequest) -> ColdStartResponse:
    """Execute the Full Cold Start Protocol.

    Steps:
    1. Seed literature from PubMed + Semantic Scholar
    2. (Lab KB seeding is manual via /api/v1/negative-results)
    3. (RCMXT calibration deferred to Phase 2)
    4. Run smoke test

    Returns complete status of all steps.
    """
    import time
    start = time.time()

    if _registry is None or _memory is None:
        raise HTTPException(
            status_code=503,
            detail="System not initialized. Start the server first.",
        )

    from app.cold_start.seeder import ColdStartSeeder
    from app.cold_start.smoke_test import SmokeTest

    seeder = ColdStartSeeder(memory=_memory)
    seed_results: list[SeedStepResult] = []
    total_stored = 0

    # Step 1: Seed from PubMed and Semantic Scholar
    for query in request.seed_queries:
        # PubMed
        pubmed_result = seeder.seed_from_pubmed(query, max_results=request.pubmed_max_results)
        seed_results.append(SeedStepResult(
            source="pubmed",
            query=query,
            papers_fetched=pubmed_result.papers_fetched,
            papers_stored=pubmed_result.papers_stored,
            papers_skipped=pubmed_result.papers_skipped,
            errors=pubmed_result.errors,
        ))
        total_stored += pubmed_result.papers_stored

        # Semantic Scholar
        s2_result = seeder.seed_from_semantic_scholar(query, limit=request.s2_limit)
        seed_results.append(SeedStepResult(
            source="semantic_scholar",
            query=query,
            papers_fetched=s2_result.papers_fetched,
            papers_stored=s2_result.papers_stored,
            papers_skipped=s2_result.papers_skipped,
            errors=s2_result.errors,
        ))
        total_stored += s2_result.papers_stored

    # Step 4: Smoke test
    smoke_checks: list[SmokeCheckResult] = []
    smoke_passed = True

    if request.run_smoke_test:
        smoke = SmokeTest(registry=_registry)
        smoke_result = await smoke.run()
        smoke_passed = smoke_result.passed

        for name, check in smoke_result.checks.items():
            smoke_checks.append(SmokeCheckResult(
                name=name,
                passed=check["passed"],
                detail=check.get("detail", ""),
            ))

    collection_counts = seeder.get_seed_status()
    duration_ms = int((time.time() - start) * 1000)

    any_errors = any(sr.errors for sr in seed_results)
    success = smoke_passed and not any_errors

    message_parts = [f"Seeded {total_stored} papers"]
    if smoke_checks:
        passed_count = sum(1 for c in smoke_checks if c.passed)
        message_parts.append(f"Smoke test: {passed_count}/{len(smoke_checks)} passed")
    if any_errors:
        message_parts.append("Some seeding errors occurred")

    return ColdStartResponse(
        mode="full",
        success=success,
        seed_results=seed_results,
        smoke_checks=smoke_checks,
        collection_counts=collection_counts,
        total_papers_stored=total_stored,
        duration_ms=duration_ms,
        message=". ".join(message_parts),
    )


@router.post("/quick", response_model=ColdStartResponse)
async def quick_start() -> ColdStartResponse:
    """Quick Start — skip seeding, verify agents only.

    Plan v4.2: Researchers should see value immediately.
    Boots with empty ChromaDB, runs smoke test only.
    """
    import time
    start = time.time()

    if _registry is None:
        raise HTTPException(
            status_code=503,
            detail="System not initialized. Start the server first.",
        )

    from app.cold_start.smoke_test import SmokeTest

    smoke = SmokeTest(registry=_registry)
    smoke_result = await smoke.run()

    smoke_checks = [
        SmokeCheckResult(name=name, passed=check["passed"], detail=check.get("detail", ""))
        for name, check in smoke_result.checks.items()
    ]

    collection_counts = {}
    if _memory is not None:
        from app.cold_start.seeder import ColdStartSeeder
        collection_counts = ColdStartSeeder(memory=_memory).get_seed_status()

    duration_ms = int((time.time() - start) * 1000)

    return ColdStartResponse(
        mode="quick",
        success=smoke_result.passed,
        smoke_checks=smoke_checks,
        collection_counts=collection_counts,
        duration_ms=duration_ms,
        message="Quick Start complete. Run Full Cold Start later for seeded knowledge.",
    )


@router.get("/status", response_model=ColdStartStatus)
async def get_cold_start_status() -> ColdStartStatus:
    """Get current Cold Start status — useful for dashboard banner."""
    if _registry is None:
        return ColdStartStatus(is_initialized=False)

    agents = _registry.list_agents()
    unhealthy = _registry.check_critical_health()

    collection_counts = {}
    total_docs = 0
    if _memory is not None:
        from app.cold_start.seeder import ColdStartSeeder
        collection_counts = ColdStartSeeder(memory=_memory).get_seed_status()
        total_docs = sum(collection_counts.values())

    return ColdStartStatus(
        is_initialized=True,
        agents_registered=len(agents),
        critical_agents_healthy=len(unhealthy) == 0,
        collection_counts=collection_counts,
        total_documents=total_docs,
        has_literature=collection_counts.get("literature", 0) > 0,
        has_lab_kb=collection_counts.get("lab_kb", 0) > 0,
    )
