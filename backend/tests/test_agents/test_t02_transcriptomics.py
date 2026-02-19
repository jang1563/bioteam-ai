"""Tests for Transcriptomics Agent (Team 2) — run, screen_papers, extract_data."""

import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.teams.t02_transcriptomics import (
    TranscriptomicsAgent,
    GeneExpressionResult,
    ScreeningResult,
    ScreeningDecision,
    ExtractionResult,
    ExtractedPaperData,
)
from app.llm.mock_layer import MockLLMLayer
from app.models.messages import ContextPackage


def make_agent(mock_responses: dict | None = None) -> TranscriptomicsAgent:
    """Create a TranscriptomicsAgent with MockLLMLayer."""
    spec = BaseAgent.load_spec("t02_transcriptomics")
    mock = MockLLMLayer(mock_responses or {})
    return TranscriptomicsAgent(spec=spec, llm=mock)


def test_run_gene_expression():
    """T02 should answer a gene expression query."""
    result = GeneExpressionResult(
        query="TNFSF11 expression in spaceflight",
        genes_analyzed=["TNFSF11", "RANK", "OPG"],
        differentially_expressed=[
            {"gene": "TNFSF11", "log2fc": 1.8, "fdr": 0.001}
        ],
        methodology="DESeq2 on GeneLab RNA-seq",
        summary="TNFSF11 is significantly upregulated in spaceflight cfRNA.",
        confidence=0.85,
    )
    agent = make_agent({"sonnet:GeneExpressionResult": result})

    context = ContextPackage(
        task_description="Is gene TNFSF11 differentially expressed in spaceflight cfRNA data?"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert output.output_type == "GeneExpressionResult"
    assert output.output["genes_analyzed"] == ["TNFSF11", "RANK", "OPG"]
    assert len(output.output["differentially_expressed"]) == 1
    assert output.model_version.startswith("mock-")
    print("  PASS: run_gene_expression")


def test_screen_papers():
    """T02 should screen papers and return include/exclude decisions."""
    result = ScreeningResult(
        total_screened=3,
        included=2,
        excluded=1,
        decisions=[
            ScreeningDecision(paper_id="doi:10.1234/a", decision="include", relevance_score=0.9,
                              reasoning="Directly addresses spaceflight anemia mechanisms."),
            ScreeningDecision(paper_id="doi:10.1234/b", decision="include", relevance_score=0.7,
                              reasoning="Relevant cfRNA data from ISS astronauts."),
            ScreeningDecision(paper_id="doi:10.1234/c", decision="exclude", relevance_score=0.2,
                              reasoning="Focuses on plant biology, not relevant."),
        ],
    )
    agent = make_agent({"sonnet:ScreeningResult": result})

    context = ContextPackage(
        task_description="Spaceflight-induced anemia mechanisms",
        prior_step_outputs=[
            {"doi": "10.1234/a", "title": "Hemolysis in spaceflight"},
            {"doi": "10.1234/b", "title": "cfRNA biomarkers on ISS"},
            {"doi": "10.1234/c", "title": "Arabidopsis in microgravity"},
        ],
    )

    output = asyncio.run(agent.screen_papers(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert output.output_type == "ScreeningResult"
    assert output.output["total_screened"] == 3
    assert output.output["included"] == 2
    assert output.output["excluded"] == 1
    print("  PASS: screen_papers")


def test_extract_data():
    """T02 should extract structured data from included papers."""
    result = ExtractionResult(
        total_extracted=2,
        papers=[
            ExtractedPaperData(
                paper_id="doi:10.1234/a",
                title="Hemolysis in spaceflight",
                genes=["TNFSF11", "EPO", "HBA1"],
                organism="human",
                tissue="blood",
                technology="RNA-seq",
                sample_size=14,
                key_findings=["54% increase in splenic hemolysis"],
                data_accession="GSE123456",
            ),
            ExtractedPaperData(
                paper_id="doi:10.1234/b",
                title="cfRNA biomarkers on ISS",
                genes=["TNFSF11", "FTL", "FTH1"],
                organism="human",
                tissue="plasma",
                technology="cfRNA-seq",
                sample_size=6,
                key_findings=["TNFSF11 elevated in 5/6 subjects"],
            ),
        ],
        common_genes=["TNFSF11"],
        methodology_summary="Two studies used different RNA technologies on human blood samples.",
    )
    agent = make_agent({"sonnet:ExtractionResult": result})

    context = ContextPackage(
        task_description="Spaceflight-induced anemia mechanisms",
        prior_step_outputs=[
            {"doi": "10.1234/a", "title": "Hemolysis in spaceflight"},
            {"doi": "10.1234/b", "title": "cfRNA biomarkers on ISS"},
        ],
    )

    output = asyncio.run(agent.extract_data(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert output.output_type == "ExtractionResult"
    assert output.output["total_extracted"] == 2
    assert output.output["common_genes"] == ["TNFSF11"]
    assert len(output.output["papers"]) == 2
    print("  PASS: extract_data")


def test_agent_metadata():
    """T02 output should carry correct agent metadata."""
    agent = make_agent()
    context = ContextPackage(task_description="Test query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.agent_id == "t02_transcriptomics"
    assert output.model_tier == "sonnet"
    assert output.model_version == "mock-sonnet"
    assert output.duration_ms >= 0
    print("  PASS: agent_metadata")


def test_spec_loaded_correctly():
    """T02 spec should have expected fields."""
    spec = BaseAgent.load_spec("t02_transcriptomics")
    assert spec.id == "t02_transcriptomics"
    assert spec.tier == "domain_expert"
    assert spec.model_tier == "sonnet"
    assert spec.criticality == "optional"
    assert spec.division == "wet_to_dry"
    print("  PASS: spec_loaded_correctly")


if __name__ == "__main__":
    print("Testing Transcriptomics Agent (T02):")
    test_run_gene_expression()
    test_screen_papers()
    test_extract_data()
    test_agent_metadata()
    test_spec_loaded_correctly()
    print("\nAll Transcriptomics Agent tests passed!")
