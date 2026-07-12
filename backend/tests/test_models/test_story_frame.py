"""Tests for story frame Pydantic models (W11 narrative planning)."""

from __future__ import annotations

import pytest
from app.models.story_frame import (
    NarrativeDriftReport,
    NarrativeType,
    StoryFrame,
    StoryFrameSet,
)
from pydantic import ValidationError

# ── Fixtures ────────────────────────────────────────────────────────────────


def _make_frame(
    frame_id: str = "SF-001",
    narrative_type: NarrativeType = NarrativeType.mechanism_discovery,
    impact_score: float = 0.85,
) -> StoryFrame:
    return StoryFrame(
        frame_id=frame_id,
        narrative_type=narrative_type,
        hook="Spaceflight induces a reversible anemia by suppressing erythropoiesis.",
        central_tension="Expected radiation damage; found hypoxia-like response instead.",
        core_claim="Microgravity, not radiation, drives spaceflight anemia via HIF-1α.",
        supporting_findings=["RNA-seq: HIF-1α pathway upregulated 3×", "RBC count -40%"],
        figure_sequence=["Fig1: RBC timeline", "Fig2: HIF heatmap", "Fig3: pathway diagram"],
        target_tier="nature_cell",
        novelty_rationale="First mechanistic link between microgravity and HIF in human astronauts.",
        blind_spots=["Radiation contribution not ruled out", "n=10 only"],
        impact_score=impact_score,
    )


# ── NarrativeType tests ──────────────────────────────────────────────────────


class TestNarrativeType:
    def test_all_six_types_exist(self):
        expected = {
            "mechanism_discovery",
            "paradigm_challenge",
            "clinical_implication",
            "field_bridge",
            "negative_reframe",
            "method_breakthrough",
        }
        actual = {t.value for t in NarrativeType}
        assert actual == expected

    def test_str_subclass(self):
        assert isinstance(NarrativeType.mechanism_discovery, str)
        assert NarrativeType.mechanism_discovery == "mechanism_discovery"

    def test_invalid_type_raises(self):
        with pytest.raises(ValidationError):
            StoryFrame(
                frame_id="SF-000",
                narrative_type="not_a_valid_type",  # type: ignore[arg-type]
                hook="h",
                central_tension="t",
                core_claim="c",
                supporting_findings=[],
                figure_sequence=[],
                target_tier="specialty",
                novelty_rationale="n",
                blind_spots=[],
                impact_score=0.5,
            )


# ── StoryFrame tests ─────────────────────────────────────────────────────────


class TestStoryFrame:
    def test_valid_frame_creates_successfully(self):
        frame = _make_frame()
        assert frame.frame_id == "SF-001"
        assert frame.narrative_type == NarrativeType.mechanism_discovery
        assert frame.version == 1

    def test_default_version_is_one(self):
        frame = _make_frame()
        assert frame.version == 1

    def test_version_can_be_set(self):
        frame = _make_frame()
        updated = frame.model_copy(update={"version": 2})
        assert updated.version == 2

    def test_impact_score_bounds_lower(self):
        with pytest.raises(ValidationError):
            _make_frame(impact_score=-0.1)

    def test_impact_score_bounds_upper(self):
        with pytest.raises(ValidationError):
            _make_frame(impact_score=1.1)

    def test_impact_score_boundary_values(self):
        frame_min = _make_frame(impact_score=0.0)
        frame_max = _make_frame(impact_score=1.0)
        assert frame_min.impact_score == 0.0
        assert frame_max.impact_score == 1.0

    def test_all_narrative_types_accepted(self):
        for nt in NarrativeType:
            frame = _make_frame(frame_id=f"SF-{nt.value}", narrative_type=nt)
            assert frame.narrative_type == nt

    def test_supporting_findings_empty_list_allowed(self):
        frame = StoryFrame(
            frame_id="SF-002",
            narrative_type=NarrativeType.negative_reframe,
            hook="h",
            central_tension="t",
            core_claim="c",
            supporting_findings=[],
            figure_sequence=[],
            target_tier="grant",
            novelty_rationale="n",
            blind_spots=[],
            impact_score=0.6,
        )
        assert frame.supporting_findings == []

    def test_model_dump_roundtrip(self):
        frame = _make_frame()
        data = frame.model_dump()
        restored = StoryFrame(**data)
        assert restored.frame_id == frame.frame_id
        assert restored.narrative_type == frame.narrative_type
        assert restored.impact_score == frame.impact_score

    def test_model_dump_mode_json(self):
        frame = _make_frame()
        data = frame.model_dump(mode="json")
        # NarrativeType should serialize as string
        assert isinstance(data["narrative_type"], str)
        assert data["narrative_type"] == "mechanism_discovery"


# ── StoryFrameSet tests ──────────────────────────────────────────────────────


class TestStoryFrameSet:
    def test_valid_set_with_multiple_frames(self):
        frames = [
            _make_frame("SF-001", NarrativeType.mechanism_discovery, 0.9),
            _make_frame("SF-002", NarrativeType.paradigm_challenge, 0.85),
            _make_frame("SF-003", NarrativeType.field_bridge, 0.75),
        ]
        fset = StoryFrameSet(frames=frames)
        assert len(fset.frames) == 3
        assert fset.selected_frame_id is None
        assert fset.generation_context == ""

    def test_selected_frame_id_can_be_set(self):
        fset = StoryFrameSet(
            frames=[_make_frame()],
            selected_frame_id="SF-001",
        )
        assert fset.selected_frame_id == "SF-001"

    def test_generation_context_stored(self):
        fset = StoryFrameSet(
            frames=[_make_frame()],
            generation_context="Spaceflight RNA-seq study, n=10 astronauts",
        )
        assert "RNA-seq" in fset.generation_context

    def test_model_dump_roundtrip(self):
        frames = [_make_frame("SF-001"), _make_frame("SF-002", NarrativeType.clinical_implication)]
        fset = StoryFrameSet(frames=frames, selected_frame_id="SF-001")
        data = fset.model_dump()
        restored = StoryFrameSet(**data)
        assert len(restored.frames) == 2
        assert restored.selected_frame_id == "SF-001"

    def test_empty_frames_list_allowed(self):
        # StoryFrameSet with 0 frames (before generation completes)
        fset = StoryFrameSet(frames=[])
        assert fset.frames == []


# ── NarrativeDriftReport tests ────────────────────────────────────────────────


class TestNarrativeDriftReport:
    def test_on_track_report(self):
        report = NarrativeDriftReport(
            section_id="DRAFT",
            consistency_score=0.92,
            recommendation="on_track",
        )
        assert report.consistency_score == 0.92
        assert report.drift_summary is None
        assert report.specific_divergences == []

    def test_minor_drift_report(self):
        report = NarrativeDriftReport(
            section_id="DRAFT",
            consistency_score=0.65,
            drift_summary="Methods section focuses on radiation, frame emphasizes HIF.",
            recommendation="minor_drift",
            specific_divergences=["Sentence 3 mentions radiation damage not in frame"],
        )
        assert report.recommendation == "minor_drift"
        assert len(report.specific_divergences) == 1

    def test_major_drift_report(self):
        report = NarrativeDriftReport(
            section_id="REVISION",
            consistency_score=0.40,
            drift_summary="Discussion contradicts hook — no longer claims HIF causality.",
            recommendation="major_drift",
        )
        assert report.consistency_score == 0.40

    def test_score_lower_bound(self):
        with pytest.raises(ValidationError):
            NarrativeDriftReport(
                section_id="DRAFT",
                consistency_score=-0.1,
                recommendation="on_track",
            )

    def test_score_upper_bound(self):
        with pytest.raises(ValidationError):
            NarrativeDriftReport(
                section_id="DRAFT",
                consistency_score=1.1,
                recommendation="on_track",
            )

    def test_boundary_scores(self):
        r0 = NarrativeDriftReport(section_id="X", consistency_score=0.0, recommendation="major_drift")
        r1 = NarrativeDriftReport(section_id="X", consistency_score=1.0, recommendation="on_track")
        assert r0.consistency_score == 0.0
        assert r1.consistency_score == 1.0

    def test_model_dump_roundtrip(self):
        report = NarrativeDriftReport(
            section_id="DRAFT",
            consistency_score=0.72,
            drift_summary="Slight drift in introduction.",
            recommendation="minor_drift",
            specific_divergences=["Para 2 introduces off-topic claim"],
        )
        data = report.model_dump()
        restored = NarrativeDriftReport(**data)
        assert restored.section_id == "DRAFT"
        assert restored.consistency_score == 0.72
