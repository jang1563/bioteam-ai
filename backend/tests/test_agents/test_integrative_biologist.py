"""Tests for Integrative Biologist Agent — run, output type, summary."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.integrative_biologist import (
    IntegrativeAnalysisResult,
    IntegrativeBiologistAgent,
)
from app.llm.mock_layer import MockLLMLayer
from app.models.messages import ContextPackage


def make_agent(mock_responses: dict | None = None) -> IntegrativeBiologistAgent:
    """Create an IntegrativeBiologistAgent with MockLLMLayer."""
    spec = BaseAgent.load_spec("integrative_biologist")
    mock = MockLLMLayer(mock_responses or {})
    return IntegrativeBiologistAgent(spec=spec, llm=mock)


def test_run_returns_output():
    """Integrative Biologist should perform multi-omics integration and return AgentOutput."""
    result = IntegrativeAnalysisResult(
        query="Integrate transcriptomic and proteomic spaceflight data",
        omics_layers=["transcriptomics", "proteomics"],
        cross_omics_findings=[
            {"gene": "TNFSF11", "rna_log2fc": 1.8, "protein_log2fc": 1.2, "concordant": True},
            {"gene": "FTL", "rna_log2fc": 0.3, "protein_log2fc": 2.1, "concordant": False},
        ],
        pathway_consensus=["osteoclast differentiation", "iron homeostasis"],
        mechanistic_links=[
            "TNFSF11 (RANKL) upregulation at both RNA and protein level drives osteoclast activation",
            "FTL post-transcriptional regulation explains RNA-protein discordance",
        ],
        confidence_per_layer={"transcriptomics": 0.85, "proteomics": 0.72},
        summary="Concordant TNFSF11 upregulation across omics layers; FTL shows post-transcriptional regulation.",
        confidence=0.78,
        caveats=["Proteomics coverage limited to ~4000 proteins", "Tissue mismatch between datasets"],
    )
    agent = make_agent({"sonnet:IntegrativeAnalysisResult": result})

    context = ContextPackage(
        task_description="Integrate transcriptomic and proteomic spaceflight data to identify convergent pathways"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert output.output["omics_layers"] == ["transcriptomics", "proteomics"]
    assert len(output.output["cross_omics_findings"]) == 2
    assert output.output["pathway_consensus"] == ["osteoclast differentiation", "iron homeostasis"]
    assert output.model_version.startswith("mock-")
    print("  PASS: run_returns_output")


def test_output_type():
    """Integrative Biologist output should have correct output_type."""
    result = IntegrativeAnalysisResult(
        query="Test query",
        summary="Test summary for integrative analysis output type verification.",
        confidence=0.75,
    )
    agent = make_agent({"sonnet:IntegrativeAnalysisResult": result})
    context = ContextPackage(task_description="Test integrative biology query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.output_type == "IntegrativeAnalysisResult"
    print("  PASS: output_type")


def test_summary_populated():
    """Integrative Biologist output should have a populated summary."""
    result = IntegrativeAnalysisResult(
        query="Mechanistic links between DNA damage and immune findings",
        summary="cGAS-STING pathway connects DNA damage (genomics) to inflammatory cytokines (proteomics).",
        confidence=0.76,
    )
    agent = make_agent({"sonnet:IntegrativeAnalysisResult": result})
    context = ContextPackage(
        task_description="What mechanistic links connect DNA damage and immune findings in astronaut blood?"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.summary
    assert len(output.summary) > 0
    assert "cGAS-STING" in output.summary
    print("  PASS: summary_populated")


def test_agent_metadata():
    """Integrative Biologist output should carry correct agent metadata."""
    agent = make_agent()
    context = ContextPackage(task_description="Test query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.agent_id == "integrative_biologist"
    assert output.model_tier == "sonnet"
    assert output.model_version == "mock-sonnet"
    assert output.duration_ms >= 0
    print("  PASS: agent_metadata")


def test_spec_loaded_correctly():
    """Integrative Biologist spec should have expected fields."""
    spec = BaseAgent.load_spec("integrative_biologist")
    assert spec.id == "integrative_biologist"
    assert spec.tier == "domain_expert"
    assert spec.model_tier == "sonnet"
    assert spec.criticality == "optional"
    assert spec.division == "cross_cutting"
    print("  PASS: spec_loaded_correctly")


if __name__ == "__main__":
    print("Testing Integrative Biologist Agent:")
    test_run_returns_output()
    test_output_type()
    test_summary_populated()
    test_agent_metadata()
    test_spec_loaded_correctly()
    print("\nAll Integrative Biologist Agent tests passed!")
