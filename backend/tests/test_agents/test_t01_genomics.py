"""Tests for Genomics Agent (Team 1) — run, output type, summary."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.teams.t01_genomics import (
    GenomicsAgent,
    GenomicsAnalysisResult,
)
from app.llm.mock_layer import MockLLMLayer
from app.models.messages import ContextPackage


def make_agent(mock_responses: dict | None = None) -> GenomicsAgent:
    """Create a GenomicsAgent with MockLLMLayer."""
    spec = BaseAgent.load_spec("t01_genomics")
    mock = MockLLMLayer(mock_responses or {})
    return GenomicsAgent(spec=spec, llm=mock)


def test_run_returns_output():
    """T01 should answer a genomics query and return AgentOutput."""
    result = GenomicsAnalysisResult(
        query="TP53 variants in spaceflight clonal hematopoiesis",
        variants_analyzed=["TP53 R248W", "DNMT3A R882H"],
        epigenetic_marks=["H3K27me3"],
        pathways=["DNA damage response", "apoptosis"],
        methodology="WGS variant calling with GATK HaplotypeCaller",
        datasets_used=["GSE150000"],
        summary="TP53 R248W detected at 2.1% VAF in 3/14 astronauts post-flight.",
        confidence=0.82,
        caveats=["Small cohort size limits generalizability"],
    )
    agent = make_agent({"sonnet:GenomicsAnalysisResult": result})

    context = ContextPackage(
        task_description="What TP53 variants are associated with spaceflight clonal hematopoiesis?"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert output.output["variants_analyzed"] == ["TP53 R248W", "DNMT3A R882H"]
    assert output.output["pathways"] == ["DNA damage response", "apoptosis"]
    assert output.model_version.startswith("mock-")
    print("  PASS: run_returns_output")


def test_output_type():
    """T01 output should have correct output_type."""
    result = GenomicsAnalysisResult(
        query="Test query",
        summary="Test summary for output type verification.",
        confidence=0.75,
    )
    agent = make_agent({"sonnet:GenomicsAnalysisResult": result})
    context = ContextPackage(task_description="Test genomics query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.output_type == "GenomicsAnalysisResult"
    print("  PASS: output_type")


def test_summary_populated():
    """T01 output should have a populated summary."""
    result = GenomicsAnalysisResult(
        query="Epigenetic changes in spaceflight",
        summary="H3K27me3 redistribution observed at promoters of stress-response genes.",
        confidence=0.70,
    )
    agent = make_agent({"sonnet:GenomicsAnalysisResult": result})
    context = ContextPackage(task_description="Characterize epigenetic changes in spaceflight blood samples")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.summary
    assert len(output.summary) > 0
    assert "H3K27me3" in output.summary
    print("  PASS: summary_populated")


def test_agent_metadata():
    """T01 output should carry correct agent metadata."""
    agent = make_agent()
    context = ContextPackage(task_description="Test query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.agent_id == "t01_genomics"
    assert output.model_tier == "sonnet"
    assert output.model_version == "mock-sonnet"
    assert output.duration_ms >= 0
    print("  PASS: agent_metadata")


def test_spec_loaded_correctly():
    """T01 spec should have expected fields."""
    spec = BaseAgent.load_spec("t01_genomics")
    assert spec.id == "t01_genomics"
    assert spec.tier == "domain_expert"
    assert spec.model_tier == "sonnet"
    assert spec.criticality == "optional"
    assert spec.division == "wet_to_dry"
    print("  PASS: spec_loaded_correctly")


if __name__ == "__main__":
    print("Testing Genomics Agent (T01):")
    test_run_returns_output()
    test_output_type()
    test_summary_populated()
    test_agent_metadata()
    test_spec_loaded_correctly()
    print("\nAll Genomics Agent tests passed!")
