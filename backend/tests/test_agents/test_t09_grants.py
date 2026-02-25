"""Tests for Grant Writing Agent (Team 9) — run, output type, summary."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.teams.t09_grants import (
    GrantWritingAgent,
    GrantWritingResult,
)
from app.llm.mock_layer import MockLLMLayer
from app.models.messages import ContextPackage


def make_agent(mock_responses: dict | None = None) -> GrantWritingAgent:
    """Create a GrantWritingAgent with MockLLMLayer."""
    spec = BaseAgent.load_spec("t09_grants")
    mock = MockLLMLayer(mock_responses or {})
    return GrantWritingAgent(spec=spec, llm=mock)


def test_run_returns_output():
    """T09 should handle a grant writing task and return AgentOutput."""
    result = GrantWritingResult(
        query="R01 specific aims for spaceflight bone loss multi-omics",
        agency="NIH/NIAMS",
        mechanism="R01",
        specific_aims=[
            "Aim 1: Characterize multi-omics signatures of spaceflight bone loss",
            "Aim 2: Identify candidate biomarkers for early bone loss detection",
            "Aim 3: Validate biomarker panel in ground-based analogs",
        ],
        significance="Spaceflight bone loss affects all astronauts and mirrors accelerated osteoporosis on Earth.",
        innovation="First multi-omics integration (genomics, proteomics, metabolomics) for spaceflight bone loss.",
        approach_summary="Leverage GeneLab datasets with matched proteomic validation in JAXA/NASA cohorts.",
        budget_considerations=["Multi-omics sequencing: $150K/year", "Personnel: 2 postdocs + 1 technician"],
        summary="Three specific aims drafted for NIH R01 on spaceflight bone loss using multi-omics approach.",
        confidence=0.82,
        caveats=["Budget may need adjustment for inflation", "Cohort size limited by astronaut availability"],
    )
    agent = make_agent({"opus:GrantWritingResult": result})

    context = ContextPackage(
        task_description="Draft specific aims for an R01 on spaceflight-induced bone loss using multi-omics"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert output.output["agency"] == "NIH/NIAMS"
    assert output.output["mechanism"] == "R01"
    assert len(output.output["specific_aims"]) == 3
    assert output.model_version.startswith("mock-")
    print("  PASS: run_returns_output")


def test_output_type():
    """T09 output should have correct output_type."""
    result = GrantWritingResult(
        query="Test query",
        summary="Test summary for grant writing output type verification.",
        confidence=0.75,
    )
    agent = make_agent({"opus:GrantWritingResult": result})
    context = ContextPackage(task_description="Test grant writing query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.output_type == "GrantWritingResult"
    print("  PASS: output_type")


def test_summary_populated():
    """T09 output should have a populated summary."""
    result = GrantWritingResult(
        query="NASA funding mechanisms for cfRNA biomarkers",
        summary="TRISH and NASA ROSES identified as primary mechanisms for cfRNA biomarker discovery project.",
        confidence=0.79,
    )
    agent = make_agent({"opus:GrantWritingResult": result})
    context = ContextPackage(task_description="What NASA funding mechanisms fit our cfRNA biomarker project?")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.summary
    assert len(output.summary) > 0
    assert "TRISH" in output.summary
    print("  PASS: summary_populated")


def test_agent_metadata():
    """T09 output should carry correct agent metadata."""
    agent = make_agent()
    context = ContextPackage(task_description="Test query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.agent_id == "t09_grants"
    assert output.model_tier == "opus"
    assert output.model_version == "mock-opus"
    assert output.duration_ms >= 0
    print("  PASS: agent_metadata")


def test_spec_loaded_correctly():
    """T09 spec should have expected fields."""
    spec = BaseAgent.load_spec("t09_grants")
    assert spec.id == "t09_grants"
    assert spec.tier == "domain_expert"
    assert spec.model_tier == "opus"
    assert spec.criticality == "optional"
    assert spec.division == "translation"
    print("  PASS: spec_loaded_correctly")


if __name__ == "__main__":
    print("Testing Grant Writing Agent (T09):")
    test_run_returns_output()
    test_output_type()
    test_summary_populated()
    test_agent_metadata()
    test_spec_loaded_correctly()
    print("\nAll Grant Writing Agent tests passed!")
