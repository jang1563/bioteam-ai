"""Tests for H2 Meta-Workflow Orchestrator — DAG-based workflow chaining.

Validates:
1. MetaWorkflowDef DAG validation (valid, cycle, missing deps)
2. MetaWorkflowNode model structure
3. MetaWorkflowInstance persistence model
4. MetaWorkflowOrchestrator.run() — sequential execution
5. MetaWorkflowOrchestrator.run() — conditional skipping
6. MetaWorkflowOrchestrator.run() — human checkpoint pause
7. MetaWorkflowOrchestrator.resume() — resume after pause
8. Topological sort correctness
9. Condition evaluation (safe pattern matching)
10. Cycle detection in DAG
11. Budget tracking across nodes
12. Preset templates validation
13. Meta-workflow API endpoint structure
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.models.meta_workflow import (
    MetaWorkflowDef,
    MetaWorkflowInstance,
    MetaWorkflowNode,
)
from app.workflows.meta_orchestrator import MetaWorkflowOrchestrator
from app.workflows.meta_templates import (
    DRUG_DISCOVERY_PIPELINE,
    FULL_RESEARCH_PIPELINE,
    INTEGRITY_DEEP_DIVE,
    META_TEMPLATES,
)

# ── Helpers ────────────────────────────────────────────────────────────


def _make_simple_dag() -> MetaWorkflowDef:
    """Create a simple 3-node linear DAG: A → B → C."""
    return MetaWorkflowDef(
        id="test_linear",
        name="Test Linear",
        nodes=[
            MetaWorkflowNode(id="a", template="W1", depends_on=[]),
            MetaWorkflowNode(id="b", template="W2", depends_on=["a"]),
            MetaWorkflowNode(id="c", template="W3", depends_on=["b"]),
        ],
    )


def _make_diamond_dag() -> MetaWorkflowDef:
    """Create a diamond DAG: A → B, A → C, B+C → D."""
    return MetaWorkflowDef(
        id="test_diamond",
        name="Test Diamond",
        nodes=[
            MetaWorkflowNode(id="a", template="W1", depends_on=[]),
            MetaWorkflowNode(id="b", template="W2", depends_on=["a"]),
            MetaWorkflowNode(id="c", template="W6", depends_on=["a"]),
            MetaWorkflowNode(id="d", template="W3", depends_on=["b", "c"]),
        ],
    )


def _make_conditional_dag() -> MetaWorkflowDef:
    """DAG with a conditional node."""
    return MetaWorkflowDef(
        id="test_conditional",
        name="Test Conditional",
        nodes=[
            MetaWorkflowNode(id="a", template="W1", depends_on=[]),
            MetaWorkflowNode(
                id="b", template="W6", depends_on=["a"],
                condition="node.a.contradiction_count > 2",
            ),
            MetaWorkflowNode(id="c", template="W2", depends_on=["a"]),
        ],
    )


async def _mock_run_workflow(**kwargs):
    """Mock workflow runner that returns immediately."""
    template = kwargs.get("template", "W1")
    mock_instance = MagicMock()
    mock_instance.id = f"wf-{template}-001"
    mock_instance.state = "COMPLETED"
    mock_instance.budget_total = 5.0
    mock_instance.budget_remaining = 4.0
    return {
        "instance": mock_instance,
        "step_results": {"REPORT": {"output": {"summary": f"Completed {template}"}}},
    }


# ── H2.1: DAG Validation ──────────────────────────────────────────────


def test_valid_dag_no_errors():
    dag = _make_simple_dag()
    errors = dag.validate_dag()
    assert errors == []


def test_diamond_dag_valid():
    dag = _make_diamond_dag()
    errors = dag.validate_dag()
    assert errors == []


def test_dag_cycle_detected():
    dag = MetaWorkflowDef(
        id="cycle",
        name="Cycle",
        nodes=[
            MetaWorkflowNode(id="a", template="W1", depends_on=["c"]),
            MetaWorkflowNode(id="b", template="W2", depends_on=["a"]),
            MetaWorkflowNode(id="c", template="W3", depends_on=["b"]),
        ],
    )
    errors = dag.validate_dag()
    assert any("cycle" in e.lower() for e in errors)


def test_dag_missing_dependency():
    dag = MetaWorkflowDef(
        id="missing",
        name="Missing",
        nodes=[
            MetaWorkflowNode(id="a", template="W1", depends_on=["nonexistent"]),
        ],
    )
    errors = dag.validate_dag()
    assert any("unknown" in e.lower() for e in errors)


# ── H2.2: Model structure ─────────────────────────────────────────────


def test_meta_node_defaults():
    node = MetaWorkflowNode(id="test", template="W1")
    assert node.depends_on == []
    assert node.human_checkpoint is False
    assert node.condition is None


def test_meta_instance_defaults():
    instance = MetaWorkflowInstance(definition_id="test", query="test query")
    assert instance.state == "PENDING"
    assert instance.budget_total == 20.0
    assert instance.node_states == {}
    assert instance.spawned_workflows == []


# ── H2.3: Topological sort ────────────────────────────────────────────


def test_topo_sort_linear():
    dag = _make_simple_dag()
    order = MetaWorkflowOrchestrator._topological_sort(dag.nodes)
    ids = [n.id for n in order]
    assert ids.index("a") < ids.index("b") < ids.index("c")


def test_topo_sort_diamond():
    dag = _make_diamond_dag()
    order = MetaWorkflowOrchestrator._topological_sort(dag.nodes)
    ids = [n.id for n in order]
    assert ids.index("a") < ids.index("b")
    assert ids.index("a") < ids.index("c")
    assert ids.index("b") < ids.index("d")
    assert ids.index("c") < ids.index("d")


# ── H2.4: Orchestrator.run() ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_run_linear():
    """Simple linear DAG should execute all nodes in order."""
    dag = _make_simple_dag()
    orchestrator = MetaWorkflowOrchestrator(run_workflow_fn=_mock_run_workflow)

    result = await orchestrator.run(dag, "test query", budget=15.0)

    assert result.state == "COMPLETED"
    assert result.node_states["a"] == "completed"
    assert result.node_states["b"] == "completed"
    assert result.node_states["c"] == "completed"
    assert len(result.spawned_workflows) == 3


@pytest.mark.asyncio
async def test_orchestrator_run_diamond():
    """Diamond DAG should execute all nodes respecting dependencies."""
    dag = _make_diamond_dag()
    orchestrator = MetaWorkflowOrchestrator(run_workflow_fn=_mock_run_workflow)

    result = await orchestrator.run(dag, "test query", budget=20.0)

    assert result.state == "COMPLETED"
    assert all(s == "completed" for s in result.node_states.values())
    assert len(result.spawned_workflows) == 4


@pytest.mark.asyncio
async def test_orchestrator_dry_run():
    """Without run_workflow_fn, orchestrator should use dry-run mode."""
    dag = _make_simple_dag()
    orchestrator = MetaWorkflowOrchestrator()  # No run_workflow_fn

    result = await orchestrator.run(dag, "test query")

    assert result.state == "COMPLETED"
    assert all(s == "completed" for s in result.node_states.values())


# ── H2.5: Conditional skipping ────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_condition_skip():
    """Node with unmet condition should be skipped."""
    dag = _make_conditional_dag()
    orchestrator = MetaWorkflowOrchestrator(run_workflow_fn=_mock_run_workflow)

    result = await orchestrator.run(dag, "test query")

    # 'b' has condition "contradiction_count > 2" — mock doesn't set this
    assert result.node_states["b"] == "skipped"
    assert result.node_states["a"] == "completed"
    assert result.node_states["c"] == "completed"


@pytest.mark.asyncio
async def test_orchestrator_condition_met():
    """Node with met condition should execute."""
    dag = _make_conditional_dag()

    async def mock_run_with_contradictions(**kwargs):
        result = await _mock_run_workflow(**kwargs)
        if kwargs.get("template") == "W1":
            result["step_results"]["CONTRADICTION_CHECK"] = {
                "output": {"contradiction_count": 5}
            }
        return result

    orchestrator = MetaWorkflowOrchestrator(run_workflow_fn=mock_run_with_contradictions)
    result = await orchestrator.run(dag, "test query")

    assert result.node_states["b"] == "completed"


# ── H2.6: Human checkpoint ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_human_checkpoint():
    """Node with human_checkpoint=True should pause."""
    dag = MetaWorkflowDef(
        id="test_hc",
        name="Test HC",
        nodes=[
            MetaWorkflowNode(id="a", template="W1"),
            MetaWorkflowNode(id="b", template="W3", depends_on=["a"], human_checkpoint=True),
            MetaWorkflowNode(id="c", template="W4", depends_on=["b"]),
        ],
    )
    orchestrator = MetaWorkflowOrchestrator(run_workflow_fn=_mock_run_workflow)

    result = await orchestrator.run(dag, "test query")

    assert result.state == "PAUSED"
    assert result.node_states["a"] == "completed"
    assert result.node_states["b"] == "pending"  # Not yet executed
    assert result.node_states["c"] == "pending"


# ── H2.7: Resume after pause ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_resume():
    """Resume after human checkpoint should continue execution."""
    dag = MetaWorkflowDef(
        id="test_resume",
        name="Test Resume",
        nodes=[
            MetaWorkflowNode(id="a", template="W1"),
            MetaWorkflowNode(id="b", template="W3", depends_on=["a"], human_checkpoint=True),
            MetaWorkflowNode(id="c", template="W4", depends_on=["b"]),
        ],
    )
    orchestrator = MetaWorkflowOrchestrator(run_workflow_fn=_mock_run_workflow)

    # First run → pauses at 'b'
    result = await orchestrator.run(dag, "test query")
    assert result.state == "PAUSED"

    # Resume → should continue from 'b'
    result.state = "PAUSED"  # Ensure it's paused
    result = await orchestrator.resume(result, dag)

    assert result.state == "COMPLETED"
    assert result.node_states["b"] == "completed"
    assert result.node_states["c"] == "completed"


# ── H2.8: Budget tracking ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_budget_tracking():
    """Budget should decrease as nodes execute."""
    dag = _make_simple_dag()
    orchestrator = MetaWorkflowOrchestrator(run_workflow_fn=_mock_run_workflow)

    result = await orchestrator.run(dag, "test", budget=15.0)

    assert result.budget_remaining < 15.0
    assert result.budget_remaining >= 0


# ── H2.9: Condition evaluator ─────────────────────────────────────────


def test_condition_completed():
    instance = MetaWorkflowInstance(definition_id="test", query="q")
    instance.node_states = {"a": "completed"}

    assert MetaWorkflowOrchestrator._evaluate_condition("node.a.completed", instance) is True
    assert MetaWorkflowOrchestrator._evaluate_condition("node.b.completed", instance) is False


def test_condition_numeric_comparison():
    instance = MetaWorkflowInstance(definition_id="test", query="q")
    instance.node_results = {
        "a": {
            "step_results": {
                "CONTRADICTION_CHECK": {"output": {"contradiction_count": 5}},
            },
        },
    }

    assert MetaWorkflowOrchestrator._evaluate_condition(
        "node.a.contradiction_count > 2", instance
    ) is True
    assert MetaWorkflowOrchestrator._evaluate_condition(
        "node.a.contradiction_count > 10", instance
    ) is False


def test_condition_truthy():
    instance = MetaWorkflowInstance(definition_id="test", query="q")
    instance.node_results = {
        "a": {
            "step_results": {
                "INTEGRITY_CHECK": {"output": {"findings_count": 3}},
            },
        },
    }

    assert MetaWorkflowOrchestrator._evaluate_condition(
        "node.a.findings_count", instance
    ) is True


def test_condition_empty_string():
    """Empty condition should return True."""
    instance = MetaWorkflowInstance(definition_id="test", query="q")
    assert MetaWorkflowOrchestrator._evaluate_condition("", instance) is True


def test_condition_none():
    """None condition should return True."""
    instance = MetaWorkflowInstance(definition_id="test", query="q")
    assert MetaWorkflowOrchestrator._evaluate_condition(None, instance) is True


# ── H2.10: Dependency failure propagation ──────────────────────────────


@pytest.mark.asyncio
async def test_dependency_failure_skips_downstream():
    """If a dependency fails, downstream nodes should be skipped."""
    dag = _make_simple_dag()

    call_count = 0

    async def failing_workflow(**kwargs):
        nonlocal call_count
        call_count += 1
        if kwargs.get("template") == "W2":
            mock_instance = MagicMock()
            mock_instance.id = "wf-fail"
            mock_instance.state = "FAILED"
            mock_instance.budget_total = 5.0
            mock_instance.budget_remaining = 5.0
            return {"instance": mock_instance, "step_results": {}}
        return await _mock_run_workflow(**kwargs)

    orchestrator = MetaWorkflowOrchestrator(run_workflow_fn=failing_workflow)
    result = await orchestrator.run(dag, "test")

    assert result.node_states["a"] == "completed"
    assert result.node_states["b"] == "failed"
    assert result.node_states["c"] == "skipped"


# ── H2.11: Preset templates ───────────────────────────────────────────


def test_full_research_pipeline_valid():
    errors = FULL_RESEARCH_PIPELINE.validate_dag()
    assert errors == []
    assert len(FULL_RESEARCH_PIPELINE.nodes) == 5


def test_integrity_deep_dive_valid():
    errors = INTEGRITY_DEEP_DIVE.validate_dag()
    assert errors == []
    assert len(INTEGRITY_DEEP_DIVE.nodes) == 3


def test_drug_discovery_pipeline_valid():
    errors = DRUG_DISCOVERY_PIPELINE.validate_dag()
    assert errors == []
    assert len(DRUG_DISCOVERY_PIPELINE.nodes) == 3


def test_all_templates_registered():
    assert len(META_TEMPLATES) == 3
    assert "full_research_pipeline" in META_TEMPLATES
    assert "integrity_deep_dive" in META_TEMPLATES
    assert "drug_discovery_pipeline" in META_TEMPLATES


def test_all_templates_valid():
    for name, template in META_TEMPLATES.items():
        errors = template.validate_dag()
        assert errors == [], f"Template {name} has errors: {errors}"


# ── H2.12: SSE events ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_sse_events():
    """SSE events should be broadcast for key lifecycle events."""
    dag = _make_simple_dag()
    mock_hub = MagicMock()
    mock_hub.broadcast_dict = AsyncMock()

    orchestrator = MetaWorkflowOrchestrator(
        run_workflow_fn=_mock_run_workflow,
        sse_hub=mock_hub,
    )

    await orchestrator.run(dag, "test")

    # Should have broadcast: meta.started + 3x(node_started+node_completed) + meta.completed
    assert mock_hub.broadcast_dict.call_count >= 5
    event_types = [
        call.kwargs.get("event_type", call.args[0] if call.args else "")
        for call in mock_hub.broadcast_dict.call_args_list
    ]
    assert "meta.started" in event_types
    assert "meta.completed" in event_types
    assert "meta.node_started" in event_types
    assert "meta.node_completed" in event_types


# ── H2.13: Orchestrator with persist_fn ────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_persist_fn_called():
    """persist_fn should be called after each state change."""
    dag = _make_simple_dag()
    persist_fn = AsyncMock()

    orchestrator = MetaWorkflowOrchestrator(
        run_workflow_fn=_mock_run_workflow,
        persist_fn=persist_fn,
    )

    await orchestrator.run(dag, "test")

    # Should be called multiple times (initial + per node)
    assert persist_fn.call_count >= 4
