"""Tests for Structural Biology Agent (Team 7) — run, output type, summary."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.teams.t07_structural_bio import (
    StructuralAnalysisResult,
    StructuralBiologyAgent,
)
from app.llm.mock_layer import MockLLMLayer
from app.models.messages import ContextPackage


def make_agent(mock_responses: dict | None = None) -> StructuralBiologyAgent:
    """Create a StructuralBiologyAgent with MockLLMLayer."""
    spec = BaseAgent.load_spec("t07_structural_bio")
    mock = MockLLMLayer(mock_responses or {})
    return StructuralBiologyAgent(spec=spec, llm=mock)


def test_run_returns_output():
    """T07 should answer a structural biology query and return AgentOutput."""
    result = StructuralAnalysisResult(
        query="TP53 R248W mutation impact on DNA binding",
        proteins_analyzed=["TP53"],
        structures=[
            {"pdb_id": "2XWR", "resolution": 1.9, "method": "X-ray crystallography"},
        ],
        binding_sites=["L1 loop DNA-binding interface", "zinc coordination site"],
        docking_results=[
            {"ligand": "DNA response element", "binding_energy": -8.2, "rmsd": 1.3},
        ],
        methodology="AlphaFold2 prediction + FoldX stability analysis",
        pdb_ids=["2XWR", "1TSR"],
        summary="R248W disrupts DNA contact at the L1 loop, reducing binding affinity by ~60%.",
        confidence=0.83,
        caveats=["FoldX stability estimate has ~1 kcal/mol error margin"],
    )
    agent = make_agent({"sonnet:StructuralAnalysisResult": result})

    context = ContextPackage(
        task_description="Predict the effect of TP53 R248W mutation on protein structure and DNA binding"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert output.output["proteins_analyzed"] == ["TP53"]
    assert output.output["pdb_ids"] == ["2XWR", "1TSR"]
    assert len(output.output["binding_sites"]) == 2
    assert output.model_version.startswith("mock-")
    print("  PASS: run_returns_output")


def test_output_type():
    """T07 output should have correct output_type."""
    result = StructuralAnalysisResult(
        query="Test query",
        summary="Test summary for structural biology output type verification.",
        confidence=0.75,
    )
    agent = make_agent({"sonnet:StructuralAnalysisResult": result})
    context = ContextPackage(task_description="Test structural biology query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.output_type == "StructuralAnalysisResult"
    print("  PASS: output_type")


def test_summary_populated():
    """T07 output should have a populated summary."""
    result = StructuralAnalysisResult(
        query="Druggable pockets on SARS-CoV-2 Mpro",
        summary="Catalytic site (C145-H41 dyad) and allosteric pocket identified; druggability score 0.87.",
        confidence=0.81,
    )
    agent = make_agent({"sonnet:StructuralAnalysisResult": result})
    context = ContextPackage(task_description="Identify druggable binding pockets on SARS-CoV-2 main protease")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.summary
    assert len(output.summary) > 0
    assert "Catalytic" in output.summary
    print("  PASS: summary_populated")


def test_agent_metadata():
    """T07 output should carry correct agent metadata."""
    agent = make_agent()
    context = ContextPackage(task_description="Test query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.agent_id == "t07_structural_bio"
    assert output.model_tier == "sonnet"
    assert output.model_version == "mock-sonnet"
    assert output.duration_ms >= 0
    print("  PASS: agent_metadata")


def test_spec_loaded_correctly():
    """T07 spec should have expected fields."""
    spec = BaseAgent.load_spec("t07_structural_bio")
    assert spec.id == "t07_structural_bio"
    assert spec.tier == "domain_expert"
    assert spec.model_tier == "sonnet"
    assert spec.criticality == "optional"
    assert spec.division == "computation"
    print("  PASS: spec_loaded_correctly")


if __name__ == "__main__":
    print("Testing Structural Biology Agent (T07):")
    test_run_returns_output()
    test_output_type()
    test_summary_populated()
    test_agent_metadata()
    test_spec_loaded_correctly()
    print("\nAll Structural Biology Agent tests passed!")
