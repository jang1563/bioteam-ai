"""GenoTEX external benchmark adapter.

GenoTEX: A Benchmark for Evaluating LLM-Based Automated Gene Expression Analysis
(https://github.com/Liu-Hy/GenoTEX)

This adapter focuses on the **unconditional** gene-trait association subset
(132 traits from 1,384 total problems). These are "knowledge benchmarks" —
the expected genes are well-established gene-trait associations from GWAS/OMIM,
not experiment-specific DEG results.

Data needed (small, ~50MB total):
  - metadata/task_info.json     — task definitions
  - metadata/gene_synonym.json  — gene symbol normalization table
  - output/regress/*.json       — ground truth gene sets per trait

Why only unconditional?
  W9 uses LLM agents (not real bioinformatics tools), so it evaluates
  biological knowledge, not pipeline execution. Unconditional tasks ask
  "which genes are associated with trait X?" — answerable from literature.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.benchmarks.adapters.base import DEFAULT_CACHE_DIR, BenchmarkAdapter
from app.benchmarks.models import BenchmarkDataset, BenchmarkResult

logger = logging.getLogger(__name__)

GENOTEX_REPO_URL = "https://github.com/Liu-Hy/GenoTEX"


class GenoTEXAdapter(BenchmarkAdapter):
    """Adapter for GenoTEX gene-trait association benchmark.

    Converts GenoTEX unconditional tasks → BenchmarkDataset.
    Gene synonyms are normalized to HGNC symbols in load_task().
    """

    def __init__(self, cache_dir: str | None = None) -> None:
        self._cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR / "genotex"
        self._task_info: dict[str, Any] | None = None
        self._synonyms: dict[str, str] | None = None

    def name(self) -> str:
        return "genotex"

    def _load_metadata(self) -> None:
        """Load task_info.json and gene_synonym.json from cache."""
        if self._task_info is not None:
            return

        task_info_path = self._cache_dir / "metadata" / "task_info.json"
        synonym_path = self._cache_dir / "metadata" / "gene_synonym.json"

        if not task_info_path.exists():
            raise FileNotFoundError(
                f"GenoTEX metadata not found at {task_info_path}. "
                f"Run download() first or manually clone {GENOTEX_REPO_URL}"
            )

        self._task_info = json.loads(task_info_path.read_text())

        if synonym_path.exists():
            raw = json.loads(synonym_path.read_text())
            # Build reverse map: synonym → canonical symbol (uppercase)
            self._synonyms = {}
            for canonical, aliases in raw.items():
                canonical_upper = canonical.upper()
                self._synonyms[canonical_upper] = canonical_upper
                if isinstance(aliases, list):
                    for alias in aliases:
                        self._synonyms[alias.upper()] = canonical_upper
        else:
            self._synonyms = {}
            logger.warning("GenoTEX gene_synonym.json not found — skipping normalization")

    def _normalize_gene(self, symbol: str) -> str:
        """Normalize gene symbol using GenoTEX synonym table."""
        if self._synonyms is None:
            self._load_metadata()
        upper = symbol.upper().strip()
        return self._synonyms.get(upper, upper) if self._synonyms else upper

    def _get_unconditional_tasks(self) -> dict[str, Any]:
        """Filter task_info to unconditional tasks only."""
        self._load_metadata()
        assert self._task_info is not None
        result: dict[str, Any] = {}
        for task_id, info in self._task_info.items():
            # GenoTEX unconditional tasks have condition=None or condition=""
            condition = info.get("condition", "") or ""
            if not condition.strip():
                result[task_id] = info
        return result

    def list_tasks(self) -> list[str]:
        """Return task IDs for all unconditional gene-trait tasks."""
        return sorted(self._get_unconditional_tasks().keys())

    def _load_ground_truth(self, task_id: str) -> list[str]:
        """Load expected gene list from output/regress/{task_id}.json."""
        gt_path = self._cache_dir / "output" / "regress" / f"{task_id}.json"
        if not gt_path.exists():
            logger.warning("GenoTEX ground truth not found: %s", gt_path)
            return []

        data = json.loads(gt_path.read_text())

        # GenoTEX output format: {"genes": [...]} or list directly
        if isinstance(data, dict):
            genes = data.get("genes", data.get("gene_list", []))
        elif isinstance(data, list):
            genes = data
        else:
            return []

        return [self._normalize_gene(g) for g in genes if isinstance(g, str)]

    def load_task(self, task_id: str) -> BenchmarkDataset:
        """Convert a GenoTEX task to BenchmarkDataset.

        Gene symbols are normalized via synonym table.
        expected_fold_changes is empty (Lasso coefficients != log2FC).
        """
        self._load_metadata()
        assert self._task_info is not None

        info = self._task_info.get(task_id)
        if not info:
            raise KeyError(f"GenoTEX task not found: {task_id}")

        trait = info.get("trait", task_id)
        expected_genes = self._load_ground_truth(task_id)

        return BenchmarkDataset(
            id=f"genotex_{task_id}",
            name=f"GenoTEX: {trait}",
            query=f"Identify genes associated with {trait}. "
                  f"Focus on well-established gene-trait associations from GWAS, OMIM, and literature.",
            data_type="expression",
            data_manifest_path="",  # Query-only mode — no data files needed
            budget=2.0,
            expected_genes=expected_genes,
            expected_pathways=[],  # GenoTEX doesn't score pathways
            expected_directions={},  # Not applicable
            expected_fold_changes={},  # Lasso coefficient != log2FC
            ground_truth_confidence="silver",
            benchmark_type="knowledge",
        )

    def download(self, cache_dir: str | None = None) -> None:
        """Download GenoTEX metadata and ground truth files.

        Only downloads metadata/ and output/regress/ (not the full 82GB dataset).
        """
        target = Path(cache_dir) if cache_dir else self._cache_dir
        metadata_dir = target / "metadata"
        output_dir = target / "output" / "regress"

        if (metadata_dir / "task_info.json").exists():
            logger.info("GenoTEX data already present at %s", target)
            return

        metadata_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "GenoTEX data not found. Please download manually:\n"
            "  git clone --depth 1 --filter=blob:none --sparse %s %s\n"
            "  cd %s && git sparse-checkout set metadata output/regress",
            GENOTEX_REPO_URL, target, target,
        )

    def native_score(self, result: BenchmarkResult, task_id: str) -> dict[str, Any]:
        """Compute GenoTEX-native P/R/F1 on gene sets.

        Uses the same set-based scoring as GenoTEX's evaluation script.
        Gene symbols are normalized before comparison.
        """
        expected = set(self._load_ground_truth(task_id))
        predicted = {self._normalize_gene(g) for g in result.predicted_genes}

        if not expected:
            return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "n_expected": 0, "n_predicted": len(predicted)}

        tp = len(predicted & expected)
        precision = tp / len(predicted) if predicted else 0.0
        recall = tp / len(expected)
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "n_expected": len(expected),
            "n_predicted": len(predicted),
            "n_tp": tp,
        }
