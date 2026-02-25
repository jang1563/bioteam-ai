"""Tests for Proteomics Agent (Team 3) — run, output type, summary."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.teams.t03_proteomics import (
    ProteomicsAgent,
    ProteomicsAnalysisResult,
)
from app.llm.mock_layer import MockLLMLayer
from app.models.messages import ContextPackage


def make_agent(mock_responses: dict | None = None) -> ProteomicsAgent:
    """Create a ProteomicsAgent with MockLLMLayer."""
    spec = BaseAgent.load_spec("t03_proteomics")
    mock = MockLLMLayer(mock_responses or {})
    return ProteomicsAgent(spec=spec, llm=mock)


def test_run_returns_output():
    """T03 should answer a proteomics query and return AgentOutput."""
    result = ProteomicsAnalysisResult(
        query="Differentially abundant proteins in astronaut plasma",
        proteins_analyzed=["ALB", "FTL", "FTH1", "HP", "HPX"],
        metabolites=["lactate", "succinate"],
        pathways=["iron homeostasis", "oxidative phosphorylation"],
        methodology="TMT-labeled LC-MS/MS with MaxQuant",
        datasets_used=["PXD012345"],
        summary="FTL and FTH1 are significantly elevated post-flight, suggesting iron mobilization.",
        confidence=0.78,
        caveats=["Limited to plasma; tissue-level changes not captured"],
    )
    agent = make_agent({"sonnet:ProteomicsAnalysisResult": result})

    context = ContextPackage(
        task_description="Which proteins are differentially abundant in astronaut plasma after long-duration spaceflight?"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert output.output["proteins_analyzed"] == ["ALB", "FTL", "FTH1", "HP", "HPX"]
    assert output.output["pathways"] == ["iron homeostasis", "oxidative phosphorylation"]
    assert output.model_version.startswith("mock-")
    print("  PASS: run_returns_output")


def test_output_type():
    """T03 output should have correct output_type."""
    result = ProteomicsAnalysisResult(
        query="Test query",
        summary="Test summary for proteomics output type verification.",
        confidence=0.80,
    )
    agent = make_agent({"sonnet:ProteomicsAnalysisResult": result})
    context = ContextPackage(task_description="Test proteomics query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.output_type == "ProteomicsAnalysisResult"
    print("  PASS: output_type")


def test_summary_populated():
    """T03 output should have a populated summary."""
    result = ProteomicsAnalysisResult(
        query="Metabolite changes in spaceflight urine",
        summary="Lactate and succinate elevated in spaceflight urine, indicating altered energy metabolism.",
        confidence=0.72,
    )
    agent = make_agent({"sonnet:ProteomicsAnalysisResult": result})
    context = ContextPackage(task_description="Map metabolite changes in spaceflight urine samples")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.summary
    assert len(output.summary) > 0
    assert "Lactate" in output.summary
    print("  PASS: summary_populated")


def test_agent_metadata():
    """T03 output should carry correct agent metadata."""
    agent = make_agent()
    context = ContextPackage(task_description="Test query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.agent_id == "t03_proteomics"
    assert output.model_tier == "sonnet"
    assert output.model_version == "mock-sonnet"
    assert output.duration_ms >= 0
    print("  PASS: agent_metadata")


def test_spec_loaded_correctly():
    """T03 spec should have expected fields."""
    spec = BaseAgent.load_spec("t03_proteomics")
    assert spec.id == "t03_proteomics"
    assert spec.tier == "domain_expert"
    assert spec.model_tier == "sonnet"
    assert spec.criticality == "optional"
    assert spec.division == "wet_to_dry"
    print("  PASS: spec_loaded_correctly")


if __name__ == "__main__":
    print("Testing Proteomics Agent (T03):")
    test_run_returns_output()
    test_output_type()
    test_summary_populated()
    test_agent_metadata()
    test_spec_loaded_correctly()
    print("\nAll Proteomics Agent tests passed!")
