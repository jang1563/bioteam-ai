"""BioAgent Bench external benchmark adapter.

BioAgent Bench: 10 end-to-end bioinformatics pipeline tasks hosted on OSF.
(https://osf.io/yp5mq/)

Only the **alzheimer-mouse** task is included. Other tasks (deseq, single-cell)
are "pipeline benchmarks" requiring actual bioinformatics tool execution
(DESeq2, Seurat), which W9's LLM agents cannot reproduce.

alzheimer-mouse is a **pathway analysis** task — the ground truth is
shared pathways between Alzheimer's and mouse models, which is answerable
from literature and biological knowledge.

Scoring: BioAgent Bench uses deterministic rules_match checks:
  - results_match: >= 1 expected pathway found in predictions → pass
  - Expected pathways: Alzheimer's disease pathway, oxidative phosphorylation, etc.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.benchmarks.adapters.base import DEFAULT_CACHE_DIR, BenchmarkAdapter
from app.benchmarks.models import BenchmarkDataset, BenchmarkResult
from app.benchmarks.scorers import PathwayLevelScorer

logger = logging.getLogger(__name__)

# Pre-defined task metadata (avoids downloading full OSF repository)
_ALZHEIMER_MOUSE_TASK = {
    "id": "alzheimer_mouse",
    "name": "Alzheimer's Disease Mouse Model Pathway Analysis",
    "query": (
        "Identify shared biological pathways between Alzheimer's disease "
        "and mouse model gene expression studies. Focus on pathways related "
        "to neurodegeneration, oxidative stress, inflammation, and synaptic function. "
        "Use GO, KEGG, and Reactome databases."
    ),
    "expected_genes": [
        "APP", "PSEN1", "PSEN2", "MAPT", "APOE", "TREM2", "CLU", "BIN1",
        "ABCA7", "CD33", "SORL1", "ADAM10", "BACE1", "GSK3B", "CDK5",
    ],
    "expected_pathways": [
        "Alzheimer's disease",
        "oxidative phosphorylation",
        "synaptic vesicle cycle",
        "neurotrophin signaling",
        "MAPK signaling",
        "calcium signaling",
        "PI3K-Akt signaling",
        "apoptosis",
    ],
    "expected_directions": {
        "APP": "up", "BACE1": "up", "GSK3B": "up",
        "ADAM10": "down", "SORL1": "down",
    },
    "pass_threshold": 1,  # >= 1 pathway overlap = pass (BioAgent Bench rule)
}


class BioAgentBenchAdapter(BenchmarkAdapter):
    """Adapter for BioAgent Bench (alzheimer-mouse task only).

    Other tasks (deseq, single-cell) are excluded as pipeline benchmarks.
    """

    def __init__(self, cache_dir: str | None = None) -> None:
        self._cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR / "bioagent_bench"
        self._tasks = {"alzheimer_mouse": _ALZHEIMER_MOUSE_TASK}

    def name(self) -> str:
        return "bioagent_bench"

    def list_tasks(self) -> list[str]:
        return sorted(self._tasks.keys())

    def load_task(self, task_id: str) -> BenchmarkDataset:
        """Convert BioAgent Bench task to BenchmarkDataset."""
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(
                f"BioAgent Bench task not found: {task_id}. "
                f"Available: {list(self._tasks.keys())} "
                f"(deseq/single-cell excluded as pipeline benchmarks)"
            )

        return BenchmarkDataset(
            id=f"bioagent_{task_id}",
            name=task["name"],
            query=task["query"],
            data_type="pathway",
            data_manifest_path="",  # Query-only mode
            budget=5.0,
            expected_genes=task["expected_genes"],
            expected_pathways=task["expected_pathways"],
            expected_directions=task.get("expected_directions", {}),
            expected_fold_changes={},
            ground_truth_confidence="silver",
            benchmark_type="knowledge",
        )

    def download(self, cache_dir: str | None = None) -> None:
        """Download BioAgent Bench ground truth data.

        The alzheimer-mouse task uses pre-defined metadata (no download needed).
        Extended ground truth can be downloaded from OSF if available.
        """
        target = Path(cache_dir) if cache_dir else self._cache_dir
        target.mkdir(parents=True, exist_ok=True)

        gt_path = target / "alzheimer_mouse_gt.json"
        if gt_path.exists():
            logger.info("BioAgent Bench data already present at %s", target)
            return

        # Save pre-defined ground truth for reproducibility
        gt_path.write_text(json.dumps(_ALZHEIMER_MOUSE_TASK, indent=2))
        logger.info("Saved BioAgent Bench ground truth to %s", gt_path)

    def native_score(self, result: BenchmarkResult, task_id: str) -> dict[str, Any]:
        """Compute BioAgent Bench native scoring.

        BioAgent Bench uses deterministic results_match:
          - Pass if >= pass_threshold expected pathways are found in predictions.
        Also computes pathway overlap count for finer granularity.
        """
        task = self._tasks.get(task_id)
        if not task:
            return {"pass": False, "matched_pathways": 0, "error": f"Unknown task: {task_id}"}

        expected_pathways = task["expected_pathways"]
        predicted_pathways = result.predicted_pathways
        threshold = task.get("pass_threshold", 1)

        # Use PathwayLevelScorer's normalization for consistent matching
        norm = PathwayLevelScorer._normalize_pathway
        pred_norm = {norm(p) for p in predicted_pathways}

        matched: list[str] = []
        for exp in expected_pathways:
            exp_n = norm(exp)
            if exp_n in pred_norm or any(exp_n in p or p in exp_n for p in pred_norm):
                matched.append(exp)

        passed = len(matched) >= threshold

        return {
            "pass": passed,
            "matched_pathways": len(matched),
            "total_expected": len(expected_pathways),
            "matched_names": matched,
            "threshold": threshold,
        }
