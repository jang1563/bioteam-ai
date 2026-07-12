"""W1 Literature Review — Tier 1 reproducibility feature E2E tests.

Tests the full W1 pipeline with Tier 1 features:
CITATION_CHECK, RCMXT_SCORE (LLM/heuristic/hybrid), SessionManifest, PRISMA flow.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.knowledge_manager import NoveltyAssessment
from app.agents.registry import create_registry
from app.agents.research_director import QueryClassification, SynthesisReport
from app.agents.teams.t02_transcriptomics import (
    ExtractedPaperData,
    ExtractionResult,
    ScreeningDecision,
    ScreeningResult,
)
from app.llm.mock_layer import MockLLMLayer
from app.models.evidence import AxisExplanation, LLMRCMXTResponse
from app.models.refinement import QualityCritique
from app.workflows.runners.w1_literature import W1LiteratureReviewRunner
from pydantic import BaseModel, Field

# === Mock Helpers ===


class _MockSearchTerms(BaseModel):
    pubmed_queries: list[str] = Field(default_factory=lambda: ["spaceflight anemia[MeSH]"])
    semantic_scholar_queries: list[str] = Field(default_factory=lambda: ["spaceflight anemia erythropoiesis"])
    keywords: list[str] = Field(default_factory=lambda: ["spaceflight", "anemia"])


def _make_mock_responses() -> dict:
    """Full W1 mock responses including LLMRCMXTResponse for Tier 1."""
    return {
        "sonnet:QueryClassification": QueryClassification(
            type="simple_query",
            reasoning="Test classification",
            target_agent="t02_transcriptomics",
        ),
        "opus:SynthesisReport": SynthesisReport(
            title="Scope: Spaceflight Anemia Mechanisms",
            summary="Hemolysis, erythropoiesis, cfRNA biomarkers.",
            key_findings=["Focus on splenic hemolysis pathway"],
            sources_cited=["10.1038/s41591-021-01637-7"],
        ),
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
        "sonnet:NoveltyAssessment": NoveltyAssessment(
            finding="Splenic hemolysis increases by 54% in microgravity",
            is_novel=True, novelty_score=0.8,
            reasoning="No prior study quantified splenic contribution.",
        ),
        "sonnet:LLMRCMXTResponse": LLMRCMXTResponse(
            claim_text="Focus on splenic hemolysis pathway",
            axes=[
                AxisExplanation(axis="R", score=0.7, reasoning="Replicated across ISS missions with consistent findings."),
                AxisExplanation(axis="C", score=0.5, reasoning="Condition-specific to microgravity exposure."),
                AxisExplanation(axis="M", score=0.75, reasoning="Well-designed studies with proper controls."),
                AxisExplanation(axis="T", score=0.65, reasoning="Established finding spanning decades."),
            ],
            x_applicable=False,
            overall_assessment="Well-supported spaceflight physiology finding.",
            confidence_in_scoring=0.8,
        ),
        # High-quality critique so refinement loop skips immediately
        "haiku:QualityCritique": QualityCritique(
            rigor_score=0.9, completeness_score=0.85, clarity_score=0.9,
            accuracy_score=0.9, overall_score=0.88,
            strengths=["Well-structured analysis"],
        ),
    }


def _make_runner(rcmxt_mode="heuristic", sse_hub=None, lab_kb=None):
    """Create W1 runner with specified RCMXT mode."""
    mock = MockLLMLayer(_make_mock_responses())
    registry = create_registry(mock)
    return W1LiteratureReviewRunner(
        registry=registry,
        sse_hub=sse_hub,
        lab_kb=lab_kb,
        rcmxt_mode=rcmxt_mode,
        llm_layer=mock if rcmxt_mode != "heuristic" else None,
    )


async def _run_full_w1(runner, query="spaceflight anemia"):
    """Run W1 to completion (pause + resume). Returns (instance, all_step_results)."""
    first = await runner.run(query=query)
    instance = first["instance"]
    assert instance.state == "WAITING_HUMAN", f"Expected WAITING_HUMAN, got {instance.state}"

    final = await runner.resume_after_human(instance, query=query)
    assert final["instance"].state == "COMPLETED"

    all_steps = {**first["step_results"], **final["step_results"]}
    return final["instance"], all_steps


# === Tests ===


def test_full_w1_with_all_10_steps():
    """Full W1 pipeline should produce all 10 step results."""
    runner = _make_runner()
    instance, all_steps = asyncio.run(_run_full_w1(runner))

    expected_steps = [
        "SCOPE", "SEARCH", "SCREEN", "EXTRACT", "NEGATIVE_CHECK",
        "SYNTHESIZE", "CITATION_CHECK", "RCMXT_SCORE", "NOVELTY_CHECK", "REPORT",
    ]
    for step_id in expected_steps:
        assert step_id in all_steps, f"Missing step: {step_id}"
    assert instance.state == "COMPLETED"


def test_citation_check_output_structure():
    """CITATION_CHECK should produce valid citation report structure."""
    runner = _make_runner()
    _, all_steps = asyncio.run(_run_full_w1(runner))

    citation = all_steps["CITATION_CHECK"]
    output = citation.output if hasattr(citation, 'output') else citation
    if isinstance(output, dict) and "output" in output:
        output = output["output"]

    assert "total_citations" in output
    assert "verified" in output
    assert "verification_rate" in output
    assert "is_clean" in output
    assert "issues" in output
    assert isinstance(output["issues"], list)
    assert isinstance(output["verification_rate"], (int, float))


def test_rcmxt_scores_output_structure_llm():
    """RCMXT_SCORE with LLM mode should produce v0.2-llm scores."""
    runner = _make_runner(rcmxt_mode="llm")
    _, all_steps = asyncio.run(_run_full_w1(runner))

    rcmxt = all_steps["RCMXT_SCORE"]
    output = rcmxt.output if hasattr(rcmxt, 'output') else rcmxt
    if isinstance(output, dict) and "output" in output:
        output = output["output"]

    assert "scores" in output
    assert "total_scored" in output
    scores = output["scores"]
    assert isinstance(scores, list)
    assert len(scores) >= 1

    # Validate score structure
    for score in scores:
        assert "R" in score
        assert "C" in score
        assert "M" in score
        assert "T" in score
        assert "composite" in score
        assert score["scorer_version"] == "v0.2-llm"
        assert 0.0 <= score["R"] <= 1.0
        assert 0.0 <= score["C"] <= 1.0


def test_rcmxt_heuristic_mode_e2e():
    """RCMXT_SCORE with heuristic mode should produce v0.1-heuristic scores."""
    runner = _make_runner(rcmxt_mode="heuristic")
    _, all_steps = asyncio.run(_run_full_w1(runner))

    rcmxt = all_steps["RCMXT_SCORE"]
    output = rcmxt.output if hasattr(rcmxt, 'output') else rcmxt
    if isinstance(output, dict) and "output" in output:
        output = output["output"]

    scores = output["scores"]
    assert len(scores) >= 1
    for score in scores:
        assert score["scorer_version"] == "v0.1-heuristic"


def test_rcmxt_hybrid_mode_e2e():
    """RCMXT_SCORE with hybrid mode should use LLM when mock succeeds."""
    runner = _make_runner(rcmxt_mode="hybrid")
    _, all_steps = asyncio.run(_run_full_w1(runner))

    rcmxt = all_steps["RCMXT_SCORE"]
    output = rcmxt.output if hasattr(rcmxt, 'output') else rcmxt
    if isinstance(output, dict) and "output" in output:
        output = output["output"]

    scores = output["scores"]
    assert len(scores) >= 1
    # Mock succeeds → should use LLM scores
    for score in scores:
        assert score["scorer_version"] == "v0.2-llm"


def test_session_manifest_in_report():
    """REPORT output should contain a valid SessionManifest."""
    runner = _make_runner()
    _, all_steps = asyncio.run(_run_full_w1(runner))

    report = all_steps["REPORT"]
    output = report.output if hasattr(report, 'output') else report
    if isinstance(output, dict) and "output" in output:
        output = output["output"]

    assert "session_manifest" in output
    manifest = output["session_manifest"]
    assert "workflow_id" in manifest
    assert "template" in manifest
    assert manifest["template"] == "W1"
    assert "query" in manifest
    assert "llm_calls" in manifest
    assert "total_input_tokens" in manifest
    assert "total_output_tokens" in manifest
    assert "total_cost" in manifest
    assert "model_versions" in manifest
    assert "system_version" in manifest
    assert manifest["system_version"] == "v0.5"


def test_prisma_flow_in_manifest():
    """SessionManifest should contain PRISMA flow data."""
    runner = _make_runner()
    _, all_steps = asyncio.run(_run_full_w1(runner))

    report = all_steps["REPORT"]
    output = report.output if hasattr(report, 'output') else report
    if isinstance(output, dict) and "output" in output:
        output = output["output"]

    manifest = output["session_manifest"]
    assert "prisma" in manifest
    prisma = manifest["prisma"]
    assert "records_identified" in prisma
    assert "records_screened" in prisma
    assert "records_excluded_screening" in prisma


def test_tier1_stored_on_instance():
    """Tier 1 data should be stored on WorkflowInstance after completion."""
    runner = _make_runner()
    instance, _ = asyncio.run(_run_full_w1(runner))

    assert instance.session_manifest is not None
    assert instance.citation_report is not None
    assert instance.rcmxt_scores is not None

    # Verify session_manifest has expected structure
    manifest = instance.session_manifest
    assert isinstance(manifest, dict)
    assert "workflow_id" in manifest

    # Verify citation_report structure
    citation = instance.citation_report
    assert isinstance(citation, dict)
    assert "total_citations" in citation

    # Verify rcmxt_scores is a list
    assert isinstance(instance.rcmxt_scores, list)


def test_report_contains_step_summaries():
    """REPORT should include summary strings from each prior step."""
    runner = _make_runner()
    _, all_steps = asyncio.run(_run_full_w1(runner))

    report = all_steps["REPORT"]
    output = report.output if hasattr(report, 'output') else report
    if isinstance(output, dict) and "output" in output:
        output = output["output"]

    assert "steps_completed" in output
    assert len(output["steps_completed"]) >= 9  # At minimum 9 steps (REPORT itself might not be in its own list)

    # At least SCOPE and SYNTHESIZE summaries should be present
    summary_keys = [k for k in output.keys() if k.endswith("_summary")]
    assert len(summary_keys) >= 4, f"Expected ≥4 step summaries, found: {summary_keys}"


def test_negative_check_runs_in_phase1():
    """NEGATIVE_CHECK should complete in Phase 1 (before SYNTHESIZE checkpoint)."""
    runner = _make_runner()
    first = asyncio.run(runner.run(query="spaceflight anemia"))

    phase1_steps = first["step_results"]
    assert "NEGATIVE_CHECK" in phase1_steps

    neg = phase1_steps["NEGATIVE_CHECK"]
    output = neg.output if hasattr(neg, 'output') else neg
    if isinstance(output, dict) and "output" in output:
        output = output["output"]
    assert "negative_results_found" in output


def test_budget_tracking_with_tier1_steps():
    """Budget should be tracked across all 10 steps including Tier 1."""
    runner = _make_runner()
    instance, _ = asyncio.run(_run_full_w1(runner))

    assert instance.budget_remaining <= instance.budget_total
    assert instance.state == "COMPLETED"
    # Budget should have been deducted for agent steps
    # (mock costs are 0, but budget deduction still happens via step costs)
    assert instance.budget_remaining >= 0


if __name__ == "__main__":
    print("Testing W1 Tier 1 E2E Integration:")
    test_full_w1_with_all_10_steps()
    test_citation_check_output_structure()
    test_rcmxt_scores_output_structure_llm()
    test_rcmxt_heuristic_mode_e2e()
    test_rcmxt_hybrid_mode_e2e()
    test_session_manifest_in_report()
    test_prisma_flow_in_manifest()
    test_tier1_stored_on_instance()
    test_report_contains_step_summaries()
    test_negative_check_runs_in_phase1()
    test_budget_tracking_with_tier1_steps()
    print("\nAll W1 Tier 1 E2E tests passed!")
