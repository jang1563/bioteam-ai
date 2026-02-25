"""Tests for Project Manager agent."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.project_manager import ProjectManagerAgent, ProjectStatus, TaskSummary
from app.llm.mock_layer import MockLLMLayer
from app.models.messages import ContextPackage


def test_generate_status():
    """Should generate a project status report via Haiku."""
    status = ProjectStatus(
        active_workflows=2,
        completed_workflows=1,
        total_cost=1.23,
        budget_remaining=48.77,
        summary="2 workflows active, 1 complete. On track.",
    )
    mock = MockLLMLayer({"haiku:ProjectStatus": status})

    spec = BaseAgent.load_spec("project_manager")
    agent = ProjectManagerAgent(spec=spec, llm=mock)

    context = ContextPackage(
        task_description="Generate status report",
        constraints={"workflow_info": {"active": 2}, "cost_info": {"total": 1.23}},
    )
    output = asyncio.run(agent.execute(context))

    assert output.is_success
    assert output.output["active_workflows"] == 2
    assert output.output["summary"] == "2 workflows active, 1 complete. On track."
    assert output.output_type == "ProjectStatus"
    print("  PASS: generate_status")


def test_summarize_task():
    """Should summarize a single task."""
    task = TaskSummary(
        task_id="task_001",
        title="Literature search for spaceflight anemia",
        status="in_progress",
        assigned_to="knowledge_manager",
    )
    mock = MockLLMLayer({"haiku:TaskSummary": task})

    spec = BaseAgent.load_spec("project_manager")
    agent = ProjectManagerAgent(spec=spec, llm=mock)

    context = ContextPackage(task_description="Summarize task: Literature search")
    output = asyncio.run(agent.summarize_task(context))

    assert output.is_success
    assert output.output["task_id"] == "task_001"
    assert output.output["status"] == "in_progress"
    print("  PASS: summarize_task")


def test_haiku_model_tier():
    """PM should always use Haiku model tier."""
    mock = MockLLMLayer({
        "haiku:ProjectStatus": ProjectStatus(summary="Test"),
    })
    spec = BaseAgent.load_spec("project_manager")
    agent = ProjectManagerAgent(spec=spec, llm=mock)

    assert agent.model_tier == "haiku"

    context = ContextPackage(task_description="Status")
    asyncio.run(agent.execute(context))

    # Verify the LLM call used haiku
    assert len(mock.call_log) == 1
    assert mock.call_log[0]["model_tier"] == "haiku"
    print("  PASS: haiku_model_tier")


def test_agent_metadata():
    """Output should carry correct agent metadata."""
    mock = MockLLMLayer({
        "haiku:ProjectStatus": ProjectStatus(summary="Test"),
    })
    spec = BaseAgent.load_spec("project_manager")
    agent = ProjectManagerAgent(spec=spec, llm=mock)

    output = asyncio.run(agent.execute(ContextPackage(task_description="Test")))

    assert output.agent_id == "project_manager"
    assert output.model_tier == "haiku"
    assert output.model_version == "mock-haiku"
    assert output.duration_ms >= 0
    print("  PASS: agent_metadata")


def test_optional_degradation():
    """PM spec should have optional criticality and skip degradation."""
    spec = BaseAgent.load_spec("project_manager")
    assert spec.criticality == "optional"
    assert spec.degradation_mode == "skip"
    print("  PASS: optional_degradation")


if __name__ == "__main__":
    print("Testing Project Manager Agent:")
    test_generate_status()
    test_summarize_task()
    test_haiku_model_tier()
    test_agent_metadata()
    test_optional_degradation()
    print("\nAll Project Manager tests passed!")
