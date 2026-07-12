"""Base class for external benchmark adapters.

Each adapter converts an external benchmark's data format into BenchmarkDataset
objects that the existing BenchmarkEngine can execute and score.

Adapters also implement native_score() to compute the external benchmark's
own scoring metrics (P/R/F1, results_match, etc.) using W9 predictions
stored in BenchmarkResult.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.benchmarks.models import BenchmarkDataset, BenchmarkResult

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "benchmarks" / "external"


class BenchmarkAdapter(ABC):
    """Abstract base class for external benchmark adapters."""

    @abstractmethod
    def name(self) -> str:
        """Short identifier for this benchmark (e.g. 'genotex', 'bioagent_bench')."""

    @abstractmethod
    def list_tasks(self) -> list[str]:
        """Return all available task IDs in this benchmark."""

    @abstractmethod
    def load_task(self, task_id: str) -> BenchmarkDataset:
        """Convert a single external task into a BenchmarkDataset.

        Gene synonym normalization (if needed) should be applied here,
        so that expected_genes contains canonical HGNC symbols.
        """

    @abstractmethod
    def download(self, cache_dir: str | None = None) -> None:
        """Download benchmark data to local cache. Sync, not async.

        Should be idempotent — skip files that already exist.
        """

    @abstractmethod
    def native_score(self, result: BenchmarkResult, task_id: str) -> dict[str, Any]:
        """Compute the external benchmark's own scoring metrics.

        Uses result.predicted_genes, result.predicted_pathways, etc.
        Returns a dict like {"precision": 0.8, "recall": 0.6, "f1": 0.686}.
        """

    def is_available(self) -> bool:
        """Check if benchmark data is downloaded and ready."""
        try:
            tasks = self.list_tasks()
            return len(tasks) > 0
        except Exception:
            return False

    def load_all(self) -> list[BenchmarkDataset]:
        """Load all tasks as BenchmarkDataset objects."""
        return [self.load_task(tid) for tid in self.list_tasks()]
