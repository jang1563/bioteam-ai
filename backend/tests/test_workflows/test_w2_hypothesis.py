"""Tests for W2 Hypothesis Generation Runner."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.registry import create_registry
from app.llm.mock_layer import MockLLMLayer
from app.workflows.runners.w2_hypothesis import (
    _METHOD_MAP,
    _PARALLEL_AGENTS,
    W2_STEPS,
    W2HypothesisRunner,
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
    return W2HypothesisRunner(registry=registry)


# === Step Definition Tests ===


def test_step_count():
    """W2 should have exactly 8 steps."""
    assert len(W2_STEPS) == 8


def test_step_order():
    expected = [
        "CONTEXTUALIZE", "GENERATE", "NEGATIVE_FILTER", "DEBATE",
        "RANK", "EVOLVE", "RCMXT_PROFILE", "PRESENT",
    ]
    actual = [s.id for s in W2_STEPS]
    assert actual == expected


def test_code_only_steps():
    for step_id in ("NEGATIVE_FILTER", "PRESENT"):
        step = get_step_by_id(step_id)
        assert step is not None
        assert step.agent_id == "code_only"
        assert step.estimated_cost == 0.0


def test_method_map_coverage():
    agent_steps = [s for s in W2_STEPS
                   if s.agent_id != "code_only" and s.id not in _PARALLEL_AGENTS]
    for step in agent_steps:
        assert step.id in _METHOD_MAP, f"{step.id} missing from _METHOD_MAP"


def test_parallel_agents_defined():
    """GENERATE and DEBATE should have parallel agent lists."""
    assert "GENERATE" in _PARALLEL_AGENTS
    assert len(_PARALLEL_AGENTS["GENERATE"]) == 7
    assert "DEBATE" in _PARALLEL_AGENTS
    assert len(_PARALLEL_AGENTS["DEBATE"]) == 3


def test_get_step_by_id():
    assert get_step_by_id("RANK") is not None
    assert get_step_by_id("NONEXISTENT") is None


def test_human_checkpoint_on_rank():
    """RANK step should be marked as a human checkpoint."""
    step = get_step_by_id("RANK")
    assert step is not None
    assert step.is_human_checkpoint is True


# === Pipeline Tests ===


def test_pipeline_pauses_at_rank():
    """W2 run() should pause at RANK human checkpoint."""
    runner = _make_runner()
    result = asyncio.run(runner.run(query="Novel mechanisms of spaceflight-induced bone loss"))

    instance = result["instance"]
    assert instance.state == "WAITING_HUMAN"
    assert result["paused_at"] is not None

    # Steps before and including RANK should have results
    step_ids = list(result["step_results"].keys())
    assert "CONTEXTUALIZE" in step_ids
    assert "GENERATE" in step_ids
    assert "NEGATIVE_FILTER" in step_ids
    assert "DEBATE" in step_ids
    assert "RANK" in step_ids

    # Steps after RANK should NOT have results yet
    assert "EVOLVE" not in step_ids
    assert "RCMXT_PROFILE" not in step_ids
    assert "PRESENT" not in step_ids


def test_resume_after_human_completes():
    """After resume_after_human(), pipeline should complete."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test hypothesis generation"))

    instance = pause_result["instance"]
    assert instance.state == "WAITING_HUMAN"

    # Resume after human approval
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test hypothesis generation"))

    assert resume_result["completed"] is True
    assert resume_result["instance"].state == "COMPLETED"
    assert resume_result["instance"].template == "W2"

    # All post-checkpoint steps should be present
    step_ids = list(resume_result["step_results"].keys())
    assert "EVOLVE" in step_ids
    assert "RCMXT_PROFILE" in step_ids
    assert "PRESENT" in step_ids


def test_present_report_structure():
    """PRESENT step should produce a structured hypothesis report."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test report structure"))

    instance = pause_result["instance"]
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test report structure"))

    present = resume_result["step_results"].get("PRESENT")
    assert present is not None
    output = present.get("output", present) if isinstance(present, dict) else present

    # Should have the expected keys
    assert "query" in output
    assert "workflow_id" in output
    assert "hypotheses" in output


def test_session_manifest_populated():
    """Instance session_manifest should contain hypothesis report after full run."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test manifest"))

    instance = pause_result["instance"]
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test manifest"))

    manifest = resume_result["instance"].session_manifest
    assert manifest is not None
    assert "hypothesis_report" in manifest


def test_budget_tracking():
    """Budget should be tracked across run() and resume_after_human()."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test budget", budget=15.0))

    instance = pause_result["instance"]
    assert instance.budget_total == 15.0
    # Budget remaining should be less than or equal to total
    assert instance.budget_remaining <= instance.budget_total

    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test budget"))
    final_instance = resume_result["instance"]
    assert final_instance.budget_remaining <= final_instance.budget_total
