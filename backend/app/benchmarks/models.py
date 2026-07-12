"""Benchmark data models for W9 evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class BenchmarkDataset(BaseModel):
    """Definition of a benchmark test case with ground truth."""

    id: str
    name: str
    query: str  # Research question to pass to W9
    data_type: str  # "expression", "variant", "pathway", "multi_omics"
    data_manifest_path: str  # W9 input path
    budget: float | None = None  # Budget override (None → cost_mode default)

    # Ground truth
    expected_genes: list[str] = Field(default_factory=list)
    expected_pathways: list[str] = Field(default_factory=list)
    expected_directions: dict[str, str] = Field(default_factory=dict)  # gene → "up"/"down"
    expected_fold_changes: dict[str, float] = Field(default_factory=dict)  # gene → log2FC

    ground_truth_confidence: str = "silver"  # "gold" / "silver" / "bronze"
    benchmark_type: str = "internal"  # "internal" | "knowledge" | "pipeline"

    @property
    def is_query_only(self) -> bool:
        """True if this dataset needs no data files (LLM knowledge only)."""
        return not self.data_manifest_path or self.benchmark_type == "knowledge"


class BenchmarkResult(BaseModel):
    """Result of a single benchmark run with scores."""

    dataset_id: str
    run_id: str
    template: str = "multi_omics"
    cost_mode: str = "standard"

    # Quantitative scores
    gene_recall: float = 0.0
    gene_precision: float = 0.0
    gene_f1: float = 0.0
    gene_jaccard: float = 0.0
    pathway_overlap: float = 0.0
    direction_accuracy: float = 0.0
    fc_correlation: float = 0.0
    biology_score: float = 0.5  # LLM-as-judge

    # Composite
    bioagent_score: float = 0.0

    # Predictions (stored for external benchmark native scoring)
    predicted_genes: list[str] = Field(default_factory=list)
    predicted_pathways: list[str] = Field(default_factory=list)
    predicted_directions: dict[str, str] = Field(default_factory=dict)
    predicted_fold_changes: dict[str, float] = Field(default_factory=dict)

    # External benchmark tracking
    external_benchmark: str | None = None  # e.g. "genotex", "bioagent_bench"
    external_task_id: str | None = None
    native_scores: dict[str, Any] = Field(default_factory=dict)

    # Meta
    total_cost_usd: float = 0.0
    runtime_seconds: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_biology_fallback: bool = False  # True if Gemini was unavailable
    fair_mode: bool = False  # True if scored without domain hints (fair evaluation)


class BenchmarkComparison(BaseModel):
    """Comparison between two benchmark runs for regression detection."""

    run_a_id: str
    run_b_id: str
    dataset_id: str
    metric_deltas: dict[str, float] = Field(default_factory=dict)
    regression_detected: bool = False
    regression_metrics: list[str] = Field(default_factory=list)
    improvement_metrics: list[str] = Field(default_factory=list)
    # Bootstrap confidence intervals (populated when history is available)
    confidence_intervals: dict[str, list[float]] | None = None  # metric → [lower, upper]
    n_bootstrap_samples: int = 0
    statistically_significant: dict[str, bool] | None = None  # metric → significant?
