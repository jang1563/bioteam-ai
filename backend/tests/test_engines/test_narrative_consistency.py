"""Tests for NarrativeConsistencyChecker engine."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.engines.narrative_consistency import NarrativeConsistencyChecker
from app.models.story_frame import NarrativeDriftReport

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_llm(report: NarrativeDriftReport | None = None, raise_exc: Exception | None = None):
    """Build a mock LLMLayer whose complete_structured returns the given report."""
    llm = MagicMock()
    if raise_exc:
        llm.complete_structured = AsyncMock(side_effect=raise_exc)
    else:
        default = report or NarrativeDriftReport(
            section_id="DRAFT",
            consistency_score=0.9,
            recommendation="on_track",
        )
        llm.complete_structured = AsyncMock(return_value=(default, MagicMock(cost=0.01)))
    return llm


def _make_frame(
    hook: str = "Microgravity, not radiation, drives spaceflight anemia.",
    core_claim: str = "HIF-1α mediates erythropoiesis suppression in astronauts.",
    central_tension: str = "Expected radiation damage; found hypoxia-like response.",
) -> dict:
    return {
        "hook": hook,
        "core_claim": core_claim,
        "central_tension": central_tension,
        "narrative_type": "mechanism_discovery",
        "target_tier": "nature_cell",
    }


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestNarrativeConsistencyChecker:
    @pytest.mark.asyncio
    async def test_on_track_section_returns_high_score(self):
        report = NarrativeDriftReport(
            section_id="DRAFT",
            consistency_score=0.92,
            recommendation="on_track",
        )
        checker = NarrativeConsistencyChecker(_make_llm(report))
        result = await checker.check("DRAFT", "Section text...", _make_frame())

        assert result.consistency_score == 0.92
        assert result.recommendation == "on_track"
        assert result.section_id == "DRAFT"

    @pytest.mark.asyncio
    async def test_minor_drift_section(self):
        report = NarrativeDriftReport(
            section_id="DRAFT",
            consistency_score=0.65,
            drift_summary="Methods section focuses on radiation, frame emphasizes HIF.",
            recommendation="minor_drift",
            specific_divergences=["Sentence 3 mentions radiation not in frame"],
        )
        checker = NarrativeConsistencyChecker(_make_llm(report))
        result = await checker.check("DRAFT", "Section text...", _make_frame())

        assert result.consistency_score == 0.65
        assert result.recommendation == "minor_drift"
        assert len(result.specific_divergences) == 1

    @pytest.mark.asyncio
    async def test_major_drift_section(self):
        report = NarrativeDriftReport(
            section_id="REVISION",
            consistency_score=0.35,
            drift_summary="Discussion contradicts hook.",
            recommendation="major_drift",
        )
        checker = NarrativeConsistencyChecker(_make_llm(report))
        result = await checker.check("REVISION", "Section text...", _make_frame())

        assert result.consistency_score == 0.35
        assert result.recommendation == "major_drift"

    @pytest.mark.asyncio
    async def test_llm_called_with_correct_model_tier(self):
        mock_llm = _make_llm()
        checker = NarrativeConsistencyChecker(mock_llm)
        await checker.check("DRAFT", "text", _make_frame())

        call_kwargs = mock_llm.complete_structured.call_args.kwargs
        assert call_kwargs["model_tier"] == "haiku"

    @pytest.mark.asyncio
    async def test_llm_called_with_correct_response_model(self):
        mock_llm = _make_llm()
        checker = NarrativeConsistencyChecker(mock_llm)
        await checker.check("DRAFT", "text", _make_frame())

        call_kwargs = mock_llm.complete_structured.call_args.kwargs
        assert call_kwargs["response_model"] is NarrativeDriftReport

    @pytest.mark.asyncio
    async def test_llm_called_with_temperature_zero(self):
        mock_llm = _make_llm()
        checker = NarrativeConsistencyChecker(mock_llm)
        await checker.check("DRAFT", "text", _make_frame())

        call_kwargs = mock_llm.complete_structured.call_args.kwargs
        assert call_kwargs["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_frame_info_injected_in_prompt(self):
        mock_llm = _make_llm()
        checker = NarrativeConsistencyChecker(mock_llm)
        await checker.check("DRAFT", "text", _make_frame(hook="MY_UNIQUE_HOOK_XYZ"))

        call_args = mock_llm.complete_structured.call_args
        messages = call_args.kwargs["messages"]
        prompt_content = messages[0]["content"]
        assert "MY_UNIQUE_HOOK_XYZ" in prompt_content

    @pytest.mark.asyncio
    async def test_section_text_truncated_to_max_chars(self):
        mock_llm = _make_llm()
        checker = NarrativeConsistencyChecker(mock_llm)
        long_text = "A" * 10_000
        await checker.check("DRAFT", long_text, _make_frame())

        call_args = mock_llm.complete_structured.call_args
        messages = call_args.kwargs["messages"]
        prompt_content = messages[0]["content"]
        # The full 10k chars should NOT appear in the prompt (truncated to _MAX_SECTION_CHARS)
        assert "A" * (checker._MAX_SECTION_CHARS + 1) not in prompt_content

    @pytest.mark.asyncio
    async def test_section_id_corrected_if_llm_returns_wrong_id(self):
        """LLM may return wrong section_id — ensure it's overridden to match call."""
        report = NarrativeDriftReport(
            section_id="WRONG_ID",  # LLM hallucinated a different section name
            consistency_score=0.88,
            recommendation="on_track",
        )
        checker = NarrativeConsistencyChecker(_make_llm(report))
        result = await checker.check("DRAFT", "text", _make_frame())

        assert result.section_id == "DRAFT"  # Must be corrected

    @pytest.mark.asyncio
    async def test_llm_failure_returns_safe_default(self):
        """If LLM call throws, return on_track default (don't crash W4)."""
        checker = NarrativeConsistencyChecker(
            _make_llm(raise_exc=RuntimeError("LLM unavailable"))
        )
        result = await checker.check("DRAFT", "text", _make_frame())

        assert result.consistency_score == 1.0
        assert result.recommendation == "on_track"
        assert result.section_id == "DRAFT"
        assert result.drift_summary is None

    @pytest.mark.asyncio
    async def test_empty_hook_returns_safe_default_without_llm_call(self):
        """Frame with empty hook and core_claim skips LLM and returns safe default."""
        mock_llm = _make_llm()
        checker = NarrativeConsistencyChecker(mock_llm)
        result = await checker.check("DRAFT", "text", {"hook": "", "core_claim": ""})

        mock_llm.complete_structured.assert_not_called()
        assert result.consistency_score == 1.0
        assert result.recommendation == "on_track"

    @pytest.mark.asyncio
    async def test_only_hook_present_still_calls_llm(self):
        """Frame with hook but no core_claim still proceeds (hook is sufficient)."""
        mock_llm = _make_llm()
        checker = NarrativeConsistencyChecker(mock_llm)
        frame = {"hook": "Some hook text", "core_claim": ""}
        await checker.check("DRAFT", "text", frame)

        mock_llm.complete_structured.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_called_once_per_section(self):
        mock_llm = _make_llm()
        checker = NarrativeConsistencyChecker(mock_llm)
        await checker.check("DRAFT", "draft text", _make_frame())
        await checker.check("REVISION", "revision text", _make_frame())

        assert mock_llm.complete_structured.call_count == 2
