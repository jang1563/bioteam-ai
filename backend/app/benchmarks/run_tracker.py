"""Benchmark run tracker — state machine for async benchmark execution.

States: pending → running → completed | failed
Only one benchmark can run at a time (asyncio.Lock).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

ACTIVE_DIR = Path(__file__).parent.parent.parent / "data" / "w9_benchmark" / "active"


class BenchmarkRunStatus(BaseModel):
    """Status of a benchmark run."""

    run_id: str
    status: str = "pending"  # pending | running | completed | failed
    dataset_id: str | None = None
    suite_id: str | None = None
    external_benchmark: str | None = None
    template: str = "literature_only"
    cost_mode: str = "quick"
    fair: bool = False
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    result_summary: dict[str, Any] = Field(default_factory=dict)


class BenchmarkRunTracker:
    """Track and manage async benchmark runs."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active_run: BenchmarkRunStatus | None = None
        ACTIVE_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def is_running(self) -> bool:
        return self._active_run is not None and self._active_run.status in ("running", "pending")

    def get_active_run(self) -> BenchmarkRunStatus | None:
        return self._active_run

    def create_run(
        self,
        dataset_id: str | None = None,
        suite_id: str | None = None,
        external_benchmark: str | None = None,
        template: str = "literature_only",
        cost_mode: str = "quick",
        fair: bool = False,
    ) -> BenchmarkRunStatus:
        """Create a new pending run."""
        run = BenchmarkRunStatus(
            run_id=f"run_{uuid.uuid4().hex[:8]}",
            dataset_id=dataset_id,
            suite_id=suite_id,
            external_benchmark=external_benchmark,
            template=template,
            cost_mode=cost_mode,
            fair=fair,
        )
        return run

    async def execute_run(self, run: BenchmarkRunStatus) -> BenchmarkRunStatus:
        """Execute a benchmark run with exclusive lock."""
        if self._lock.locked():
            run.status = "failed"
            run.error = "Another benchmark is already running"
            return run

        async with self._lock:
            self._active_run = run
            run.status = "running"
            run.started_at = datetime.now(timezone.utc)
            self._save_status(run)

            try:
                from app.benchmarks.engine import BenchmarkEngine
                engine = BenchmarkEngine()

                if run.external_benchmark:
                    result_summary = await self._run_external(engine, run)
                elif run.suite_id:
                    result_summary = await self._run_suite(engine, run)
                elif run.dataset_id:
                    result_summary = await self._run_dataset(engine, run)
                else:
                    raise ValueError("No dataset_id, suite_id, or external_benchmark specified")

                run.status = "completed"
                run.result_summary = result_summary
            except Exception as e:
                run.status = "failed"
                run.error = str(e)
                logger.exception("Benchmark run %s failed", run.run_id)
            finally:
                run.completed_at = datetime.now(timezone.utc)
                self._save_status(run)
                self._active_run = None

            return run

    async def _run_dataset(self, engine: Any, run: BenchmarkRunStatus) -> dict:
        from app.benchmarks.datasets import get_dataset
        dataset = get_dataset(run.dataset_id or "")
        if not dataset:
            raise ValueError(f"Unknown dataset: {run.dataset_id}")
        result = await engine.run_dataset(
            dataset,
            template=run.template,
            cost_mode=run.cost_mode,
            fair=run.fair,
        )
        return {
            "bioagent_score": result.bioagent_score,
            "gene_recall": result.gene_recall,
            "pathway_overlap": result.pathway_overlap,
            "total_cost_usd": result.total_cost_usd,
            "fair_mode": result.fair_mode,
        }

    async def _run_suite(self, engine: Any, run: BenchmarkRunStatus) -> dict:
        from app.benchmarks.datasets import get_suite
        datasets = get_suite(run.suite_id or "")
        if not datasets:
            raise ValueError(f"Unknown suite: {run.suite_id}")
        results = await engine.run_suite(
            datasets,
            template=run.template,
            cost_mode=run.cost_mode,
            fair=run.fair,
        )
        if not results:
            return {"n_datasets": 0}
        return {
            "n_datasets": len(results),
            "avg_bioagent_score": sum(r.bioagent_score for r in results) / len(results),
            "total_cost_usd": sum(r.total_cost_usd for r in results),
            "fair_mode": all(r.fair_mode for r in results),
        }

    async def _run_external(self, engine: Any, run: BenchmarkRunStatus) -> dict:
        import importlib
        adapters = {
            "bioagent_bench": "app.benchmarks.adapters.bioagent_bench.BioAgentBenchAdapter",
            "genotex": "app.benchmarks.adapters.genotex.GenoTEXAdapter",
        }
        adapter_path = adapters.get(run.external_benchmark or "")
        if not adapter_path:
            raise ValueError(f"Unknown external benchmark: {run.external_benchmark}")
        module_path, class_name = adapter_path.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        adapter = getattr(mod, class_name)()
        results = await engine.run_external(adapter, cost_mode=run.cost_mode)
        if not results:
            return {"n_tasks": 0}
        return {
            "n_tasks": len(results),
            "avg_bioagent_score": sum(r.bioagent_score for r in results) / len(results),
            "native_scores": [r.native_scores for r in results],
        }

    def _save_status(self, run: BenchmarkRunStatus) -> None:
        """Save run status to disk."""
        path = ACTIVE_DIR / f"{run.run_id}.json"
        path.write_text(run.model_dump_json(indent=2))

    def get_run_status(self, run_id: str) -> BenchmarkRunStatus | None:
        """Load run status from disk."""
        if "/" in run_id or "\\" in run_id or ".." in run_id:
            return None
        path = ACTIVE_DIR / f"{run_id}.json"
        if path.exists():
            return BenchmarkRunStatus.model_validate_json(path.read_text())
        return None
