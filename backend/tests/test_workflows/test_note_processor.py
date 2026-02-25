"""Tests for NoteProcessor — centralized note processing for workflow runners."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from datetime import datetime, timezone

from app.models.messages import ContextPackage
from app.models.workflow import WorkflowInstance
from app.workflows.note_processor import NoteProcessor


def _make_instance(**kwargs) -> WorkflowInstance:
    return WorkflowInstance(template="W1", **kwargs)


def _make_context(task: str = "test query") -> ContextPackage:
    return ContextPackage(task_description=task)


# --- get_pending_notes ---


def test_get_pending_no_notes():
    """Instance with no injected notes returns empty list."""
    inst = _make_instance()
    assert NoteProcessor.get_pending_notes(inst, "SEARCH") == []


def test_get_pending_targeted_note():
    """Note targeting a specific step is returned for that step."""
    inst = _make_instance(injected_notes=[
        {"text": "Add paper X", "action": "ADD_PAPER", "target_step": "SEARCH"},
    ])
    pending = NoteProcessor.get_pending_notes(inst, "SEARCH")
    assert len(pending) == 1
    assert pending[0]["text"] == "Add paper X"
    assert pending[0]["_index"] == 0


def test_get_pending_untargeted_note():
    """Note with target_step=None applies to any step."""
    inst = _make_instance(injected_notes=[
        {"text": "General note", "action": "FREE_TEXT", "target_step": None},
    ])
    pending = NoteProcessor.get_pending_notes(inst, "SYNTHESIZE")
    assert len(pending) == 1
    assert pending[0]["text"] == "General note"


def test_get_pending_skips_processed():
    """Already-processed notes are not returned."""
    inst = _make_instance(injected_notes=[
        {"text": "Old note", "action": "FREE_TEXT", "processed_at": "2024-01-01T00:00:00"},
        {"text": "New note", "action": "FREE_TEXT", "target_step": None},
    ])
    pending = NoteProcessor.get_pending_notes(inst, "SEARCH")
    assert len(pending) == 1
    assert pending[0]["text"] == "New note"
    assert pending[0]["_index"] == 1


def test_get_pending_wrong_step():
    """Note targeting a different step is not returned."""
    inst = _make_instance(injected_notes=[
        {"text": "For search only", "action": "ADD_PAPER", "target_step": "SEARCH"},
    ])
    pending = NoteProcessor.get_pending_notes(inst, "SYNTHESIZE")
    assert len(pending) == 0


# --- apply_to_context ---


def test_apply_add_paper():
    """ADD_PAPER action adds DOI to seed_papers constraint."""
    context = _make_context()
    notes = [{"action": "ADD_PAPER", "text": "10.1234/test", "metadata": {"doi": "10.1234/test"}, "_index": 0}]
    new_ctx = NoteProcessor.apply_to_context(notes, context)
    assert "10.1234/test" in new_ctx.constraints.get("seed_papers", [])
    # Original context unchanged
    assert "seed_papers" not in context.constraints


def test_apply_exclude_paper():
    """EXCLUDE_PAPER action adds DOI to excluded_dois constraint."""
    context = _make_context()
    notes = [{"action": "EXCLUDE_PAPER", "text": "10.5678/bad", "metadata": {"doi": "10.5678/bad"}, "_index": 0}]
    new_ctx = NoteProcessor.apply_to_context(notes, context)
    assert "10.5678/bad" in new_ctx.constraints.get("excluded_dois", [])


def test_apply_modify_query():
    """MODIFY_QUERY action overrides task_description."""
    context = _make_context("original query")
    notes = [{"action": "MODIFY_QUERY", "text": "new query about X", "metadata": {}, "_index": 0}]
    new_ctx = NoteProcessor.apply_to_context(notes, context)
    assert new_ctx.task_description == "new query about X"
    assert context.task_description == "original query"


def test_apply_edit_text():
    """EDIT_TEXT action injects revision instruction into prior_step_outputs."""
    context = _make_context()
    notes = [{"action": "EDIT_TEXT", "text": "Please revise the conclusion", "metadata": {}, "_index": 0}]
    new_ctx = NoteProcessor.apply_to_context(notes, context)
    assert len(new_ctx.prior_step_outputs) == 1
    assert new_ctx.prior_step_outputs[0]["type"] == "director_revision_instruction"
    assert "revise the conclusion" in new_ctx.prior_step_outputs[0]["instruction"]


def test_apply_free_text():
    """FREE_TEXT action injects director context."""
    context = _make_context()
    notes = [{"action": "FREE_TEXT", "text": "Focus on human subjects", "metadata": {}, "_index": 0}]
    new_ctx = NoteProcessor.apply_to_context(notes, context)
    assert len(new_ctx.prior_step_outputs) == 1
    assert new_ctx.prior_step_outputs[0]["type"] == "director_note"
    assert "human subjects" in new_ctx.prior_step_outputs[0]["content"]


def test_apply_unknown_action_fallback():
    """Unknown action falls back to FREE_TEXT behavior."""
    context = _make_context()
    notes = [{"action": "UNKNOWN_ACTION", "text": "Some text", "metadata": {}, "_index": 0}]
    new_ctx = NoteProcessor.apply_to_context(notes, context)
    assert len(new_ctx.prior_step_outputs) == 1
    assert new_ctx.prior_step_outputs[0]["type"] == "director_note"


def test_apply_multiple_notes():
    """Multiple notes are applied in order."""
    context = _make_context()
    notes = [
        {"action": "ADD_PAPER", "text": "", "metadata": {"doi": "10.1/a"}, "_index": 0},
        {"action": "ADD_PAPER", "text": "", "metadata": {"doi": "10.1/b"}, "_index": 1},
        {"action": "FREE_TEXT", "text": "Extra context", "metadata": {}, "_index": 2},
    ]
    new_ctx = NoteProcessor.apply_to_context(notes, context)
    assert new_ctx.constraints["seed_papers"] == ["10.1/a", "10.1/b"]
    assert len(new_ctx.prior_step_outputs) == 1


def test_apply_preserves_existing_constraints():
    """Existing constraints are preserved alongside new ones."""
    context = ContextPackage(
        task_description="test",
        constraints={"workflow_id": "w-123", "budget_remaining": 3.0},
    )
    notes = [{"action": "ADD_PAPER", "text": "", "metadata": {"doi": "10.1/x"}, "_index": 0}]
    new_ctx = NoteProcessor.apply_to_context(notes, context)
    assert new_ctx.constraints["workflow_id"] == "w-123"
    assert new_ctx.constraints["budget_remaining"] == 3.0
    assert "10.1/x" in new_ctx.constraints["seed_papers"]


# --- mark_processed ---


def test_mark_processed():
    """mark_processed adds processed_at timestamp to specified notes."""
    inst = _make_instance(injected_notes=[
        {"text": "Note A", "action": "FREE_TEXT"},
        {"text": "Note B", "action": "ADD_PAPER"},
        {"text": "Note C", "action": "FREE_TEXT"},
    ])
    NoteProcessor.mark_processed(inst, [0, 2])
    assert "processed_at" in inst.injected_notes[0]
    assert "processed_at" not in inst.injected_notes[1]
    assert "processed_at" in inst.injected_notes[2]


def test_mark_processed_out_of_range():
    """Out-of-range indices are silently ignored."""
    inst = _make_instance(injected_notes=[
        {"text": "Note A", "action": "FREE_TEXT"},
    ])
    NoteProcessor.mark_processed(inst, [0, 5, -1])
    assert "processed_at" in inst.injected_notes[0]


def test_add_paper_deduplicates():
    """ADD_PAPER does not add duplicate DOIs."""
    context = ContextPackage(
        task_description="test",
        constraints={"seed_papers": ["10.1/existing"]},
    )
    notes = [
        {"action": "ADD_PAPER", "text": "", "metadata": {"doi": "10.1/existing"}, "_index": 0},
        {"action": "ADD_PAPER", "text": "", "metadata": {"doi": "10.1/new"}, "_index": 1},
    ]
    new_ctx = NoteProcessor.apply_to_context(notes, context)
    assert new_ctx.constraints["seed_papers"] == ["10.1/existing", "10.1/new"]


if __name__ == "__main__":
    print("Testing NoteProcessor:")
    test_get_pending_no_notes()
    test_get_pending_targeted_note()
    test_get_pending_untargeted_note()
    test_get_pending_skips_processed()
    test_get_pending_wrong_step()
    test_apply_add_paper()
    test_apply_exclude_paper()
    test_apply_modify_query()
    test_apply_edit_text()
    test_apply_free_text()
    test_apply_unknown_action_fallback()
    test_apply_multiple_notes()
    test_apply_preserves_existing_constraints()
    test_mark_processed()
    test_mark_processed_out_of_range()
    test_add_paper_deduplicates()
    print("\nAll NoteProcessor tests passed!")
