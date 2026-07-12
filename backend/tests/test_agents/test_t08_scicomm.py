"""Tests for Scientific Communication Agent (Team 8) — run, output type, summary."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.teams.t08_scicomm import (
    SciCommAgent,
    SciCommResult,
)
from app.llm.mock_layer import MockLLMLayer
from app.models.messages import ContextPackage


def make_agent(mock_responses: dict | None = None) -> SciCommAgent:
    """Create a SciCommAgent with MockLLMLayer."""
    spec = BaseAgent.load_spec("t08_scicomm")
    mock = MockLLMLayer(mock_responses or {})
    return SciCommAgent(spec=spec, llm=mock)


def test_run_returns_output():
    """T08 should handle a scientific communication task and return AgentOutput."""
    result = SciCommResult(
        query="Lay summary of spaceflight anemia findings",
        document_type="lay_summary",
        content="When astronauts travel to space, their bodies destroy more red blood cells than normal...",
        structure=["Hook", "Key Finding", "Health Impact", "Mission Relevance"],
        key_messages=[
            "Astronauts lose 54% more red blood cells in space",
            "This discovery helps plan longer missions to Mars",
        ],
        target_audience="General public / NASA outreach",
        summary="Lay summary drafted for NASA outreach on spaceflight anemia findings.",
        confidence=0.90,
        suggestions=["Add infographic for RBC destruction rate", "Include astronaut quote"],
    )
    agent = make_agent({"sonnet:SciCommResult": result})

    context = ContextPackage(
        task_description="Write a lay summary of our spaceflight anemia findings for NASA outreach"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert output.output["document_type"] == "lay_summary"
    assert len(output.output["key_messages"]) == 2
    assert output.model_version.startswith("mock-")
    print("  PASS: run_returns_output")


def test_output_type():
    """T08 output should have correct output_type."""
    result = SciCommResult(
        query="Test query",
        summary="Test summary for scicomm output type verification.",
        confidence=0.80,
    )
    agent = make_agent({"sonnet:SciCommResult": result})
    context = ContextPackage(task_description="Test scicomm query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.output_type == "SciCommResult"
    print("  PASS: output_type")


def test_summary_populated():
    """T08 output should have a populated summary."""
    result = SciCommResult(
        query="Structure an abstract for cfRNA biomarker paper",
        summary="Structured abstract with Background, Methods, Results, Conclusions for cfRNA biomarker paper.",
        confidence=0.85,
    )
    agent = make_agent({"sonnet:SciCommResult": result})
    context = ContextPackage(task_description="Structure an abstract for our cfRNA biomarker paper")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.summary
    assert len(output.summary) > 0
    assert "abstract" in output.summary.lower()
    print("  PASS: summary_populated")


def test_agent_metadata():
    """T08 output should carry correct agent metadata."""
    agent = make_agent()
    context = ContextPackage(task_description="Test query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.agent_id == "t08_scicomm"
    assert output.model_tier == "sonnet"
    assert output.model_version == "mock-sonnet"
    assert output.duration_ms >= 0
    print("  PASS: agent_metadata")


def test_spec_loaded_correctly():
    """T08 spec should have expected fields."""
    spec = BaseAgent.load_spec("t08_scicomm")
    assert spec.id == "t08_scicomm"
    assert spec.tier == "domain_expert"
    assert spec.model_tier == "sonnet"
    assert spec.criticality == "optional"
    assert spec.division == "translation"
    print("  PASS: spec_loaded_correctly")


if __name__ == "__main__":
    print("Testing Scientific Communication Agent (T08):")
    test_run_returns_output()
    test_output_type()
    test_summary_populated()
    test_agent_metadata()
    test_spec_loaded_correctly()
    print("\nAll Scientific Communication Agent tests passed!")
