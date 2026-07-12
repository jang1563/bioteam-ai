"""End-to-end benchmark tests using mock agent outputs.

Tests the full scoring pipeline: extractor → scorer → BenchmarkResult
without actual LLM calls. BiologyLevelScorer falls back to 0.5 (no Gemini).
"""

from __future__ import annotations

import pytest
from app.benchmarks.datasets import CANCER_PATHWAY, FIXTURE_DEGS, get_dataset, get_suite
from app.benchmarks.extractors import W9ResultExtractor
from app.benchmarks.models import BenchmarkResult
from app.benchmarks.scorers import W9BenchmarkScorer

# ---------------------------------------------------------------------------
# Extractor tests with realistic mock data
# ---------------------------------------------------------------------------


class TestExtractorE2E:
    """Test that extractors pull correct data from realistic step_results."""

    def test_cancer_pathway_gene_extraction(self, cancer_pathway_step_results):
        genes = W9ResultExtractor.extract_gene_list(cancer_pathway_step_results)
        # Should find genes from EXPRESSION_ANALYSIS, LITERATURE_COMPARISON, and CROSS_OMICS
        assert "TP53" in genes
        assert "PIK3CA" in genes
        assert "PTEN" in genes
        assert "ERBB2" in genes
        assert "AKT1" in genes  # from CROSS_OMICS_INTEGRATION
        assert "GATA3" in genes  # from LITERATURE_COMPARISON

    def test_cancer_pathway_pathway_extraction(self, cancer_pathway_step_results):
        pathways = W9ResultExtractor.extract_pathways(cancer_pathway_step_results)
        # Should find from PATHWAY_ENRICHMENT + LITERATURE_COMPARISON + CROSS_OMICS
        pathway_lower = [p.lower() for p in pathways]
        assert any("pi3k" in p for p in pathway_lower)
        assert any("p53" in p for p in pathway_lower)
        assert any("apoptosis" in p for p in pathway_lower)  # from CROSS_OMICS
        assert any("mtor" in p.lower() for p in pathway_lower)  # from CROSS_OMICS

    def test_cancer_pathway_direction_extraction(self, cancer_pathway_step_results):
        directions = W9ResultExtractor.extract_directions(cancer_pathway_step_results)
        assert directions.get("TP53") == "down"
        assert directions.get("PIK3CA") == "up"
        assert directions.get("ERBB2") == "up"
        assert directions.get("PTEN") == "down"

    def test_cancer_pathway_fc_extraction(self, cancer_pathway_step_results):
        fcs = W9ResultExtractor.extract_fold_changes(cancer_pathway_step_results)
        assert abs(fcs.get("PIK3CA", 0) - 1.5) < 0.01
        assert abs(fcs.get("TP53", 0) - (-1.8)) < 0.01

    def test_fixture_degs_gene_extraction(self, fixture_degs_step_results):
        genes = W9ResultExtractor.extract_gene_list(fixture_degs_step_results)
        # All 10 genes from EXPRESSION_ANALYSIS
        assert "BRCA1" in genes
        assert "EGFR" in genes
        assert "KRAS" in genes
        assert len(genes) == 10

    def test_alzheimer_gene_extraction(self, alzheimer_step_results):
        genes = W9ResultExtractor.extract_gene_list(alzheimer_step_results)
        assert "APP" in genes
        assert "PSEN1" in genes
        assert "TREM2" in genes
        assert "BACE1" in genes
        assert "ADAM10" in genes


# ---------------------------------------------------------------------------
# Scorer E2E tests
# ---------------------------------------------------------------------------


class TestScorerE2E:
    """Test the full scorer pipeline with mock data."""

    @pytest.mark.asyncio
    async def test_cancer_pathway_scoring(self, cancer_pathway_step_results):
        extractor = W9ResultExtractor()
        scorer = W9BenchmarkScorer()
        dataset = CANCER_PATHWAY

        predicted_genes = extractor.extract_gene_list(cancer_pathway_step_results)
        predicted_pathways = extractor.extract_pathways(cancer_pathway_step_results)
        predicted_directions = extractor.extract_directions(cancer_pathway_step_results)
        predicted_fcs = extractor.extract_fold_changes(cancer_pathway_step_results)

        result = await scorer.score(
            predicted_genes=predicted_genes,
            predicted_pathways=predicted_pathways,
            predicted_directions=predicted_directions,
            predicted_fcs=predicted_fcs,
            dataset=dataset,
            query=dataset.query,
            run_id="test_e2e_cancer",
            template="literature_only",
            cost_mode="quick",
            total_cost=0.0,
            runtime_seconds=1.0,
        )

        # Gene recall should be meaningful (our mock includes most ground truth genes)
        assert result.gene_recall >= 0.3, f"gene_recall {result.gene_recall:.3f} too low"
        assert result.gene_precision > 0, "gene_precision should be > 0"

        # Pathway overlap should be meaningful
        assert result.pathway_overlap >= 0.3, f"pathway_overlap {result.pathway_overlap:.3f} too low"

        # Direction accuracy should be good (our mock uses correct directions)
        assert result.direction_accuracy >= 0.5, f"direction_accuracy {result.direction_accuracy:.3f}"

        # BioAgent Score composite should be positive
        assert result.bioagent_score > 0, "bioagent_score should be > 0"

        # biology_score fallback (no Gemini in CI)
        assert result.biology_score == 0.5 or result.biology_score > 0

    @pytest.mark.asyncio
    async def test_fixture_degs_scoring(self, fixture_degs_step_results):
        scorer = W9BenchmarkScorer()
        dataset = FIXTURE_DEGS
        ext = W9ResultExtractor()

        result = await scorer.score(
            predicted_genes=ext.extract_gene_list(fixture_degs_step_results),
            predicted_pathways=ext.extract_pathways(fixture_degs_step_results),
            predicted_directions=ext.extract_directions(fixture_degs_step_results),
            predicted_fcs=ext.extract_fold_changes(fixture_degs_step_results),
            dataset=dataset,
            query=dataset.query,
            run_id="test_e2e_degs",
            template="rnaseq_dea",
            cost_mode="quick",
            total_cost=0.0,
            runtime_seconds=1.0,
        )

        # Fixture DEGs have high overlap with ground truth
        assert result.gene_recall >= 0.5
        assert result.pathway_overlap >= 0.3
        assert result.bioagent_score > 0

    @pytest.mark.asyncio
    async def test_alzheimer_native_scoring(self, alzheimer_step_results):
        """Test BioAgent Bench native scoring via adapter."""
        from app.benchmarks.adapters.bioagent_bench import BioAgentBenchAdapter

        adapter = BioAgentBenchAdapter()
        ext = W9ResultExtractor()
        scorer = W9BenchmarkScorer()
        dataset = adapter.load_task("alzheimer_mouse")

        predicted_genes = ext.extract_gene_list(alzheimer_step_results)
        predicted_pathways = ext.extract_pathways(alzheimer_step_results)
        predicted_directions = ext.extract_directions(alzheimer_step_results)
        predicted_fcs = ext.extract_fold_changes(alzheimer_step_results)

        result = await scorer.score(
            predicted_genes=predicted_genes,
            predicted_pathways=predicted_pathways,
            predicted_directions=predicted_directions,
            predicted_fcs=predicted_fcs,
            dataset=dataset,
            query=dataset.query,
            run_id="test_e2e_alzheimer",
            template="literature_only",
            cost_mode="quick",
            total_cost=0.0,
            runtime_seconds=1.0,
        )

        # Annotate with native scoring
        native = adapter.native_score(result, "alzheimer_mouse")
        result.external_benchmark = "bioagent_bench"
        result.external_task_id = "alzheimer_mouse"
        result.native_scores = native

        # BioAgent Bench native: pass=True if >= 1 pathway matches
        assert native["pass"] is True
        assert native["matched_pathways"] >= 1
        assert "Alzheimer's disease" in native["matched_names"]

        # Our scorer should also show meaningful overlap
        assert result.gene_recall >= 0.2
        assert result.pathway_overlap >= 0.2


# ---------------------------------------------------------------------------
# Dataset classification tests
# ---------------------------------------------------------------------------


class TestDatasetClassification:
    """Test is_query_only property and suite definitions."""

    def test_cancer_pathway_is_query_only(self):
        assert CANCER_PATHWAY.is_query_only

    def test_fixture_degs_is_not_query_only(self):
        assert not FIXTURE_DEGS.is_query_only

    def test_query_only_suite(self):
        suite = get_suite("query_only")
        assert len(suite) == 2
        assert all(d.is_query_only for d in suite)

    def test_ci_quick_suite(self):
        suite = get_suite("ci_quick")
        assert len(suite) == 3

    def test_get_dataset_by_id(self):
        ds = get_dataset("cancer_pathway")
        assert ds is not None
        assert ds.id == "cancer_pathway"

    def test_fixture_degs_path_exists(self):
        from pathlib import Path
        assert FIXTURE_DEGS.data_manifest_path
        assert Path(FIXTURE_DEGS.data_manifest_path).exists()


# ---------------------------------------------------------------------------
# BenchmarkResult comparison
# ---------------------------------------------------------------------------


class TestBenchmarkComparison:
    """Test regression detection between runs."""

    def test_compare_detects_regression(self):
        from app.benchmarks.engine import BenchmarkEngine

        run_a = BenchmarkResult(
            dataset_id="test", run_id="a",
            gene_recall=0.8, gene_precision=0.7, bioagent_score=0.75,
        )
        run_b = BenchmarkResult(
            dataset_id="test", run_id="b",
            gene_recall=0.5, gene_precision=0.7, bioagent_score=0.60,
        )

        comp = BenchmarkEngine.compare_runs(run_a, run_b)
        assert comp.regression_detected
        assert "gene_recall" in comp.regression_metrics
        assert "bioagent_score" in comp.regression_metrics

    def test_compare_detects_improvement(self):
        from app.benchmarks.engine import BenchmarkEngine

        run_a = BenchmarkResult(
            dataset_id="test", run_id="a", gene_recall=0.5, bioagent_score=0.50,
        )
        run_b = BenchmarkResult(
            dataset_id="test", run_id="b", gene_recall=0.8, bioagent_score=0.75,
        )

        comp = BenchmarkEngine.compare_runs(run_a, run_b)
        assert not comp.regression_detected
        assert "gene_recall" in comp.improvement_metrics
