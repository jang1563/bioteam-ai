"""Tests for W11 Story Planning Runner."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.agents.registry import create_registry
from app.llm.mock_layer import MockLLMLayer
from app.models.story_frame import NarrativeType, StoryFrame, StoryFrameSet
from app.models.workflow import WorkflowInstance
from app.workflows.runners.w11_story_planning import (
    W11_STEPS,
    W11StoryPlanningRunner,
    _extract_selected_frame_id,
    _extract_tier_from_notes,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


def _make_runner(llm=None):
    mock_llm = llm or MockLLMLayer({})
    registry = create_registry(mock_llm)
    return W11StoryPlanningRunner(registry=registry)


def _make_instance(phase: str = "awaiting_scope", budget: float = 2.0) -> WorkflowInstance:
    inst = WorkflowInstance(
        template="W11",
        query="spaceflight anemia RNA-seq study",
        budget_total=budget,
        budget_remaining=budget,
        state="WAITING_HUMAN",
        session_manifest={"w11_phase": phase, "query": "spaceflight anemia RNA-seq study"},
    )
    return inst


def _make_frame_set(n: int = 3) -> StoryFrameSet:
    frames = []
    types = [
        NarrativeType.mechanism_discovery,
        NarrativeType.paradigm_challenge,
        NarrativeType.clinical_implication,
        NarrativeType.field_bridge,
        NarrativeType.negative_reframe,
    ]
    for i in range(1, n + 1):
        frames.append(StoryFrame(
            frame_id=f"SF-{i:03d}",
            narrative_type=types[(i - 1) % len(types)],
            hook=f"Hook text for frame {i}.",
            central_tension=f"Tension for frame {i}.",
            core_claim=f"Core claim for frame {i}.",
            supporting_findings=[f"Finding {i}a", f"Finding {i}b"],
            figure_sequence=[f"Fig{i}.1", f"Fig{i}.2"],
            target_tier="specialty",
            novelty_rationale=f"Novelty rationale for frame {i}.",
            blind_spots=[f"Blind spot {i}"],
            impact_score=round(0.9 - (i - 1) * 0.05, 2),
        ))
    return StoryFrameSet(frames=frames, generation_context="spaceflight study", generation_mode="llm")


# ── Step definition tests ────────────────────────────────────────────────────


class TestW11Steps:
    def test_step_count_is_four(self):
        assert len(W11_STEPS) == 4

    def test_step_order(self):
        assert [s.id for s in W11_STEPS] == ["SCOPE", "GENERATE_FRAMES", "HUMAN_CHECKPOINT", "PRESENT"]

    def test_scope_is_human_checkpoint(self):
        scope = next(s for s in W11_STEPS if s.id == "SCOPE")
        assert scope.is_human_checkpoint is True
        assert scope.estimated_cost == 0.0

    def test_human_checkpoint_is_human_checkpoint(self):
        hc = next(s for s in W11_STEPS if s.id == "HUMAN_CHECKPOINT")
        assert hc.is_human_checkpoint is True
        assert hc.estimated_cost == 0.0

    def test_generate_frames_is_code_only(self):
        gf = next(s for s in W11_STEPS if s.id == "GENERATE_FRAMES")
        assert gf.agent_id == "code_only"
        assert gf.estimated_cost > 0  # Opus is expensive

    def test_present_is_code_only_zero_cost(self):
        present = next(s for s in W11_STEPS if s.id == "PRESENT")
        assert present.agent_id == "code_only"
        assert present.estimated_cost == 0.0
        assert present.next_step is None


# ── Helper function tests ─────────────────────────────────────────────────────


class TestExtractTierFromNotes:
    def test_target_tier_key(self):
        notes = [{"text": "target_tier: nature_cell"}]
        assert _extract_tier_from_notes(notes) == "nature_cell"

    def test_tier_key(self):
        notes = [{"text": "tier: specialty"}]
        assert _extract_tier_from_notes(notes) == "specialty"

    def test_grant_tier(self):
        notes = [{"text": "target_tier: grant"}]
        assert _extract_tier_from_notes(notes) == "grant"

    def test_falls_back_to_specialty(self):
        assert _extract_tier_from_notes([]) == "specialty"
        assert _extract_tier_from_notes([{"text": "no tier info here"}]) == "specialty"

    def test_most_recent_note_wins(self):
        notes = [
            {"text": "target_tier: grant"},
            {"text": "target_tier: nature_cell"},
        ]
        # Most recent (last) should win
        assert _extract_tier_from_notes(notes) == "nature_cell"

    def test_case_insensitive(self):
        notes = [{"text": "TARGET_TIER: nature_cell"}]
        assert _extract_tier_from_notes(notes) == "nature_cell"


class TestExtractSelectedFrameId:
    def test_explicit_key_value(self):
        notes = [{"text": "selected_frame_id: SF-002"}]
        assert _extract_selected_frame_id(notes) == "SF-002"

    def test_bare_frame_id(self):
        notes = [{"text": "SF-003"}]
        assert _extract_selected_frame_id(notes) == "SF-003"

    def test_returns_none_when_missing(self):
        assert _extract_selected_frame_id([]) is None
        assert _extract_selected_frame_id([{"text": "no frame here"}]) is None

    def test_most_recent_note_wins(self):
        notes = [
            {"text": "SF-001"},
            {"text": "selected_frame_id: SF-003"},
        ]
        assert _extract_selected_frame_id(notes) == "SF-003"

    def test_case_insensitive_id(self):
        notes = [{"text": "selected_frame_id: sf-002"}]
        result = _extract_selected_frame_id(notes)
        assert result == "SF-002"


# ── run() tests ──────────────────────────────────────────────────────────────


class TestW11Run:
    @pytest.mark.asyncio
    async def test_run_sets_phase_awaiting_scope(self):
        runner = _make_runner()
        result = await runner.run("spaceflight anemia study")
        inst = result["instance"]
        assert inst.session_manifest["w11_phase"] == "awaiting_scope"

    @pytest.mark.asyncio
    async def test_run_pauses_at_scope(self):
        runner = _make_runner()
        result = await runner.run("spaceflight anemia study")
        inst = result["instance"]
        assert inst.state == "WAITING_HUMAN"
        assert result["paused_at"] == "SCOPE"

    @pytest.mark.asyncio
    async def test_run_stores_query_in_manifest(self):
        runner = _make_runner()
        query = "HIF-1a spaceflight anemia study"
        result = await runner.run(query)
        inst = result["instance"]
        assert inst.session_manifest["query"] == query

    @pytest.mark.asyncio
    async def test_run_stores_scope_summary(self):
        runner = _make_runner()
        result = await runner.run("test query")
        inst = result["instance"]
        assert "scope_summary" in inst.session_manifest

    @pytest.mark.asyncio
    async def test_run_uses_custom_instance(self):
        runner = _make_runner()
        inst = WorkflowInstance(template="W11", budget_total=5.0, budget_remaining=5.0)
        result = await runner.run("test", instance=inst)
        assert result["instance"] is inst


# ── resume_after_human() from SCOPE phase ────────────────────────────────────


class TestW11ResumeFromScope:
    def _make_runner_with_mock_llm(self, frame_set: StoryFrameSet):
        mock_llm = MockLLMLayer({})
        registry = create_registry(mock_llm)
        runner = W11StoryPlanningRunner(registry=registry)
        # Patch _generate_frames to return our frame_set
        runner._generate_frames = AsyncMock(return_value=frame_set)
        return runner

    @pytest.mark.asyncio
    async def test_resume_scope_generates_frames(self):
        frame_set = _make_frame_set(3)
        runner = self._make_runner_with_mock_llm(frame_set)
        inst = _make_instance("awaiting_scope")
        inst.state = "RUNNING"

        result = await runner.resume_after_human(inst, "spaceflight anemia")

        assert "paused_at" in result
        assert result["paused_at"] == "HUMAN_CHECKPOINT"
        runner._generate_frames.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resume_scope_stores_frame_options(self):
        frame_set = _make_frame_set(3)
        runner = self._make_runner_with_mock_llm(frame_set)
        inst = _make_instance("awaiting_scope")
        inst.state = "RUNNING"

        await runner.resume_after_human(inst, "test")

        assert "frame_options" in inst.session_manifest
        stored = inst.session_manifest["frame_options"]
        assert len(stored["frames"]) == 3
        assert stored["generation_mode"] == "llm"

    @pytest.mark.asyncio
    async def test_resume_scope_updates_phase_to_awaiting_selection(self):
        frame_set = _make_frame_set(2)
        runner = self._make_runner_with_mock_llm(frame_set)
        inst = _make_instance("awaiting_scope")
        inst.state = "RUNNING"

        await runner.resume_after_human(inst, "test")

        assert inst.session_manifest["w11_phase"] == "awaiting_selection"

    @pytest.mark.asyncio
    async def test_resume_scope_fires_second_hc(self):
        frame_set = _make_frame_set(2)
        runner = self._make_runner_with_mock_llm(frame_set)
        inst = _make_instance("awaiting_scope")
        inst.state = "RUNNING"

        await runner.resume_after_human(inst, "test")

        assert inst.state == "WAITING_HUMAN"

    @pytest.mark.asyncio
    async def test_resume_scope_extracts_tier_from_notes(self):
        frame_set = _make_frame_set(1)
        runner = self._make_runner_with_mock_llm(frame_set)
        inst = _make_instance("awaiting_scope")
        inst.state = "RUNNING"
        inst.injected_notes = [{"text": "target_tier: nature_cell"}]

        await runner.resume_after_human(inst, "test")

        assert inst.session_manifest.get("target_tier") == "nature_cell"


# ── resume_after_human() from HUMAN_CHECKPOINT phase ─────────────────────────


class TestW11ResumeFromSelection:
    def _setup(self, frame_set: StoryFrameSet, selected_note: str = "SF-002") -> tuple:
        runner = _make_runner()
        inst = _make_instance("awaiting_selection")
        inst.state = "RUNNING"
        inst.session_manifest["frame_options"] = frame_set.model_dump(mode="json")
        inst.injected_notes = [{"text": f"selected_frame_id: {selected_note}"}]
        return runner, inst

    @pytest.mark.asyncio
    async def test_resume_selection_completes_workflow(self):
        frame_set = _make_frame_set(3)
        runner, inst = self._setup(frame_set, "SF-002")
        result = await runner.resume_after_human(inst, "test")

        assert result.get("completed") is True
        assert inst.state == "COMPLETED"

    @pytest.mark.asyncio
    async def test_resume_selection_stores_selected_frame(self):
        frame_set = _make_frame_set(3)
        runner, inst = self._setup(frame_set, "SF-002")
        await runner.resume_after_human(inst, "test")

        assert "selected_story_frame" in inst.session_manifest
        sf = inst.session_manifest["selected_story_frame"]
        assert sf["frame_id"] == "SF-002"

    @pytest.mark.asyncio
    async def test_resume_selection_invalid_frame_stays_at_checkpoint(self):
        frame_set = _make_frame_set(3)
        runner = _make_runner()
        inst = _make_instance("awaiting_selection")
        inst.state = "RUNNING"
        inst.session_manifest["frame_options"] = frame_set.model_dump(mode="json")
        inst.injected_notes = [{"text": "selected_frame_id: SF-999"}]  # Invalid

        result = await runner.resume_after_human(inst, "test")

        assert result.get("completed") is False
        assert inst.state == "WAITING_HUMAN"
        assert "selected_story_frame" not in inst.session_manifest
        assert inst.session_manifest["selection_error"] == "Invalid story frame selection: SF-999"

    @pytest.mark.asyncio
    async def test_resume_selection_sets_phase_complete(self):
        frame_set = _make_frame_set(2)
        runner, inst = self._setup(frame_set, "SF-001")
        await runner.resume_after_human(inst, "test")

        assert inst.session_manifest["w11_phase"] == "complete"

    @pytest.mark.asyncio
    async def test_resume_selection_returns_correct_frame_id(self):
        frame_set = _make_frame_set(3)
        runner, inst = self._setup(frame_set, "SF-003")
        result = await runner.resume_after_human(inst, "test")

        assert result.get("selected_frame_id") == "SF-003"


# ── Unknown phase handling ────────────────────────────────────────────────────


class TestW11UnknownPhase:
    @pytest.mark.asyncio
    async def test_unknown_phase_returns_error(self):
        runner = _make_runner()
        inst = _make_instance("totally_wrong_phase")
        inst.state = "RUNNING"

        result = await runner.resume_after_human(inst, "test")

        assert "error" in result
        assert result.get("completed") is False


# ── LLM fallback ─────────────────────────────────────────────────────────────


class TestW11LLMFallback:
    @pytest.mark.asyncio
    async def test_no_llm_returns_synthetic_frames(self):
        runner = _make_runner()
        # Simulate no LLM available
        runner._get_llm = MagicMock(return_value=None)

        inst = WorkflowInstance(
            template="W11", budget_total=2.0, budget_remaining=2.0,
            session_manifest={"w11_phase": "awaiting_scope", "query": "test"},
        )
        inst.state = "RUNNING"

        result = await runner.resume_after_human(inst, "test query")

        # Should still generate a synthetic fallback and pause at HC
        assert result.get("paused_at") == "HUMAN_CHECKPOINT"
        assert "frame_options" in inst.session_manifest
        frame_options = inst.session_manifest["frame_options"]
        frames = frame_options["frames"]
        assert len(frames) >= 1
        assert frame_options["generation_mode"] == "synthetic_fallback"
        assert frame_options["fallback_reason"] == "LLM unavailable"
        assert frames[0]["provenance"] == "synthetic_fallback"
