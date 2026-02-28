"""Tests for CheckpointManager and SessionCheckpoint."""

from __future__ import annotations

import pytest
from app.models.agent import AgentOutput
from app.models.step_error import StepErrorReport
from app.workflows.checkpoint_manager import CheckpointManager
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture
def in_memory_engine():
    engine = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(in_memory_engine):
    with Session(in_memory_engine) as session:
        yield session


@pytest.fixture(autouse=True)
def enable_checkpoints(monkeypatch):
    """Force checkpoint_enabled=True for all tests."""
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "checkpoint_enabled", True)
    monkeypatch.setattr(cfg.settings, "checkpoint_dir", "/tmp/test_runs")


def test_save_and_load_step(db_session):
    mgr = CheckpointManager(db_session)
    output = AgentOutput(
        agent_id="t01_genomics",
        output={"variants": 42},
        summary="Found 42 variants",
        cost=0.25,
    )

    cp = mgr.save_step(
        workflow_id="wf-001",
        step_id="GENOMIC_ANALYSIS",
        step_index=3,
        agent_id="t01_genomics",
        output=output,
        cost=0.25,
    )

    assert cp.workflow_id == "wf-001"
    assert cp.step_id == "GENOMIC_ANALYSIS"
    assert cp.status == "completed"

    loaded = mgr.load_completed_steps("wf-001")
    assert "GENOMIC_ANALYSIS" in loaded
    assert loaded["GENOMIC_ANALYSIS"].agent_id == "t01_genomics"


def test_save_list_output(db_session):
    mgr = CheckpointManager(db_session)
    outputs = [
        AgentOutput(agent_id="t01_genomics", output={"a": 1}, cost=0.1),
        AgentOutput(agent_id="qa_statistical_rigor", output={"b": 2}, cost=0.05),
    ]

    mgr.save_step(
        workflow_id="wf-002",
        step_id="PARALLEL_STEP",
        step_index=1,
        agent_id="t01_genomics",
        output=outputs,
        cost=0.15,
    )

    loaded = mgr.load_completed_steps("wf-002")
    assert "PARALLEL_STEP" in loaded


def test_upsert_existing_step(db_session):
    mgr = CheckpointManager(db_session)
    output_v1 = AgentOutput(agent_id="t01_genomics", output={"v": 1})
    mgr.save_step("wf-003", "STEP_A", 0, "t01_genomics", output_v1)

    output_v2 = AgentOutput(agent_id="t01_genomics", output={"v": 2})
    mgr.save_step("wf-003", "STEP_A", 0, "t01_genomics", output_v2)

    loaded = mgr.load_completed_steps("wf-003")
    assert loaded["STEP_A"].output == {"v": 2}


def test_cost_total(db_session):
    mgr = CheckpointManager(db_session)
    for i, cost in enumerate([1.0, 2.5, 0.75]):
        mgr.save_step("wf-004", f"STEP_{i}", i, "agent", AgentOutput(agent_id="agent"), cost=cost)

    total = mgr.get_cost_total("wf-004")
    assert abs(total - 4.25) < 0.001


def test_save_error_report(db_session):
    mgr = CheckpointManager(db_session)
    report = StepErrorReport(
        step_id="BLAST",
        agent_id="t01_genomics",
        error_type="TRANSIENT",
        error_message="Connection timeout",
        recovery_suggestions=["Retry in 30s"],
        suggested_action="RETRY",
    )

    # Should not raise
    mgr.save_error_report("wf-005", "BLAST", report)


def test_error_classification_transient():
    import httpx

    timeout_exc = httpx.TimeoutException("Connection timed out")
    report = StepErrorReport.classify("BLAST", "t01_genomics", timeout_exc, retry_count=1)
    assert report.error_type == "TRANSIENT"
    assert report.suggested_action == "RETRY"
    assert report.retry_count == 1


def test_error_classification_user_input():
    exc = FileNotFoundError("No such file: /data/samples.vcf")
    report = StepErrorReport.classify("INGEST_DATA", "code", exc, retry_count=0)
    assert report.error_type == "USER_INPUT"
    assert report.suggested_action == "USER_PROVIDE_INPUT"


def test_error_classification_http_429():
    import httpx

    response = httpx.Response(status_code=429)
    exc = httpx.HTTPStatusError("Rate limited", request=None, response=response)
    report = StepErrorReport.classify("VEP", "t01", exc, retry_count=0)
    assert report.error_type == "TRANSIENT"


def test_load_empty_workflow(db_session):
    mgr = CheckpointManager(db_session)
    result = mgr.load_completed_steps("nonexistent-wf")
    assert result == {}
