"""System-level W7 Data Integrity Audit E2E — full pipeline with planted errors.

Tests the complete 8-step W7 pipeline:
  COLLECT → GENE_CHECK → STAT_CHECK → RETRACTION_CHECK
  → METADATA_CHECK → IMAGE_CHECK → LLM_CONTEXTUALIZE → REPORT

Planted error text is injected via instance.query (COLLECT always falls back to query).
Mock retraction client is injected for DOI checking.
MockLLMLayer with no presets: IntegrityContextAssessment defaults pass through.

Expected findings (8):
  - 1× p_value_mismatch (t(28)=2.05, p=.500)
  - 1× grimmer_sd_failure (SD=2.50, N=10)
  - 1× grimmer_percent_failure (33.3%, N=10)
  - 3× gene_name_error (1-Mar, 7-Sep, 2-Dec)
  - 1× retracted_reference (Wakefield DOI)
  - 1× genome_build_inconsistency (hg19+hg38)
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.registry import create_registry
from app.engines.integrity.finding_models import RetractionStatus
from app.engines.integrity.retraction_checker import RetractionChecker
from app.llm.mock_layer import MockLLMLayer
from app.models.workflow import WorkflowInstance
from app.workflows.runners.w7_integrity import W7IntegrityRunner

# ══════════════════════════════════════════════════════════════════
# Planted error text
# ══════════════════════════════════════════════════════════════════

PARAGRAPH_STATS = (
    "In the treated group (M = 4.20, SD = 2.50, N = 10), BMI showed "
    "significant change. A paired t-test confirmed the effect, t(28) = 2.05, p = .500. "
    "Response rate was 33.3% (N = 10) in the intervention arm."
)

PARAGRAPH_GENES = (
    "RNA-seq analysis revealed significant upregulation of 1-Mar and 7-Sep "
    "in treated samples compared to controls. Expression of BRCA1 and TP53 "
    "remained stable. Additionally, 2-Dec showed downregulation (FC = -2.3)."
)

PARAGRAPH_RETRACTION_GENOME = (
    "Our results are consistent with prior work (doi:10.1016/S0140-6736(97)11096-0) "
    "on developmental outcomes. Reads were aligned to hg19 for compatibility, "
    "then variant calls were filtered using hg38 annotation databases."
)

PARAGRAPH_CLEAN = (
    "CRISPR-Cas9 editing was performed in HEK293T cells cultured in DMEM "
    "with 10% FBS at 37C. Libraries were sequenced on NovaSeq 6000. "
    "Data deposited in GEO (GSE198765) and SRA (SRR12345678)."
)

PLANTED_TEXT = "\n\n".join([
    PARAGRAPH_STATS,
    PARAGRAPH_GENES,
    PARAGRAPH_RETRACTION_GENOME,
    PARAGRAPH_CLEAN,
])

WAKEFIELD_DOI = "10.1016/S0140-6736(97)11096-0"


# ══════════════════════════════════════════════════════════════════
# Mock setup
# ══════════════════════════════════════════════════════════════════


class _MockCrossrefClient:
    def __init__(self, status_map: dict[str, RetractionStatus]):
        self._map = status_map

    async def check_retraction(self, doi: str) -> RetractionStatus:
        return self._map.get(doi, RetractionStatus(doi=doi))


def _make_runner() -> W7IntegrityRunner:
    """Create W7 runner with mock LLM and mock retraction client."""
    mock_llm = MockLLMLayer()  # No presets — defaults pass through
    registry = create_registry(mock_llm)
    runner = W7IntegrityRunner(registry=registry)
    # Inject mock retraction client
    runner._retraction_checker = RetractionChecker(
        crossref_client=_MockCrossrefClient({
            WAKEFIELD_DOI: RetractionStatus(doi=WAKEFIELD_DOI, is_retracted=True),
        }),
    )
    return runner


def _make_instance(query: str) -> WorkflowInstance:
    return WorkflowInstance(
        template="W7",
        query=query,
        budget_total=3.0,
        budget_remaining=3.0,
    )


# ══════════════════════════════════════════════════════════════════
# Shared fixture: run pipeline once, share across test classes
# ══════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def w7_result():
    """Run the W7 pipeline once with planted errors (module-scoped)."""
    import asyncio
    runner = _make_runner()
    instance = _make_instance(PLANTED_TEXT)
    result_instance = asyncio.run(runner.run(instance))
    return result_instance


@pytest.fixture(scope="module")
def w7_findings(w7_result):
    """Extract findings from the W7 report."""
    report = w7_result.session_manifest.get("integrity_report", {})
    return report.get("findings", [])


@pytest.fixture(scope="module")
def w7_report(w7_result):
    """Extract the full report dict."""
    return w7_result.session_manifest.get("integrity_report", {})


# ══════════════════════════════════════════════════════════════════
# Pipeline Completion
# ══════════════════════════════════════════════════════════════════


class TestW7PipelineCompletion:
    """Verify the full pipeline runs without errors."""

    def test_pipeline_completes(self, w7_result):
        assert w7_result.state == "COMPLETED", f"W7 ended in {w7_result.state}"

    def test_eight_steps_recorded(self, w7_result):
        assert len(w7_result.step_history) == 8, (
            f"Expected 8 step_history entries, got {len(w7_result.step_history)}"
        )

    def test_step_order(self, w7_result):
        expected = [
            "COLLECT", "GENE_CHECK", "STAT_CHECK", "RETRACTION_CHECK",
            "METADATA_CHECK", "IMAGE_CHECK", "LLM_CONTEXTUALIZE", "REPORT",
        ]
        actual = [h["step_id"] for h in w7_result.step_history]
        assert actual == expected

    def test_no_failed_steps(self, w7_result):
        for h in w7_result.step_history:
            assert h["status"] == "completed", f"Step {h['step_id']} status={h['status']}"

    def test_all_steps_have_duration(self, w7_result):
        for h in w7_result.step_history:
            assert "duration_ms" in h, f"Step {h['step_id']} missing duration"
            assert h["duration_ms"] >= 0


# ══════════════════════════════════════════════════════════════════
# Planted Error Detection
# ══════════════════════════════════════════════════════════════════


class TestW7PlantedErrors:
    """Verify each planted error is detected by the pipeline."""

    def test_pvalue_detection(self, w7_findings):
        pval = [f for f in w7_findings if f.get("category") == "p_value_mismatch"]
        assert len(pval) >= 1, f"Expected ≥1 p_value_mismatch, got {len(pval)}"

    def test_grimmer_sd_detection(self, w7_findings):
        sd = [f for f in w7_findings if f.get("category") == "grimmer_sd_failure"]
        assert len(sd) >= 1, f"Expected ≥1 grimmer_sd_failure, got {len(sd)}"

    def test_grimmer_pct_detection(self, w7_findings):
        pct = [f for f in w7_findings if f.get("category") == "grimmer_percent_failure"]
        assert len(pct) >= 1, f"Expected ≥1 grimmer_percent_failure, got {len(pct)}"

    def test_gene_name_detection(self, w7_findings):
        genes = [f for f in w7_findings if f.get("category") == "gene_name_error"]
        assert len(genes) >= 3, f"Expected ≥3 gene_name_error, got {len(genes)}"

    def test_retraction_detection(self, w7_findings):
        ret = [f for f in w7_findings if f.get("category") == "retracted_reference"]
        assert len(ret) >= 1, f"Expected ≥1 retracted_reference, got {len(ret)}"

    def test_genome_build_detection(self, w7_findings):
        gb = [f for f in w7_findings if f.get("category") == "genome_build_inconsistency"]
        assert len(gb) >= 1, f"Expected ≥1 genome_build_inconsistency, got {len(gb)}"

    def test_total_findings_in_range(self, w7_findings):
        total = len(w7_findings)
        assert 7 <= total <= 15, f"Expected 7-15 findings, got {total}"


# ══════════════════════════════════════════════════════════════════
# Severity Levels
# ══════════════════════════════════════════════════════════════════


class TestW7Severity:
    """Verify severity assignments for different finding types."""

    def test_critical_from_retraction(self, w7_findings):
        ret = [f for f in w7_findings if f.get("category") == "retracted_reference"]
        assert any(f.get("severity") == "critical" for f in ret), (
            "Retracted reference should have critical severity"
        )

    def test_warning_from_grimmer(self, w7_findings):
        grimmer = [f for f in w7_findings
                    if f.get("category") in ("grimmer_sd_failure", "grimmer_percent_failure")]
        for f in grimmer:
            assert f.get("severity") in ("warning", "error", "info"), (
                f"GRIMMER finding has unexpected severity: {f.get('severity')}"
            )

    def test_warning_from_genes(self, w7_findings):
        genes = [f for f in w7_findings if f.get("category") == "gene_name_error"]
        for f in genes:
            assert f.get("severity") in ("warning", "error", "info"), (
                f"Gene finding has unexpected severity: {f.get('severity')}"
            )


# ══════════════════════════════════════════════════════════════════
# Report Assembly
# ══════════════════════════════════════════════════════════════════


class TestW7ReportAssembly:
    """Verify the REPORT step assembles findings correctly."""

    def test_report_in_manifest(self, w7_result):
        assert "integrity_report" in w7_result.session_manifest

    def test_overall_level_critical(self, w7_report):
        assert w7_report["overall_level"] == "critical", (
            f"Expected critical (retraction), got {w7_report['overall_level']}"
        )

    def test_findings_by_category(self, w7_report):
        cats = w7_report.get("findings_by_category", {})
        assert len(cats) >= 4, f"Expected ≥4 categories, got {len(cats)}: {list(cats.keys())}"

    def test_findings_by_severity(self, w7_report):
        sevs = w7_report.get("findings_by_severity", {})
        assert "critical" in sevs, "Should have critical severity"
        assert sevs["critical"] >= 1

    def test_total_matches_findings(self, w7_report):
        assert w7_report["total_findings"] == len(w7_report.get("findings", []))


# ══════════════════════════════════════════════════════════════════
# Clean Text — Zero Warnings
# ══════════════════════════════════════════════════════════════════


class TestW7CleanText:
    """Run pipeline with only clean text — should have zero warning+ findings."""

    @pytest.fixture(scope="class")
    def clean_result(self):
        import asyncio
        runner = _make_runner()
        instance = _make_instance(PARAGRAPH_CLEAN)
        return asyncio.run(runner.run(instance))

    def test_pipeline_completes(self, clean_result):
        assert clean_result.state == "COMPLETED"

    def test_clean_zero_warnings(self, clean_result):
        report = clean_result.session_manifest.get("integrity_report", {})
        findings = report.get("findings", [])
        warnings_plus = [f for f in findings if f.get("severity") in ("warning", "error", "critical")]
        assert len(warnings_plus) == 0, (
            f"Clean text should have 0 warning+ findings, got {len(warnings_plus)}: "
            f"{[f.get('category') for f in warnings_plus]}"
        )

    def test_clean_overall_level(self, clean_result):
        report = clean_result.session_manifest.get("integrity_report", {})
        assert report.get("overall_level") == "clean"


# ══════════════════════════════════════════════════════════════════
# Scorecard (P/R gate)
# ══════════════════════════════════════════════════════════════════


PLANTED_CATEGORIES = [
    "p_value_mismatch",
    "grimmer_sd_failure",
    "grimmer_percent_failure",
    "gene_name_error",
    "gene_name_error",
    "gene_name_error",
    "retracted_reference",
    "genome_build_inconsistency",
]


class TestW7Scorecard:
    """Compute precision/recall for planted errors as a regression gate."""

    def test_scorecard(self, w7_findings):
        detected_categories = [f.get("category") for f in w7_findings]

        # True positives: planted categories that were detected
        tp = 0
        remaining_detected = list(detected_categories)
        for cat in PLANTED_CATEGORIES:
            if cat in remaining_detected:
                tp += 1
                remaining_detected.remove(cat)

        fn = len(PLANTED_CATEGORIES) - tp  # Planted but not detected
        fp = len(remaining_detected)  # Detected but not planted

        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        print("\n" + "=" * 50)
        print("  W7 SYSTEM-LEVEL SCORECARD")
        print("=" * 50)
        print(f"  Planted errors: {len(PLANTED_CATEGORIES)}")
        print(f"  Total findings: {len(w7_findings)}")
        print(f"  TP={tp} FP={fp} FN={fn}")
        print(f"  Precision={precision:.3f} Recall={recall:.3f} F1={f1:.3f}")
        print("=" * 50)

        assert precision >= 0.80, f"W7 system precision {precision:.3f} < 0.80"
        assert recall >= 0.75, f"W7 system recall {recall:.3f} < 0.75"
