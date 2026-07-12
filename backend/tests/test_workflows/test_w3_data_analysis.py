"""Tests for W3 Data Analysis Runner."""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.registry import create_registry
from app.llm.mock_layer import MockLLMLayer
from app.models.agent import AgentOutput
from app.workflows.runners.w3_data_analysis import (
    _METHOD_MAP,
    W3_STEPS,
    W3DataAnalysisRunner,
    get_step_by_id,
)


def _patch_qa_aliases(registry):
    """Register QA agents under the alias IDs used by workflow runners.

    The registry registers QA agents with spec IDs (qa_statistical_rigor, etc.)
    but the runners reference them as (statistical_rigor_qa, etc.).
    """
    alias_map = {
        "statistical_rigor_qa": "qa_statistical_rigor",
        "biological_plausibility_qa": "qa_biological_plausibility",
        "reproducibility_qa": "qa_reproducibility",
    }
    for alias, spec_id in alias_map.items():
        agent = registry.get(spec_id)
        if agent and registry.get(alias) is None:
            registry._agents[alias] = agent


def _make_runner():
    mock = MockLLMLayer({})
    registry = create_registry(mock)
    _patch_qa_aliases(registry)
    return W3DataAnalysisRunner(registry=registry)


# === Step Definition Tests ===


def test_step_count():
    """W3 should have exactly 11 steps."""
    assert len(W3_STEPS) == 11


def test_step_order():
    expected = [
        "INGEST", "QC", "PLAN", "EXECUTE", "INTEGRATE",
        "VALIDATE", "PLAUSIBILITY", "INTERPRET",
        "CONTRADICTION_CHECK", "AUDIT", "REPORT",
    ]
    actual = [s.id for s in W3_STEPS]
    assert actual == expected


def test_code_only_steps():
    step = get_step_by_id("REPORT")
    assert step is not None
    assert step.agent_id == "code_only"
    assert step.estimated_cost == 0.0


def test_method_map_coverage():
    agent_steps = [s for s in W3_STEPS if s.agent_id != "code_only"]
    for step in agent_steps:
        assert step.id in _METHOD_MAP, f"{step.id} missing from _METHOD_MAP"


def test_get_step_by_id():
    assert get_step_by_id("PLAN") is not None
    assert get_step_by_id("NONEXISTENT") is None


def test_human_checkpoint_on_plan():
    """PLAN step should be marked as a human checkpoint."""
    step = get_step_by_id("PLAN")
    assert step is not None
    assert step.is_human_checkpoint is True


def test_no_parallel_steps():
    """W3 should have no parallel steps."""
    for step in W3_STEPS:
        assert step.is_parallel is False or step.is_parallel is None or not step.is_parallel


# === Pipeline Tests ===


def test_pipeline_pauses_at_plan():
    """W3 run() should pause at PLAN human checkpoint."""
    runner = _make_runner()
    result = asyncio.run(runner.run(query="Analyze RNA-seq data from spaceflight samples"))

    instance = result["instance"]
    assert instance.state == "WAITING_HUMAN"
    assert result["paused_at"] is not None

    # Steps before and including PLAN should have results
    step_ids = list(result["step_results"].keys())
    assert "INGEST" in step_ids
    assert "QC" in step_ids
    assert "PLAN" in step_ids

    # Steps after PLAN should NOT have results yet
    assert "EXECUTE" not in step_ids
    assert "INTEGRATE" not in step_ids
    assert "REPORT" not in step_ids


def test_resume_after_human_completes():
    """After resume_after_human(), pipeline should complete."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test data analysis pipeline"))

    instance = pause_result["instance"]
    assert instance.state == "WAITING_HUMAN"

    # Resume after human approval
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test data analysis pipeline"))

    assert resume_result["completed"] is True
    assert resume_result["instance"].state == "COMPLETED"
    assert resume_result["instance"].template == "W3"

    # All post-checkpoint steps should be present
    step_ids = list(resume_result["step_results"].keys())
    assert "EXECUTE" in step_ids
    assert "INTEGRATE" in step_ids
    assert "VALIDATE" in step_ids
    assert "PLAUSIBILITY" in step_ids
    assert "INTERPRET" in step_ids
    assert "CONTRADICTION_CHECK" in step_ids
    assert "AUDIT" in step_ids
    assert "REPORT" in step_ids


def test_report_structure():
    """REPORT step should produce a structured analysis report."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test report structure"))

    instance = pause_result["instance"]
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test report structure"))

    report = resume_result["step_results"].get("REPORT")
    assert report is not None
    output = report.get("output", report) if isinstance(report, dict) else report

    # Should have the expected keys
    assert "query" in output
    assert "workflow_id" in output
    assert "analysis_results" in output


def test_session_manifest_populated():
    """Instance session_manifest should contain analysis report after full run."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test manifest"))

    instance = pause_result["instance"]
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test manifest"))

    manifest = resume_result["instance"].session_manifest
    assert manifest is not None
    assert "analysis_report" in manifest


def test_budget_tracking():
    """Budget should be tracked across run() and resume_after_human()."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test budget", budget=10.0))

    instance = pause_result["instance"]
    assert instance.budget_total == 10.0
    # Budget remaining should be less than or equal to total
    assert instance.budget_remaining <= instance.budget_total

    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test budget"))
    final_instance = resume_result["instance"]
    assert final_instance.budget_remaining <= final_instance.budget_total


# === _maybe_execute_code Tests (Docker mocked) ===

# DockerCodeRunner is lazily imported inside _maybe_execute_code
_DOCKER_RUNNER_PATH = "app.execution.docker_runner.DockerCodeRunner"


def _make_exec_result(exit_code: int = 0, stdout: str = "ok", runtime: float = 0.3):
    from app.models.code_execution import ExecutionResult
    return ExecutionResult(
        stdout=stdout,
        stderr="",
        exit_code=exit_code,
        runtime_seconds=runtime,
    )


def _make_minimal_runner():
    """W3 runner with a minimal mock registry (no LLM calls needed)."""
    registry = MagicMock()
    return W3DataAnalysisRunner(registry=registry)


def test_maybe_execute_code_no_code_block():
    """Returns original result unchanged when output has no code_block."""
    runner = _make_minimal_runner()
    original = AgentOutput(
        agent_id="t04_biostatistics",
        output={"analysis": "done"},
        summary="ok",
        is_success=True,
        cost=0.05,
    )
    result = asyncio.run(runner._maybe_execute_code(original))
    assert result is original


def test_maybe_execute_code_null_code_block():
    """Returns original result when code_block is None."""
    runner = _make_minimal_runner()
    original = AgentOutput(
        agent_id="t04_biostatistics",
        output={"code_block": None},
        summary="ok",
        is_success=True,
    )
    result = asyncio.run(runner._maybe_execute_code(original))
    assert result is original


def test_maybe_execute_code_non_dict_code_block():
    """Returns original result when code_block is not a dict (malformed)."""
    runner = _make_minimal_runner()
    original = AgentOutput(
        agent_id="t04_biostatistics",
        output={"code_block": "print('hello')"},
        summary="ok",
        is_success=True,
    )
    result = asyncio.run(runner._maybe_execute_code(original))
    assert result is original


def test_maybe_execute_code_non_dict_output():
    """Returns original result when agent output is not a dict at all."""
    runner = _make_minimal_runner()
    original = AgentOutput(
        agent_id="t04_biostatistics",
        output="plain string",
        summary="ok",
        is_success=True,
    )
    result = asyncio.run(runner._maybe_execute_code(original))
    assert result is original


def test_maybe_execute_code_success():
    """Successful Docker run merges execution_result into output."""
    runner = _make_minimal_runner()
    agent_out = AgentOutput(
        agent_id="t04_biostatistics",
        output={
            "n_samples": 42,
            "code_block": {"language": "python", "code": "print(42)", "dependencies": []},
        },
        summary="ok",
        is_success=True,
        cost=0.15,
    )

    with patch(_DOCKER_RUNNER_PATH) as MockRunner:
        instance = MockRunner.return_value
        instance.run = AsyncMock(return_value=_make_exec_result(exit_code=0, stdout="42\n"))

        result = asyncio.run(runner._maybe_execute_code(agent_out))

    assert result is not agent_out
    assert result.is_success is True
    assert result.cost == agent_out.cost
    exec_r = result.output["execution_result"]
    assert exec_r["exit_code"] == 0
    assert exec_r["stdout"] == "42\n"
    assert exec_r["sandbox_used"] is True
    assert "execution_warning" not in result.output
    # Original fields preserved
    assert result.output["n_samples"] == 42


def test_maybe_execute_code_nonzero_exit_adds_warning():
    """Non-zero exit code adds execution_warning to output."""
    runner = _make_minimal_runner()
    agent_out = AgentOutput(
        agent_id="t04_biostatistics",
        output={"code_block": {"language": "python", "code": "exit(2)", "dependencies": []}},
        summary="ok",
        is_success=True,
    )

    with patch(_DOCKER_RUNNER_PATH) as MockRunner:
        instance = MockRunner.return_value
        instance.run = AsyncMock(return_value=_make_exec_result(exit_code=2, stdout=""))

        result = asyncio.run(runner._maybe_execute_code(agent_out))

    assert result.output["execution_result"]["exit_code"] == 2
    assert "execution_warning" in result.output
    assert "2" in result.output["execution_warning"]


def test_maybe_execute_code_uses_settings_for_runner_config():
    """DockerCodeRunner is initialised with values from settings."""
    runner = _make_minimal_runner()
    agent_out = AgentOutput(
        agent_id="t04_biostatistics",
        output={"code_block": {"language": "python", "code": "pass", "dependencies": []}},
        summary="ok",
        is_success=True,
    )

    with (
        patch(_DOCKER_RUNNER_PATH) as MockRunner,
        patch("app.workflows.runners.w3_data_analysis.settings") as mock_settings,
    ):
        mock_settings.docker_timeout_seconds = 60
        mock_settings.docker_memory_limit = "256m"
        mock_settings.docker_cpu_limit = "0.5"
        mock_settings.docker_image_python = "python:3.12-slim"
        mock_settings.docker_image_r = "r-base:4.4"

        instance = MockRunner.return_value
        instance.run = AsyncMock(return_value=_make_exec_result())

        asyncio.run(runner._maybe_execute_code(agent_out))

        init_kwargs = MockRunner.call_args.kwargs
        assert init_kwargs["timeout"] == 60
        assert init_kwargs["memory"] == "256m"
        assert init_kwargs["cpus"] == "0.5"


def test_run_agent_step_triggers_docker_for_execute_step():
    """_run_agent_step calls _maybe_execute_code when step=EXECUTE and docker enabled."""
    mock_agent = MagicMock()
    code_block = {"language": "python", "code": "print(1)", "dependencies": []}
    mock_agent.run = AsyncMock(return_value=AgentOutput(
        agent_id="t04_biostatistics",
        output={"result": "done", "code_block": code_block},
        summary="ok",
        is_success=True,
        cost=0.1,
    ))
    registry = MagicMock()
    registry.get.return_value = mock_agent

    runner = W3DataAnalysisRunner(registry=registry)
    step = get_step_by_id("EXECUTE")
    assert step is not None

    from app.models.workflow import WorkflowInstance
    instance = WorkflowInstance(template="W3", query="test", budget_total=50.0)

    exec_result = _make_exec_result(stdout="1\n")
    with (
        patch(_DOCKER_RUNNER_PATH) as MockRunner,
        patch("app.workflows.runners.w3_data_analysis.settings") as mock_settings,
        patch("app.workflows.note_processor.NoteProcessor") as mock_np,
    ):
        mock_settings.docker_enabled = True
        mock_settings.docker_timeout_seconds = 120
        mock_settings.docker_memory_limit = "512m"
        mock_settings.docker_cpu_limit = "1.0"
        mock_settings.docker_image_python = "python:3.12-slim"
        mock_settings.docker_image_r = "r-base:4.4"
        mock_np.get_pending_notes.return_value = []

        instance_runner = MockRunner.return_value
        instance_runner.run = AsyncMock(return_value=exec_result)

        result = asyncio.run(runner._run_agent_step(step, "test query", instance))

    assert result.output.get("execution_result") is not None
    assert result.output["execution_result"]["stdout"] == "1\n"


def test_run_agent_step_skips_docker_for_non_execute_steps():
    """_run_agent_step does NOT call Docker for steps other than EXECUTE."""
    mock_agent = MagicMock()
    code_block = {"language": "python", "code": "print(1)", "dependencies": []}
    mock_agent.run = AsyncMock(return_value=AgentOutput(
        agent_id="t04_biostatistics",
        output={"result": "done", "code_block": code_block},
        summary="ok",
        is_success=True,
        cost=0.1,
    ))
    registry = MagicMock()
    registry.get.return_value = mock_agent

    runner = W3DataAnalysisRunner(registry=registry)
    step = get_step_by_id("VALIDATE")  # not EXECUTE
    assert step is not None

    from app.models.workflow import WorkflowInstance
    instance = WorkflowInstance(template="W3", query="test", budget_total=50.0)

    with (
        patch("app.workflows.runners.w3_data_analysis.settings") as mock_settings,
        patch("app.workflows.note_processor.NoteProcessor") as mock_np,
    ):
        mock_settings.docker_enabled = True
        mock_np.get_pending_notes.return_value = []

        result = asyncio.run(runner._run_agent_step(step, "test query", instance))

    # code_block passed through, but no execution_result
    assert "execution_result" not in result.output


def test_run_agent_step_skips_docker_when_disabled():
    """_run_agent_step skips _maybe_execute_code when docker_enabled=False."""
    mock_agent = MagicMock()
    code_block = {"language": "python", "code": "print(1)", "dependencies": []}
    mock_agent.run = AsyncMock(return_value=AgentOutput(
        agent_id="t04_biostatistics",
        output={"result": "done", "code_block": code_block},
        summary="ok",
        is_success=True,
        cost=0.1,
    ))
    registry = MagicMock()
    registry.get.return_value = mock_agent

    runner = W3DataAnalysisRunner(registry=registry)
    step = get_step_by_id("EXECUTE")

    from app.models.workflow import WorkflowInstance
    instance = WorkflowInstance(template="W3", query="test", budget_total=50.0)

    with (
        patch("app.workflows.runners.w3_data_analysis.settings") as mock_settings,
        patch("app.workflows.note_processor.NoteProcessor") as mock_np,
    ):
        mock_settings.docker_enabled = False
        mock_np.get_pending_notes.return_value = []

        result = asyncio.run(runner._run_agent_step(step, "test query", instance))

    assert "execution_result" not in result.output
    assert result.output.get("code_block") == code_block
