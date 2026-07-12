"""Tests for Experimental Designer Agent — run, output type, summary."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.experimental_designer import (
    ExperimentalDesignerAgent,
    ExperimentalDesignResult,
)
from app.llm.mock_layer import MockLLMLayer
from app.models.messages import ContextPackage


def make_agent(mock_responses: dict | None = None) -> ExperimentalDesignerAgent:
    """Create an ExperimentalDesignerAgent with MockLLMLayer."""
    spec = BaseAgent.load_spec("experimental_designer")
    mock = MockLLMLayer(mock_responses or {})
    return ExperimentalDesignerAgent(spec=spec, llm=mock)


def test_run_returns_output():
    """Experimental Designer should design an experiment and return AgentOutput."""
    result = ExperimentalDesignResult(
        query="Mouse study for spaceflight-induced bone loss",
        design_type="Randomized controlled trial with ground analog",
        groups=[
            {"name": "Flight", "n": 10, "description": "ISS-exposed mice"},
            {"name": "Ground control", "n": 10, "description": "Vivarium-housed mice"},
            {"name": "Hindlimb unloading", "n": 10, "description": "Ground analog"},
        ],
        sample_size=30,
        power_analysis="n=10/group provides 80% power to detect 15% BMD change (alpha=0.05, two-sided)",
        controls=["Vivarium ground control", "Hindlimb unloading analog"],
        randomization="Stratified by sex and age, block randomization within strata",
        blocking_strategy="Block by sex (M/F) and age (8-10 wk / 12-14 wk)",
        statistical_tests=["Two-way ANOVA", "Tukey post-hoc", "Bonferroni correction"],
        summary="3-group RCT with n=10/group; blocked by sex/age; 80% power for 15% BMD change.",
        confidence=0.85,
        caveats=["ISS flight opportunities limit replication", "Hindlimb unloading is imperfect analog"],
    )
    agent = make_agent({"sonnet:ExperimentalDesignResult": result})

    context = ContextPackage(
        task_description="Design a mouse study to test spaceflight-induced bone loss with ground controls"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert output.output["design_type"] == "Randomized controlled trial with ground analog"
    assert len(output.output["groups"]) == 3
    assert output.output["sample_size"] == 30
    assert output.model_version.startswith("mock-")
    print("  PASS: run_returns_output")


def test_output_type():
    """Experimental Designer output should have correct output_type."""
    result = ExperimentalDesignResult(
        query="Test query",
        summary="Test summary for experimental design output type verification.",
        confidence=0.75,
    )
    agent = make_agent({"sonnet:ExperimentalDesignResult": result})
    context = ContextPackage(task_description="Test experimental design query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.output_type == "ExperimentalDesignResult"
    print("  PASS: output_type")


def test_summary_populated():
    """Experimental Designer output should have a populated summary."""
    result = ExperimentalDesignResult(
        query="cfRNA biomarker discovery study design",
        summary="Repeated-measures design with n=20/group for medium effect size across 3 timepoints.",
        confidence=0.80,
    )
    agent = make_agent({"sonnet:ExperimentalDesignResult": result})
    context = ContextPackage(task_description="Sample size for cfRNA biomarker discovery with 3 timepoints")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.summary
    assert len(output.summary) > 0
    assert "n=20" in output.summary
    print("  PASS: summary_populated")


def test_agent_metadata():
    """Experimental Designer output should carry correct agent metadata."""
    agent = make_agent()
    context = ContextPackage(task_description="Test query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.agent_id == "experimental_designer"
    assert output.model_tier == "sonnet"
    assert output.model_version == "mock-sonnet"
    assert output.duration_ms >= 0
    print("  PASS: agent_metadata")


def test_spec_loaded_correctly():
    """Experimental Designer spec should have expected fields."""
    spec = BaseAgent.load_spec("experimental_designer")
    assert spec.id == "experimental_designer"
    assert spec.tier == "domain_expert"
    assert spec.model_tier == "sonnet"
    assert spec.criticality == "optional"
    assert spec.division == "cross_cutting"
    print("  PASS: spec_loaded_correctly")


if __name__ == "__main__":
    print("Testing Experimental Designer Agent:")
    test_run_returns_output()
    test_output_type()
    test_summary_populated()
    test_agent_metadata()
    test_spec_loaded_correctly()
    print("\nAll Experimental Designer Agent tests passed!")
