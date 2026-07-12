"""REST API for benchmark results and execution."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/benchmarks", tags=["benchmarks"])

RUNS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "w9_benchmark" / "runs"
W8_RUNS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "w8_benchmark" / "runs"

# Singleton tracker (created lazily)
_tracker = None


def _get_tracker():
    global _tracker
    if _tracker is None:
        from app.benchmarks.run_tracker import BenchmarkRunTracker
        _tracker = BenchmarkRunTracker()
    return _tracker


def _load_all_results() -> list[dict]:
    """Load all W9 benchmark result files, sorted by timestamp (newest first)."""
    if not RUNS_DIR.exists():
        return []
    files = sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    results = []
    for f in files:
        try:
            data = json.loads(f.read_text())
            data.setdefault("benchmark_type", "w9_bioinfo")
            data.setdefault("fair_mode", False)
            results.append(data)
        except json.JSONDecodeError:
            logger.warning("Skipping invalid JSON: %s", f)
    return results


def _load_w8_results() -> list[dict]:
    """Load all W8 peer review benchmark results, sorted newest first."""
    if not W8_RUNS_DIR.exists():
        return []
    files = sorted(
        W8_RUNS_DIR.glob("w8_benchmark_run_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    results = []
    for f in files:
        try:
            data = json.loads(f.read_text())
            data.setdefault("run_id", f.stem)
            data.setdefault("benchmark_type", "w8_peer_review")
            results.append(data)
        except json.JSONDecodeError:
            logger.warning("Skipping invalid W8 JSON: %s", f)
    return results


# ---------------------------------------------------------------------------
# GET endpoints
# ---------------------------------------------------------------------------


@router.get("/config")
async def get_benchmark_config():
    """Return current benchmark configuration (read-only)."""
    from app.benchmarks.scorers import BIOAGENT_WEIGHTS
    from app.config import settings
    return {
        "w8": {
            "similarity_threshold": settings.w8_similarity_threshold,
            "token_cosine_threshold": settings.w8_token_cosine_threshold,
            "match_mode": settings.w8_match_mode,
            "corpus_version": settings.w8_corpus_version,
        },
        "w9": {
            "regression_threshold": settings.w9_regression_threshold,
            "default_budget": settings.w9_default_budget,
            "bioagent_weights": BIOAGENT_WEIGHTS,
        },
    }


@router.get("/results")
async def list_results(limit: int = Query(default=20, ge=1, le=100), dataset_id: str | None = None) -> list[dict]:
    """List all benchmark results."""
    results = _load_all_results()
    if dataset_id:
        results = [r for r in results if r.get("dataset_id") == dataset_id]
    return results[:limit]


@router.get("/results/{run_id}")
async def get_result(run_id: str) -> dict:
    """Get a specific benchmark result by run_id."""
    for result in _load_all_results():
        if result.get("run_id") == run_id:
            return result
    raise HTTPException(status_code=404, detail=f"Run {run_id} not found")


@router.get("/compare")
async def compare_results(a: str, b: str) -> dict:
    """Compare two benchmark runs by run_id."""
    from app.benchmarks.engine import BenchmarkEngine
    from app.benchmarks.models import BenchmarkResult

    all_results = _load_all_results()
    run_a = next((r for r in all_results if r.get("run_id") == a), None)
    run_b = next((r for r in all_results if r.get("run_id") == b), None)

    if not run_a:
        raise HTTPException(status_code=404, detail=f"Run {a} not found")
    if not run_b:
        raise HTTPException(status_code=404, detail=f"Run {b} not found")

    result_a = BenchmarkResult(**run_a)
    result_b = BenchmarkResult(**run_b)

    comparison = BenchmarkEngine.compare_runs(result_a, result_b)
    return comparison.model_dump()


@router.get("/datasets")
async def list_datasets() -> list[dict]:
    """List available benchmark datasets."""
    from app.benchmarks.datasets import BENCHMARK_DATASETS
    return [
        {
            "id": ds.id,
            "name": ds.name,
            "data_type": ds.data_type,
            "confidence": ds.ground_truth_confidence,
            "is_query_only": ds.is_query_only,
            "benchmark_type": ds.benchmark_type,
            "expected_gene_count": len(ds.expected_genes),
            "expected_pathway_count": len(ds.expected_pathways),
        }
        for ds in BENCHMARK_DATASETS.values()
    ]


@router.get("/suites")
async def list_suites() -> dict[str, list[str]]:
    """List available benchmark suites."""
    from app.benchmarks.datasets import BENCHMARK_SUITES
    return BENCHMARK_SUITES


@router.get("/trends")
async def get_trends(metric: str = "bioagent_score", last_n: int = Query(default=20, ge=1, le=100), dataset_id: str | None = None) -> list[dict]:
    """Get metric trends over time."""
    results = _load_all_results()
    if dataset_id:
        results = [r for r in results if r.get("dataset_id") == dataset_id]

    results = [r for r in results if metric in r]
    return [
        {
            "run_id": r.get("run_id"),
            "dataset_id": r.get("dataset_id"),
            "timestamp": r.get("timestamp"),
            "value": r.get(metric, 0.0),
        }
        for r in results[:last_n]
    ]


# ---------------------------------------------------------------------------
# W8 peer review benchmark endpoints
# ---------------------------------------------------------------------------


@router.get("/w8/results")
async def list_w8_results(limit: int = Query(default=20, ge=1, le=100)) -> list[dict]:
    """List all W8 peer review benchmark results."""
    return _load_w8_results()[:limit]


@router.get("/w8/results/{run_id}")
async def get_w8_result(run_id: str) -> dict:
    """Get a specific W8 benchmark result."""
    for result in _load_w8_results():
        if result.get("run_id") == run_id:
            return result
    raise HTTPException(status_code=404, detail=f"W8 run {run_id} not found")


# ---------------------------------------------------------------------------
# POST endpoints — benchmark execution
# ---------------------------------------------------------------------------


class BenchmarkRunRequest(BaseModel):
    """Request body for triggering a benchmark run."""
    dataset_id: str | None = None
    suite_id: str | None = None
    external_benchmark: str | None = None
    template: str = "literature_only"
    cost_mode: str = "quick"
    fair: bool = False


@router.post("/run", status_code=202)
async def trigger_benchmark_run(request: BenchmarkRunRequest, background_tasks: BackgroundTasks) -> dict:
    """Trigger a benchmark run as a background task.

    Returns 202 Accepted with run_id. Check status via GET /runs/{run_id}/status.
    Returns 429 if another benchmark is already running.
    """
    tracker = _get_tracker()

    if tracker.is_running:
        raise HTTPException(
            status_code=429,
            detail="Another benchmark is already running. Check /runs/active for status.",
        )

    if not request.dataset_id and not request.suite_id and not request.external_benchmark:
        raise HTTPException(
            status_code=400,
            detail="Must specify dataset_id, suite_id, or external_benchmark",
        )

    run = tracker.create_run(
        dataset_id=request.dataset_id,
        suite_id=request.suite_id,
        external_benchmark=request.external_benchmark,
        template=request.template,
        cost_mode=request.cost_mode,
        fair=request.fair,
    )

    background_tasks.add_task(tracker.execute_run, run)

    return {
        "run_id": run.run_id,
        "status": "pending",
        "fair": run.fair,
        "message": "Benchmark run queued. Check /runs/{run_id}/status for progress.",
    }


@router.get("/runs/active")
async def get_active_run() -> dict:
    """Get the currently running benchmark, if any."""
    tracker = _get_tracker()
    active = tracker.get_active_run()
    if active:
        return active.model_dump()
    return {"status": "idle", "message": "No benchmark currently running."}


@router.get("/runs/{run_id}/status")
async def get_run_status(run_id: str) -> dict:
    """Get status of a specific benchmark run."""
    tracker = _get_tracker()

    # Check active run first
    active = tracker.get_active_run()
    if active and active.run_id == run_id:
        return active.model_dump()

    # Check saved status
    saved = tracker.get_run_status(run_id)
    if saved:
        return saved.model_dump()

    raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
