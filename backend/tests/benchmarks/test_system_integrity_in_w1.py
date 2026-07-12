"""System-level test: W1 INTEGRITY_CHECK step catches planted errors in synthesis text.

Tests the integration between W1 pipeline and DIA quick_check:
  W1.resume_after_human → ... → INTEGRITY_CHECK → DIA.quick_check(text)

Strategy: Override opus:SynthesisReport mock to embed planted errors in the summary.
The INTEGRITY_CHECK step extracts text from SYNTHESIZE output["summary"].
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.ambiguity_engine import ContradictionClassification
from app.agents.knowledge_manager import NoveltyAssessment
from app.agents.registry import create_registry
from app.agents.research_director import SynthesisReport
from app.agents.teams.t02_transcriptomics import (
    ExtractedPaperData,
    ExtractionResult,
    ScreeningDecision,
    ScreeningResult,
)
from app.engines.integrity.finding_models import RetractionStatus
from app.engines.integrity.retraction_checker import RetractionChecker
from app.llm.mock_layer import MockLLMLayer
from app.workflows.runners.w1_literature import W1LiteratureReviewRunner
from pydantic import BaseModel, Field


# Mock for KM's SearchTerms
class _MockSearchTerms(BaseModel):
    pubmed_queries: list[str] = Field(default_factory=lambda: ["spaceflight anemia[MeSH]"])
    semantic_scholar_queries: list[str] = Field(default_factory=lambda: ["spaceflight anemia"])
    keywords: list[str] = Field(default_factory=lambda: ["spaceflight", "anemia"])


def _base_mock_responses() -> dict:
    """Standard W1 mock responses (reused from conftest pattern)."""
    return {
        "sonnet:SearchTerms": _MockSearchTerms(),
        "sonnet:ScreeningResult": ScreeningResult(
            total_screened=3, included=2, excluded=1,
            decisions=[
                ScreeningDecision(paper_id="p1", decision="include", relevance_score=0.9),
                ScreeningDecision(paper_id="p2", decision="include", relevance_score=0.7),
                ScreeningDecision(paper_id="p3", decision="exclude", relevance_score=0.1),
            ],
        ),
        "sonnet:ExtractionResult": ExtractionResult(
            total_extracted=2,
            papers=[
                ExtractedPaperData(paper_id="p1", genes=["EPO", "TNFSF11"], organism="human"),
                ExtractedPaperData(paper_id="p2", genes=["HBA1"], organism="mouse"),
            ],
            common_genes=["EPO"],
        ),
        "sonnet:ContradictionClassification": ContradictionClassification(
            types=[], confidence=0.9, is_genuine_contradiction=False,
        ),
        "sonnet:NoveltyAssessment": NoveltyAssessment(
            finding="Splenic hemolysis increases by 54%",
            is_novel=True, novelty_score=0.8,
            reasoning="No prior study quantified this.",
        ),
    }


# ══════════════════════════════════════════════════════════════════
# Planted error in synthesis summary
# ══════════════════════════════════════════════════════════════════

PLANTED_SUMMARY = (
    "Hemolysis increases by 54% in microgravity "
    "(M = 4.20, SD = 2.50, N = 10). "
    "Key gene 1-Mar showed upregulation. "
    "Statistical analysis confirmed the effect, "
    "t(28) = 2.05, p = .500."
)

CLEAN_SUMMARY = (
    "Research scope defined: hemolysis, erythropoiesis, and cfRNA biomarkers. "
    "Focus on splenic hemolysis pathway."
)


def _make_runner_with_summary(summary: str) -> W1LiteratureReviewRunner:
    """Create W1 runner with customized SynthesisReport summary."""
    responses = {
        **_base_mock_responses(),
        "opus:SynthesisReport": SynthesisReport(
            title="Spaceflight Anemia Review",
            summary=summary,
            key_findings=["Splenic hemolysis pathway"],
        ),
    }
    mock_llm = MockLLMLayer(responses)
    registry = create_registry(mock_llm)
    return W1LiteratureReviewRunner(registry=registry)


# ══════════════════════════════════════════════════════════════════
# Integrity detection tests
# ══════════════════════════════════════════════════════════════════


class TestW1IntegrityDetection:
    """Verify INTEGRITY_CHECK catches planted errors in synthesis summary."""

    @pytest.fixture(scope="class")
    def w1_result(self):
        runner = _make_runner_with_summary(PLANTED_SUMMARY)
        first = asyncio.run(runner.run(query="spaceflight anemia"))
        assert first["instance"].state == "WAITING_HUMAN"
        final = asyncio.run(runner.resume_after_human(first["instance"], query="spaceflight anemia"))
        return final

    @pytest.fixture(scope="class")
    def integrity_output(self, w1_result):
        step_results = w1_result["step_results"]
        ic = step_results.get("INTEGRITY_CHECK", {})
        return ic if isinstance(ic, dict) else (ic.get("output", {}) if hasattr(ic, "get") else {})

    @pytest.fixture(scope="class")
    def integrity_findings(self, w1_result):
        manifest = w1_result["instance"].session_manifest
        ic_data = manifest.get("integrity_quick_check", {})
        return ic_data.get("findings", [])

    def test_pipeline_completed(self, w1_result):
        assert w1_result["completed"] is True
        assert w1_result["instance"].state == "COMPLETED"

    def test_integrity_step_ran(self, w1_result):
        assert "INTEGRITY_CHECK" in w1_result["step_results"]

    def test_catches_gene_name(self, integrity_findings):
        genes = [f for f in integrity_findings if f.get("category") == "gene_name_error"]
        assert len(genes) >= 1, f"Expected ≥1 gene_name_error from '1-Mar', got {len(genes)}"

    def test_catches_pvalue(self, integrity_findings):
        pvals = [f for f in integrity_findings if f.get("category") == "p_value_mismatch"]
        assert len(pvals) >= 1, f"Expected ≥1 p_value_mismatch, got {len(pvals)}"

    def test_catches_grimmer_sd(self, integrity_findings):
        sds = [f for f in integrity_findings if f.get("category") == "grimmer_sd_failure"]
        assert len(sds) >= 1, f"Expected ≥1 grimmer_sd_failure, got {len(sds)}"

    def test_manifest_populated(self, w1_result):
        manifest = w1_result["instance"].session_manifest
        assert "integrity_quick_check" in manifest

    def test_total_findings_gte_3(self, integrity_findings):
        assert len(integrity_findings) >= 3, (
            f"Expected ≥3 integrity findings, got {len(integrity_findings)}"
        )


# ══════════════════════════════════════════════════════════════════
# Clean synthesis — zero findings
# ══════════════════════════════════════════════════════════════════


class TestW1IntegrityClean:
    """Verify clean synthesis text produces zero integrity findings."""

    @pytest.fixture(scope="class")
    def clean_result(self):
        runner = _make_runner_with_summary(CLEAN_SUMMARY)
        first = asyncio.run(runner.run(query="spaceflight anemia"))
        assert first["instance"].state == "WAITING_HUMAN"
        final = asyncio.run(runner.resume_after_human(first["instance"], query="spaceflight anemia"))
        return final

    def test_pipeline_completed(self, clean_result):
        assert clean_result["completed"] is True

    def test_clean_zero_findings(self, clean_result):
        manifest = clean_result["instance"].session_manifest
        ic_data = manifest.get("integrity_quick_check", {})
        findings = ic_data.get("findings", [])
        warnings_plus = [f for f in findings if f.get("severity") in ("warning", "error", "critical")]
        assert len(warnings_plus) == 0, (
            f"Clean synthesis should have 0 warning+ findings, got {len(warnings_plus)}"
        )

    def test_clean_overall_level(self, clean_result):
        manifest = clean_result["instance"].session_manifest
        ic_data = manifest.get("integrity_quick_check", {})
        assert ic_data.get("overall_level") == "clean"


# ══════════════════════════════════════════════════════════════════
# W1 + Retraction in synthesis
# ══════════════════════════════════════════════════════════════════


WAKEFIELD_DOI = "10.1016/S0140-6736(97)11096-0"

RETRACTION_SUMMARY = (
    "Hemolysis increases by 54% in microgravity. "
    f"This is consistent with prior work (doi:{WAKEFIELD_DOI}) "
    "on developmental outcomes."
)


class _MockCrossrefClient:
    def __init__(self, status_map):
        self._map = status_map

    async def check_retraction(self, doi: str) -> RetractionStatus:
        return self._map.get(doi, RetractionStatus(doi=doi))


class TestW1IntegrityWithRetraction:
    """Verify retraction DOI in synthesis is detected by INTEGRITY_CHECK."""

    @pytest.fixture(scope="class")
    def retraction_result(self):
        runner = _make_runner_with_summary(RETRACTION_SUMMARY)
        # Inject mock retraction client into the DIA agent
        dia = runner.registry.get("data_integrity_auditor")
        if dia:
            dia._retraction_checker = RetractionChecker(
                crossref_client=_MockCrossrefClient({
                    WAKEFIELD_DOI: RetractionStatus(doi=WAKEFIELD_DOI, is_retracted=True),
                }),
            )
        first = asyncio.run(runner.run(query="spaceflight anemia"))
        assert first["instance"].state == "WAITING_HUMAN"
        final = asyncio.run(runner.resume_after_human(first["instance"], query="spaceflight anemia"))
        return final

    def test_pipeline_completed(self, retraction_result):
        assert retraction_result["completed"] is True

    def test_retraction_detected(self, retraction_result):
        manifest = retraction_result["instance"].session_manifest
        ic_data = manifest.get("integrity_quick_check", {})
        findings = ic_data.get("findings", [])
        ret = [f for f in findings if f.get("category") == "retracted_reference"]
        assert len(ret) >= 1, f"Expected ≥1 retracted_reference, got {len(ret)}"

    def test_critical_severity(self, retraction_result):
        manifest = retraction_result["instance"].session_manifest
        ic_data = manifest.get("integrity_quick_check", {})
        findings = ic_data.get("findings", [])
        ret = [f for f in findings if f.get("category") == "retracted_reference"]
        assert any(f.get("severity") == "critical" for f in ret), (
            "Retracted reference should have critical severity"
        )
