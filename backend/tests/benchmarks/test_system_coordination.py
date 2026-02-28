"""System-level tests: Agent registry, workflow state machine, budget, loops, Director notes.

Tests cross-workflow coordination and infrastructure that all pipelines depend on.
No LLM calls — purely tests the orchestration layer.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.registry import create_registry
from app.llm.mock_layer import MockLLMLayer
from app.models.messages import ContextPackage
from app.models.workflow import WorkflowInstance
from app.workflows.engine import IllegalTransitionError, WorkflowEngine
from app.workflows.note_processor import NoteProcessor
from app.workflows.runners.w1_literature import W1_STEPS
from app.workflows.runners.w7_integrity import W7_STEPS

# ══════════════════════════════════════════════════════════════════
# Agent Registry
# ══════════════════════════════════════════════════════════════════


class TestAgentRegistrySystem:
    """Verify all agents register and substitution logic works."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.registry = create_registry(MockLLMLayer())

    def test_all_agents_registered(self):
        specs = self.registry.list_agents()
        expected = self.registry._expected_count
        assert len(specs) == expected, f"Expected {expected} agents, got {len(specs)}"

    def test_critical_agents_healthy(self):
        unhealthy = self.registry.check_critical_health()
        assert unhealthy == [], f"Critical agents unhealthy at startup: {unhealthy}"

    def test_substitution_t01_t02(self):
        sub = self.registry.find_substitute("t01_genomics")
        assert sub == "t02_transcriptomics"

    def test_substitution_t03_t02(self):
        sub = self.registry.find_substitute("t03_proteomics")
        assert sub == "t02_transcriptomics"

    def test_substitution_t04_t05(self):
        sub = self.registry.find_substitute("t04_biostatistics")
        assert sub == "t05_ml_dl"

    def test_substitution_t06_integrative(self):
        sub = self.registry.find_substitute("t06_systems_bio")
        assert sub == "integrative_biologist"

    def test_no_substitute_scicomm(self):
        sub = self.registry.find_substitute("t08_scicomm")
        assert sub is None

    def test_no_substitute_structural(self):
        sub = self.registry.find_substitute("t07_structural_bio")
        assert sub is None

    def test_agent_availability(self):
        assert self.registry.is_available("research_director")
        assert self.registry.is_available("knowledge_manager")
        assert not self.registry.is_available("nonexistent_agent")

    def test_mark_unavailable(self):
        self.registry.mark_unavailable("t10_data_eng")
        assert not self.registry.is_available("t10_data_eng")

    def test_unavailable_critical_detected(self):
        self.registry.mark_unavailable("research_director")
        unhealthy = self.registry.check_critical_health()
        assert "research_director" in unhealthy


# ══════════════════════════════════════════════════════════════════
# Workflow State Machine
# ══════════════════════════════════════════════════════════════════


class TestWorkflowStateMachine:
    """Verify all legal/illegal transitions in the WorkflowEngine."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.engine = WorkflowEngine()

    def _make_instance(self, state: str = "PENDING") -> WorkflowInstance:
        inst = WorkflowInstance(template="W1")
        inst.state = state
        return inst

    def test_legal_full_lifecycle(self):
        inst = self._make_instance("PENDING")
        self.engine.start(inst)
        assert inst.state == "RUNNING"

        self.engine.request_human(inst)
        assert inst.state == "WAITING_HUMAN"

        self.engine.resume(inst)
        assert inst.state == "RUNNING"

        self.engine.complete(inst)
        assert inst.state == "COMPLETED"

    def test_illegal_from_completed(self):
        inst = self._make_instance("COMPLETED")
        with pytest.raises(IllegalTransitionError):
            self.engine.transition(inst, "RUNNING")

    def test_illegal_from_cancelled(self):
        inst = self._make_instance("CANCELLED")
        with pytest.raises(IllegalTransitionError):
            self.engine.transition(inst, "RUNNING")

    def test_over_budget_cycle(self):
        inst = self._make_instance("RUNNING")
        self.engine.mark_over_budget(inst)
        assert inst.state == "OVER_BUDGET"

        self.engine.resume(inst)
        assert inst.state == "RUNNING"

    def test_pause_resume(self):
        inst = self._make_instance("RUNNING")
        self.engine.pause(inst)
        assert inst.state == "PAUSED"

        self.engine.resume(inst)
        assert inst.state == "RUNNING"

    def test_fail_retry(self):
        inst = self._make_instance("RUNNING")
        self.engine.fail(inst)
        assert inst.state == "FAILED"

        self.engine.transition(inst, "RUNNING")
        assert inst.state == "RUNNING"

    def test_cancel_from_running(self):
        inst = self._make_instance("RUNNING")
        self.engine.cancel(inst)
        assert inst.state == "CANCELLED"

    def test_illegal_pending_to_completed(self):
        inst = self._make_instance("PENDING")
        with pytest.raises(IllegalTransitionError):
            self.engine.transition(inst, "COMPLETED")

    def test_can_transition_check(self):
        assert self.engine.can_transition("PENDING", "RUNNING")
        assert not self.engine.can_transition("COMPLETED", "RUNNING")
        assert not self.engine.can_transition("PENDING", "COMPLETED")

    def test_get_valid_transitions(self):
        valid = self.engine.get_valid_transitions("RUNNING")
        assert "COMPLETED" in valid
        assert "FAILED" in valid
        assert "PAUSED" in valid

        assert self.engine.get_valid_transitions("COMPLETED") == []


# ══════════════════════════════════════════════════════════════════
# Budget Enforcement
# ══════════════════════════════════════════════════════════════════


class TestBudgetEnforcement:
    """Verify budget checks and deductions."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.engine = WorkflowEngine()

    def test_sufficient_budget(self):
        inst = WorkflowInstance(template="W1", budget_remaining=5.0)
        assert self.engine.check_budget(inst, 1.0)

    def test_insufficient_budget(self):
        inst = WorkflowInstance(template="W1", budget_remaining=5.0)
        assert not self.engine.check_budget(inst, 6.0)

    def test_exact_budget(self):
        inst = WorkflowInstance(template="W1", budget_remaining=5.0)
        assert self.engine.check_budget(inst, 5.0)

    def test_deduct_budget(self):
        inst = WorkflowInstance(template="W1", budget_remaining=5.0)
        remaining = self.engine.deduct_budget(inst, 2.0)
        assert remaining == pytest.approx(3.0)
        assert inst.budget_remaining == pytest.approx(3.0)

    def test_budget_floor_zero(self):
        inst = WorkflowInstance(template="W1", budget_remaining=5.0)
        remaining = self.engine.deduct_budget(inst, 999.0)
        assert remaining == 0.0
        assert inst.budget_remaining == 0.0


# ══════════════════════════════════════════════════════════════════
# Loop Detection
# ══════════════════════════════════════════════════════════════════


class TestLoopDetection:
    """Verify loop counters and max-loop enforcement."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.engine = WorkflowEngine()

    def test_within_limit(self):
        inst = WorkflowInstance(template="W1", max_loops=3)
        assert self.engine.check_loop(inst, "REFINE")

    def test_at_limit(self):
        inst = WorkflowInstance(template="W1", max_loops=3)
        inst.loop_count = {"REFINE": 3}
        assert not self.engine.check_loop(inst, "REFINE")

    def test_increment(self):
        inst = WorkflowInstance(template="W1", max_loops=3)
        count = self.engine.increment_loop(inst, "REFINE")
        assert count == 1
        count = self.engine.increment_loop(inst, "REFINE")
        assert count == 2

    def test_multiple_steps(self):
        inst = WorkflowInstance(template="W1", max_loops=3)
        self.engine.increment_loop(inst, "STEP_A")
        self.engine.increment_loop(inst, "STEP_B")
        assert inst.loop_count["STEP_A"] == 1
        assert inst.loop_count["STEP_B"] == 1


# ══════════════════════════════════════════════════════════════════
# Director Notes
# ══════════════════════════════════════════════════════════════════


class TestDirectorNotes:
    """Verify NoteProcessor applies all action types correctly."""

    def _make_instance_with_notes(self, notes: list[dict]) -> WorkflowInstance:
        inst = WorkflowInstance(template="W1")
        inst.injected_notes = notes
        return inst

    def test_add_paper_note(self):
        inst = self._make_instance_with_notes([
            {"action": "ADD_PAPER", "text": "", "metadata": {"doi": "10.1234/test"}, "target_step": "SEARCH"},
        ])
        pending = NoteProcessor.get_pending_notes(inst, "SEARCH")
        assert len(pending) == 1

        context = ContextPackage(task_description="test query")
        new_ctx = NoteProcessor.apply_to_context(pending, context)
        assert "seed_papers" in new_ctx.constraints
        assert "10.1234/test" in new_ctx.constraints["seed_papers"]

    def test_exclude_paper_note(self):
        inst = self._make_instance_with_notes([
            {"action": "EXCLUDE_PAPER", "text": "", "metadata": {"doi": "10.5678/bad"}, "target_step": "SCREEN"},
        ])
        pending = NoteProcessor.get_pending_notes(inst, "SCREEN")
        context = ContextPackage(task_description="test")
        new_ctx = NoteProcessor.apply_to_context(pending, context)
        assert "excluded_dois" in new_ctx.constraints
        assert "10.5678/bad" in new_ctx.constraints["excluded_dois"]

    def test_modify_query_note(self):
        inst = self._make_instance_with_notes([
            {"action": "MODIFY_QUERY", "text": "new research question", "metadata": {}, "target_step": "SCOPE"},
        ])
        pending = NoteProcessor.get_pending_notes(inst, "SCOPE")
        context = ContextPackage(task_description="original query")
        new_ctx = NoteProcessor.apply_to_context(pending, context)
        assert new_ctx.task_description == "new research question"

    def test_edit_text_note(self):
        inst = self._make_instance_with_notes([
            {"action": "EDIT_TEXT", "text": "revise paragraph 2", "metadata": {}, "target_step": None},
        ])
        pending = NoteProcessor.get_pending_notes(inst, "SYNTHESIZE")
        assert len(pending) == 1  # target_step=None matches any step

        context = ContextPackage(task_description="test")
        new_ctx = NoteProcessor.apply_to_context(pending, context)
        revision = [o for o in new_ctx.prior_step_outputs if o.get("type") == "director_revision_instruction"]
        assert len(revision) == 1
        assert revision[0]["instruction"] == "revise paragraph 2"

    def test_free_text_note(self):
        inst = self._make_instance_with_notes([
            {"action": "FREE_TEXT", "text": "consider cfRNA data", "metadata": {}, "target_step": None},
        ])
        pending = NoteProcessor.get_pending_notes(inst, "EXTRACT")
        context = ContextPackage(task_description="test")
        new_ctx = NoteProcessor.apply_to_context(pending, context)
        director_notes = [o for o in new_ctx.prior_step_outputs if o.get("type") == "director_note"]
        assert len(director_notes) == 1

    def test_processed_marking(self):
        inst = self._make_instance_with_notes([
            {"action": "FREE_TEXT", "text": "note 1", "metadata": {}, "target_step": "SCOPE"},
            {"action": "FREE_TEXT", "text": "note 2", "metadata": {}, "target_step": "SCOPE"},
        ])
        pending = NoteProcessor.get_pending_notes(inst, "SCOPE")
        assert len(pending) == 2

        NoteProcessor.mark_processed(inst, [n["_index"] for n in pending])

        # After marking, get_pending_notes should return empty
        pending_after = NoteProcessor.get_pending_notes(inst, "SCOPE")
        assert len(pending_after) == 0

        # Verify processed_at timestamp exists
        for note in inst.injected_notes:
            assert "processed_at" in note

    def test_skip_already_processed(self):
        inst = self._make_instance_with_notes([
            {"action": "FREE_TEXT", "text": "done", "metadata": {}, "target_step": "SCOPE",
             "processed_at": "2025-01-01T00:00:00"},
        ])
        pending = NoteProcessor.get_pending_notes(inst, "SCOPE")
        assert len(pending) == 0


# ══════════════════════════════════════════════════════════════════
# Cost Estimate Sanity
# ══════════════════════════════════════════════════════════════════


class TestCostEstimateSanity:
    """Verify step cost estimates are reasonable and within budget caps."""

    def test_w1_estimates_under_budget(self):
        total = sum(s.estimated_cost for s in W1_STEPS)
        assert total < 5.0, f"W1 total estimated cost {total:.3f} exceeds $5.00 budget"

    def test_w7_estimates_under_budget(self):
        total = sum(s.estimated_cost for s in W7_STEPS)
        assert total < 3.0, f"W7 total estimated cost {total:.3f} exceeds $3.00 budget"

    def test_code_only_zero_cost_w1(self):
        code_steps = [s for s in W1_STEPS if s.agent_id == "code_only"]
        for step in code_steps:
            assert step.estimated_cost == 0.0, f"W1 {step.id} code_only has cost {step.estimated_cost}"

    def test_code_only_zero_cost_w7(self):
        code_steps = [s for s in W7_STEPS if s.agent_id == "code_only"]
        for step in code_steps:
            assert step.estimated_cost == 0.0, f"W7 {step.id} code_only has cost {step.estimated_cost}"

    def test_llm_steps_nonzero_w1(self):
        llm_steps = [s for s in W1_STEPS if s.agent_id != "code_only"]
        for step in llm_steps:
            assert step.estimated_cost > 0, f"W1 LLM step {step.id} has zero cost"

    def test_llm_steps_nonzero_w7(self):
        llm_steps = [s for s in W7_STEPS if s.agent_id != "code_only"]
        for step in llm_steps:
            assert step.estimated_cost > 0, f"W7 LLM step {step.id} has zero cost"

    def test_w1_step_count(self):
        assert len(W1_STEPS) == 12

    def test_w7_step_count(self):
        assert len(W7_STEPS) == 8
