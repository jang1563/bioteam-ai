"""Tests for W4 Manuscript Writing Runner."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.registry import create_registry
from app.llm.mock_layer import MockLLMLayer
from app.workflows.runners.w4_manuscript import (
    _METHOD_MAP,
    W4_STEPS,
    W4ManuscriptRunner,
    get_step_by_id,
)


def _patch_qa_aliases(registry):
    """Register QA agents under the alias IDs used by workflow runners.

    The registry registers QA agents with spec IDs (qa_statistical_rigor, etc.)
    but the runners reference them as (statistical_rigor_qa, etc.).
    """
    alias_map = {
        "statistical_rigor_qa": "qa_statistical_rigor",
        "biological_plausibility_qa": "qa_biological_plausibility",
        "reproducibility_qa": "qa_reproducibility",
    }
    for alias, spec_id in alias_map.items():
        agent = registry.get(spec_id)
        if agent and registry.get(alias) is None:
            registry._agents[alias] = agent


def _make_runner():
    mock = MockLLMLayer({})
    registry = create_registry(mock)
    _patch_qa_aliases(registry)
    return W4ManuscriptRunner(registry=registry)


# === Step Definition Tests ===


def test_step_count():
    """W4 should have exactly 9 steps."""
    assert len(W4_STEPS) == 9


def test_step_order():
    expected = [
        "OUTLINE", "ASSEMBLE", "DRAFT", "FIGURES",
        "STATISTICAL_REVIEW", "PLAUSIBILITY_REVIEW",
        "REPRODUCIBILITY_CHECK", "REVISION", "REPORT",
    ]
    actual = [s.id for s in W4_STEPS]
    assert actual == expected


def test_code_only_steps():
    step = get_step_by_id("REPORT")
    assert step is not None
    assert step.agent_id == "code_only"
    assert step.estimated_cost == 0.0


def test_method_map_coverage():
    agent_steps = [s for s in W4_STEPS if s.agent_id != "code_only"]
    for step in agent_steps:
        assert step.id in _METHOD_MAP, f"{step.id} missing from _METHOD_MAP"


def test_get_step_by_id():
    assert get_step_by_id("OUTLINE") is not None
    assert get_step_by_id("NONEXISTENT") is None


def test_human_checkpoint_on_outline():
    """OUTLINE step should be marked as a human checkpoint."""
    step = get_step_by_id("OUTLINE")
    assert step is not None
    assert step.is_human_checkpoint is True


def test_no_parallel_steps():
    """W4 should have no parallel steps."""
    for step in W4_STEPS:
        assert step.is_parallel is False or step.is_parallel is None or not step.is_parallel


# === Pipeline Tests ===


def test_pipeline_pauses_at_outline():
    """W4 run() should pause at OUTLINE human checkpoint."""
    runner = _make_runner()
    result = asyncio.run(runner.run(query="Draft manuscript on spaceflight-induced anemia mechanisms"))

    instance = result["instance"]
    assert instance.state == "WAITING_HUMAN"
    assert result["paused_at"] is not None

    # Only OUTLINE should have results (it's the first step and the checkpoint)
    step_ids = list(result["step_results"].keys())
    assert "OUTLINE" in step_ids

    # Steps after OUTLINE should NOT have results yet
    assert "ASSEMBLE" not in step_ids
    assert "DRAFT" not in step_ids
    assert "REPORT" not in step_ids


def test_resume_after_human_completes():
    """After resume_after_human(), pipeline should complete."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test manuscript pipeline"))

    instance = pause_result["instance"]
    assert instance.state == "WAITING_HUMAN"

    # Resume after human approval
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test manuscript pipeline"))

    assert resume_result["completed"] is True
    assert resume_result["instance"].state == "COMPLETED"
    assert resume_result["instance"].template == "W4"

    # All post-checkpoint steps should be present
    step_ids = list(resume_result["step_results"].keys())
    assert "ASSEMBLE" in step_ids
    assert "DRAFT" in step_ids
    assert "FIGURES" in step_ids
    assert "STATISTICAL_REVIEW" in step_ids
    assert "PLAUSIBILITY_REVIEW" in step_ids
    assert "REPRODUCIBILITY_CHECK" in step_ids
    assert "REVISION" in step_ids
    assert "REPORT" in step_ids


def test_report_structure():
    """REPORT step should produce a structured manuscript report."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test report structure"))

    instance = pause_result["instance"]
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test report structure"))

    report = resume_result["step_results"].get("REPORT")
    assert report is not None
    output = report.get("output", report) if isinstance(report, dict) else report

    # Should have the expected keys
    assert "query" in output
    assert "workflow_id" in output
    assert "reviews" in output


def test_session_manifest_populated():
    """Instance session_manifest should contain manuscript report after full run."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test manifest"))

    instance = pause_result["instance"]
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test manifest"))

    manifest = resume_result["instance"].session_manifest
    assert manifest is not None
    assert "manuscript_report" in manifest


def test_session_manifest_reviews():
    """Session manifest should include review summaries from _store_manuscript_results."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test reviews"))

    instance = pause_result["instance"]
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test reviews"))

    manifest = resume_result["instance"].session_manifest
    assert manifest is not None
    assert "reviews" in manifest
    assert "workflow_template" in manifest
    assert manifest["workflow_template"] == "W4"


def test_budget_tracking():
    """Budget should be tracked across run() and resume_after_human()."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test budget", budget=25.0))

    instance = pause_result["instance"]
    assert instance.budget_total == 25.0
    # Budget remaining should be less than or equal to total
    assert instance.budget_remaining <= instance.budget_total

    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test budget"))
    final_instance = resume_result["instance"]
    assert final_instance.budget_remaining <= final_instance.budget_total
