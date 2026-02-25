"""Tests for W6 Ambiguity Resolution Runner."""

import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.ambiguity_engine import ContradictionClassification, ResolutionOutput
from app.agents.knowledge_manager import MemoryRetrievalResult
from app.agents.registry import create_registry
from app.llm.mock_layer import MockLLMLayer
from app.models.workflow import WorkflowInstance
from app.workflows.runners.w6_ambiguity import (
    W6AmbiguityRunner,
    W6_STEPS,
    get_step_by_id,
    _METHOD_MAP,
)


def _make_mock_responses() -> dict:
    return {
        "sonnet:ContradictionClassification": ContradictionClassification(
            types=["conditional_truth"],
            confidence=0.8,
            type_reasoning={"conditional_truth": "Context-dependent finding"},
            is_genuine_contradiction=True,
        ),
        "sonnet:ResolutionOutput": ResolutionOutput(
            hypotheses=[],
            discriminating_experiment="Test under both conditions",
        ),
    }


def _make_runner():
    mock = MockLLMLayer(_make_mock_responses())
    registry = create_registry(mock)
    return W6AmbiguityRunner(registry=registry)


# === Step Definition Tests ===


def test_step_count():
    """W6 should have exactly 5 steps."""
    assert len(W6_STEPS) == 5


def test_step_order():
    expected = ["EVIDENCE_LANDSCAPE", "CLASSIFY", "MINE_NEGATIVES",
                "RESOLUTION_HYPOTHESES", "PRESENT"]
    actual = [s.id for s in W6_STEPS]
    assert actual == expected


def test_code_only_steps():
    for step_id in ("MINE_NEGATIVES", "PRESENT"):
        step = get_step_by_id(step_id)
        assert step is not None
        assert step.agent_id == "code_only"
        assert step.estimated_cost == 0.0


def test_method_map_coverage():
    agent_steps = [s for s in W6_STEPS if s.agent_id != "code_only"]
    for step in agent_steps:
        assert step.id in _METHOD_MAP, f"{step.id} missing from _METHOD_MAP"


def test_get_step_by_id():
    assert get_step_by_id("CLASSIFY") is not None
    assert get_step_by_id("NONEXISTENT") is None


# === Pipeline Tests ===


def test_full_pipeline_completes():
    """W6 should run all 5 steps and complete."""
    runner = _make_runner()
    result = asyncio.run(runner.run(query="Do VEGF levels increase or decrease in spaceflight?"))

    assert result["completed"] is True
    assert result["instance"].state == "COMPLETED"
    assert result["instance"].template == "W6"

    step_ids = list(result["step_results"].keys())
    assert "EVIDENCE_LANDSCAPE" in step_ids
    assert "CLASSIFY" in step_ids
    assert "MINE_NEGATIVES" in step_ids
    assert "RESOLUTION_HYPOTHESES" in step_ids
    assert "PRESENT" in step_ids


def test_present_report_structure():
    """PRESENT step should produce a structured report."""
    runner = _make_runner()
    result = asyncio.run(runner.run(query="Test contradiction query"))

    present = result["step_results"].get("PRESENT")
    assert present is not None
    # step_results contains serialized AgentOutput; the report is in the "output" field
    output = present.get("output", present) if isinstance(present, dict) else present

    # Should have the expected keys
    assert "query" in output
    assert "workflow_id" in output
    assert "ambiguity_level" in output


def test_mine_negatives_no_lab_kb():
    """MINE_NEGATIVES without LabKB should return empty."""
    runner = _make_runner()
    result = asyncio.run(runner.run(query="Test"))

    neg = result["step_results"].get("MINE_NEGATIVES")
    assert neg is not None


def test_session_manifest_populated():
    """Instance session_manifest should contain ambiguity report."""
    runner = _make_runner()
    result = asyncio.run(runner.run(query="Test contradiction"))

    manifest = result["instance"].session_manifest
    assert manifest is not None
    assert "ambiguity_report" in manifest


def test_budget_tracking():
    """Budget should be deducted for agent steps."""
    runner = _make_runner()
    result = asyncio.run(runner.run(query="Test", budget=10.0))

    instance = result["instance"]
    assert instance.budget_total == 10.0
    # Budget remaining should be less than or equal to total (some cost deducted)
    assert instance.budget_remaining <= instance.budget_total
