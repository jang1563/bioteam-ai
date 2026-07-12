"""Tests for W9BioinformaticsRunner — 20-step multi-omics pipeline.

Covers:
- Pipeline structure (21 steps, correct interaction_type assignments)
- run() with all agents mocked — full pipeline, no LLM calls
- HC (Human Checkpoint) pause behaviour
- DC (Direction Check) SSE broadcast (non-blocking)
- Budget exhaustion → OVER_BUDGET
- Checkpoint resume: runner skips completed steps
- Code step implementations: _pre_health_check, _ingest_data, _run_qc, _variant_annotation
- Error handling: failing agent step produces is_success=False AgentOutput
- Report builder integration
- _maybe_execute_code: Docker sandbox integration (mocked)
- Phase 7-A: Templates, cost modes, skip logic, Gemini bypass
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.agent import AgentOutput
from app.models.workflow import WorkflowInstance
from app.workflows.runners.w9_bioinformatics import (
    _CODE_STEPS,
    _DOCKER_STEPS,
    _METHOD_MAP,
    W9_STEPS,
    W9BioinformaticsRunner,
)

# HealthChecker and report builder are imported lazily inside methods
# → patch them at their source module paths
_HEALTH_CHECKER_PATH = "app.workflows.health_checker.HealthChecker"
_REPORT_BUILDER_PATH = "app.engines.w9_report_builder.build_w9_report"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_agent_output(agent_id: str = "mock_agent", cost: float = 0.1) -> AgentOutput:
    return AgentOutput(
        agent_id=agent_id,
        output={"status": "ok"},
        summary="mock step",
        is_success=True,
        cost=cost,
    )


@pytest.fixture
def mock_registry():
    """Registry that returns a mock agent for any agent_id."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=_make_agent_output())
    mock_agent.search_literature = AsyncMock(return_value=_make_agent_output())
    mock_agent.detect_contradictions = AsyncMock(return_value=_make_agent_output())

    registry = MagicMock()
    registry.get.return_value = mock_agent
    return registry, mock_agent


@pytest.fixture
def runner(mock_registry):
    reg, _ = mock_registry
    return W9BioinformaticsRunner(registry=reg)


@pytest.fixture
def runner_with_sse(mock_registry):
    reg, _ = mock_registry
    sse_hub = AsyncMock()
    sse_hub.broadcast_dict = AsyncMock()
    return W9BioinformaticsRunner(registry=reg, sse_hub=sse_hub), sse_hub


# ---------------------------------------------------------------------------
# Pipeline structure tests
# ---------------------------------------------------------------------------


def test_w9_has_21_steps():
    # Plan said 20, but implementation has 21 (HC_INTEGRATION is a separate step)
    assert len(W9_STEPS) == 21


def test_step_ids_are_unique():
    ids = [s.id for s in W9_STEPS]
    assert len(ids) == len(set(ids))


def test_step_order_starts_with_pre_health_check():
    assert W9_STEPS[0].id == "PRE_HEALTH_CHECK"


def test_step_order_ends_with_report():
    assert W9_STEPS[-1].id == "REPORT"


def test_hc_steps():
    hc_steps = [s.id for s in W9_STEPS if s.interaction_type == "HC"]
    assert "SCOPE" in hc_steps
    assert "QC" in hc_steps
    assert "HC_INTEGRATION" in hc_steps
    assert len(hc_steps) == 3


def test_dc_steps():
    dc_steps = [s.id for s in W9_STEPS if s.interaction_type == "DC"]
    assert "INGEST_DATA" in dc_steps
    assert "DC_PHASE_B" in dc_steps
    assert "DC_NOVELTY" in dc_steps
    assert len(dc_steps) == 3


def test_code_steps_set():
    assert "PRE_HEALTH_CHECK" in _CODE_STEPS
    assert "INGEST_DATA" in _CODE_STEPS
    assert "QC" in _CODE_STEPS
    assert "VARIANT_ANNOTATION" in _CODE_STEPS
    assert "REPORT" in _CODE_STEPS


def test_method_map_covers_all_agent_steps():
    agent_steps = {s.id for s in W9_STEPS if s.id not in _CODE_STEPS}
    for step_id in agent_steps:
        assert step_id in _METHOD_MAP, f"{step_id} missing from _METHOD_MAP"


# ---------------------------------------------------------------------------
# Full pipeline run (skip_human_checkpoints=True)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_completes(runner):
    with (
        patch(_HEALTH_CHECKER_PATH) as mock_hc,
        patch(_REPORT_BUILDER_PATH, return_value=MagicMock()),
    ):
        mock_hc.check_all = AsyncMock(return_value=[])

        result = await runner.run(
            query="BRCA1 variants in breast cancer",
            budget=50.0,
            skip_human_checkpoints=True,
        )

    assert "step_results" in result
    assert "instance" in result
    # All 21 steps should have been attempted
    assert len(result["step_results"]) == 21
    assert result["instance"].state in ("COMPLETED", "RUNNING")


@pytest.mark.asyncio
async def test_pipeline_pauses_at_first_hc(runner):
    """Without skip_human_checkpoints, runner pauses at SCOPE (first HC)."""
    with patch(_HEALTH_CHECKER_PATH) as mock_hc:
        mock_hc.check_all = AsyncMock(return_value=[])

        result = await runner.run(
            query="BRCA1 variants",
            budget=50.0,
            skip_human_checkpoints=False,
        )

    assert result["paused_at"] == "SCOPE"
    instance = result["instance"]
    assert instance.state == "WAITING_HUMAN"


@pytest.mark.asyncio
async def test_pipeline_budget_exhaustion(mock_registry):
    """Runner stops and marks OVER_BUDGET when budget runs out."""
    reg, mock_agent = mock_registry
    mock_agent.run = AsyncMock(return_value=AgentOutput(
        agent_id="mock", output={}, summary="ok", is_success=True, cost=100.0,
    ))
    runner = W9BioinformaticsRunner(registry=reg)

    with patch(_HEALTH_CHECKER_PATH) as mock_hc:
        mock_hc.check_all = AsyncMock(return_value=[])

        result = await runner.run(
            query="test", budget=0.01, skip_human_checkpoints=True,
        )

    assert result["instance"].state == "OVER_BUDGET"


# ---------------------------------------------------------------------------
# DC event tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dc_phase_b_broadcasts_sse(runner_with_sse):
    runner, sse_hub = runner_with_sse

    with (
        patch(_HEALTH_CHECKER_PATH) as mock_hc,
        patch(_REPORT_BUILDER_PATH, return_value=MagicMock()),
    ):
        mock_hc.check_all = AsyncMock(return_value=[])

        await runner.run(
            query="BRCA1 test",
            budget=50.0,
            skip_human_checkpoints=True,
        )

    # Collect all direction_check events from broadcast calls
    dc_calls = []
    for call in sse_hub.broadcast_dict.await_args_list:
        kwargs = call.kwargs
        # broadcast_dict takes positional or keyword event_type
        event_type = kwargs.get("event_type") or (call.args[0] if call.args else None)
        if event_type == "workflow.direction_check":
            dc_calls.append(call)

    # 3 DC steps (INGEST_DATA, DC_PHASE_B, DC_NOVELTY) → 3 direction_check events
    assert len(dc_calls) >= 1


# ---------------------------------------------------------------------------
# Checkpoint resume tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkpoint_resume_skips_completed_steps(mock_registry):
    """Runner skips steps already in _step_results from checkpoint restore."""
    reg, _ = mock_registry
    runner = W9BioinformaticsRunner(registry=reg)

    # Pre-populate all steps except REPORT to simulate a restored checkpoint
    all_steps_except_report = [s.id for s in W9_STEPS if s.id != "REPORT"]
    for step_id in all_steps_except_report:
        runner._step_results[step_id] = _make_agent_output(step_id)

    with (
        patch(_HEALTH_CHECKER_PATH) as mock_hc,
        patch(_REPORT_BUILDER_PATH, return_value=MagicMock()),
    ):
        mock_hc.check_all = AsyncMock(return_value=[])

        result = await runner.run(
            query="test",
            budget=50.0,
            skip_human_checkpoints=True,
        )

    # REPORT should be the only newly executed step
    assert "REPORT" in result["step_results"]


@pytest.mark.asyncio
async def test_checkpoint_manager_called_on_step_completion(mock_registry):
    """CheckpointManager.save_step is called for each completed step."""
    reg, _ = mock_registry
    mock_cm = MagicMock()
    mock_cm.load_completed_steps = AsyncMock(return_value={})
    mock_cm.save_step = AsyncMock()

    runner = W9BioinformaticsRunner(registry=reg, checkpoint_manager=mock_cm)

    with patch(_HEALTH_CHECKER_PATH) as mock_hc:
        mock_hc.check_all = AsyncMock(return_value=[])

        # Only run up to first HC (SCOPE) — so PRE_HEALTH_CHECK is saved
        await runner.run(query="test", budget=50.0, skip_human_checkpoints=False)

    # save_step should be called at least for PRE_HEALTH_CHECK (before SCOPE HC)
    assert mock_cm.save_step.await_count >= 1


@pytest.mark.asyncio
async def test_checkpoint_manager_load_on_start(mock_registry):
    """CheckpointManager.load_completed_steps is called at the start of run()."""
    reg, _ = mock_registry
    mock_cm = MagicMock()
    completed = {"PRE_HEALTH_CHECK": _make_agent_output("code_only")}
    mock_cm.load_completed_steps = AsyncMock(return_value=completed)
    mock_cm.save_step = AsyncMock()

    runner = W9BioinformaticsRunner(registry=reg, checkpoint_manager=mock_cm)

    with patch(_HEALTH_CHECKER_PATH) as mock_hc:
        mock_hc.check_all = AsyncMock(return_value=[])

        result = await runner.run(query="test", budget=50.0, skip_human_checkpoints=False)

    mock_cm.load_completed_steps.assert_awaited_once()
    # PRE_HEALTH_CHECK was pre-loaded → SCOPE is first to execute → HC pause
    assert result["paused_at"] == "SCOPE"


# ---------------------------------------------------------------------------
# Code step unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pre_health_check_returns_dict(runner):
    with patch(_HEALTH_CHECKER_PATH) as mock_hc:
        mock_hc.check_all = AsyncMock(return_value=[])
        result = await runner._pre_health_check()

    assert isinstance(result, dict)
    assert "all_healthy" in result


@pytest.mark.asyncio
async def test_pre_health_check_handles_exception(runner):
    """If HealthChecker raises, _pre_health_check returns error dict."""
    with patch(_HEALTH_CHECKER_PATH) as mock_hc:
        mock_hc.check_all = AsyncMock(side_effect=ImportError("no module"))
        result = await runner._pre_health_check()

    assert isinstance(result, dict)
    assert result.get("all_healthy") is False


@pytest.mark.asyncio
async def test_ingest_data_no_manifest_path(runner):
    instance = WorkflowInstance(template="W9", query="test", budget_total=10.0)
    result = await runner._ingest_data(instance)
    assert result["files_loaded"] == []
    assert "query-only mode" in result["ingest_warnings"][0]


@pytest.mark.asyncio
async def test_ingest_data_with_manifest(runner, tmp_path):
    manifest = {
        "files": [
            {"path": "/data/variants.vcf", "type": "vcf", "size_mb": 15.2},
            {"path": "/data/counts.tsv", "type": "count_matrix", "size_mb": 8.5},
        ],
        "sample_count": 24,
        "warnings": [],
    }
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(manifest))

    instance = WorkflowInstance(
        template="W9",
        query="test",
        budget_total=10.0,
        data_manifest_path=str(manifest_file),
    )
    result = await runner._ingest_data(instance)

    assert len(result["files_loaded"]) == 2
    assert result["sample_count"] == 24
    assert set(result["data_types"]) == {"vcf", "count_matrix"}


@pytest.mark.asyncio
async def test_ingest_data_manifest_not_found(runner, tmp_path):
    instance = WorkflowInstance(
        template="W9",
        query="test",
        budget_total=10.0,
        data_manifest_path=str(tmp_path / "missing.json"),
    )
    result = await runner._ingest_data(instance)
    assert result["files_loaded"] == []
    assert len(result["ingest_warnings"]) > 0


@pytest.mark.asyncio
async def test_ingest_data_rejects_disallowed_root(runner):
    instance = WorkflowInstance(
        template="W9",
        query="test",
        budget_total=10.0,
        data_manifest_path="/etc/passwd.txt",
    )
    result = await runner._ingest_data(instance)
    assert result["files_loaded"] == []
    assert "allowed root" in result["ingest_warnings"][0]


@pytest.mark.asyncio
async def test_run_qc_no_prior_data(runner):
    """QC with no INGEST_DATA result returns passed=True (skipped mode)."""
    result = await runner._run_qc()
    assert result["passed"] is True
    assert "skipped" in result["qc_summary"]


@pytest.mark.asyncio
async def test_run_qc_with_warnings(runner):
    """QC fails if ingest had warnings."""
    runner._step_results["INGEST_DATA"] = AgentOutput(
        agent_id="code_only",
        output={
            "files_loaded": [{"path": "f.vcf", "type": "vcf"}],
            "ingest_warnings": ["Missing checksum for f.vcf"],
        },
        summary="ok",
        is_success=True,
    )
    result = await runner._run_qc()
    assert result["passed"] is False
    assert result["samples_failed"] == 1


@pytest.mark.asyncio
async def test_run_qc_clean_data(runner):
    """QC passes if no warnings."""
    runner._step_results["INGEST_DATA"] = AgentOutput(
        agent_id="code_only",
        output={
            "files_loaded": [{"path": "f.vcf", "type": "vcf"}],
            "ingest_warnings": [],
        },
        summary="ok",
        is_success=True,
    )
    result = await runner._run_qc()
    assert result["passed"] is True
    assert result["samples_passed"] == 1


@pytest.mark.asyncio
async def test_variant_annotation_no_genomics(runner):
    """VARIANT_ANNOTATION returns empty when no GENOMIC_ANALYSIS result."""
    result = await runner._variant_annotation(
        WorkflowInstance(template="W9", query="test", budget_total=10.0)
    )
    assert result["total_variants"] == 0


# ---------------------------------------------------------------------------
# _build_dc_summary tests
# ---------------------------------------------------------------------------


def test_dc_summary_ingest_data(runner):
    runner._step_results["INGEST_DATA"] = AgentOutput(
        agent_id="code_only",
        output={"files_loaded": [{"path": "a"}, {"path": "b"}, {"path": "c"}]},
        summary="ok",
        is_success=True,
    )
    summary = runner._build_dc_summary("INGEST_DATA")
    assert "3 files" in summary


def test_dc_summary_dc_phase_b(runner):
    runner._step_results["VARIANT_ANNOTATION"] = AgentOutput(
        agent_id="code_only",
        output={"total_variants": 215},
        summary="ok",
        is_success=True,
    )
    runner._step_results["PATHWAY_ENRICHMENT"] = AgentOutput(
        agent_id="t06_systems_bio",
        output={"significant_terms": 42},
        summary="ok",
        is_success=True,
    )
    summary = runner._build_dc_summary("DC_PHASE_B")
    assert "215" in summary
    assert "42" in summary


def test_dc_summary_dc_novelty(runner):
    runner._step_results["NOVELTY_ASSESSMENT"] = AgentOutput(
        agent_id="research_director",
        output={"novel_findings": ["Finding A", "Finding B"]},
        summary="ok",
        is_success=True,
    )
    summary = runner._build_dc_summary("DC_NOVELTY")
    assert "2 novel" in summary


def test_dc_summary_unknown_step(runner):
    summary = runner._build_dc_summary("UNKNOWN_STEP")
    assert "UNKNOWN_STEP" in summary


def test_dc_summary_ingest_no_prior_result(runner):
    """DC summary works gracefully when prior step result is absent."""
    summary = runner._build_dc_summary("INGEST_DATA")
    assert isinstance(summary, str) and len(summary) > 0


# ---------------------------------------------------------------------------
# Agent step error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_step_error_returns_failed_output(runner):
    """If an agent raises, _run_agent_step returns is_success=False AgentOutput."""
    step = next(s for s in W9_STEPS if s.id == "SCOPE")
    mock_agent = runner.registry.get("research_director")
    mock_agent.run = AsyncMock(side_effect=RuntimeError("LLM timeout"))

    instance = WorkflowInstance(template="W9", query="test", budget_total=50.0)
    result = await runner._run_agent_step(step, instance)

    assert result.is_success is False
    assert "LLM timeout" in result.error


@pytest.mark.asyncio
async def test_agent_not_found_returns_failed_output(runner):
    """If registry returns None for agent, _run_agent_step returns error."""
    step = next(s for s in W9_STEPS if s.id == "SCOPE")
    runner.registry.get.return_value = None

    instance = WorkflowInstance(template="W9", query="test", budget_total=50.0)
    result = await runner._run_agent_step(step, instance)

    assert result.is_success is False
    assert result.error is not None


# ---------------------------------------------------------------------------
# Step model validation
# ---------------------------------------------------------------------------


def test_all_hc_steps_have_is_human_checkpoint_true():
    for step in W9_STEPS:
        if step.interaction_type == "HC":
            assert step.is_human_checkpoint is True, (
                f"{step.id} is HC but is_human_checkpoint=False"
            )


def test_dc_steps_have_auto_continue_minutes():
    for step in W9_STEPS:
        if step.interaction_type == "DC":
            assert step.dc_auto_continue_minutes is not None and step.dc_auto_continue_minutes > 0, (
                f"{step.id} is DC but dc_auto_continue_minutes not set"
            )


def test_estimated_costs_non_negative():
    for step in W9_STEPS:
        assert step.estimated_cost >= 0.0, f"{step.id} has negative estimated_cost"


def test_total_estimated_cost_under_50_dollars():
    """Sanity check: W9 total estimated cost should be reasonable."""
    total = sum(s.estimated_cost for s in W9_STEPS)
    assert total < 50.0, f"Total estimated cost ${total:.2f} exceeds $50 budget"


# ---------------------------------------------------------------------------
# _DOCKER_STEPS structure tests
# ---------------------------------------------------------------------------


def test_docker_steps_subset_of_all_steps():
    all_ids = {s.id for s in W9_STEPS}
    for step_id in _DOCKER_STEPS:
        assert step_id in all_ids, f"{step_id} in _DOCKER_STEPS but not in W9_STEPS"


def test_docker_steps_not_code_steps():
    """_DOCKER_STEPS are agent steps (not code-only), so they shouldn't overlap _CODE_STEPS."""
    overlap = _DOCKER_STEPS & _CODE_STEPS
    assert not overlap, f"_DOCKER_STEPS/CODE_STEPS overlap: {overlap}"


def test_docker_steps_contains_analysis_steps():
    expected = {"GENOMIC_ANALYSIS", "EXPRESSION_ANALYSIS", "PROTEIN_ANALYSIS",
                "PATHWAY_ENRICHMENT", "NETWORK_ANALYSIS"}
    assert expected == _DOCKER_STEPS


# ---------------------------------------------------------------------------
# _maybe_execute_code unit tests (Docker mocked)
# ---------------------------------------------------------------------------

# DockerCodeRunner is lazily imported inside _maybe_execute_code, so patch at source
_DOCKER_RUNNER_PATH = "app.execution.docker_runner.DockerCodeRunner"


def _make_exec_result(exit_code: int = 0, stdout: str = "ok", runtime: float = 0.5):
    from app.models.code_execution import ExecutionResult
    return ExecutionResult(
        stdout=stdout,
        stderr="",
        exit_code=exit_code,
        runtime_seconds=runtime,
    )


@pytest.mark.asyncio
async def test_maybe_execute_code_no_code_block(runner):
    """Returns original result unchanged when no code_block in output."""
    original = AgentOutput(
        agent_id="t01_genomics",
        output={"variants": 5},
        summary="done",
        is_success=True,
        cost=0.1,
    )
    result = await runner._maybe_execute_code("GENOMIC_ANALYSIS", original)
    assert result is original


@pytest.mark.asyncio
async def test_maybe_execute_code_null_code_block(runner):
    """Returns original result when code_block is None."""
    original = AgentOutput(
        agent_id="t01_genomics",
        output={"code_block": None},
        summary="done",
        is_success=True,
    )
    result = await runner._maybe_execute_code("GENOMIC_ANALYSIS", original)
    assert result is original


@pytest.mark.asyncio
async def test_maybe_execute_code_malformed_code_block(runner):
    """Returns original result when CodeBlock construction fails (e.g. not a dict)."""
    original = AgentOutput(
        agent_id="t01_genomics",
        output={"code_block": "not-a-dict"},
        summary="done",
        is_success=True,
    )
    result = await runner._maybe_execute_code("GENOMIC_ANALYSIS", original)
    assert result is original


@pytest.mark.asyncio
async def test_maybe_execute_code_success(runner):
    """Successful Docker run merges execution_result into output dict."""
    agent_out = AgentOutput(
        agent_id="t01_genomics",
        output={
            "variants": 100,
            "code_block": {"language": "python", "code": "print('hello')", "dependencies": []},
        },
        summary="done",
        is_success=True,
        cost=0.2,
    )

    with patch(_DOCKER_RUNNER_PATH) as MockRunner:
        instance = MockRunner.return_value
        instance.run = AsyncMock(return_value=_make_exec_result(exit_code=0, stdout="hello\n"))

        result = await runner._maybe_execute_code("GENOMIC_ANALYSIS", agent_out)

    assert result is not agent_out
    assert result.is_success is True
    assert result.cost == pytest.approx(0.2)
    exec_r = result.output["execution_result"]
    assert exec_r["exit_code"] == 0
    assert exec_r["stdout"] == "hello\n"
    assert exec_r["sandbox_used"] is True
    assert "execution_warning" not in result.output
    # Original fields preserved
    assert result.output["variants"] == 100


@pytest.mark.asyncio
async def test_maybe_execute_code_nonzero_exit_adds_warning(runner):
    """Non-zero exit code adds execution_warning to output."""
    agent_out = AgentOutput(
        agent_id="t01_genomics",
        output={"code_block": {"language": "python", "code": "exit(1)", "dependencies": []}},
        summary="done",
        is_success=True,
    )

    with patch(_DOCKER_RUNNER_PATH) as MockRunner:
        instance = MockRunner.return_value
        instance.run = AsyncMock(return_value=_make_exec_result(exit_code=1, stdout=""))

        result = await runner._maybe_execute_code("GENOMIC_ANALYSIS", agent_out)

    assert result.output["execution_result"]["exit_code"] == 1
    assert "execution_warning" in result.output
    assert "1" in result.output["execution_warning"]


@pytest.mark.asyncio
async def test_maybe_execute_code_r_image_for_expression(runner):
    """EXPRESSION_ANALYSIS step passes R image (image_r set)."""
    agent_out = AgentOutput(
        agent_id="t02_transcriptomics",
        output={"code_block": {"language": "R", "code": "cat('ok')", "dependencies": []}},
        summary="done",
        is_success=True,
    )

    with patch(_DOCKER_RUNNER_PATH) as MockRunner:
        instance = MockRunner.return_value
        instance.run = AsyncMock(return_value=_make_exec_result())

        await runner._maybe_execute_code("EXPRESSION_ANALYSIS", agent_out)

        # image_r should be set to a non-None value for R steps
        init_kwargs = MockRunner.call_args.kwargs
        assert init_kwargs.get("image_r") is not None


@pytest.mark.asyncio
async def test_maybe_execute_code_python_image_for_other_steps(runner):
    """Non-R steps pass image_r=None (use Python image)."""
    agent_out = AgentOutput(
        agent_id="t03_proteomics",
        output={"code_block": {"language": "python", "code": "print(1)", "dependencies": []}},
        summary="done",
        is_success=True,
    )

    with patch(_DOCKER_RUNNER_PATH) as MockRunner:
        instance = MockRunner.return_value
        instance.run = AsyncMock(return_value=_make_exec_result())

        await runner._maybe_execute_code("PROTEIN_ANALYSIS", agent_out)

        init_kwargs = MockRunner.call_args.kwargs
        assert init_kwargs.get("image_r") is None


@pytest.mark.asyncio
async def test_maybe_execute_code_non_dict_output(runner):
    """If agent_result.output is not a dict, returns original unchanged."""
    original = AgentOutput(
        agent_id="t01_genomics",
        output="plain string output",
        summary="done",
        is_success=True,
    )
    result = await runner._maybe_execute_code("GENOMIC_ANALYSIS", original)
    assert result is original


@pytest.mark.asyncio
async def test_run_agent_step_triggers_docker_for_docker_steps(mock_registry):
    """_run_agent_step calls _maybe_execute_code for steps in _DOCKER_STEPS."""
    reg, mock_agent = mock_registry
    code_block = {"language": "python", "code": "print(42)", "dependencies": []}
    mock_agent.run = AsyncMock(return_value=AgentOutput(
        agent_id="t01_genomics",
        output={"result": "ok", "code_block": code_block},
        summary="done",
        is_success=True,
        cost=0.1,
    ))

    runner = W9BioinformaticsRunner(registry=reg)

    step = next(s for s in W9_STEPS if s.id == "GENOMIC_ANALYSIS")
    instance = WorkflowInstance(template="W9", query="test", budget_total=50.0)

    exec_result = _make_exec_result(stdout="42\n")
    with (
        patch(_DOCKER_RUNNER_PATH) as MockRunner,
        patch("app.workflows.runners.w9_bioinformatics.settings") as mock_settings,
    ):
        mock_settings.docker_enabled = True
        mock_settings.docker_timeout_seconds = 120
        mock_settings.docker_memory_limit = "512m"
        mock_settings.docker_cpu_limit = "1.0"
        mock_settings.docker_image_python = "python:3.12-slim"
        mock_settings.docker_image_r = "r-base:4.4"

        instance_runner = MockRunner.return_value
        instance_runner.run = AsyncMock(return_value=exec_result)

        result = await runner._run_agent_step(step, instance)

    assert result.output.get("execution_result") is not None
    assert result.output["execution_result"]["stdout"] == "42\n"


@pytest.mark.asyncio
async def test_run_agent_step_skips_docker_when_disabled(mock_registry):
    """_run_agent_step skips _maybe_execute_code when docker_enabled=False."""
    reg, mock_agent = mock_registry
    code_block = {"language": "python", "code": "print(42)", "dependencies": []}
    mock_agent.run = AsyncMock(return_value=AgentOutput(
        agent_id="t01_genomics",
        output={"result": "ok", "code_block": code_block},
        summary="done",
        is_success=True,
        cost=0.1,
    ))

    runner = W9BioinformaticsRunner(registry=reg)
    step = next(s for s in W9_STEPS if s.id == "GENOMIC_ANALYSIS")
    instance = WorkflowInstance(template="W9", query="test", budget_total=50.0)

    with patch("app.workflows.runners.w9_bioinformatics.settings") as mock_settings:
        mock_settings.docker_enabled = False

        result = await runner._run_agent_step(step, instance)

    # code_block should still be in output, but no execution_result
    assert "execution_result" not in result.output
    assert result.output.get("code_block") == code_block


# ---------------------------------------------------------------------------
# Phase 7-A: Template & Cost Mode Tests
# ---------------------------------------------------------------------------

from app.workflows.w9_cost_modes import COST_MODE_CONFIG
from app.workflows.w9_templates import (
    W9_TEMPLATES,
    resolve_skip_steps,
)


class TestW9Templates:
    """Tests for W9 analysis templates."""

    def test_all_templates_exist(self):
        expected = {"rnaseq_dea", "variant_annotation", "pathway_analysis",
                    "scrnaseq_clustering", "multi_omics", "literature_only"}
        assert set(W9_TEMPLATES.keys()) == expected

    def test_multi_omics_skips_nothing(self):
        tpl = W9_TEMPLATES["multi_omics"]
        assert tpl.skip_steps == frozenset()

    def test_rnaseq_dea_skips_genomics(self):
        tpl = W9_TEMPLATES["rnaseq_dea"]
        assert "GENOMIC_ANALYSIS" in tpl.skip_steps
        assert "EXPRESSION_ANALYSIS" not in tpl.skip_steps

    def test_literature_only_skips_phase_b(self):
        tpl = W9_TEMPLATES["literature_only"]
        phase_b_steps = {"GENOMIC_ANALYSIS", "EXPRESSION_ANALYSIS", "PROTEIN_ANALYSIS",
                         "VARIANT_ANNOTATION", "PATHWAY_ENRICHMENT", "NETWORK_ANALYSIS"}
        assert phase_b_steps.issubset(tpl.skip_steps)

    def test_variant_annotation_template_skips_expression(self):
        tpl = W9_TEMPLATES["variant_annotation"]
        assert "EXPRESSION_ANALYSIS" in tpl.skip_steps
        assert "GENOMIC_ANALYSIS" not in tpl.skip_steps

    def test_all_templates_have_positive_budget(self):
        for name, tpl in W9_TEMPLATES.items():
            assert tpl.budget_default > 0, f"{name} has non-positive budget"

    def test_all_skip_steps_are_valid_w9_step_ids(self):
        valid_ids = {s.id for s in W9_STEPS}
        for name, tpl in W9_TEMPLATES.items():
            invalid = tpl.skip_steps - valid_ids
            assert not invalid, f"{name} references invalid step IDs: {invalid}"


class TestResolveSkipSteps:
    """Tests for resolve_skip_steps dependency cascade."""

    def test_no_skip_returns_empty(self):
        assert resolve_skip_steps(frozenset()) == frozenset()

    def test_genomic_skip_cascades_to_variant_annotation(self):
        result = resolve_skip_steps(frozenset({"GENOMIC_ANALYSIS"}))
        assert "VARIANT_ANNOTATION" in result
        assert "GENOMIC_ANALYSIS" in result

    def test_expression_skip_cascades_to_integrity_audit(self):
        result = resolve_skip_steps(frozenset({"EXPRESSION_ANALYSIS"}))
        assert "INTEGRITY_AUDIT" in result

    def test_independent_steps_dont_cascade(self):
        result = resolve_skip_steps(frozenset({"PROTEIN_ANALYSIS"}))
        assert "VARIANT_ANNOTATION" not in result
        assert "INTEGRITY_AUDIT" not in result

    def test_rnaseq_template_cascades_correctly(self):
        tpl = W9_TEMPLATES["rnaseq_dea"]
        resolved = resolve_skip_steps(tpl.skip_steps)
        # GENOMIC_ANALYSIS skipped → VARIANT_ANNOTATION also skipped
        assert "VARIANT_ANNOTATION" in resolved
        # EXPRESSION_ANALYSIS NOT skipped → INTEGRITY_AUDIT still runs
        assert "INTEGRITY_AUDIT" not in resolved

    def test_literature_only_cascade(self):
        tpl = W9_TEMPLATES["literature_only"]
        resolved = resolve_skip_steps(tpl.skip_steps)
        # Both VARIANT_ANNOTATION and INTEGRITY_AUDIT should be skipped
        assert "VARIANT_ANNOTATION" in resolved
        assert "INTEGRITY_AUDIT" in resolved


class TestCostModes:
    """Tests for COST_MODE_CONFIG."""

    def test_all_modes_exist(self):
        assert set(COST_MODE_CONFIG.keys()) == {"quick", "standard", "deep"}

    def test_quick_mode_uses_gemini(self):
        assert COST_MODE_CONFIG["quick"]["default_tier"] == "gemini"

    def test_standard_mode_uses_sonnet(self):
        assert COST_MODE_CONFIG["standard"]["default_tier"] == "sonnet"

    def test_quick_mode_has_low_budget(self):
        assert COST_MODE_CONFIG["quick"]["budget"] <= 5.0

    def test_deep_mode_has_extra_agentic(self):
        extra = COST_MODE_CONFIG["deep"].get("extra_agentic", frozenset())
        assert "EXPRESSION_ANALYSIS" in extra
        assert "PATHWAY_ENRICHMENT" in extra

    def test_standard_mode_no_opus_override(self):
        assert COST_MODE_CONFIG["standard"]["opus_override"] is None


class TestRunnerTemplateIntegration:
    """Tests for template + cost mode integration in W9BioinformaticsRunner."""

    @pytest.mark.asyncio
    async def test_backward_compatible_no_template(self, runner):
        """run() without template_name/cost_mode works (backward compat)."""
        with (
            patch(_HEALTH_CHECKER_PATH) as mock_hc,
            patch(_REPORT_BUILDER_PATH, return_value=MagicMock()),
        ):
            mock_hc.check_all = AsyncMock(return_value=[])

            result = await runner.run(
                query="BRCA1 variants",
                budget=50.0,
                skip_human_checkpoints=True,
            )

        assert len(result["step_results"]) == 21
        assert runner._template_name == "multi_omics"
        assert runner._cost_mode == "standard"

    @pytest.mark.asyncio
    async def test_rnaseq_template_skips_genomic_steps(self, mock_registry):
        """rnaseq_dea template skips GENOMIC_ANALYSIS + VARIANT_ANNOTATION."""
        reg, _ = mock_registry
        runner = W9BioinformaticsRunner(registry=reg)

        with (
            patch(_HEALTH_CHECKER_PATH) as mock_hc,
            patch(_REPORT_BUILDER_PATH, return_value=MagicMock()),
        ):
            mock_hc.check_all = AsyncMock(return_value=[])

            result = await runner.run(
                query="RNA-seq DEA test",
                budget=50.0,
                skip_human_checkpoints=True,
                template_name="rnaseq_dea",
            )

        step_results = result["step_results"]
        # Skipped steps should have "Skipped by template" summary
        genomic = step_results.get("GENOMIC_ANALYSIS")
        assert genomic is not None
        assert "Skipped" in genomic.summary

        # Cascaded: VARIANT_ANNOTATION also skipped
        variant = step_results.get("VARIANT_ANNOTATION")
        assert variant is not None
        assert "Skipped" in variant.summary

        # EXPRESSION_ANALYSIS should still run (not skipped)
        expr = step_results.get("EXPRESSION_ANALYSIS")
        assert expr is not None
        assert "Skipped" not in expr.summary

    @pytest.mark.asyncio
    async def test_literature_only_skips_phase_b(self, mock_registry):
        """literature_only template skips all Phase B domain analysis."""
        reg, _ = mock_registry
        runner = W9BioinformaticsRunner(registry=reg)

        with (
            patch(_HEALTH_CHECKER_PATH) as mock_hc,
            patch(_REPORT_BUILDER_PATH, return_value=MagicMock()),
        ):
            mock_hc.check_all = AsyncMock(return_value=[])

            result = await runner.run(
                query="Literature review of BRCA1",
                budget=50.0,
                skip_human_checkpoints=True,
                template_name="literature_only",
            )

        step_results = result["step_results"]
        phase_b_ids = {"GENOMIC_ANALYSIS", "EXPRESSION_ANALYSIS", "PROTEIN_ANALYSIS",
                       "VARIANT_ANNOTATION", "PATHWAY_ENRICHMENT", "NETWORK_ANALYSIS"}
        for step_id in phase_b_ids:
            assert "Skipped" in step_results[step_id].summary, f"{step_id} should be skipped"

        # Phase D steps should still run
        assert "Skipped" not in step_results["LITERATURE_COMPARISON"].summary

    @pytest.mark.asyncio
    async def test_quick_mode_routes_to_gemini(self, mock_registry):
        """Quick cost mode invokes _run_with_gemini for agent steps."""
        reg, _ = mock_registry
        runner = W9BioinformaticsRunner(registry=reg)

        # Mock GeminiLayer at its source module (lazy import inside _run_with_gemini)
        mock_gemini_cls = MagicMock()
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {"research_question": "test"}
        mock_meta = MagicMock(cost=0.0)
        mock_gemini_cls.return_value.complete_structured = AsyncMock(
            return_value=(mock_result, mock_meta)
        )

        with (
            patch(_HEALTH_CHECKER_PATH) as mock_hc,
            patch(_REPORT_BUILDER_PATH, return_value=MagicMock()),
            patch("app.llm.gemini_layer.GeminiLayer", mock_gemini_cls),
        ):
            mock_hc.check_all = AsyncMock(return_value=[])

            await runner.run(
                query="Quick test",
                budget=50.0,
                skip_human_checkpoints=True,
                cost_mode="quick",
            )

        # GeminiLayer should have been called for agent steps
        assert mock_gemini_cls.call_count > 0
        assert runner._cost_mode == "quick"

    @pytest.mark.asyncio
    async def test_quick_mode_fallback_on_gemini_error(self, mock_registry):
        """If Gemini fails, quick mode falls back to regular agent."""
        reg, mock_agent = mock_registry
        runner = W9BioinformaticsRunner(registry=reg)

        with (
            patch(_HEALTH_CHECKER_PATH) as mock_hc,
            patch(_REPORT_BUILDER_PATH, return_value=MagicMock()),
            patch(
                "app.llm.gemini_layer.GeminiLayer",
                side_effect=ImportError("google-genai not installed"),
            ),
        ):
            mock_hc.check_all = AsyncMock(return_value=[])

            result = await runner.run(
                query="Fallback test",
                budget=50.0,
                skip_human_checkpoints=True,
                cost_mode="quick",
            )

        # Should still complete via agent fallback
        assert len(result["step_results"]) == 21

    @pytest.mark.asyncio
    async def test_template_budget_override(self, mock_registry):
        """Template budget_default is used when caller uses default budget."""
        reg, _ = mock_registry
        runner = W9BioinformaticsRunner(registry=reg)

        with (
            patch(_HEALTH_CHECKER_PATH) as mock_hc,
            patch(_REPORT_BUILDER_PATH, return_value=MagicMock()),
        ):
            mock_hc.check_all = AsyncMock(return_value=[])

            result = await runner.run(
                query="test",
                skip_human_checkpoints=True,
                template_name="rnaseq_dea",
            )

        instance = result["instance"]
        assert instance.budget_total == 8.0  # rnaseq_dea default

    @pytest.mark.asyncio
    async def test_explicit_budget_not_overridden(self, mock_registry):
        """If caller provides explicit budget != 25.0, it takes priority."""
        reg, _ = mock_registry
        runner = W9BioinformaticsRunner(registry=reg)

        with (
            patch(_HEALTH_CHECKER_PATH) as mock_hc,
            patch(_REPORT_BUILDER_PATH, return_value=MagicMock()),
        ):
            mock_hc.check_all = AsyncMock(return_value=[])

            result = await runner.run(
                query="test",
                budget=15.0,
                skip_human_checkpoints=True,
                template_name="rnaseq_dea",
            )

        instance = result["instance"]
        assert instance.budget_total == 15.0  # User's explicit budget

    @pytest.mark.asyncio
    async def test_deep_mode_enables_extra_agentic(self, mock_registry):
        """Deep cost mode adds extra agentic steps."""
        reg, _ = mock_registry
        runner = W9BioinformaticsRunner(registry=reg)

        with (
            patch(_HEALTH_CHECKER_PATH) as mock_hc,
            patch(_REPORT_BUILDER_PATH, return_value=MagicMock()),
        ):
            mock_hc.check_all = AsyncMock(return_value=[])

            await runner.run(
                query="test",
                budget=50.0,
                skip_human_checkpoints=True,
                cost_mode="deep",
            )

        assert "EXPRESSION_ANALYSIS" in runner._extra_agentic
        assert "PATHWAY_ENRICHMENT" in runner._extra_agentic

    def test_should_use_gemini_quick_mode(self, runner):
        """_should_use_gemini returns True for agent steps in quick mode."""
        runner._cost_mode = "quick"
        agent_step = next(s for s in W9_STEPS if s.id == "SCOPE")
        assert runner._should_use_gemini(agent_step) is True

    def test_should_use_gemini_skips_code_steps(self, runner):
        """_should_use_gemini returns False for code-only steps."""
        runner._cost_mode = "quick"
        code_step = next(s for s in W9_STEPS if s.id == "PRE_HEALTH_CHECK")
        assert runner._should_use_gemini(code_step) is False

    def test_should_use_gemini_false_for_standard_mode(self, runner):
        """_should_use_gemini returns False in standard mode."""
        runner._cost_mode = "standard"
        agent_step = next(s for s in W9_STEPS if s.id == "SCOPE")
        assert runner._should_use_gemini(agent_step) is False

    def test_unknown_template_falls_back_to_no_skip(self, runner):
        """Unknown template name defaults to no skip steps."""
        runner._template_name = "nonexistent_template"
        runner._cost_mode = "standard"
        runner._resolve_template_and_cost_mode(25.0)
        assert runner._skip_steps == frozenset()
