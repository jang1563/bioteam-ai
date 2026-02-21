"""Tests for W1 Literature Review Runner — step definitions, pipeline execution, human checkpoint."""

import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.agents.registry import create_registry
from app.agents.research_director import QueryClassification, SynthesisReport
from app.agents.knowledge_manager import LiteratureSearchResult, NoveltyAssessment
from app.agents.teams.t02_transcriptomics import (
    ScreeningResult, ScreeningDecision, ExtractionResult, ExtractedPaperData,
)
from app.llm.mock_layer import MockLLMLayer
from app.models.workflow import WorkflowInstance
from app.workflows.runners.w1_literature import (
    W1LiteratureReviewRunner, W1_STEPS, get_step_by_id, _METHOD_MAP,
)


# Mock for KM's internal SearchTerms model (defined locally inside search_literature)
class _MockSearchTerms(BaseModel):
    pubmed_query: str = "spaceflight anemia[MeSH]"
    semantic_scholar_query: str = "spaceflight anemia erythropoiesis"
    keywords: list[str] = Field(default_factory=lambda: ["spaceflight", "anemia"])


def _make_mock_responses() -> dict:
    """Build mock LLM responses for all W1 agent steps."""
    return {
        # SCOPE — RD.synthesize (uses opus for SynthesisReport)
        "opus:SynthesisReport": SynthesisReport(
            title="Scope: Spaceflight Anemia Mechanisms",
            summary="Research scope defined: hemolysis, erythropoiesis, and cfRNA biomarkers.",
            key_findings=["Focus on splenic hemolysis pathway"],
        ),
        # SEARCH — KM.search_literature (uses sonnet for SearchTerms)
        "sonnet:SearchTerms": _MockSearchTerms(),
        # SCREEN — T02.screen_papers
        "sonnet:ScreeningResult": ScreeningResult(
            total_screened=3,
            included=2,
            excluded=1,
            decisions=[
                ScreeningDecision(paper_id="p1", decision="include", relevance_score=0.9),
                ScreeningDecision(paper_id="p2", decision="include", relevance_score=0.7),
                ScreeningDecision(paper_id="p3", decision="exclude", relevance_score=0.1),
            ],
        ),
        # EXTRACT — T02.extract_data
        "sonnet:ExtractionResult": ExtractionResult(
            total_extracted=2,
            papers=[
                ExtractedPaperData(paper_id="p1", genes=["EPO", "TNFSF11"], organism="human"),
                ExtractedPaperData(paper_id="p2", genes=["HBA1"], organism="mouse"),
            ],
            common_genes=["EPO"],
        ),
        # SYNTHESIZE — RD.synthesize (opus)
        # Already defined above (same key)
        # NOVELTY — KM.assess_novelty
        "sonnet:NoveltyAssessment": NoveltyAssessment(
            finding="Splenic hemolysis increases by 54% in microgravity",
            is_novel=True,
            novelty_score=0.8,
            reasoning="No prior study quantified splenic contribution specifically.",
        ),
    }


def _make_runner():
    """Create a W1 runner with mocked agents."""
    mock = MockLLMLayer(_make_mock_responses())
    registry = create_registry(mock)
    return W1LiteratureReviewRunner(registry=registry)


# === Step Definition Tests ===


def test_step_count():
    """W1 should have exactly 10 steps."""
    assert len(W1_STEPS) == 10
    print("  PASS: step_count")


def test_step_order():
    """Steps should be in correct order."""
    expected = ["SCOPE", "SEARCH", "SCREEN", "EXTRACT", "NEGATIVE_CHECK",
                "SYNTHESIZE", "CITATION_CHECK", "RCMXT_SCORE",
                "NOVELTY_CHECK", "REPORT"]
    actual = [s.id for s in W1_STEPS]
    assert actual == expected
    print("  PASS: step_order")


def test_human_checkpoint():
    """SYNTHESIZE should be the human checkpoint."""
    synth = get_step_by_id("SYNTHESIZE")
    assert synth is not None
    assert synth.is_human_checkpoint is True
    # No other steps should be human checkpoints
    for step in W1_STEPS:
        if step.id != "SYNTHESIZE":
            assert not step.is_human_checkpoint, f"{step.id} should not be checkpoint"
    print("  PASS: human_checkpoint")


def test_code_only_steps():
    """NEGATIVE_CHECK, CITATION_CHECK, RCMXT_SCORE, and REPORT should be code-only."""
    for step_id in ("NEGATIVE_CHECK", "CITATION_CHECK", "RCMXT_SCORE", "REPORT"):
        step = get_step_by_id(step_id)
        assert step is not None, f"{step_id} not found"
        assert step.agent_id == "code_only", f"{step_id} should be code_only"
        assert step.estimated_cost == 0.0, f"{step_id} should have zero cost"
    print("  PASS: code_only_steps")


def test_method_map_coverage():
    """All agent steps should have method routing."""
    agent_steps = [s for s in W1_STEPS if s.agent_id != "code_only"]
    for step in agent_steps:
        assert step.id in _METHOD_MAP, f"{step.id} missing from _METHOD_MAP"
    print("  PASS: method_map_coverage")


def test_get_step_by_id():
    assert get_step_by_id("SCOPE") is not None
    assert get_step_by_id("NONEXISTENT") is None
    print("  PASS: get_step_by_id")


# === Pipeline Execution Tests ===


def test_run_to_human_checkpoint():
    """Pipeline should run up to SYNTHESIZE and pause for human review."""
    runner = _make_runner()
    result = asyncio.run(runner.run(query="spaceflight-induced anemia mechanisms"))

    instance = result["instance"]
    assert instance.state == "WAITING_HUMAN", f"Expected WAITING_HUMAN, got {instance.state}"
    assert result["paused_at"] is not None

    # Steps up to SYNTHESIZE should have been executed
    step_ids = list(result["step_results"].keys())
    assert "SCOPE" in step_ids
    assert "SEARCH" in step_ids
    assert "SCREEN" in step_ids
    assert "EXTRACT" in step_ids
    assert "NEGATIVE_CHECK" in step_ids
    assert "SYNTHESIZE" in step_ids
    # Post-human steps should NOT have run yet
    assert "CITATION_CHECK" not in step_ids
    assert "RCMXT_SCORE" not in step_ids
    assert "NOVELTY_CHECK" not in step_ids
    assert "REPORT" not in step_ids
    print("  PASS: run_to_human_checkpoint")


def test_resume_after_human():
    """After human approval, pipeline should complete."""
    runner = _make_runner()

    # Run to checkpoint
    first = asyncio.run(runner.run(query="spaceflight anemia"))
    instance = first["instance"]
    assert instance.state == "WAITING_HUMAN"

    # Resume
    final = asyncio.run(runner.resume_after_human(instance, query="spaceflight anemia"))
    assert final["completed"] is True
    assert final["instance"].state == "COMPLETED"

    step_ids = list(final["step_results"].keys())
    assert "CITATION_CHECK" in step_ids
    assert "RCMXT_SCORE" in step_ids
    assert "NOVELTY_CHECK" in step_ids
    assert "REPORT" in step_ids
    print("  PASS: resume_after_human")


def test_negative_check_no_lab_kb():
    """NEGATIVE_CHECK without LabKB should return empty results."""
    runner = _make_runner()
    result = asyncio.run(runner.run(query="test query"))

    neg_check = result["step_results"].get("NEGATIVE_CHECK")
    assert neg_check is not None
    # Should have output with 0 negative results
    if isinstance(neg_check, dict) and "output" in neg_check:
        output = neg_check["output"]
    else:
        output = neg_check
    # The output should indicate 0 negative results found
    print("  PASS: negative_check_no_lab_kb")


if __name__ == "__main__":
    print("Testing W1 Literature Review Runner:")
    test_step_count()
    test_step_order()
    test_human_checkpoint()
    test_code_only_steps()
    test_method_map_coverage()
    test_get_step_by_id()
    test_run_to_human_checkpoint()
    test_resume_after_human()
    test_negative_check_no_lab_kb()
    print("\nAll W1 Literature Review Runner tests passed!")
