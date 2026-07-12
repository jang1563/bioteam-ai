"""Tests for W5 Grant Proposal Runner."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.registry import create_registry
from app.llm.mock_layer import MockLLMLayer
from app.workflows.runners.w5_grant import (
    _METHOD_MAP,
    _MOCK_REVIEW_AGENTS,
    W5_STEPS,
    W5GrantProposalRunner,
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
    return W5GrantProposalRunner(registry=registry)


# === Step Definition Tests ===


def test_step_count():
    """W5 should have exactly 8 steps."""
    assert len(W5_STEPS) == 8


def test_step_order():
    expected = [
        "OPPORTUNITY", "SPECIFIC_AIMS", "STRATEGY", "PRELIMINARY_DATA",
        "BUDGET_PLAN", "MOCK_REVIEW", "REVISION", "REPORT",
    ]
    actual = [s.id for s in W5_STEPS]
    assert actual == expected


def test_code_only_steps():
    step = get_step_by_id("REPORT")
    assert step is not None
    assert step.agent_id == "code_only"
    assert step.estimated_cost == 0.0


def test_method_map_coverage():
    """All non-code-only, non-parallel agent steps should be in _METHOD_MAP."""
    agent_steps = [s for s in W5_STEPS
                   if s.agent_id != "code_only" and not s.is_parallel]
    for step in agent_steps:
        assert step.id in _METHOD_MAP, f"{step.id} missing from _METHOD_MAP"


def test_mock_review_agents_defined():
    """MOCK_REVIEW should have 3 QA agents defined."""
    assert len(_MOCK_REVIEW_AGENTS) == 3
    assert "statistical_rigor_qa" in _MOCK_REVIEW_AGENTS
    assert "biological_plausibility_qa" in _MOCK_REVIEW_AGENTS
    assert "reproducibility_qa" in _MOCK_REVIEW_AGENTS


def test_get_step_by_id():
    assert get_step_by_id("SPECIFIC_AIMS") is not None
    assert get_step_by_id("NONEXISTENT") is None


def test_human_checkpoint_on_specific_aims():
    """SPECIFIC_AIMS step should be marked as a human checkpoint."""
    step = get_step_by_id("SPECIFIC_AIMS")
    assert step is not None
    assert step.is_human_checkpoint is True


def test_mock_review_is_parallel():
    """MOCK_REVIEW step should be marked as parallel."""
    step = get_step_by_id("MOCK_REVIEW")
    assert step is not None
    assert step.is_parallel is True


# === Pipeline Tests ===


def test_pipeline_pauses_at_specific_aims():
    """W5 run() should pause at SPECIFIC_AIMS human checkpoint."""
    runner = _make_runner()
    result = asyncio.run(runner.run(query="NIH R01 proposal for spaceflight anemia mechanisms"))

    instance = result["instance"]
    assert instance.state == "WAITING_HUMAN"
    assert result["paused_at"] is not None

    # Steps before and including SPECIFIC_AIMS should have results
    step_ids = list(result["step_results"].keys())
    assert "OPPORTUNITY" in step_ids
    assert "SPECIFIC_AIMS" in step_ids

    # Steps after SPECIFIC_AIMS should NOT have results yet
    assert "STRATEGY" not in step_ids
    assert "PRELIMINARY_DATA" not in step_ids
    assert "MOCK_REVIEW" not in step_ids
    assert "REPORT" not in step_ids


def test_resume_after_human_completes():
    """After resume_after_human(), pipeline should complete."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test grant proposal pipeline"))

    instance = pause_result["instance"]
    assert instance.state == "WAITING_HUMAN"

    # Resume after human approval
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test grant proposal pipeline"))

    assert resume_result["completed"] is True
    assert resume_result["instance"].state == "COMPLETED"
    assert resume_result["instance"].template == "W5"

    # All post-checkpoint steps should be present
    step_ids = list(resume_result["step_results"].keys())
    assert "STRATEGY" in step_ids
    assert "PRELIMINARY_DATA" in step_ids
    assert "BUDGET_PLAN" in step_ids
    assert "MOCK_REVIEW" in step_ids
    assert "REVISION" in step_ids
    assert "REPORT" in step_ids


def test_report_structure():
    """REPORT step should produce a structured grant proposal report."""
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
    assert "specific_aims" in output
    assert "mock_review_feedback" in output


def test_session_manifest_populated():
    """Instance session_manifest should contain grant report after full run."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test manifest"))

    instance = pause_result["instance"]
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test manifest"))

    manifest = resume_result["instance"].session_manifest
    assert manifest is not None
    assert "grant_report" in manifest


def test_session_manifest_mock_reviews():
    """Session manifest should include mock review feedback from _store_grant_results."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test mock reviews"))

    instance = pause_result["instance"]
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test mock reviews"))

    manifest = resume_result["instance"].session_manifest
    assert manifest is not None
    assert "mock_reviews" in manifest
    assert "workflow_template" in manifest
    assert manifest["workflow_template"] == "W5"


def test_budget_tracking():
    """Budget should be tracked across run() and resume_after_human()."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test budget", budget=30.0))

    instance = pause_result["instance"]
    assert instance.budget_total == 30.0
    # Budget remaining should be less than or equal to total
    assert instance.budget_remaining <= instance.budget_total

    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test budget"))
    final_instance = resume_result["instance"]
    assert final_instance.budget_remaining <= final_instance.budget_total
