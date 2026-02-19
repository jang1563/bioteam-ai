"""Tests for workflow SQLite persistence (C2)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from sqlmodel import Session, select

from app.db.database import engine, create_db_and_tables
from app.models.workflow import WorkflowInstance
from app.api.v1.workflows import _save_instance, _get_instance


def setup_module():
    """Create tables before tests."""
    create_db_and_tables()


def test_save_and_load_instance():
    """Should persist and load a WorkflowInstance from SQLite."""
    instance = WorkflowInstance(
        template="W1",
        budget_total=5.0,
        budget_remaining=5.0,
    )
    _save_instance(instance)

    loaded = _get_instance(instance.id)
    assert loaded.id == instance.id
    assert loaded.template == "W1"
    assert loaded.budget_total == 5.0
    assert loaded.state == "PENDING"


def test_save_updates_existing():
    """Saving the same instance twice should update, not duplicate."""
    instance = WorkflowInstance(
        template="W1",
        budget_total=5.0,
        budget_remaining=5.0,
    )
    _save_instance(instance)

    # Modify and save again
    instance.state = "RUNNING"
    instance.budget_remaining = 3.5
    _save_instance(instance)

    loaded = _get_instance(instance.id)
    assert loaded.state == "RUNNING"
    assert loaded.budget_remaining == 3.5

    # Verify no duplicate
    with Session(engine) as session:
        results = session.exec(
            select(WorkflowInstance).where(WorkflowInstance.id == instance.id)
        ).all()
        assert len(results) == 1


def test_get_nonexistent_returns_404():
    """Getting a nonexistent workflow should raise HTTPException 404."""
    from fastapi import HTTPException
    try:
        _get_instance("nonexistent-id")
        assert False, "Should have raised"
    except HTTPException as e:
        assert e.status_code == 404


def test_json_fields_round_trip():
    """JSON fields (step_history, loop_count, etc.) should survive persistence."""
    instance = WorkflowInstance(
        template="W1",
        budget_total=5.0,
        budget_remaining=5.0,
        step_history=[{"step_id": "SCOPE", "result": "ok"}],
        loop_count={"SEARCH": 2},
        injected_notes=[{"text": "focus on human", "action": "FREE_TEXT"}],
        seed_papers=["doi:10.1234/test"],
    )
    _save_instance(instance)

    loaded = _get_instance(instance.id)
    assert loaded.step_history == [{"step_id": "SCOPE", "result": "ok"}]
    assert loaded.loop_count == {"SEARCH": 2}
    assert len(loaded.injected_notes) == 1
    assert loaded.seed_papers == ["doi:10.1234/test"]


if __name__ == "__main__":
    print("Testing Workflow Persistence:")
    setup_module()
    test_save_and_load_instance()
    test_save_updates_existing()
    test_get_nonexistent_returns_404()
    test_json_fields_round_trip()
    print("\nAll Workflow Persistence tests passed!")
