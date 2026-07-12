"""Tests for external benchmark adapters (Phase 7-F).

Tests cover:
- BenchmarkAdapter ABC contract
- GenoTEX adapter: task loading, gene normalization, native scoring
- BioAgent Bench adapter: task loading, pathway matching, pass/fail scoring
- BenchmarkEngine.run_external() integration
- PathwayLevelScorer KEGG species suffix stripping
- BenchmarkResult new fields (predicted_*, external_*, native_scores)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.benchmarks.adapters.base import BenchmarkAdapter
from app.benchmarks.adapters.bioagent_bench import BioAgentBenchAdapter
from app.benchmarks.adapters.genotex import GenoTEXAdapter
from app.benchmarks.engine import BenchmarkEngine
from app.benchmarks.models import BenchmarkDataset, BenchmarkResult
from app.benchmarks.scorers import PathwayLevelScorer

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def genotex_cache(tmp_path: Path) -> Path:
    """Create a minimal GenoTEX cache directory with test data."""
    metadata_dir = tmp_path / "metadata"
    output_dir = tmp_path / "output" / "regress"
    metadata_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    # task_info.json — 3 tasks: 2 unconditional, 1 conditional
    task_info = {
        "trait_alzheimer": {
            "trait": "Alzheimer's disease",
            "condition": "",
        },
        "trait_diabetes": {
            "trait": "Type 2 diabetes",
            "condition": None,
        },
        "trait_cancer_conditional": {
            "trait": "Breast cancer",
            "condition": "postmenopausal women",  # Should be excluded
        },
    }
    (metadata_dir / "task_info.json").write_text(json.dumps(task_info))

    # gene_synonym.json — canonical → aliases
    synonyms = {
        "APP": ["A4", "AD1"],
        "MAPT": ["TAU", "MTBT1"],
        "TP53": ["P53", "LFS1"],
    }
    (metadata_dir / "gene_synonym.json").write_text(json.dumps(synonyms))

    # Ground truth files
    (output_dir / "trait_alzheimer.json").write_text(json.dumps({
        "genes": ["APP", "MAPT", "PSEN1", "APOE", "TREM2"],
    }))
    (output_dir / "trait_diabetes.json").write_text(json.dumps(
        ["TCF7L2", "PPARG", "KCNJ11", "SLC30A8", "CDKN2A"]
    ))

    return tmp_path


@pytest.fixture
def bioagent_cache(tmp_path: Path) -> Path:
    """Create a BioAgent Bench cache directory."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# GenoTEX Adapter Tests
# ---------------------------------------------------------------------------


class TestGenoTEXAdapter:
    """Tests for GenoTEXAdapter."""

    def test_name(self, genotex_cache: Path):
        adapter = GenoTEXAdapter(cache_dir=str(genotex_cache))
        assert adapter.name() == "genotex"

    def test_list_tasks_filters_unconditional(self, genotex_cache: Path):
        adapter = GenoTEXAdapter(cache_dir=str(genotex_cache))
        tasks = adapter.list_tasks()
        assert "trait_alzheimer" in tasks
        assert "trait_diabetes" in tasks
        assert "trait_cancer_conditional" not in tasks  # Conditional → excluded
        assert len(tasks) == 2

    def test_load_task_alzheimer(self, genotex_cache: Path):
        adapter = GenoTEXAdapter(cache_dir=str(genotex_cache))
        dataset = adapter.load_task("trait_alzheimer")

        assert isinstance(dataset, BenchmarkDataset)
        assert dataset.id == "genotex_trait_alzheimer"
        assert "Alzheimer" in dataset.name
        assert "Alzheimer" in dataset.query
        assert dataset.data_type == "expression"
        assert dataset.data_manifest_path == ""  # Query-only
        assert dataset.budget == 2.0
        assert dataset.benchmark_type == "knowledge"
        assert len(dataset.expected_genes) == 5
        assert "APP" in dataset.expected_genes
        assert "MAPT" in dataset.expected_genes

    def test_load_task_diabetes(self, genotex_cache: Path):
        adapter = GenoTEXAdapter(cache_dir=str(genotex_cache))
        dataset = adapter.load_task("trait_diabetes")
        assert "diabetes" in dataset.query.lower()
        assert "TCF7L2" in dataset.expected_genes

    def test_load_task_unknown_raises(self, genotex_cache: Path):
        adapter = GenoTEXAdapter(cache_dir=str(genotex_cache))
        with pytest.raises(KeyError, match="nonexistent"):
            adapter.load_task("nonexistent")

    def test_load_task_no_fold_changes(self, genotex_cache: Path):
        """GenoTEX doesn't use fold changes (Lasso != log2FC)."""
        adapter = GenoTEXAdapter(cache_dir=str(genotex_cache))
        dataset = adapter.load_task("trait_alzheimer")
        assert dataset.expected_fold_changes == {}
        assert dataset.expected_directions == {}
        assert dataset.expected_pathways == []

    def test_gene_synonym_normalization(self, genotex_cache: Path):
        adapter = GenoTEXAdapter(cache_dir=str(genotex_cache))
        adapter._load_metadata()

        # Canonical stays canonical
        assert adapter._normalize_gene("APP") == "APP"
        # Alias → canonical
        assert adapter._normalize_gene("A4") == "APP"
        assert adapter._normalize_gene("TAU") == "MAPT"
        assert adapter._normalize_gene("P53") == "TP53"
        # Case insensitive
        assert adapter._normalize_gene("a4") == "APP"
        assert adapter._normalize_gene("tau") == "MAPT"
        # Unknown stays as-is (uppercase)
        assert adapter._normalize_gene("UNKNOWNGENE") == "UNKNOWNGENE"

    def test_native_score_perfect(self, genotex_cache: Path):
        adapter = GenoTEXAdapter(cache_dir=str(genotex_cache))
        result = BenchmarkResult(
            dataset_id="genotex_trait_alzheimer",
            run_id="test",
            predicted_genes=["APP", "MAPT", "PSEN1", "APOE", "TREM2"],
        )
        scores = adapter.native_score(result, "trait_alzheimer")
        assert scores["precision"] == 1.0
        assert scores["recall"] == 1.0
        assert scores["f1"] == 1.0
        assert scores["n_tp"] == 5

    def test_native_score_partial(self, genotex_cache: Path):
        adapter = GenoTEXAdapter(cache_dir=str(genotex_cache))
        result = BenchmarkResult(
            dataset_id="genotex_trait_alzheimer",
            run_id="test",
            predicted_genes=["APP", "MAPT", "EXTRA1", "EXTRA2"],
        )
        scores = adapter.native_score(result, "trait_alzheimer")
        assert scores["recall"] == pytest.approx(2 / 5)  # 2/5 expected found
        assert scores["precision"] == pytest.approx(2 / 4)  # 2/4 predicted correct
        assert scores["n_tp"] == 2

    def test_native_score_no_overlap(self, genotex_cache: Path):
        adapter = GenoTEXAdapter(cache_dir=str(genotex_cache))
        result = BenchmarkResult(
            dataset_id="test",
            run_id="test",
            predicted_genes=["X", "Y", "Z"],
        )
        scores = adapter.native_score(result, "trait_alzheimer")
        assert scores["precision"] == 0.0
        assert scores["recall"] == 0.0
        assert scores["f1"] == 0.0

    def test_native_score_empty_predictions(self, genotex_cache: Path):
        adapter = GenoTEXAdapter(cache_dir=str(genotex_cache))
        result = BenchmarkResult(dataset_id="test", run_id="test", predicted_genes=[])
        scores = adapter.native_score(result, "trait_alzheimer")
        assert scores["precision"] == 0.0
        assert scores["recall"] == 0.0

    def test_native_score_synonym_resolution(self, genotex_cache: Path):
        """Predicted 'TAU' should match expected 'MAPT' via synonym normalization."""
        adapter = GenoTEXAdapter(cache_dir=str(genotex_cache))
        result = BenchmarkResult(
            dataset_id="test",
            run_id="test",
            predicted_genes=["TAU", "A4"],  # Aliases for MAPT, APP
        )
        scores = adapter.native_score(result, "trait_alzheimer")
        assert scores["n_tp"] == 2
        assert scores["recall"] == pytest.approx(2 / 5)

    def test_load_all(self, genotex_cache: Path):
        adapter = GenoTEXAdapter(cache_dir=str(genotex_cache))
        datasets = adapter.load_all()
        assert len(datasets) == 2
        assert all(isinstance(d, BenchmarkDataset) for d in datasets)

    def test_is_available(self, genotex_cache: Path):
        adapter = GenoTEXAdapter(cache_dir=str(genotex_cache))
        assert adapter.is_available()

    def test_is_available_no_data(self, tmp_path: Path):
        adapter = GenoTEXAdapter(cache_dir=str(tmp_path / "nonexistent"))
        assert not adapter.is_available()

    def test_download_creates_dirs(self, tmp_path: Path):
        target = tmp_path / "download_test"
        adapter = GenoTEXAdapter(cache_dir=str(target))
        adapter.download(str(target))
        # Should create directories even if data not available
        assert (target / "metadata").exists()
        assert (target / "output" / "regress").exists()

    def test_ground_truth_list_format(self, genotex_cache: Path):
        """Ground truth can be a plain list (trait_diabetes)."""
        adapter = GenoTEXAdapter(cache_dir=str(genotex_cache))
        dataset = adapter.load_task("trait_diabetes")
        assert "TCF7L2" in dataset.expected_genes
        assert len(dataset.expected_genes) == 5


# ---------------------------------------------------------------------------
# BioAgent Bench Adapter Tests
# ---------------------------------------------------------------------------


class TestBioAgentBenchAdapter:
    """Tests for BioAgentBenchAdapter."""

    def test_name(self, bioagent_cache: Path):
        adapter = BioAgentBenchAdapter(cache_dir=str(bioagent_cache))
        assert adapter.name() == "bioagent_bench"

    def test_list_tasks(self, bioagent_cache: Path):
        adapter = BioAgentBenchAdapter(cache_dir=str(bioagent_cache))
        tasks = adapter.list_tasks()
        assert tasks == ["alzheimer_mouse"]

    def test_load_task_alzheimer_mouse(self, bioagent_cache: Path):
        adapter = BioAgentBenchAdapter(cache_dir=str(bioagent_cache))
        dataset = adapter.load_task("alzheimer_mouse")

        assert isinstance(dataset, BenchmarkDataset)
        assert dataset.id == "bioagent_alzheimer_mouse"
        assert "Alzheimer" in dataset.name
        assert dataset.data_type == "pathway"
        assert dataset.data_manifest_path == ""
        assert dataset.budget == 5.0
        assert dataset.benchmark_type == "knowledge"
        assert len(dataset.expected_genes) > 0
        assert "APP" in dataset.expected_genes
        assert len(dataset.expected_pathways) > 0
        assert "Alzheimer's disease" in dataset.expected_pathways

    def test_load_task_unknown_raises(self, bioagent_cache: Path):
        adapter = BioAgentBenchAdapter(cache_dir=str(bioagent_cache))
        with pytest.raises(KeyError, match="deseq"):
            adapter.load_task("deseq")

    def test_load_task_has_directions(self, bioagent_cache: Path):
        adapter = BioAgentBenchAdapter(cache_dir=str(bioagent_cache))
        dataset = adapter.load_task("alzheimer_mouse")
        assert dataset.expected_directions.get("APP") == "up"
        assert dataset.expected_directions.get("SORL1") == "down"

    def test_native_score_pass(self, bioagent_cache: Path):
        """Predictions with >=1 matching pathway should pass."""
        adapter = BioAgentBenchAdapter(cache_dir=str(bioagent_cache))
        result = BenchmarkResult(
            dataset_id="bioagent_alzheimer_mouse",
            run_id="test",
            predicted_pathways=["Alzheimer's disease", "cell cycle", "random pathway"],
        )
        scores = adapter.native_score(result, "alzheimer_mouse")
        assert scores["pass"] is True
        assert scores["matched_pathways"] >= 1
        assert "Alzheimer's disease" in scores["matched_names"]

    def test_native_score_fail(self, bioagent_cache: Path):
        """No matching pathways should fail."""
        adapter = BioAgentBenchAdapter(cache_dir=str(bioagent_cache))
        result = BenchmarkResult(
            dataset_id="test",
            run_id="test",
            predicted_pathways=["unrelated pathway", "another unrelated"],
        )
        scores = adapter.native_score(result, "alzheimer_mouse")
        assert scores["pass"] is False
        assert scores["matched_pathways"] == 0

    def test_native_score_fuzzy_match(self, bioagent_cache: Path):
        """Pathway matching should use normalized comparison."""
        adapter = BioAgentBenchAdapter(cache_dir=str(bioagent_cache))
        result = BenchmarkResult(
            dataset_id="test",
            run_id="test",
            predicted_pathways=["MAPK signaling pathway", "PI3K-Akt signaling pathway"],
        )
        scores = adapter.native_score(result, "alzheimer_mouse")
        assert scores["pass"] is True
        assert scores["matched_pathways"] >= 2

    def test_native_score_empty_predictions(self, bioagent_cache: Path):
        adapter = BioAgentBenchAdapter(cache_dir=str(bioagent_cache))
        result = BenchmarkResult(
            dataset_id="test",
            run_id="test",
            predicted_pathways=[],
        )
        scores = adapter.native_score(result, "alzheimer_mouse")
        assert scores["pass"] is False
        assert scores["matched_pathways"] == 0

    def test_download_saves_ground_truth(self, bioagent_cache: Path):
        adapter = BioAgentBenchAdapter(cache_dir=str(bioagent_cache))
        adapter.download()
        gt_path = bioagent_cache / "alzheimer_mouse_gt.json"
        assert gt_path.exists()
        data = json.loads(gt_path.read_text())
        assert data["id"] == "alzheimer_mouse"

    def test_is_available(self, bioagent_cache: Path):
        adapter = BioAgentBenchAdapter(cache_dir=str(bioagent_cache))
        assert adapter.is_available()


# ---------------------------------------------------------------------------
# PathwayLevelScorer KEGG Regex Tests
# ---------------------------------------------------------------------------


class TestPathwayKEGGNormalization:
    """Tests for KEGG species suffix stripping in PathwayLevelScorer."""

    def test_kegg_homo_sapiens_suffix(self):
        norm = PathwayLevelScorer._normalize_pathway
        assert norm("Phagosome Homo sapiens hsa04145") == "phagosome"

    def test_kegg_mus_musculus_suffix(self):
        norm = PathwayLevelScorer._normalize_pathway
        assert norm("MAPK signaling pathway Mus musculus mmu04010") == "mapk"

    def test_kegg_rattus_norvegicus_suffix(self):
        norm = PathwayLevelScorer._normalize_pathway
        assert norm("Apoptosis Rattus norvegicus rno04210") == "apoptosis"

    def test_kegg_no_suffix(self):
        """Normal pathway names should not be affected."""
        norm = PathwayLevelScorer._normalize_pathway
        assert norm("PI3K-Akt signaling pathway") == "pi3k-akt"

    def test_kegg_suffix_enables_cross_match(self):
        """KEGG name with species suffix should match plain name."""
        scores = PathwayLevelScorer.score(
            ["Phagosome Homo sapiens hsa04145"],
            ["phagosome"],
        )
        assert scores["pathway_overlap"] == 1.0

    def test_kegg_suffix_drosophila(self):
        norm = PathwayLevelScorer._normalize_pathway
        assert norm("Wnt signaling Drosophila melanogaster dme04310") == "wnt"

    def test_kegg_suffix_cerevisiae(self):
        norm = PathwayLevelScorer._normalize_pathway
        assert norm("Cell cycle Saccharomyces cerevisiae sce04111") == "cell cycle"


# ---------------------------------------------------------------------------
# BenchmarkResult New Fields Tests
# ---------------------------------------------------------------------------


class TestBenchmarkResultNewFields:
    """Tests for new fields added to BenchmarkResult."""

    def test_predicted_fields_default_empty(self):
        result = BenchmarkResult(dataset_id="test", run_id="test")
        assert result.predicted_genes == []
        assert result.predicted_pathways == []
        assert result.predicted_directions == {}
        assert result.predicted_fold_changes == {}

    def test_predicted_fields_populated(self):
        result = BenchmarkResult(
            dataset_id="test",
            run_id="test",
            predicted_genes=["BRCA1", "TP53"],
            predicted_pathways=["PI3K-Akt"],
            predicted_directions={"BRCA1": "up"},
            predicted_fold_changes={"BRCA1": 2.5},
        )
        assert result.predicted_genes == ["BRCA1", "TP53"]
        assert result.predicted_pathways == ["PI3K-Akt"]
        assert result.predicted_directions == {"BRCA1": "up"}
        assert result.predicted_fold_changes == {"BRCA1": 2.5}

    def test_external_fields_default_none(self):
        result = BenchmarkResult(dataset_id="test", run_id="test")
        assert result.external_benchmark is None
        assert result.external_task_id is None
        assert result.native_scores == {}

    def test_external_fields_populated(self):
        result = BenchmarkResult(
            dataset_id="test",
            run_id="test",
            external_benchmark="genotex",
            external_task_id="trait_alzheimer",
            native_scores={"precision": 0.8, "recall": 0.6, "f1": 0.686},
        )
        assert result.external_benchmark == "genotex"
        assert result.external_task_id == "trait_alzheimer"
        assert result.native_scores["f1"] == pytest.approx(0.686)

    def test_benchmark_type_default(self):
        dataset = BenchmarkDataset(
            id="test", name="Test", query="test",
            data_type="expression", data_manifest_path="/tmp/x",
        )
        assert dataset.benchmark_type == "internal"

    def test_benchmark_type_knowledge(self):
        dataset = BenchmarkDataset(
            id="test", name="Test", query="test",
            data_type="expression", data_manifest_path="",
            benchmark_type="knowledge",
        )
        assert dataset.benchmark_type == "knowledge"

    def test_result_serialization_roundtrip(self):
        """Ensure new fields survive JSON roundtrip."""
        result = BenchmarkResult(
            dataset_id="test",
            run_id="test",
            predicted_genes=["A", "B"],
            external_benchmark="genotex",
            native_scores={"f1": 0.75},
        )
        data = result.model_dump()
        restored = BenchmarkResult(**data)
        assert restored.predicted_genes == ["A", "B"]
        assert restored.external_benchmark == "genotex"
        assert restored.native_scores == {"f1": 0.75}


# ---------------------------------------------------------------------------
# BenchmarkEngine External Integration Tests
# ---------------------------------------------------------------------------


class TestBenchmarkEngineExternal:
    """Tests for BenchmarkEngine.run_external() and _infer_template()."""

    def test_infer_template_expression(self):
        dataset = BenchmarkDataset(
            id="test", name="test", query="test",
            data_type="expression", data_manifest_path="",
        )
        assert BenchmarkEngine._infer_template(dataset) == "rnaseq_dea"

    def test_infer_template_variant(self):
        dataset = BenchmarkDataset(
            id="test", name="test", query="test",
            data_type="variant", data_manifest_path="",
        )
        assert BenchmarkEngine._infer_template(dataset) == "variant_annotation"

    def test_infer_template_pathway(self):
        dataset = BenchmarkDataset(
            id="test", name="test", query="test",
            data_type="pathway", data_manifest_path="",
        )
        assert BenchmarkEngine._infer_template(dataset) == "pathway_analysis"

    def test_infer_template_multi_omics(self):
        dataset = BenchmarkDataset(
            id="test", name="test", query="test",
            data_type="multi_omics", data_manifest_path="",
        )
        assert BenchmarkEngine._infer_template(dataset) == "multi_omics"

    def test_infer_template_unknown_defaults_to_rnaseq(self):
        dataset = BenchmarkDataset(
            id="test", name="test", query="test",
            data_type="unknown_type", data_manifest_path="",
        )
        assert BenchmarkEngine._infer_template(dataset) == "rnaseq_dea"

    @pytest.mark.asyncio
    async def test_run_external_calls_adapter_methods(self):
        """Verify run_external() orchestration: load_task → run_dataset → native_score."""
        # Mock adapter
        mock_adapter = MagicMock(spec=BenchmarkAdapter)
        mock_adapter.name.return_value = "test_bench"
        mock_adapter.list_tasks.return_value = ["task_1"]
        mock_adapter.load_task.return_value = BenchmarkDataset(
            id="ext_task_1", name="Test Task", query="test query",
            data_type="expression", data_manifest_path="",
            expected_genes=["A", "B"], benchmark_type="knowledge",
        )
        mock_adapter.native_score.return_value = {"f1": 0.8}

        # Mock engine to avoid actual W9 execution
        engine = BenchmarkEngine()
        mock_result = BenchmarkResult(
            dataset_id="ext_task_1", run_id="test",
            predicted_genes=["A", "C"],
            gene_recall=0.5, bioagent_score=0.4,
        )
        engine.run_dataset = AsyncMock(return_value=mock_result)

        results = await engine.run_external(mock_adapter, cost_mode="quick")

        assert len(results) == 1
        assert results[0].external_benchmark == "test_bench"
        assert results[0].external_task_id == "task_1"
        assert results[0].native_scores == {"f1": 0.8}

        mock_adapter.load_task.assert_called_once_with("task_1")
        mock_adapter.native_score.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_external_with_specific_task_ids(self):
        """run_external() should only run specified task IDs."""
        mock_adapter = MagicMock(spec=BenchmarkAdapter)
        mock_adapter.name.return_value = "test"
        mock_adapter.list_tasks.return_value = ["a", "b", "c"]
        mock_adapter.load_task.return_value = BenchmarkDataset(
            id="test", name="Test", query="test",
            data_type="pathway", data_manifest_path="",
            expected_genes=["X"], benchmark_type="knowledge",
        )
        mock_adapter.native_score.return_value = {}

        engine = BenchmarkEngine()
        engine.run_dataset = AsyncMock(return_value=BenchmarkResult(
            dataset_id="test", run_id="test",
        ))

        results = await engine.run_external(mock_adapter, task_ids=["b"], cost_mode="quick")
        assert len(results) == 1
        mock_adapter.load_task.assert_called_once_with("b")

    @pytest.mark.asyncio
    async def test_run_external_with_template_override(self):
        """Template override should bypass _infer_template()."""
        mock_adapter = MagicMock(spec=BenchmarkAdapter)
        mock_adapter.name.return_value = "test"
        mock_adapter.list_tasks.return_value = ["task_1"]
        mock_adapter.load_task.return_value = BenchmarkDataset(
            id="test", name="Test", query="test",
            data_type="expression", data_manifest_path="",
            benchmark_type="knowledge",
        )
        mock_adapter.native_score.return_value = {}

        engine = BenchmarkEngine()
        engine.run_dataset = AsyncMock(return_value=BenchmarkResult(
            dataset_id="test", run_id="test",
        ))

        await engine.run_external(mock_adapter, template="literature_only", cost_mode="quick")

        # Verify the template override was used
        call_args = engine.run_dataset.call_args
        assert call_args[0][1] == "literature_only"  # template argument

    @pytest.mark.asyncio
    async def test_run_external_handles_task_failure(self):
        """If a task fails, skip it and continue with others."""
        mock_adapter = MagicMock(spec=BenchmarkAdapter)
        mock_adapter.name.return_value = "test"
        mock_adapter.list_tasks.return_value = ["task_ok", "task_fail"]

        call_count = 0

        def load_side_effect(task_id):
            nonlocal call_count
            call_count += 1
            if task_id == "task_fail":
                raise ValueError("bad task")
            return BenchmarkDataset(
                id=f"test_{task_id}", name="Test", query="test",
                data_type="expression", data_manifest_path="",
                benchmark_type="knowledge",
            )

        mock_adapter.load_task.side_effect = load_side_effect
        mock_adapter.native_score.return_value = {}

        engine = BenchmarkEngine()
        engine.run_dataset = AsyncMock(return_value=BenchmarkResult(
            dataset_id="test", run_id="test",
        ))

        results = await engine.run_external(mock_adapter, cost_mode="quick")
        assert len(results) == 1  # Only task_ok succeeded


# ---------------------------------------------------------------------------
# Composite Scorer Predicted Fields Integration
# ---------------------------------------------------------------------------


class TestScorerPredictedFields:
    """Verify that W9BenchmarkScorer includes predicted fields in results."""

    @pytest.mark.asyncio
    async def test_scorer_populates_predicted_fields(self):
        from app.benchmarks.scorers import W9BenchmarkScorer

        scorer = W9BenchmarkScorer()
        scorer.biology_scorer = MagicMock()
        scorer.biology_scorer.score = AsyncMock(return_value={
            "biology_score": 0.7, "reasoning": "ok", "is_fallback": False,
        })

        dataset = BenchmarkDataset(
            id="test", name="Test", query="test",
            data_type="expression", data_manifest_path="/tmp/x",
            expected_genes=["A", "B"], expected_pathways=["p53"],
        )

        result = await scorer.score(
            predicted_genes=["A", "C", "D"],
            predicted_pathways=["p53 signaling pathway"],
            predicted_directions={"A": "up"},
            predicted_fcs={"A": 2.0},
            dataset=dataset,
            run_id="scorer_test",
        )

        assert result.predicted_genes == ["A", "C", "D"]
        assert result.predicted_pathways == ["p53 signaling pathway"]
        assert result.predicted_directions == {"A": "up"}
        assert result.predicted_fold_changes == {"A": 2.0}
