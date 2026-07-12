"""Tests for Research Director agent."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.research_director import (
    QueryClassification,
    ResearchDirectorAgent,
    SynthesisReport,
)
from app.llm.mock_layer import MockLLMLayer
from app.models.messages import ContextPackage


def make_agent(mock_responses: dict | None = None) -> ResearchDirectorAgent:
    """Create a ResearchDirectorAgent with MockLLMLayer."""
    spec = BaseAgent.load_spec("research_director")
    mock = MockLLMLayer(mock_responses or {})
    return ResearchDirectorAgent(spec=spec, llm=mock)


def test_classify_simple_query():
    """RD should classify a simple lookup as simple_query."""
    classification = QueryClassification(
        type="simple_query",
        reasoning="Single gene expression lookup, answerable by transcriptomics specialist.",
        target_agent="t02_transcriptomics",
    )
    agent = make_agent({"sonnet:QueryClassification": classification})

    context = ContextPackage(
        task_description="Is gene TNFSF11 differentially expressed in spaceflight cfRNA data?"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert output.output_type == "QueryClassification"
    assert output.output["type"] == "simple_query"
    assert output.output["target_agent"] == "t02_transcriptomics"
    assert output.model_version.startswith("mock-")
    print("  PASS: classify simple query")


def test_classify_workflow_query():
    """RD should classify a complex query as needs_workflow."""
    classification = QueryClassification(
        type="needs_workflow",
        reasoning="Comparing mechanisms across species requires systematic literature review.",
        workflow_type="W1",
    )
    agent = make_agent({"sonnet:QueryClassification": classification})

    context = ContextPackage(
        task_description="Compare spaceflight-induced anemia mechanisms across rodent and human studies"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert output.output["type"] == "needs_workflow"
    assert output.output["workflow_type"] == "W1"
    print("  PASS: classify workflow query")


def test_synthesize():
    """RD should synthesize multiple agent outputs."""
    synthesis = SynthesisReport(
        title="Spaceflight Anemia Mechanisms",
        summary="Hemolysis is the primary driver of space anemia.",
        key_findings=["Splenic hemolysis increases by 54%", "EPO levels normalize by day 10"],
        evidence_gaps=["No human splenic imaging data in microgravity"],
        sources_cited=["10.1038/s41591-022-01696-6"],
    )
    agent = make_agent({"opus:SynthesisReport": synthesis})

    context = ContextPackage(
        task_description="Synthesize findings on spaceflight anemia",
        prior_step_outputs=[
            {"agent_id": "t02_transcriptomics", "summary": "EPO-related genes upregulated"},
            {"agent_id": "t04_biostatistics", "summary": "Hemoglobin decline significant (p<0.001)"},
        ],
    )

    output = asyncio.run(agent.synthesize(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert output.output_type == "SynthesisReport"
    assert len(output.output["key_findings"]) > 0
    assert len(output.output["sources_cited"]) > 0
    print("  PASS: synthesize outputs")


def test_agent_metadata():
    """RD output should carry model metadata."""
    classification = QueryClassification(
        type="simple_query",
        reasoning="Simple factual question.",
        target_agent="t02_transcriptomics",
    )
    agent = make_agent({"sonnet:QueryClassification": classification})
    context = ContextPackage(task_description="What is spaceflight anemia?")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.agent_id == "research_director"
    assert output.model_tier == "sonnet"
    assert output.model_version == "mock-sonnet"
    assert output.duration_ms >= 0
    assert output.retry_count == 0
    print("  PASS: agent metadata correct")


def test_call_log():
    """MockLLMLayer should log all calls for inspection."""
    classification = QueryClassification(
        type="simple_query",
        reasoning="Test",
        target_agent="t02_transcriptomics",
    )
    mock = MockLLMLayer({"sonnet:QueryClassification": classification})
    spec = BaseAgent.load_spec("research_director")
    agent = ResearchDirectorAgent(spec=spec, llm=mock)

    context = ContextPackage(task_description="Test query")
    asyncio.run(agent.execute(context))

    assert len(mock.call_log) == 1
    call = mock.call_log[0]
    assert call["method"] == "complete_structured"
    assert call["model_tier"] == "sonnet"
    assert call["response_model"] == "QueryClassification"
    assert call["temperature"] is None  # Uses default from config
    print("  PASS: call log captured")


if __name__ == "__main__":
    print("Testing Research Director Agent:")
    test_classify_simple_query()
    test_classify_workflow_query()
    test_synthesize()
    test_agent_metadata()
    test_call_log()
    print("\nAll Research Director tests passed!")
