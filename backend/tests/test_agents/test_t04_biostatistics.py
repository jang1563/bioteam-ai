"""Tests for Biostatistics Agent (Team 4) — run, output type, summary."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.teams.t04_biostatistics import (
    BiostatisticsAgent,
    StatisticalAnalysisResult,
)
from app.llm.mock_layer import MockLLMLayer
from app.models.messages import ContextPackage


def make_agent(mock_responses: dict | None = None) -> BiostatisticsAgent:
    """Create a BiostatisticsAgent with MockLLMLayer."""
    spec = BaseAgent.load_spec("t04_biostatistics")
    mock = MockLLMLayer(mock_responses or {})
    return BiostatisticsAgent(spec=spec, llm=mock)


def test_run_returns_output():
    """T04 should answer a biostatistics query and return AgentOutput."""
    result = StatisticalAnalysisResult(
        query="Repeated-measures ANOVA for spaceflight gene expression",
        methods_recommended=["Linear mixed-effects model", "Repeated-measures ANOVA"],
        assumptions=["Normality of residuals", "Sphericity (Mauchly test)"],
        sample_size_estimate=20,
        effect_size="Cohen's d = 0.8 (large)",
        power=0.85,
        corrections=["Greenhouse-Geisser correction for sphericity violation"],
        summary="Recommend mixed-effects model for 3-timepoint spaceflight data; n=20/group provides 85% power.",
        confidence=0.88,
        caveats=["Variance estimate from pilot data may be unstable"],
    )
    agent = make_agent({"sonnet:StatisticalAnalysisResult": result})

    context = ContextPackage(
        task_description="What statistical test for comparing gene expression across 3 spaceflight timepoints?"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert "Linear mixed-effects model" in output.output["methods_recommended"]
    assert output.output["power"] == 0.85
    assert output.model_version.startswith("mock-")
    print("  PASS: run_returns_output")


def test_output_type():
    """T04 output should have correct output_type."""
    result = StatisticalAnalysisResult(
        query="Test query",
        summary="Test summary for biostatistics output type verification.",
        confidence=0.75,
    )
    agent = make_agent({"sonnet:StatisticalAnalysisResult": result})
    context = ContextPackage(task_description="Test biostatistics query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.output_type == "StatisticalAnalysisResult"
    print("  PASS: output_type")


def test_summary_populated():
    """T04 output should have a populated summary."""
    result = StatisticalAnalysisResult(
        query="Power analysis for cfRNA biomarker study",
        summary="Need n=25/group to detect 1.5-fold change with 80% power (alpha=0.05, two-sided).",
        confidence=0.80,
    )
    agent = make_agent({"sonnet:StatisticalAnalysisResult": result})
    context = ContextPackage(task_description="Sample size for cfRNA biomarker study with 80% power")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.summary
    assert len(output.summary) > 0
    assert "n=25" in output.summary
    print("  PASS: summary_populated")


def test_agent_metadata():
    """T04 output should carry correct agent metadata."""
    agent = make_agent()
    context = ContextPackage(task_description="Test query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.agent_id == "t04_biostatistics"
    assert output.model_tier == "sonnet"
    assert output.model_version == "mock-sonnet"
    assert output.duration_ms >= 0
    print("  PASS: agent_metadata")


def test_spec_loaded_correctly():
    """T04 spec should have expected fields."""
    spec = BaseAgent.load_spec("t04_biostatistics")
    assert spec.id == "t04_biostatistics"
    assert spec.tier == "domain_expert"
    assert spec.model_tier == "sonnet"
    assert spec.criticality == "optional"
    assert spec.division == "computation"
    print("  PASS: spec_loaded_correctly")


if __name__ == "__main__":
    print("Testing Biostatistics Agent (T04):")
    test_run_returns_output()
    test_output_type()
    test_summary_populated()
    test_agent_metadata()
    test_spec_loaded_correctly()
    print("\nAll Biostatistics Agent tests passed!")
