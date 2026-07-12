"""Tests for Systems Biology Agent (Team 6) — run, output type, summary."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.teams.t06_systems_bio import (
    NetworkAnalysisResult,
    SystemsBiologyAgent,
)
from app.llm.mock_layer import MockLLMLayer
from app.models.messages import ContextPackage


def make_agent(mock_responses: dict | None = None) -> SystemsBiologyAgent:
    """Create a SystemsBiologyAgent with MockLLMLayer."""
    spec = BaseAgent.load_spec("t06_systems_bio")
    mock = MockLLMLayer(mock_responses or {})
    return SystemsBiologyAgent(spec=spec, llm=mock)


def test_run_returns_output():
    """T06 should answer a systems biology query and return AgentOutput."""
    result = NetworkAnalysisResult(
        query="Enriched pathways in spaceflight DEGs across tissues",
        enriched_pathways=[
            {"name": "Oxidative phosphorylation", "p_adj": 1.2e-6, "gene_count": 32},
            {"name": "DNA damage response", "p_adj": 3.4e-5, "gene_count": 18},
        ],
        hub_genes=["TP53", "AKT1", "MAPK3"],
        network_modules=[
            {"module": "M1", "size": 45, "top_pathway": "Oxidative phosphorylation"},
        ],
        databases_used=["KEGG", "Reactome", "STRING"],
        methodology="WGCNA module detection + GO/KEGG enrichment",
        summary="Oxidative phosphorylation and DNA damage response are consistently enriched across tissues.",
        confidence=0.85,
        caveats=["Cross-tissue comparison limited by different sequencing depths"],
    )
    agent = make_agent({"sonnet:NetworkAnalysisResult": result})

    context = ContextPackage(
        task_description="What pathways are enriched in spaceflight DEGs across multiple tissues?"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert len(output.output["enriched_pathways"]) == 2
    assert output.output["hub_genes"] == ["TP53", "AKT1", "MAPK3"]
    assert output.model_version.startswith("mock-")
    print("  PASS: run_returns_output")


def test_output_type():
    """T06 output should have correct output_type."""
    result = NetworkAnalysisResult(
        query="Test query",
        summary="Test summary for network analysis output type verification.",
        confidence=0.75,
    )
    agent = make_agent({"sonnet:NetworkAnalysisResult": result})
    context = ContextPackage(task_description="Test systems biology query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.output_type == "NetworkAnalysisResult"
    print("  PASS: output_type")


def test_summary_populated():
    """T06 output should have a populated summary."""
    result = NetworkAnalysisResult(
        query="Gene regulatory network from spaceflight transcriptomics",
        summary="WGCNA identified 8 modules; hub genes TP53 and STAT3 connect immune and stress modules.",
        confidence=0.78,
    )
    agent = make_agent({"sonnet:NetworkAnalysisResult": result})
    context = ContextPackage(task_description="Build a gene regulatory network from multi-tissue spaceflight data")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.summary
    assert len(output.summary) > 0
    assert "WGCNA" in output.summary
    print("  PASS: summary_populated")


def test_agent_metadata():
    """T06 output should carry correct agent metadata."""
    agent = make_agent()
    context = ContextPackage(task_description="Test query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.agent_id == "t06_systems_bio"
    assert output.model_tier == "sonnet"
    assert output.model_version == "mock-sonnet"
    assert output.duration_ms >= 0
    print("  PASS: agent_metadata")


def test_spec_loaded_correctly():
    """T06 spec should have expected fields."""
    spec = BaseAgent.load_spec("t06_systems_bio")
    assert spec.id == "t06_systems_bio"
    assert spec.tier == "domain_expert"
    assert spec.model_tier == "sonnet"
    assert spec.criticality == "optional"
    assert spec.division == "computation"
    print("  PASS: spec_loaded_correctly")


if __name__ == "__main__":
    print("Testing Systems Biology Agent (T06):")
    test_run_returns_output()
    test_output_type()
    test_summary_populated()
    test_agent_metadata()
    test_spec_loaded_correctly()
    print("\nAll Systems Biology Agent tests passed!")
