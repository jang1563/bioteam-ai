"""Tests for CostTracker."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.cost.tracker import CostTracker
from sqlmodel import Session, SQLModel, create_engine


def _setup_db():
    """Create a fresh in-memory SQLite database."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


def test_record_and_retrieve():
    """Should record a cost and retrieve workflow total."""
    engine = _setup_db()
    with Session(engine) as session:
        tracker = CostTracker(session)

        tracker.record_actual(
            workflow_id="w1_test",
            step_id="SEARCH",
            agent_id="knowledge_manager",
            model_tier="sonnet",
            model_version="claude-sonnet-4-5-20250929",
            input_tokens=1500,
            output_tokens=800,
            cost_usd=0.057,
        )
        tracker.record_actual(
            workflow_id="w1_test",
            step_id="SCREEN",
            agent_id="t02_transcriptomics",
            model_tier="sonnet",
            input_tokens=2000,
            output_tokens=500,
            cost_usd=0.045,
        )

        total = tracker.get_workflow_cost("w1_test")
        assert abs(total - 0.102) < 0.001
        print(f"  PASS: record_and_retrieve (total=${total:.4f})")


def test_check_budget_pass():
    """Should pass budget check when under limit."""
    engine = _setup_db()
    with Session(engine) as session:
        tracker = CostTracker(session)
        # No costs recorded yet — budget is full
        assert tracker.check_budget("w1_new", 0.50, "W1") is True
        print("  PASS: check_budget_pass")


def test_check_budget_fail():
    """Should fail budget check when over limit."""
    engine = _setup_db()
    with Session(engine) as session:
        tracker = CostTracker(session)

        # Spend almost the entire W1 budget ($5)
        tracker.record_actual(
            workflow_id="w1_expensive",
            step_id="SEARCH",
            agent_id="knowledge_manager",
            model_tier="opus",
            cost_usd=4.80,
        )

        # Next step costs $0.30 — exceeds remaining $0.20
        assert tracker.check_budget("w1_expensive", 0.30, "W1") is False
        print("  PASS: check_budget_fail")


def test_budget_status():
    """Should return correct budget status dict."""
    engine = _setup_db()
    with Session(engine) as session:
        tracker = CostTracker(session)

        tracker.record_actual(
            workflow_id="w1_status",
            step_id="SEARCH",
            agent_id="knowledge_manager",
            model_tier="sonnet",
            cost_usd=2.50,
        )

        status = tracker.get_budget_status("w1_status", "W1")
        assert status["budget"] == 5.0
        assert abs(status["spent"] - 2.50) < 0.01
        assert abs(status["remaining"] - 2.50) < 0.01
        assert abs(status["percentage"] - 0.50) < 0.01
        assert status["alert"] is False  # 50% < 80% threshold
        print("  PASS: budget_status")


def test_budget_alert():
    """Should flag alert when spending exceeds threshold."""
    engine = _setup_db()
    with Session(engine) as session:
        tracker = CostTracker(session)

        tracker.record_actual(
            workflow_id="w1_alert",
            step_id="SYNTH",
            agent_id="research_director",
            model_tier="opus",
            cost_usd=4.20,
        )

        status = tracker.get_budget_status("w1_alert", "W1")
        assert status["alert"] is True  # 84% > 80% threshold
        print("  PASS: budget_alert")


def test_workflow_breakdown():
    """Should return per-step breakdown."""
    engine = _setup_db()
    with Session(engine) as session:
        tracker = CostTracker(session)

        tracker.record_actual(
            workflow_id="w1_break",
            step_id="SEARCH",
            agent_id="knowledge_manager",
            model_tier="sonnet",
            cost_usd=0.05,
        )
        tracker.record_actual(
            workflow_id="w1_break",
            step_id="SCREEN",
            agent_id="t02_transcriptomics",
            model_tier="sonnet",
            cost_usd=0.08,
        )

        breakdown = tracker.get_workflow_breakdown("w1_break")
        assert len(breakdown) == 2
        assert breakdown[0]["step_id"] == "SEARCH"
        assert breakdown[1]["step_id"] == "SCREEN"
        print("  PASS: workflow_breakdown")


def test_accuracy_report():
    """Should compare estimated vs actual cost."""
    engine = _setup_db()
    with Session(engine) as session:
        tracker = CostTracker(session)

        tracker.record_actual(
            workflow_id="w1_acc",
            step_id="SEARCH",
            agent_id="knowledge_manager",
            model_tier="sonnet",
            cost_usd=1.20,
        )

        report = tracker.get_accuracy_report("w1_acc", "W1", estimated_cost=1.00)
        assert abs(report.actual_cost - 1.20) < 0.01
        assert abs(report.ratio - 1.20) < 0.01  # actual/estimated = 1.2
        assert len(report.per_step_breakdown) == 1
        print(f"  PASS: accuracy_report (ratio={report.ratio})")


def test_model_tier_summary():
    """Should aggregate costs by model tier."""
    engine = _setup_db()
    with Session(engine) as session:
        tracker = CostTracker(session)

        tracker.record_actual(workflow_id="w1", step_id="S1", agent_id="rd",
                              model_tier="opus", cost_usd=0.80, input_tokens=500, output_tokens=200)
        tracker.record_actual(workflow_id="w1", step_id="S2", agent_id="km",
                              model_tier="sonnet", cost_usd=0.10, input_tokens=1000, output_tokens=300)
        tracker.record_actual(workflow_id="w1", step_id="S3", agent_id="pm",
                              model_tier="haiku", cost_usd=0.02, input_tokens=800, output_tokens=100)

        summary = tracker.get_model_tier_summary()
        assert summary["opus"]["calls"] == 1
        assert abs(summary["opus"]["total_cost"] - 0.80) < 0.01
        assert summary["sonnet"]["calls"] == 1
        assert summary["haiku"]["calls"] == 1
        print("  PASS: model_tier_summary")


def test_session_budget_check():
    """Should enforce session-level budget."""
    engine = _setup_db()
    with Session(engine) as session:
        tracker = CostTracker(session)
        tracker.session_budget = 1.0  # Override for test

        tracker.record_actual(workflow_id="w1", step_id="S1", agent_id="rd",
                              model_tier="opus", cost_usd=0.90)

        # Session has $0.10 left, but requesting $0.20
        assert tracker.check_budget("w2_new", 0.20, "W2") is False
        # But $0.05 should be fine
        assert tracker.check_budget("w2_new", 0.05, "W2") is True
        print("  PASS: session_budget_check")


if __name__ == "__main__":
    print("Testing CostTracker:")
    test_record_and_retrieve()
    test_check_budget_pass()
    test_check_budget_fail()
    test_budget_status()
    test_budget_alert()
    test_workflow_breakdown()
    test_accuracy_report()
    test_model_tier_summary()
    test_session_budget_check()
    print("\nAll CostTracker tests passed!")
