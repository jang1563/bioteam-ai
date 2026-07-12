"""Tests for W9 Bioinformatics Benchmark Infrastructure.

Tests cover:
- Extractors: W9 result → flat gene/pathway/direction lists
- Scorers: Gene-level, pathway-level, direction-level, biology-level
- Composite scorer: BioAgent Score formula
- Engine: compare_runs regression detection
- Datasets: Registry completeness
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.benchmarks.adapters.bioagent_bench import BioAgentBenchAdapter
from app.benchmarks.adapters.genotex import GenoTEXAdapter
from app.benchmarks.datasets import BENCHMARK_DATASETS, BENCHMARK_SUITES, get_dataset, get_suite
from app.benchmarks.engine import BenchmarkEngine
from app.benchmarks.extractors import W9ResultExtractor
from app.benchmarks.models import BenchmarkDataset, BenchmarkResult
from app.benchmarks.scorers import (
    FAIR_WEIGHTS,
    BiologyLevelScorer,
    DirectionLevelScorer,
    GeneLevelScorer,
    PathwayLevelScorer,
    W9BenchmarkScorer,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_agent_output(output: dict) -> MagicMock:
    """Create a mock AgentOutput with .output attribute."""
    mock = MagicMock()
    mock.output = output
    return mock


SAMPLE_STEP_RESULTS = {
    "EXPRESSION_ANALYSIS": _make_agent_output({
        "up_regulated": [
            {"gene": "BRCA1", "log2FC": 2.5, "padj": 0.001},
            {"gene": "TP53", "log2FC": 1.8, "padj": 0.003},
            {"gene": "EGFR", "log2FC": 3.2, "padj": 0.0001},
        ],
        "down_regulated": [
            {"gene": "MYC", "log2FC": -1.5, "padj": 0.01},
            {"gene": "PTEN", "log2FC": -2.1, "padj": 0.002},
        ],
    }),
    "VARIANT_ANNOTATION": _make_agent_output({
        "affected_genes": ["BRCA1", "ATM", "CHEK2"],
    }),
    "NETWORK_ANALYSIS": _make_agent_output({
        "hub_genes": ["TP53", "BRCA1", "AKT1"],
    }),
    "PROTEIN_ANALYSIS": _make_agent_output({
        "differentially_abundant": [
            {"gene": "EGFR", "fold_change": 2.1},
            {"gene": "CDH1", "fold_change": 0.5},
        ],
    }),
    "PATHWAY_ENRICHMENT": _make_agent_output({
        "top_pathways": [
            {"name": "PI3K-Akt signaling pathway", "pvalue": 1e-10},
            {"name": "p53 signaling pathway", "pvalue": 1e-8},
            {"name": "cell cycle", "pvalue": 1e-7},
        ],
        "go_bp_top5": [
            {"name": "DNA repair", "pvalue": 1e-6},
        ],
    }),
}

SAMPLE_DATASET = BenchmarkDataset(
    id="test_dataset",
    name="Test Dataset",
    query="Test query for BRCA analysis",
    data_type="expression",
    data_manifest_path="/tmp/test_manifest.json",
    expected_genes=["BRCA1", "TP53", "EGFR", "MYC", "PTEN", "RB1", "KRAS"],
    expected_pathways=["PI3K-Akt signaling", "p53 signaling", "cell cycle", "apoptosis"],
    expected_directions={"BRCA1": "up", "TP53": "up", "EGFR": "up", "MYC": "down", "PTEN": "down"},
    expected_fold_changes={"BRCA1": 2.5, "TP53": 1.8, "EGFR": 3.2, "MYC": -1.5, "PTEN": -2.1},
    ground_truth_confidence="gold",
)


# ---------------------------------------------------------------------------
# Extractor Tests
# ---------------------------------------------------------------------------


class TestW9ResultExtractor:
    """Tests for W9ResultExtractor."""

    def test_extract_gene_list_from_expression(self):
        genes = W9ResultExtractor.extract_gene_list(SAMPLE_STEP_RESULTS)
        assert "BRCA1" in genes
        assert "TP53" in genes
        assert "EGFR" in genes
        assert "MYC" in genes
        assert "PTEN" in genes

    def test_extract_gene_list_from_variants(self):
        genes = W9ResultExtractor.extract_gene_list(SAMPLE_STEP_RESULTS)
        assert "ATM" in genes
        assert "CHEK2" in genes

    def test_extract_gene_list_from_network(self):
        genes = W9ResultExtractor.extract_gene_list(SAMPLE_STEP_RESULTS)
        assert "AKT1" in genes

    def test_extract_gene_list_from_protein(self):
        genes = W9ResultExtractor.extract_gene_list(SAMPLE_STEP_RESULTS)
        assert "CDH1" in genes

    def test_extract_gene_list_deduplicates(self):
        genes = W9ResultExtractor.extract_gene_list(SAMPLE_STEP_RESULTS)
        # BRCA1 appears in expression, variant, network — should be unique
        assert genes.count("BRCA1") == 1

    def test_extract_gene_list_sorted(self):
        genes = W9ResultExtractor.extract_gene_list(SAMPLE_STEP_RESULTS)
        assert genes == sorted(genes)

    def test_extract_gene_list_empty_results(self):
        genes = W9ResultExtractor.extract_gene_list({})
        assert genes == []

    def test_extract_directions(self):
        dirs = W9ResultExtractor.extract_directions(SAMPLE_STEP_RESULTS)
        assert dirs["BRCA1"] == "up"
        assert dirs["TP53"] == "up"
        assert dirs["MYC"] == "down"
        assert dirs["PTEN"] == "down"

    def test_extract_directions_empty(self):
        dirs = W9ResultExtractor.extract_directions({})
        assert dirs == {}

    def test_extract_pathways(self):
        pathways = W9ResultExtractor.extract_pathways(SAMPLE_STEP_RESULTS)
        assert "PI3K-Akt signaling pathway" in pathways
        assert "p53 signaling pathway" in pathways
        assert "cell cycle" in pathways
        assert "DNA repair" in pathways

    def test_extract_pathways_no_duplicates(self):
        pathways = W9ResultExtractor.extract_pathways(SAMPLE_STEP_RESULTS)
        assert len(pathways) == len(set(pathways))

    def test_extract_fold_changes(self):
        fcs = W9ResultExtractor.extract_fold_changes(SAMPLE_STEP_RESULTS)
        assert fcs["BRCA1"] == pytest.approx(2.5)
        assert fcs["EGFR"] == pytest.approx(3.2)
        assert fcs["MYC"] == pytest.approx(-1.5)

    def test_extract_fold_changes_empty(self):
        fcs = W9ResultExtractor.extract_fold_changes({})
        assert fcs == {}

    def test_get_output_handles_dict_directly(self):
        """When step result is a plain dict (not AgentOutput)."""
        results = {"EXPRESSION_ANALYSIS": {"up_regulated": [{"gene": "TEST1"}], "down_regulated": []}}
        genes = W9ResultExtractor.extract_gene_list(results)
        assert "TEST1" in genes


# ---------------------------------------------------------------------------
# Gene Level Scorer Tests
# ---------------------------------------------------------------------------


class TestGeneLevelScorer:
    """Tests for GeneLevelScorer."""

    def test_perfect_overlap(self):
        scores = GeneLevelScorer.score(["A", "B", "C"], ["A", "B", "C"])
        assert scores["gene_recall"] == 1.0
        assert scores["gene_precision"] == 1.0
        assert scores["gene_f1"] == 1.0
        assert scores["gene_jaccard"] == 1.0

    def test_no_overlap(self):
        scores = GeneLevelScorer.score(["A", "B"], ["C", "D"])
        assert scores["gene_recall"] == 0.0
        assert scores["gene_precision"] == 0.0
        assert scores["gene_f1"] == 0.0
        assert scores["gene_jaccard"] == 0.0

    def test_partial_overlap(self):
        scores = GeneLevelScorer.score(["A", "B", "C"], ["A", "B", "D"])
        assert scores["gene_recall"] == pytest.approx(2 / 3)
        assert scores["gene_precision"] == pytest.approx(2 / 3)
        assert scores["gene_jaccard"] == pytest.approx(2 / 4)  # |{A,B}| / |{A,B,C,D}|

    def test_high_recall_low_precision(self):
        scores = GeneLevelScorer.score(
            ["A", "B", "C", "D", "E", "F"],  # 6 predicted, only 2 correct
            ["A", "B"],
        )
        assert scores["gene_recall"] == 1.0
        assert scores["gene_precision"] == pytest.approx(2 / 6)

    def test_case_insensitive(self):
        scores = GeneLevelScorer.score(["brca1", "TP53"], ["BRCA1", "tp53"])
        assert scores["gene_recall"] == 1.0

    def test_empty_expected(self):
        scores = GeneLevelScorer.score(["A"], [])
        assert scores["gene_recall"] == 0.0

    def test_empty_predicted(self):
        scores = GeneLevelScorer.score([], ["A", "B"])
        assert scores["gene_recall"] == 0.0
        assert scores["gene_precision"] == 0.0

    def test_known_values_manual_verification(self):
        """Manual verification: predicted={A,B,C,X,Y}, expected={A,B,C,D,E}"""
        scores = GeneLevelScorer.score(
            ["A", "B", "C", "X", "Y"],
            ["A", "B", "C", "D", "E"],
        )
        # TP=3 (A,B,C), FP=2 (X,Y), FN=2 (D,E)
        assert scores["gene_recall"] == pytest.approx(3 / 5)
        assert scores["gene_precision"] == pytest.approx(3 / 5)
        assert scores["gene_f1"] == pytest.approx(3 / 5)  # 2*0.6*0.6/(0.6+0.6)
        assert scores["gene_jaccard"] == pytest.approx(3 / 7)  # 3 / |{A,B,C,D,E,X,Y}|


# ---------------------------------------------------------------------------
# Pathway Level Scorer Tests
# ---------------------------------------------------------------------------


class TestPathwayLevelScorer:
    """Tests for PathwayLevelScorer."""

    def test_exact_match(self):
        scores = PathwayLevelScorer.score(
            ["PI3K-Akt signaling pathway"],
            ["PI3K-Akt signaling pathway"],
        )
        assert scores["pathway_overlap"] == 1.0

    def test_normalized_match_strips_pathway(self):
        """'PI3K-Akt signaling pathway' normalizes to 'pi3k-akt'."""
        scores = PathwayLevelScorer.score(
            ["PI3K-Akt signaling pathway"],
            ["PI3K-Akt"],
        )
        assert scores["pathway_overlap"] == 1.0

    def test_substring_match(self):
        scores = PathwayLevelScorer.score(
            ["MAPK signaling pathway", "cell cycle"],
            ["MAPK", "cell cycle"],
        )
        assert scores["pathway_overlap"] == 1.0

    def test_no_match(self):
        scores = PathwayLevelScorer.score(
            ["wnt signaling"],
            ["notch signaling"],
        )
        assert scores["pathway_overlap"] == 0.0

    def test_partial_match(self):
        scores = PathwayLevelScorer.score(
            ["PI3K-Akt", "apoptosis", "wnt signaling"],
            ["PI3K-Akt", "apoptosis", "notch signaling", "cell cycle"],
        )
        assert scores["pathway_overlap"] == pytest.approx(2 / 4)

    def test_empty_expected(self):
        scores = PathwayLevelScorer.score(["something"], [])
        assert scores["pathway_overlap"] == 0.0

    def test_fuzzy_match_above_threshold(self):
        """Names with SequenceMatcher ratio >= 0.70 should match via fuzzy tier."""
        scores = PathwayLevelScorer.score(
            ["cardiac muscle contraction"],
            ["cardiac contraction"],
        )
        # Normalized: "cardiac muscle contraction" vs "cardiac contraction"
        # Exact: no. Substring: not contiguous ("cardiac contraction" != "cardiac muscle contraction")
        # SequenceMatcher: "cardiac "(8) + "contraction"(11) → ratio ≈ 0.844 ✓
        assert scores["pathway_overlap"] == 1.0

    def test_fuzzy_match_below_threshold(self):
        """Names with ratio < 0.70 should NOT match."""
        scores = PathwayLevelScorer.score(
            ["toll-like receptor"],
            ["tnf receptor"],
        )
        # Normalized: "toll-like receptor" vs "tnf receptor"
        # No exact/substring match; SequenceMatcher ratio ≈ 0.667 < 0.70
        assert scores["pathway_overlap"] == 0.0


# ---------------------------------------------------------------------------
# Direction Level Scorer Tests
# ---------------------------------------------------------------------------


class TestDirectionLevelScorer:
    """Tests for DirectionLevelScorer."""

    def test_perfect_directions(self):
        scores = DirectionLevelScorer.score(
            {"A": "up", "B": "down"},
            {"A": "up", "B": "down"},
        )
        assert scores["direction_accuracy"] == 1.0

    def test_all_wrong_directions(self):
        scores = DirectionLevelScorer.score(
            {"A": "down", "B": "up"},
            {"A": "up", "B": "down"},
        )
        assert scores["direction_accuracy"] == 0.0

    def test_partial_directions(self):
        scores = DirectionLevelScorer.score(
            {"A": "up", "B": "down", "C": "up"},
            {"A": "up", "B": "up", "C": "up"},
        )
        # A correct, B wrong, C correct → 2/3
        assert scores["direction_accuracy"] == pytest.approx(2 / 3)

    def test_non_overlapping_genes(self):
        scores = DirectionLevelScorer.score(
            {"X": "up", "Y": "down"},
            {"A": "up", "B": "down"},
        )
        assert scores["direction_accuracy"] == 0.0

    def test_empty_expected(self):
        scores = DirectionLevelScorer.score({"A": "up"}, {})
        assert scores["direction_accuracy"] == 0.0

    def test_fc_correlation_perfect(self):
        scores = DirectionLevelScorer.score(
            {"A": "up", "B": "down", "C": "up"},
            {"A": "up", "B": "down", "C": "up"},
            predicted_fcs={"A": 2.0, "B": -1.5, "C": 3.0},
            expected_fcs={"A": 2.0, "B": -1.5, "C": 3.0},
        )
        assert scores["fc_correlation"] == pytest.approx(1.0)

    def test_fc_correlation_negative(self):
        scores = DirectionLevelScorer.score(
            {"A": "down", "B": "up", "C": "down"},
            {"A": "up", "B": "down", "C": "up"},
            predicted_fcs={"A": -2.0, "B": 1.5, "C": -3.0},
            expected_fcs={"A": 2.0, "B": -1.5, "C": 3.0},
        )
        assert scores["fc_correlation"] == pytest.approx(0.0)  # clamped: anti-correlation → 0

    def test_fc_correlation_too_few_genes(self):
        """Need >=3 genes for Spearman correlation."""
        scores = DirectionLevelScorer.score(
            {"A": "up"},
            {"A": "up"},
            predicted_fcs={"A": 2.0},
            expected_fcs={"A": 2.0},
        )
        assert scores["fc_correlation"] == 0.0


# ---------------------------------------------------------------------------
# Biology Level Scorer Tests
# ---------------------------------------------------------------------------


class TestBiologyLevelScorer:
    """Tests for BiologyLevelScorer."""

    @pytest.mark.asyncio
    async def test_fallback_when_gemini_unavailable(self):
        """Should return 0.5 with is_fallback=True when import fails."""
        scorer = BiologyLevelScorer()

        # Test actual fallback by patching GeminiLayer import
        with patch.dict("sys.modules", {"app.llm.gemini_layer": None}):
            result = await scorer.score("test", ["BRCA1"], ["PI3K"], SAMPLE_DATASET)
            assert result["biology_score"] == 0.5
            assert result["is_fallback"] is True

    @pytest.mark.asyncio
    async def test_score_returns_valid_range(self):
        """Score should be between 0 and 1."""
        scorer = BiologyLevelScorer()
        # Patch GeminiLayer to return a valid JSON response
        mock_gemini = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"score": 0.85, "reasoning": "Good analysis"}'
        mock_gemini.complete = AsyncMock(return_value=(mock_response, None))

        with patch("app.llm.gemini_layer.GeminiLayer", return_value=mock_gemini):
            result = await scorer.score("test", ["BRCA1"], ["PI3K"], SAMPLE_DATASET)
            assert 0.0 <= result["biology_score"] <= 1.0


# ---------------------------------------------------------------------------
# Composite Scorer Tests
# ---------------------------------------------------------------------------


class TestW9BenchmarkScorer:
    """Tests for W9BenchmarkScorer composite."""

    @pytest.mark.asyncio
    async def test_composite_score_formula(self):
        """Verify BioAgent Score formula with known inputs."""
        scorer = W9BenchmarkScorer()

        # Mock biology scorer to avoid LLM call
        scorer.biology_scorer = MagicMock()
        scorer.biology_scorer.score = AsyncMock(return_value={
            "biology_score": 0.8,
            "reasoning": "test",
            "is_fallback": False,
        })

        result = await scorer.score(
            predicted_genes=["BRCA1", "TP53", "EGFR", "MYC", "PTEN"],
            predicted_pathways=["PI3K-Akt signaling", "p53 signaling", "cell cycle"],
            predicted_directions={"BRCA1": "up", "TP53": "up", "MYC": "down", "PTEN": "down"},
            predicted_fcs={"BRCA1": 2.5, "TP53": 1.8, "MYC": -1.5, "PTEN": -2.1},
            dataset=SAMPLE_DATASET,
            run_id="test_run",
        )

        assert isinstance(result, BenchmarkResult)
        assert result.dataset_id == "test_dataset"
        assert result.run_id == "test_run"

        # Verify individual scores are populated
        assert result.gene_recall > 0.0
        assert result.gene_precision > 0.0
        assert result.pathway_overlap > 0.0
        assert result.direction_accuracy > 0.0

        # Verify composite in [0, 1]
        assert 0.0 <= result.bioagent_score <= 1.0

    @pytest.mark.asyncio
    async def test_composite_score_weights_sum(self):
        """Verify raw weights sum to 1.0 (renormalization is dynamic at score time)."""
        from app.benchmarks.scorers import BIOAGENT_WEIGHTS
        assert sum(BIOAGENT_WEIGHTS.values()) == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_perfect_score(self):
        """Perfect predictions should yield score ~1.0."""
        scorer = W9BenchmarkScorer()
        scorer.biology_scorer = MagicMock()
        scorer.biology_scorer.score = AsyncMock(return_value={
            "biology_score": 1.0,
            "reasoning": "perfect",
            "is_fallback": False,
        })

        dataset = BenchmarkDataset(
            id="perf",
            name="Perfect",
            query="test",
            data_type="expression",
            data_manifest_path="/tmp/x",
            expected_genes=["A", "B", "C"],
            expected_pathways=["alpha pathway"],
            expected_directions={"A": "up", "B": "down", "C": "up"},
            expected_fold_changes={"A": 2.0, "B": -1.5, "C": 3.0},
        )

        result = await scorer.score(
            predicted_genes=["A", "B", "C"],
            predicted_pathways=["alpha pathway"],
            predicted_directions={"A": "up", "B": "down", "C": "up"},
            predicted_fcs={"A": 2.0, "B": -1.5, "C": 3.0},
            dataset=dataset,
        )

        assert result.bioagent_score >= 0.95

    @pytest.mark.asyncio
    async def test_zero_score(self):
        """No overlap should yield score ~0.075 (only biology fallback × 0.15)."""
        scorer = W9BenchmarkScorer()
        scorer.biology_scorer = MagicMock()
        scorer.biology_scorer.score = AsyncMock(return_value={
            "biology_score": 0.0,
            "reasoning": "no match",
            "is_fallback": True,
        })

        result = await scorer.score(
            predicted_genes=["X", "Y"],
            predicted_pathways=["nothing"],
            predicted_directions={"X": "up"},
            predicted_fcs={},
            dataset=SAMPLE_DATASET,
        )

        assert result.bioagent_score == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_renormalize_missing_directions(self):
        """When expected_directions={}, direction_accuracy weight is excluded and renormalized."""
        scorer = W9BenchmarkScorer()
        scorer.biology_scorer = MagicMock()
        scorer.biology_scorer.score = AsyncMock(return_value={
            "biology_score": 0.8, "reasoning": "ok", "is_fallback": False,
        })

        dataset = BenchmarkDataset(
            id="no_dir", name="No Directions", query="test",
            data_type="expression", data_manifest_path="",
            expected_genes=["A", "B", "C"],
            expected_pathways=["alpha"],
            expected_directions={},      # empty → excluded from composite
            expected_fold_changes={},    # empty → excluded from composite
        )

        result = await scorer.score(
            predicted_genes=["A", "B", "C"],
            predicted_pathways=["alpha"],
            predicted_directions={"A": "up"},
            predicted_fcs={},
            dataset=dataset,
        )

        # With renormalization, only gene_recall(0.40), pathway(0.267),
        # biology(0.20), precision(0.133) are active — all perfect except bio=0.8
        # Score ≈ 0.40*1.0 + 0.267*1.0 + 0.20*0.8 + 0.133*1.0 ≈ 0.96
        assert result.bioagent_score >= 0.95

    @pytest.mark.asyncio
    async def test_renormalize_vs_full_weights(self):
        """Renormalized score should be higher than non-renormalized when directions missing."""
        scorer = W9BenchmarkScorer()
        scorer.biology_scorer = MagicMock()
        scorer.biology_scorer.score = AsyncMock(return_value={
            "biology_score": 0.9, "reasoning": "ok", "is_fallback": False,
        })

        # Dataset WITH directions → no renormalization
        dataset_with = BenchmarkDataset(
            id="with_dir", name="With", query="test",
            data_type="expression", data_manifest_path="",
            expected_genes=["A", "B"],
            expected_pathways=["alpha"],
            expected_directions={"A": "up"},
            expected_fold_changes={"A": 2.0},
        )

        # Dataset WITHOUT directions → renormalized
        dataset_without = BenchmarkDataset(
            id="no_dir", name="Without", query="test",
            data_type="expression", data_manifest_path="",
            expected_genes=["A", "B"],
            expected_pathways=["alpha"],
            expected_directions={},
            expected_fold_changes={},
        )

        result_with = await scorer.score(
            predicted_genes=["A", "B"],
            predicted_pathways=["alpha"],
            predicted_directions={},  # no direction predictions → 0% accuracy
            predicted_fcs={},
            dataset=dataset_with,
        )

        result_without = await scorer.score(
            predicted_genes=["A", "B"],
            predicted_pathways=["alpha"],
            predicted_directions={},
            predicted_fcs={},
            dataset=dataset_without,
        )

        # Without renormalization, direction+fc get 0 → drags score down
        # With renormalization, those weights redistributed → higher score
        assert result_without.bioagent_score > result_with.bioagent_score


# ---------------------------------------------------------------------------
# Engine Tests
# ---------------------------------------------------------------------------


class TestBenchmarkEngine:
    """Tests for BenchmarkEngine."""

    def test_compare_runs_no_regression(self):
        run_a = BenchmarkResult(
            dataset_id="test", run_id="a",
            gene_recall=0.7, gene_precision=0.6, gene_f1=0.65, gene_jaccard=0.5,
            pathway_overlap=0.5, direction_accuracy=0.8, bioagent_score=0.65,
        )
        run_b = BenchmarkResult(
            dataset_id="test", run_id="b",
            gene_recall=0.72, gene_precision=0.62, gene_f1=0.67, gene_jaccard=0.52,
            pathway_overlap=0.52, direction_accuracy=0.82, bioagent_score=0.67,
        )

        comparison = BenchmarkEngine.compare_runs(run_a, run_b)
        assert not comparison.regression_detected
        assert len(comparison.regression_metrics) == 0

    def test_compare_runs_detects_regression(self):
        run_a = BenchmarkResult(
            dataset_id="test", run_id="a",
            gene_recall=0.8, bioagent_score=0.7,
        )
        run_b = BenchmarkResult(
            dataset_id="test", run_id="b",
            gene_recall=0.5, bioagent_score=0.4,  # Dropped by 0.3
        )

        comparison = BenchmarkEngine.compare_runs(run_a, run_b)
        assert comparison.regression_detected
        assert "gene_recall" in comparison.regression_metrics
        assert "bioagent_score" in comparison.regression_metrics

    def test_compare_runs_detects_improvement(self):
        run_a = BenchmarkResult(
            dataset_id="test", run_id="a",
            gene_recall=0.5, bioagent_score=0.4,
        )
        run_b = BenchmarkResult(
            dataset_id="test", run_id="b",
            gene_recall=0.8, bioagent_score=0.7,
        )

        comparison = BenchmarkEngine.compare_runs(run_a, run_b)
        assert not comparison.regression_detected
        assert "gene_recall" in comparison.improvement_metrics
        assert "bioagent_score" in comparison.improvement_metrics

    def test_compare_runs_threshold(self):
        """Custom threshold: 10% regression threshold."""
        run_a = BenchmarkResult(
            dataset_id="test", run_id="a",
            gene_recall=0.8,
        )
        run_b = BenchmarkResult(
            dataset_id="test", run_id="b",
            gene_recall=0.72,  # -0.08, within 10% threshold
        )

        comparison = BenchmarkEngine.compare_runs(run_a, run_b, regression_threshold=0.10)
        assert not comparison.regression_detected

    def test_compare_runs_config_fallback(self):
        """compare_runs uses 0.05 default when config unavailable."""
        run_a = BenchmarkResult(dataset_id="test", run_id="a", gene_recall=0.8)
        run_b = BenchmarkResult(dataset_id="test", run_id="b", gene_recall=0.74)  # -0.06 > 0.05

        comparison = BenchmarkEngine.compare_runs(run_a, run_b)
        assert comparison.regression_detected
        assert "gene_recall" in comparison.regression_metrics

    def test_compare_runs_ci_fields_default_none(self):
        """BenchmarkComparison CI fields default to None/0."""
        run_a = BenchmarkResult(dataset_id="test", run_id="a", gene_recall=0.8)
        run_b = BenchmarkResult(dataset_id="test", run_id="b", gene_recall=0.8)

        comparison = BenchmarkEngine.compare_runs(run_a, run_b)
        assert comparison.confidence_intervals is None
        assert comparison.n_bootstrap_samples == 0
        assert comparison.statistically_significant is None

    def test_bootstrap_ci_basic(self):
        """Bootstrap CI returns lower <= upper for repeated runs."""
        runs = [
            BenchmarkResult(dataset_id="test", run_id=f"r{i}", gene_recall=0.6 + i * 0.02)
            for i in range(10)
        ]
        lo, hi = BenchmarkEngine.compute_bootstrap_ci(runs, "gene_recall", n_samples=500)
        assert lo <= hi
        assert 0.5 <= lo <= 0.8
        assert 0.5 <= hi <= 0.8

    def test_bootstrap_ci_single_result(self):
        """Single result returns degenerate CI: lo == hi."""
        runs = [BenchmarkResult(dataset_id="test", run_id="r0", bioagent_score=0.42)]
        lo, hi = BenchmarkEngine.compute_bootstrap_ci(runs, "bioagent_score")
        assert lo == hi == 0.42

    def test_bootstrap_ci_empty(self):
        """Empty list returns (0.0, 0.0)."""
        lo, hi = BenchmarkEngine.compute_bootstrap_ci([], "gene_recall")
        assert lo == 0.0
        assert hi == 0.0


# ---------------------------------------------------------------------------
# Scorer Weights Tests
# ---------------------------------------------------------------------------


class TestBioAgentWeights:
    """Tests for BIOAGENT_WEIGHTS module constant."""

    def test_weights_sum_to_one(self):
        from app.benchmarks.scorers import BIOAGENT_WEIGHTS
        total = sum(BIOAGENT_WEIGHTS.values())
        assert total == pytest.approx(1.0), f"Weights sum to {total}, expected 1.0"

    def test_weights_all_positive(self):
        from app.benchmarks.scorers import BIOAGENT_WEIGHTS
        for metric, weight in BIOAGENT_WEIGHTS.items():
            assert weight > 0, f"Weight for {metric} must be positive, got {weight}"

    def test_weights_keys_match_metrics(self):
        from app.benchmarks.scorers import BIOAGENT_WEIGHTS
        expected_keys = {"gene_recall", "pathway_overlap", "direction_accuracy", "biology_score", "gene_precision", "fc_correlation"}
        assert set(BIOAGENT_WEIGHTS.keys()) == expected_keys


class TestFairWeights:
    """Tests for FAIR_WEIGHTS module constant."""

    def test_fair_weights_sum_to_one(self):
        total = sum(FAIR_WEIGHTS.values())
        assert total == pytest.approx(1.0), f"Fair weights sum to {total}, expected 1.0"

    def test_fair_weights_no_biology(self):
        assert "biology_score" not in FAIR_WEIGHTS

    def test_fair_weights_equal_pr(self):
        assert FAIR_WEIGHTS["gene_recall"] == FAIR_WEIGHTS["gene_precision"]

    def test_fair_weights_all_positive(self):
        for metric, weight in FAIR_WEIGHTS.items():
            assert weight > 0, f"Fair weight for {metric} must be positive, got {weight}"


# ---------------------------------------------------------------------------
# Fair Mode Scoring Tests
# ---------------------------------------------------------------------------


class TestFairModeScoring:
    """Tests for fair mode evaluation (no domain hints, equal P/R weights)."""

    @pytest.mark.asyncio
    async def test_fair_vs_optimized_weights(self):
        """Fair mode uses FAIR_WEIGHTS (equal P/R, no biology)."""
        scorer = W9BenchmarkScorer()
        scorer.biology_scorer = MagicMock()
        scorer.biology_scorer.score = AsyncMock(return_value={
            "biology_score": 0.95, "reasoning": "ok", "is_fallback": False,
        })

        dataset = BenchmarkDataset(
            id="test", name="Test", query="test",
            data_type="expression", data_manifest_path="",
            expected_genes=["A", "B", "C"],
            expected_pathways=["alpha"],
            expected_directions={"A": "up"},
            expected_fold_changes={"A": 2.0},
        )

        result_opt = await scorer.score(
            predicted_genes=["A", "B", "C", "X", "Y"],  # low precision (3/5)
            predicted_pathways=["alpha"],
            predicted_directions={"A": "up"},
            predicted_fcs={"A": 2.0},
            dataset=dataset,
            fair=False,
        )

        result_fair = await scorer.score(
            predicted_genes=["A", "B", "C", "X", "Y"],
            predicted_pathways=["alpha"],
            predicted_directions={"A": "up"},
            predicted_fcs={"A": 2.0},
            dataset=dataset,
            fair=True,
        )

        # Fair mode penalizes low precision more (0.25 vs 0.10 weight)
        # and excludes inflated biology_score (0.95)
        assert result_fair.bioagent_score < result_opt.bioagent_score
        assert result_fair.fair_mode is True
        assert result_opt.fair_mode is False

    @pytest.mark.asyncio
    async def test_fair_mode_field_set(self):
        """BenchmarkResult.fair_mode reflects the fair parameter."""
        scorer = W9BenchmarkScorer()
        scorer.biology_scorer = MagicMock()
        scorer.biology_scorer.score = AsyncMock(return_value={
            "biology_score": 0.8, "reasoning": "ok", "is_fallback": False,
        })

        dataset = BenchmarkDataset(
            id="test", name="Test", query="test",
            data_type="expression", data_manifest_path="",
            expected_genes=["A"],
            expected_pathways=[],
            expected_directions={},
            expected_fold_changes={},
        )

        result = await scorer.score(
            predicted_genes=["A"],
            predicted_pathways=[],
            predicted_directions={},
            predicted_fcs={},
            dataset=dataset,
            fair=True,
        )
        assert result.fair_mode is True

    def test_benchmark_result_fair_mode_default(self):
        """BenchmarkResult.fair_mode defaults to False."""
        r = BenchmarkResult(dataset_id="test", run_id="r1")
        assert r.fair_mode is False


# ---------------------------------------------------------------------------
# Dataset Registry Tests
# ---------------------------------------------------------------------------


class TestBenchmarkDatasets:
    """Tests for benchmark dataset definitions."""

    def test_all_datasets_have_ids(self):
        for did, ds in BENCHMARK_DATASETS.items():
            assert ds.id == did

    def test_all_datasets_have_expected_genes(self):
        for ds in BENCHMARK_DATASETS.values():
            # fixture_vcf is a minimal CI fixture with no gene-level ground truth
            if ds.ground_truth_confidence == "bronze":
                continue
            assert len(ds.expected_genes) > 0, f"{ds.id} has no expected genes"

    def test_all_datasets_have_queries(self):
        for ds in BENCHMARK_DATASETS.values():
            assert len(ds.query) > 10, f"{ds.id} query too short"

    def test_all_datasets_have_manifest_or_query_only(self):
        for ds in BENCHMARK_DATASETS.values():
            assert ds.data_manifest_path or ds.is_query_only, \
                f"{ds.id} has neither manifest path nor query-only flag"

    def test_suites_reference_valid_datasets(self):
        for suite_id, dataset_ids in BENCHMARK_SUITES.items():
            for did in dataset_ids:
                assert did in BENCHMARK_DATASETS, f"Suite '{suite_id}' references unknown dataset '{did}'"

    def test_get_dataset_returns_correct_dataset(self):
        ds = get_dataset("cancer_pathway")
        assert ds is not None
        assert ds.id == "cancer_pathway"

    def test_get_dataset_returns_none_for_unknown(self):
        assert get_dataset("nonexistent") is None

    def test_get_suite_returns_datasets(self):
        suite = get_suite("core_bioinfo")
        assert len(suite) == 4

    def test_get_suite_empty_for_unknown(self):
        assert get_suite("nonexistent") == []

    def test_gold_confidence_datasets(self):
        gold = [ds for ds in BENCHMARK_DATASETS.values() if ds.ground_truth_confidence == "gold"]
        assert len(gold) >= 2, "Should have at least 2 gold-standard datasets"


# ---------------------------------------------------------------------------
# BioAgentBench Adapter Tests
# ---------------------------------------------------------------------------


class TestBioAgentBenchAdapter:
    """Tests for BioAgentBenchAdapter (alzheimer-mouse task)."""

    def test_name(self):
        adapter = BioAgentBenchAdapter()
        assert adapter.name() == "bioagent_bench"

    def test_list_tasks(self):
        adapter = BioAgentBenchAdapter()
        tasks = adapter.list_tasks()
        assert tasks == ["alzheimer_mouse"]

    def test_load_task_returns_dataset(self):
        adapter = BioAgentBenchAdapter()
        ds = adapter.load_task("alzheimer_mouse")
        assert isinstance(ds, BenchmarkDataset)
        assert ds.id == "bioagent_alzheimer_mouse"
        assert ds.benchmark_type == "knowledge"
        assert ds.ground_truth_confidence == "silver"
        assert len(ds.expected_genes) == 15
        assert len(ds.expected_pathways) == 8

    def test_load_task_query_only(self):
        adapter = BioAgentBenchAdapter()
        ds = adapter.load_task("alzheimer_mouse")
        assert ds.is_query_only is True

    def test_load_task_unknown_raises(self):
        adapter = BioAgentBenchAdapter()
        with pytest.raises(KeyError, match="not found"):
            adapter.load_task("nonexistent")

    def test_native_score_pass(self):
        """Score passes when >=1 expected pathway found."""
        adapter = BioAgentBenchAdapter()
        result = BenchmarkResult(
            dataset_id="test", run_id="r1",
            predicted_pathways=["Alzheimer's disease", "something else"],
        )
        score = adapter.native_score(result, "alzheimer_mouse")
        assert score["pass"] is True
        assert score["matched_pathways"] >= 1

    def test_native_score_fail(self):
        """Score fails when no expected pathway found."""
        adapter = BioAgentBenchAdapter()
        result = BenchmarkResult(
            dataset_id="test", run_id="r1",
            predicted_pathways=["totally unrelated pathway xyz"],
        )
        score = adapter.native_score(result, "alzheimer_mouse")
        assert score["pass"] is False
        assert score["matched_pathways"] == 0

    def test_native_score_partial_match(self):
        """Substring matching works for pathway names."""
        adapter = BioAgentBenchAdapter()
        result = BenchmarkResult(
            dataset_id="test", run_id="r1",
            predicted_pathways=["PI3K-Akt signaling pathway"],
        )
        score = adapter.native_score(result, "alzheimer_mouse")
        assert score["pass"] is True
        assert score["matched_pathways"] >= 1

    def test_native_score_unknown_task(self):
        adapter = BioAgentBenchAdapter()
        result = BenchmarkResult(dataset_id="test", run_id="r1")
        score = adapter.native_score(result, "unknown_task")
        assert score["pass"] is False
        assert "error" in score

    def test_download_idempotent(self, tmp_path):
        adapter = BioAgentBenchAdapter(cache_dir=str(tmp_path))
        adapter.download()
        gt_file = tmp_path / "alzheimer_mouse_gt.json"
        assert gt_file.exists()
        # Second call should not fail
        adapter.download()
        assert gt_file.exists()

    def test_is_available(self):
        adapter = BioAgentBenchAdapter()
        assert adapter.is_available() is True

    def test_load_all(self):
        adapter = BioAgentBenchAdapter()
        datasets = adapter.load_all()
        assert len(datasets) == 1
        assert datasets[0].id == "bioagent_alzheimer_mouse"


# ---------------------------------------------------------------------------
# GenoTEX Adapter Tests
# ---------------------------------------------------------------------------


class TestGenoTEXAdapter:
    """Tests for GenoTEXAdapter with fake metadata."""

    @pytest.fixture()
    def fake_genotex(self, tmp_path):
        """Create minimal GenoTEX metadata for testing."""
        import json

        meta_dir = tmp_path / "metadata"
        meta_dir.mkdir(parents=True)
        output_dir = tmp_path / "output" / "regress"
        output_dir.mkdir(parents=True)

        task_info = {
            "task_001": {"trait": "Diabetes", "condition": ""},
            "task_002": {"trait": "Hypertension", "condition": ""},
            "task_003": {"trait": "Cancer", "condition": "age > 50"},
        }
        (meta_dir / "task_info.json").write_text(json.dumps(task_info))

        synonyms = {"INS": ["INSULIN"], "PPARG": ["PPARG2"]}
        (meta_dir / "gene_synonym.json").write_text(json.dumps(synonyms))

        (output_dir / "task_001.json").write_text(json.dumps({"genes": ["INS", "PPARG", "HNF1A"]}))
        (output_dir / "task_002.json").write_text(json.dumps(["ACE", "AGT"]))

        return tmp_path

    def test_name(self, fake_genotex):
        adapter = GenoTEXAdapter(cache_dir=str(fake_genotex))
        assert adapter.name() == "genotex"

    def test_list_tasks_unconditional_only(self, fake_genotex):
        adapter = GenoTEXAdapter(cache_dir=str(fake_genotex))
        tasks = adapter.list_tasks()
        assert "task_001" in tasks
        assert "task_002" in tasks
        assert "task_003" not in tasks  # conditional → excluded

    def test_load_task(self, fake_genotex):
        adapter = GenoTEXAdapter(cache_dir=str(fake_genotex))
        ds = adapter.load_task("task_001")
        assert isinstance(ds, BenchmarkDataset)
        assert ds.id == "genotex_task_001"
        assert "INS" in ds.expected_genes
        assert ds.benchmark_type == "knowledge"
        assert ds.ground_truth_confidence == "silver"

    def test_load_task_gene_count(self, fake_genotex):
        adapter = GenoTEXAdapter(cache_dir=str(fake_genotex))
        ds = adapter.load_task("task_001")
        assert len(ds.expected_genes) == 3  # INS, PPARG, HNF1A

    def test_gene_normalization(self, fake_genotex):
        adapter = GenoTEXAdapter(cache_dir=str(fake_genotex))
        assert adapter._normalize_gene("INSULIN") == "INS"
        assert adapter._normalize_gene("PPARG2") == "PPARG"
        assert adapter._normalize_gene("HNF1A") == "HNF1A"  # no synonym → passthrough

    def test_native_score(self, fake_genotex):
        adapter = GenoTEXAdapter(cache_dir=str(fake_genotex))
        result = BenchmarkResult(
            dataset_id="test", run_id="r1",
            predicted_genes=["INS", "PPARG", "FAKE_GENE"],
        )
        score = adapter.native_score(result, "task_001")
        assert score["n_expected"] == 3
        assert score["n_predicted"] == 3
        assert score["n_tp"] == 2  # INS + PPARG match
        assert score["recall"] == pytest.approx(2 / 3, abs=1e-3)  # native_score rounds to 4 decimals
        assert score["precision"] == pytest.approx(2 / 3, abs=1e-3)

    def test_native_score_with_synonym(self, fake_genotex):
        """Predicted gene uses synonym; should still match after normalization."""
        adapter = GenoTEXAdapter(cache_dir=str(fake_genotex))
        result = BenchmarkResult(
            dataset_id="test", run_id="r1",
            predicted_genes=["INSULIN"],  # synonym for INS
        )
        score = adapter.native_score(result, "task_001")
        assert score["n_tp"] == 1

    def test_load_task_unknown_raises(self, fake_genotex):
        adapter = GenoTEXAdapter(cache_dir=str(fake_genotex))
        with pytest.raises(KeyError, match="not found"):
            adapter.load_task("nonexistent")

    def test_metadata_not_found_raises(self, tmp_path):
        adapter = GenoTEXAdapter(cache_dir=str(tmp_path))
        with pytest.raises(FileNotFoundError, match="metadata not found"):
            adapter.list_tasks()

    def test_load_task_list_format(self, fake_genotex):
        """task_002 ground truth is stored as a plain list (not dict)."""
        adapter = GenoTEXAdapter(cache_dir=str(fake_genotex))
        ds = adapter.load_task("task_002")
        assert "ACE" in ds.expected_genes
        assert "AGT" in ds.expected_genes

    def test_is_available(self, fake_genotex):
        adapter = GenoTEXAdapter(cache_dir=str(fake_genotex))
        assert adapter.is_available() is True

    def test_not_available_without_data(self, tmp_path):
        adapter = GenoTEXAdapter(cache_dir=str(tmp_path))
        assert adapter.is_available() is False
