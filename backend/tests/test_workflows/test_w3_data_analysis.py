"""Tests for W3 Data Analysis Runner."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.registry import create_registry
from app.llm.mock_layer import MockLLMLayer
from app.workflows.runners.w3_data_analysis import (
    _METHOD_MAP,
    W3_STEPS,
    W3DataAnalysisRunner,
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
    return W3DataAnalysisRunner(registry=registry)


# === Step Definition Tests ===


def test_step_count():
    """W3 should have exactly 11 steps."""
    assert len(W3_STEPS) == 11


def test_step_order():
    expected = [
        "INGEST", "QC", "PLAN", "EXECUTE", "INTEGRATE",
        "VALIDATE", "PLAUSIBILITY", "INTERPRET",
        "CONTRADICTION_CHECK", "AUDIT", "REPORT",
    ]
    actual = [s.id for s in W3_STEPS]
    assert actual == expected


def test_code_only_steps():
    step = get_step_by_id("REPORT")
    assert step is not None
    assert step.agent_id == "code_only"
    assert step.estimated_cost == 0.0


def test_method_map_coverage():
    agent_steps = [s for s in W3_STEPS if s.agent_id != "code_only"]
    for step in agent_steps:
        assert step.id in _METHOD_MAP, f"{step.id} missing from _METHOD_MAP"


def test_get_step_by_id():
    assert get_step_by_id("PLAN") is not None
    assert get_step_by_id("NONEXISTENT") is None


def test_human_checkpoint_on_plan():
    """PLAN step should be marked as a human checkpoint."""
    step = get_step_by_id("PLAN")
    assert step is not None
    assert step.is_human_checkpoint is True


def test_no_parallel_steps():
    """W3 should have no parallel steps."""
    for step in W3_STEPS:
        assert step.is_parallel is False or step.is_parallel is None or not step.is_parallel


# === Pipeline Tests ===


def test_pipeline_pauses_at_plan():
    """W3 run() should pause at PLAN human checkpoint."""
    runner = _make_runner()
    result = asyncio.run(runner.run(query="Analyze RNA-seq data from spaceflight samples"))

    instance = result["instance"]
    assert instance.state == "WAITING_HUMAN"
    assert result["paused_at"] is not None

    # Steps before and including PLAN should have results
    step_ids = list(result["step_results"].keys())
    assert "INGEST" in step_ids
    assert "QC" in step_ids
    assert "PLAN" in step_ids

    # Steps after PLAN should NOT have results yet
    assert "EXECUTE" not in step_ids
    assert "INTEGRATE" not in step_ids
    assert "REPORT" not in step_ids


def test_resume_after_human_completes():
    """After resume_after_human(), pipeline should complete."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test data analysis pipeline"))

    instance = pause_result["instance"]
    assert instance.state == "WAITING_HUMAN"

    # Resume after human approval
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test data analysis pipeline"))

    assert resume_result["completed"] is True
    assert resume_result["instance"].state == "COMPLETED"
    assert resume_result["instance"].template == "W3"

    # All post-checkpoint steps should be present
    step_ids = list(resume_result["step_results"].keys())
    assert "EXECUTE" in step_ids
    assert "INTEGRATE" in step_ids
    assert "VALIDATE" in step_ids
    assert "PLAUSIBILITY" in step_ids
    assert "INTERPRET" in step_ids
    assert "CONTRADICTION_CHECK" in step_ids
    assert "AUDIT" in step_ids
    assert "REPORT" in step_ids


def test_report_structure():
    """REPORT step should produce a structured analysis report."""
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
    assert "analysis_results" in output


def test_session_manifest_populated():
    """Instance session_manifest should contain analysis report after full run."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test manifest"))

    instance = pause_result["instance"]
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test manifest"))

    manifest = resume_result["instance"].session_manifest
    assert manifest is not None
    assert "analysis_report" in manifest


def test_budget_tracking():
    """Budget should be tracked across run() and resume_after_human()."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test budget", budget=10.0))

    instance = pause_result["instance"]
    assert instance.budget_total == 10.0
    # Budget remaining should be less than or equal to total
    assert instance.budget_remaining <= instance.budget_total

    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test budget"))
    final_instance = resume_result["instance"]
    assert final_instance.budget_remaining <= final_instance.budget_total
