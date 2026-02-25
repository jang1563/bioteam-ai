"""Tests for Workflow Engine state machine."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.models.workflow import WorkflowInstance
from app.workflows.engine import (
    IllegalTransitionError,
    WorkflowEngine,
)


def make_instance(state: str = "PENDING", **kwargs) -> WorkflowInstance:
    """Create a test WorkflowInstance."""
    return WorkflowInstance(template="W1", state=state, **kwargs)


# === Legal Transition Tests ===

def test_pending_to_running():
    engine = WorkflowEngine()
    inst = make_instance("PENDING")
    engine.start(inst, first_step="SEARCH")
    assert inst.state == "RUNNING"
    assert inst.current_step == "SEARCH"
    print("  PASS: PENDING → RUNNING")


def test_pending_to_cancelled():
    engine = WorkflowEngine()
    inst = make_instance("PENDING")
    engine.cancel(inst)
    assert inst.state == "CANCELLED"
    print("  PASS: PENDING → CANCELLED")


def test_running_to_paused():
    engine = WorkflowEngine()
    inst = make_instance("RUNNING")
    engine.pause(inst)
    assert inst.state == "PAUSED"
    print("  PASS: RUNNING → PAUSED")


def test_running_to_waiting_human():
    engine = WorkflowEngine()
    inst = make_instance("RUNNING")
    engine.request_human(inst)
    assert inst.state == "WAITING_HUMAN"
    print("  PASS: RUNNING → WAITING_HUMAN")


def test_running_to_over_budget():
    engine = WorkflowEngine()
    inst = make_instance("RUNNING")
    engine.mark_over_budget(inst)
    assert inst.state == "OVER_BUDGET"
    print("  PASS: RUNNING → OVER_BUDGET")


def test_running_to_failed():
    engine = WorkflowEngine()
    inst = make_instance("RUNNING")
    engine.fail(inst, "Test error")
    assert inst.state == "FAILED"
    print("  PASS: RUNNING → FAILED")


def test_running_to_completed():
    engine = WorkflowEngine()
    inst = make_instance("RUNNING")
    engine.complete(inst)
    assert inst.state == "COMPLETED"
    print("  PASS: RUNNING → COMPLETED")


def test_running_to_cancelled():
    engine = WorkflowEngine()
    inst = make_instance("RUNNING")
    engine.cancel(inst)
    assert inst.state == "CANCELLED"
    print("  PASS: RUNNING → CANCELLED")


def test_paused_to_running():
    engine = WorkflowEngine()
    inst = make_instance("PAUSED")
    engine.resume(inst)
    assert inst.state == "RUNNING"
    print("  PASS: PAUSED → RUNNING")


def test_paused_to_cancelled():
    engine = WorkflowEngine()
    inst = make_instance("PAUSED")
    engine.cancel(inst)
    assert inst.state == "CANCELLED"
    print("  PASS: PAUSED → CANCELLED")


def test_waiting_to_running():
    engine = WorkflowEngine()
    inst = make_instance("WAITING_HUMAN")
    engine.resume(inst)
    assert inst.state == "RUNNING"
    print("  PASS: WAITING_HUMAN → RUNNING")


def test_waiting_to_cancelled():
    engine = WorkflowEngine()
    inst = make_instance("WAITING_HUMAN")
    engine.cancel(inst)
    assert inst.state == "CANCELLED"
    print("  PASS: WAITING_HUMAN → CANCELLED")


def test_over_budget_to_running():
    engine = WorkflowEngine()
    inst = make_instance("OVER_BUDGET")
    engine.resume(inst)
    assert inst.state == "RUNNING"
    print("  PASS: OVER_BUDGET → RUNNING")


def test_over_budget_to_cancelled():
    engine = WorkflowEngine()
    inst = make_instance("OVER_BUDGET")
    engine.cancel(inst)
    assert inst.state == "CANCELLED"
    print("  PASS: OVER_BUDGET → CANCELLED")


def test_failed_to_running():
    engine = WorkflowEngine()
    inst = make_instance("FAILED")
    engine.resume(inst)
    assert inst.state == "RUNNING"
    print("  PASS: FAILED → RUNNING")


def test_failed_to_cancelled():
    engine = WorkflowEngine()
    inst = make_instance("FAILED")
    engine.cancel(inst)
    assert inst.state == "CANCELLED"
    print("  PASS: FAILED → CANCELLED")


# === Illegal Transition Tests ===

def test_completed_is_terminal():
    engine = WorkflowEngine()
    inst = make_instance("COMPLETED")
    try:
        engine.transition(inst, "RUNNING")
        assert False, "Should raise"
    except IllegalTransitionError as e:
        assert e.from_state == "COMPLETED"
    print("  PASS: COMPLETED is terminal")


def test_cancelled_is_terminal():
    engine = WorkflowEngine()
    inst = make_instance("CANCELLED")
    try:
        engine.transition(inst, "RUNNING")
        assert False, "Should raise"
    except IllegalTransitionError as e:
        assert e.from_state == "CANCELLED"
    print("  PASS: CANCELLED is terminal")


def test_pending_to_paused_illegal():
    engine = WorkflowEngine()
    inst = make_instance("PENDING")
    try:
        engine.pause(inst)
        assert False, "Should raise"
    except IllegalTransitionError:
        pass
    print("  PASS: PENDING → PAUSED is illegal")


def test_pending_to_over_budget_illegal():
    engine = WorkflowEngine()
    inst = make_instance("PENDING")
    try:
        engine.mark_over_budget(inst)
        assert False, "Should raise"
    except IllegalTransitionError:
        pass
    print("  PASS: PENDING → OVER_BUDGET is illegal")


# === Feature Tests ===

def test_advance_records_history():
    engine = WorkflowEngine()
    inst = make_instance("RUNNING")

    engine.advance(inst, "SEARCH", {"papers_found": 47})
    engine.advance(inst, "SCREEN", {"papers_screened": 47})

    assert len(inst.step_history) == 2
    assert inst.step_history[0]["step_id"] == "SEARCH"
    assert inst.step_history[1]["step_id"] == "SCREEN"
    assert inst.current_step == "SCREEN"
    print("  PASS: advance records history")


def test_loop_check():
    engine = WorkflowEngine()
    inst = make_instance("RUNNING", max_loops=2)

    assert engine.check_loop(inst, "SYNTH") is True
    engine.increment_loop(inst, "SYNTH")
    assert engine.check_loop(inst, "SYNTH") is True
    engine.increment_loop(inst, "SYNTH")
    assert engine.check_loop(inst, "SYNTH") is False  # 2 >= 2
    print("  PASS: loop check")


def test_budget_check():
    engine = WorkflowEngine()
    inst = make_instance("RUNNING", budget_total=5.0, budget_remaining=1.50)

    assert engine.check_budget(inst, 1.00) is True
    assert engine.check_budget(inst, 2.00) is False
    print("  PASS: budget check")


def test_budget_deduction():
    engine = WorkflowEngine()
    inst = make_instance("RUNNING", budget_remaining=5.0)

    remaining = engine.deduct_budget(inst, 1.23)
    assert abs(remaining - 3.77) < 0.001
    assert abs(inst.budget_remaining - 3.77) < 0.001
    print("  PASS: budget deduction")


def test_can_transition():
    engine = WorkflowEngine()
    assert engine.can_transition("PENDING", "RUNNING") is True
    assert engine.can_transition("PENDING", "PAUSED") is False
    assert engine.can_transition("COMPLETED", "RUNNING") is False
    print("  PASS: can_transition")


def test_get_valid_transitions():
    engine = WorkflowEngine()
    valid = engine.get_valid_transitions("RUNNING")
    assert "PAUSED" in valid
    assert "COMPLETED" in valid
    assert "FAILED" in valid
    assert "CANCELLED" in valid

    terminal = engine.get_valid_transitions("COMPLETED")
    assert terminal == []
    print("  PASS: get_valid_transitions")


# === Full Lifecycle Test ===

def test_full_lifecycle():
    """Complete workflow lifecycle: PENDING → RUNNING → PAUSED → RUNNING → COMPLETED."""
    engine = WorkflowEngine()
    inst = make_instance("PENDING")

    engine.start(inst, "SEARCH")
    assert inst.state == "RUNNING"

    engine.advance(inst, "SEARCH", {"papers": 47})
    engine.advance(inst, "SCREEN", {"screened": 47})

    engine.pause(inst)
    assert inst.state == "PAUSED"

    engine.resume(inst)
    assert inst.state == "RUNNING"

    engine.advance(inst, "SYNTH", {"synthesized": True})
    engine.complete(inst)
    assert inst.state == "COMPLETED"

    assert len(inst.step_history) == 3
    print("  PASS: full lifecycle")


if __name__ == "__main__":
    print("Testing Workflow Engine:")
    # Legal transitions
    test_pending_to_running()
    test_pending_to_cancelled()
    test_running_to_paused()
    test_running_to_waiting_human()
    test_running_to_over_budget()
    test_running_to_failed()
    test_running_to_completed()
    test_running_to_cancelled()
    test_paused_to_running()
    test_paused_to_cancelled()
    test_waiting_to_running()
    test_waiting_to_cancelled()
    test_over_budget_to_running()
    test_over_budget_to_cancelled()
    test_failed_to_running()
    test_failed_to_cancelled()
    # Illegal transitions
    test_completed_is_terminal()
    test_cancelled_is_terminal()
    test_pending_to_paused_illegal()
    test_pending_to_over_budget_illegal()
    # Features
    test_advance_records_history()
    test_loop_check()
    test_budget_check()
    test_budget_deduction()
    test_can_transition()
    test_get_valid_transitions()
    test_full_lifecycle()
    print("\nAll Workflow Engine tests passed!")
