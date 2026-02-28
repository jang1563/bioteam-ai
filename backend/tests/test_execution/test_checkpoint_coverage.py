"""Tests for H4 checkpoint coverage extension.

Validates:
1. load_completed_steps returns full list for parallel steps
2. checkpoint_helpers functions work correctly
3. All runners accept checkpoint_manager parameter
4. _get_runner factory creates CheckpointManager for all templates
5. W7 is in _SUPPORTED_TEMPLATES
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.models.agent import AgentOutput
from app.workflows.checkpoint_helpers import (
    load_and_skip_completed,
    save_step_checkpoint,
    should_skip_step,
)
from app.workflows.checkpoint_manager import CheckpointManager
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def in_memory_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(in_memory_engine):
    with Session(in_memory_engine) as session:
        yield session


@pytest.fixture(autouse=True)
def enable_checkpoints(monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "checkpoint_enabled", True)
    monkeypatch.setattr(cfg.settings, "checkpoint_dir", "/tmp/test_runs")


# ── H4.1: load_completed_steps returns full list ──────────────────────


def test_load_completed_steps_returns_list_for_parallel(db_session):
    """Parallel steps should restore as list[AgentOutput], not just first element."""
    mgr = CheckpointManager(db_session)
    outputs = [
        AgentOutput(agent_id="t01_genomics", output={"gene": "TP53"}, cost=0.1),
        AgentOutput(agent_id="t02_transcriptomics", output={"expr": 42}, cost=0.1),
        AgentOutput(agent_id="t03_proteomics", output={"prot": "ok"}, cost=0.1),
    ]

    mgr.save_step(
        workflow_id="wf-parallel",
        step_id="GENERATE",
        step_index=1,
        agent_id="t01_genomics",
        output=outputs,
        cost=0.3,
    )

    loaded = mgr.load_completed_steps("wf-parallel")
    assert "GENERATE" in loaded
    result = loaded["GENERATE"]
    assert isinstance(result, list), f"Expected list, got {type(result)}"
    assert len(result) == 3
    assert result[0].agent_id == "t01_genomics"
    assert result[1].agent_id == "t02_transcriptomics"
    assert result[2].agent_id == "t03_proteomics"


def test_load_completed_steps_single_remains_single(db_session):
    """Single-agent steps should still return a single AgentOutput."""
    mgr = CheckpointManager(db_session)
    output = AgentOutput(agent_id="research_director", output={"scope": "ok"}, cost=0.05)

    mgr.save_step("wf-single", "SCOPE", 0, "research_director", output, cost=0.05)

    loaded = mgr.load_completed_steps("wf-single")
    assert "SCOPE" in loaded
    result = loaded["SCOPE"]
    assert isinstance(result, AgentOutput), f"Expected AgentOutput, got {type(result)}"
    assert result.agent_id == "research_director"


def test_load_completed_steps_empty_list_returns_fallback(db_session):
    """Empty parallel output list should return a fallback single-item list."""
    mgr = CheckpointManager(db_session)
    # Manually save a row with empty outputs list
    from app.models.session_checkpoint import SessionCheckpoint

    cp = SessionCheckpoint(
        workflow_id="wf-empty",
        step_id="PARALLEL",
        step_index=0,
        agent_id="t01",
        status="completed",
        agent_output={"outputs": []},
    )
    db_session.add(cp)
    db_session.commit()

    loaded = mgr.load_completed_steps("wf-empty")
    result = loaded["PARALLEL"]
    assert isinstance(result, list)
    assert len(result) == 1  # fallback


# ── H4.2: checkpoint_helpers ──────────────────────────────────────────


def test_save_step_checkpoint_none_manager():
    """save_step_checkpoint should be a no-op when manager is None."""
    save_step_checkpoint(
        None, "wf-x", "STEP_A", 0, "agent", AgentOutput(agent_id="agent"), cost=0.0,
    )
    # No exception = pass


def test_save_step_checkpoint_success(db_session):
    mgr = CheckpointManager(db_session)
    output = AgentOutput(agent_id="t01", output={"data": 1})

    save_step_checkpoint(mgr, "wf-help", "STEP_B", 1, "t01", output, cost=0.5)

    loaded = mgr.load_completed_steps("wf-help")
    assert "STEP_B" in loaded
    assert loaded["STEP_B"].output == {"data": 1}


def test_save_step_checkpoint_handles_error():
    """save_step_checkpoint should not raise even if save fails."""
    mgr = MagicMock(spec=CheckpointManager)
    mgr.save_step.side_effect = Exception("DB connection lost")

    # Should not raise
    save_step_checkpoint(mgr, "wf-err", "STEP_C", 2, "agent", AgentOutput(agent_id="agent"))


def test_load_and_skip_completed_none_manager():
    """load_and_skip_completed should return empty dict when manager is None."""
    step_results = {}
    result = load_and_skip_completed(None, "wf-x", step_results)
    assert result == {}
    assert step_results == {}


def test_load_and_skip_completed_merges(db_session):
    """load_and_skip_completed should merge prior steps into step_results dict."""
    mgr = CheckpointManager(db_session)
    out1 = AgentOutput(agent_id="rd", output={"scope": "done"})
    out2 = AgentOutput(agent_id="km", output={"papers": 10})
    mgr.save_step("wf-merge", "SCOPE", 0, "rd", out1)
    mgr.save_step("wf-merge", "SEARCH", 1, "km", out2)

    step_results: dict = {}
    prior = load_and_skip_completed(mgr, "wf-merge", step_results)

    assert len(prior) == 2
    assert "SCOPE" in step_results
    assert "SEARCH" in step_results
    assert step_results["SCOPE"].agent_id == "rd"


def test_load_and_skip_completed_handles_error():
    """load_and_skip_completed should return empty dict on error."""
    mgr = MagicMock(spec=CheckpointManager)
    mgr.load_completed_steps.side_effect = Exception("DB error")

    step_results = {}
    result = load_and_skip_completed(mgr, "wf-err", step_results)
    assert result == {}


def test_should_skip_step():
    step_results = {"SCOPE": AgentOutput(agent_id="rd"), "SEARCH": AgentOutput(agent_id="km")}
    assert should_skip_step("SCOPE", step_results) is True
    assert should_skip_step("SEARCH", step_results) is True
    assert should_skip_step("SCREEN", step_results) is False


# ── H4.3: All runners accept checkpoint_manager ──────────────────────


def test_w1_runner_accepts_checkpoint_manager():
    from app.workflows.runners.w1_literature import W1LiteratureReviewRunner
    with patch("app.workflows.runners.w1_literature.AsyncWorkflowRunner"):
        runner = W1LiteratureReviewRunner(
            registry=MagicMock(), checkpoint_manager=MagicMock(),
        )
    assert runner._checkpoint_manager is not None


def test_w2_runner_accepts_checkpoint_manager():
    from app.workflows.runners.w2_hypothesis import W2HypothesisRunner
    runner = W2HypothesisRunner(registry=MagicMock(), checkpoint_manager=MagicMock())
    assert runner._checkpoint_manager is not None


def test_w3_runner_accepts_checkpoint_manager():
    from app.workflows.runners.w3_data_analysis import W3DataAnalysisRunner
    runner = W3DataAnalysisRunner(registry=MagicMock(), checkpoint_manager=MagicMock())
    assert runner._checkpoint_manager is not None


def test_w4_runner_accepts_checkpoint_manager():
    from app.workflows.runners.w4_manuscript import W4ManuscriptRunner
    runner = W4ManuscriptRunner(registry=MagicMock(), checkpoint_manager=MagicMock())
    assert runner._checkpoint_manager is not None


def test_w5_runner_accepts_checkpoint_manager():
    from app.workflows.runners.w5_grant import W5GrantProposalRunner
    runner = W5GrantProposalRunner(registry=MagicMock(), checkpoint_manager=MagicMock())
    assert runner._checkpoint_manager is not None


def test_w6_runner_accepts_checkpoint_manager():
    from app.workflows.runners.w6_ambiguity import W6AmbiguityRunner
    runner = W6AmbiguityRunner(registry=MagicMock(), checkpoint_manager=MagicMock())
    assert runner._checkpoint_manager is not None


def test_w7_runner_accepts_checkpoint_manager():
    from app.workflows.runners.w7_integrity import W7IntegrityRunner
    runner = W7IntegrityRunner(registry=MagicMock(), checkpoint_manager=MagicMock())
    assert runner._checkpoint_manager is not None


def test_w8_runner_accepts_checkpoint_manager():
    from app.workflows.runners.w8_paper_review import W8PaperReviewRunner
    runner = W8PaperReviewRunner(registry=MagicMock(), checkpoint_manager=MagicMock())
    assert runner._checkpoint_manager is not None


def test_w10_runner_accepts_checkpoint_manager():
    from app.workflows.runners.w10_drug_discovery import W10DrugDiscoveryRunner
    runner = W10DrugDiscoveryRunner(registry=MagicMock(), checkpoint_manager=MagicMock())
    assert runner._checkpoint_manager is not None


# ── H4.4: Factory & W7 registration ──────────────────────────────────


def test_w7_in_supported_templates():
    from app.api.v1.workflows import _SUPPORTED_TEMPLATES
    assert "W7" in _SUPPORTED_TEMPLATES


def test_all_templates_supported():
    from app.api.v1.workflows import _SUPPORTED_TEMPLATES
    for t in ["W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9", "W10"]:
        assert t in _SUPPORTED_TEMPLATES, f"{t} not in _SUPPORTED_TEMPLATES"


@patch("app.api.v1.workflows._make_checkpoint_manager")
def test_get_runner_passes_checkpoint_manager(mock_cp):
    """_get_runner should pass checkpoint_manager to all runners."""
    from app.api.v1.workflows import _get_runner

    mock_cp.return_value = MagicMock()
    mock_registry = MagicMock()
    mock_registry.get.return_value = MagicMock()

    for template in ["W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9", "W10"]:
        runner = _get_runner(template, mock_registry, MagicMock(), None, None, MagicMock())
        assert runner is not None, f"No runner for {template}"
        # Check that checkpoint_manager was set
        cp_attr = getattr(runner, "_checkpoint_manager", None)
        assert cp_attr is not None, f"Runner for {template} missing _checkpoint_manager"


@patch("app.api.v1.workflows._make_checkpoint_manager")
def test_get_runner_no_checkpoint_without_persist_fn(mock_cp):
    """When persist_fn is None, checkpoint_manager should be None."""
    from app.api.v1.workflows import _get_runner

    runner = _get_runner("W1", MagicMock(), MagicMock(), None, None, None)
    assert runner is not None
    mock_cp.assert_not_called()
