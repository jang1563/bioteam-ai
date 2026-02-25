"""Error recovery E2E tests — budget overage, agent failures, hybrid fallback.

Tests that the W1 pipeline handles error conditions gracefully.
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


def _base_mock_responses() -> dict:
    """Standard mock responses for W1 pipeline."""
    return {
        "sonnet:QueryClassification": QueryClassification(
            type="simple_query",
            reasoning="Test",
            target_agent="t02_transcriptomics",
        ),
        "opus:SynthesisReport": SynthesisReport(
            title="Scope: Test",
            summary="Test summary.",
            key_findings=["Finding 1"],
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
                ExtractedPaperData(paper_id="p1", genes=["EPO"], organism="human"),
                ExtractedPaperData(paper_id="p2", genes=["HBA1"], organism="mouse"),
            ],
            common_genes=["EPO"],
        ),
        "sonnet:NoveltyAssessment": NoveltyAssessment(
            finding="Test finding",
            is_novel=True, novelty_score=0.8,
            reasoning="Test reasoning.",
        ),
        "sonnet:LLMRCMXTResponse": LLMRCMXTResponse(
            claim_text="Finding 1",
            axes=[
                AxisExplanation(axis="R", score=0.7, reasoning="Replicated across studies."),
                AxisExplanation(axis="C", score=0.5, reasoning="Context-dependent."),
                AxisExplanation(axis="M", score=0.75, reasoning="Well-designed studies."),
                AxisExplanation(axis="T", score=0.65, reasoning="Established over decades."),
            ],
            x_applicable=False,
            overall_assessment="Well-supported finding.",
            confidence_in_scoring=0.8,
        ),
        # High-quality critique so refinement loop skips immediately
        "haiku:QualityCritique": QualityCritique(
            rigor_score=0.9, completeness_score=0.85, clarity_score=0.9,
            accuracy_score=0.9, overall_score=0.88,
            strengths=["Well-structured analysis"],
        ),
    }


async def _run_full_w1(runner, query="spaceflight anemia"):
    """Run W1 to completion."""
    first = await runner.run(query=query)
    instance = first["instance"]
    if instance.state == "WAITING_HUMAN":
        final = await runner.resume_after_human(instance, query=query)
        all_steps = {**first["step_results"], **final["step_results"]}
        return final["instance"], all_steps
    return instance, first["step_results"]


# === Tests ===


def test_hybrid_fallback_on_llm_failure():
    """Hybrid mode should fallback to heuristic when LLM mock has no RCMXT response."""
    # Create mock WITHOUT LLMRCMXTResponse — forces LLM call to fail
    responses = _base_mock_responses()
    del responses["sonnet:LLMRCMXTResponse"]
    mock = MockLLMLayer(responses)
    registry = create_registry(mock)

    runner = W1LiteratureReviewRunner(
        registry=registry,
        rcmxt_mode="hybrid",
        llm_layer=mock,
    )
    instance, all_steps = asyncio.run(_run_full_w1(runner))
    assert instance.state == "COMPLETED"

    # RCMXT should still have scored (via heuristic fallback)
    rcmxt = all_steps["RCMXT_SCORE"]
    output = rcmxt.output if hasattr(rcmxt, 'output') else rcmxt
    if isinstance(output, dict) and "output" in output:
        output = output["output"]

    scores = output["scores"]
    # Heuristic fallback should produce scores
    for score in scores:
        assert score["scorer_version"] == "v0.1-heuristic"


def test_pipeline_continues_after_negative_check_no_lab_kb():
    """Pipeline should continue normally when no Lab KB is configured."""
    mock = MockLLMLayer(_base_mock_responses())
    registry = create_registry(mock)
    runner = W1LiteratureReviewRunner(
        registry=registry,
        lab_kb=None,  # No Lab KB
    )

    instance, all_steps = asyncio.run(_run_full_w1(runner))
    assert instance.state == "COMPLETED"

    neg_check = all_steps["NEGATIVE_CHECK"]
    output = neg_check.output if hasattr(neg_check, 'output') else neg_check
    if isinstance(output, dict) and "output" in output:
        output = output["output"]
    assert output["negative_results_found"] == 0


def test_empty_synthesis_produces_empty_rcmxt():
    """When SYNTHESIZE has no key_findings, RCMXT_SCORE should produce 0 scores."""
    responses = _base_mock_responses()
    # Override synthesis to have empty key_findings
    responses["opus:SynthesisReport"] = SynthesisReport(
        title="Empty Scope",
        summary="No findings.",
        key_findings=[],
    )
    mock = MockLLMLayer(responses)
    registry = create_registry(mock)

    runner = W1LiteratureReviewRunner(registry=registry)
    instance, all_steps = asyncio.run(_run_full_w1(runner))
    assert instance.state == "COMPLETED"

    rcmxt = all_steps["RCMXT_SCORE"]
    output = rcmxt.output if hasattr(rcmxt, 'output') else rcmxt
    if isinstance(output, dict) and "output" in output:
        output = output["output"]

    assert output["total_scored"] == 0
    assert output["scores"] == []


def test_citation_check_with_no_search_sources():
    """CITATION_CHECK should produce valid output even with no SEARCH papers."""
    responses = _base_mock_responses()
    mock = MockLLMLayer(responses)
    registry = create_registry(mock)
    runner = W1LiteratureReviewRunner(registry=registry)

    # Run the pipeline — mock SEARCH output won't have real papers
    instance, all_steps = asyncio.run(_run_full_w1(runner))
    assert instance.state == "COMPLETED"

    citation = all_steps["CITATION_CHECK"]
    output = citation.output if hasattr(citation, 'output') else citation
    if isinstance(output, dict) and "output" in output:
        output = output["output"]

    assert "total_citations" in output
    assert "is_clean" in output
    assert isinstance(output["issues"], list)


def test_lab_kb_failure_doesnt_crash_pipeline():
    """If Lab KB search raises, NEGATIVE_CHECK should return 0 results gracefully."""

    class FailingLabKB:
        def search(self, query):
            raise RuntimeError("Database connection lost")

    mock = MockLLMLayer(_base_mock_responses())
    registry = create_registry(mock)
    runner = W1LiteratureReviewRunner(
        registry=registry,
        lab_kb=FailingLabKB(),
    )

    instance, all_steps = asyncio.run(_run_full_w1(runner))
    assert instance.state == "COMPLETED"

    neg_check = all_steps["NEGATIVE_CHECK"]
    output = neg_check.output if hasattr(neg_check, 'output') else neg_check
    if isinstance(output, dict) and "output" in output:
        output = output["output"]
    assert output["negative_results_found"] == 0


def test_multiple_key_findings_scored_independently():
    """Multiple key findings should each get their own RCMXT score."""
    responses = _base_mock_responses()
    responses["opus:SynthesisReport"] = SynthesisReport(
        title="Multi-finding scope",
        summary="Multiple findings.",
        key_findings=[
            "Hemolysis increases 54% in microgravity",
            "TNFSF11 upregulation in spaceflight cfRNA",
            "Bone density loss accelerated in long-duration missions",
        ],
    )
    mock = MockLLMLayer(responses)
    registry = create_registry(mock)
    runner = W1LiteratureReviewRunner(registry=registry)

    instance, all_steps = asyncio.run(_run_full_w1(runner))
    assert instance.state == "COMPLETED"

    rcmxt = all_steps["RCMXT_SCORE"]
    output = rcmxt.output if hasattr(rcmxt, 'output') else rcmxt
    if isinstance(output, dict) and "output" in output:
        output = output["output"]

    assert output["total_scored"] == 3
    assert len(output["scores"]) == 3


if __name__ == "__main__":
    print("Testing Error Recovery E2E:")
    test_hybrid_fallback_on_llm_failure()
    test_pipeline_continues_after_negative_check_no_lab_kb()
    test_empty_synthesis_produces_empty_rcmxt()
    test_citation_check_with_no_search_sources()
    test_lab_kb_failure_doesnt_crash_pipeline()
    test_multiple_key_findings_scored_independently()
    print("\nAll Error Recovery E2E tests passed!")
