"""Tests for RCMXTScorer — LLM mode, hybrid fallback, and model validation."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.engines.rcmxt_scorer import RCMXT_SCORING_RUBRIC, RCMXTScorer
from app.llm.mock_layer import MockLLMLayer
from app.models.evidence import AxisExplanation, LLMRCMXTResponse, RCMXTScore

# === Fixtures ===


def _make_papers(n: int, year: int = 2024) -> list[dict]:
    return [
        {"doi": f"10.1234/paper{i}", "pmid": f"{30000000 + i}", "year": year}
        for i in range(n)
    ]


def _make_extracted(n: int, organism: str = "human", tech: str = "RNA-seq") -> list[dict]:
    return [
        {"paper_id": f"p{i}", "organism": organism, "technology": tech, "sample_size": 10}
        for i in range(n)
    ]


def _mock_4axis_response() -> LLMRCMXTResponse:
    """4-axis response (X not applicable)."""
    return LLMRCMXTResponse(
        claim_text="Test claim about spaceflight anemia",
        axes=[
            AxisExplanation(axis="R", score=0.85, reasoning="Replicated across multiple ISS missions by independent teams."),
            AxisExplanation(axis="C", score=0.55, reasoning="Condition-specific to microgravity exposure duration."),
            AxisExplanation(axis="M", score=0.75, reasoning="Well-designed studies with CO breath analysis and blood sampling."),
            AxisExplanation(axis="T", score=0.70, reasoning="Consistent finding from Skylab through ISS missions over decades."),
        ],
        x_applicable=False,
        overall_assessment="Well-supported spaceflight physiology finding.",
        confidence_in_scoring=0.85,
    )


def _mock_5axis_response() -> LLMRCMXTResponse:
    """5-axis response (X applicable)."""
    return LLMRCMXTResponse(
        claim_text="Multi-omics mitochondrial dysfunction claim",
        axes=[
            AxisExplanation(axis="R", score=0.70, reasoning="Replicated in GeneLab meta-analysis across rodent and human data."),
            AxisExplanation(axis="C", score=0.60, reasoning="Converges across tissues and species."),
            AxisExplanation(axis="M", score=0.65, reasoning="Meta-analysis robust but heterogeneous source quality."),
            AxisExplanation(axis="X", score=0.75, reasoning="Transcriptomics, proteomics, and metabolomics converge on mitochondrial stress."),
            AxisExplanation(axis="T", score=0.60, reasoning="Identified in 2020, gaining traction but relatively recent."),
        ],
        x_applicable=True,
        overall_assessment="Well-supported multi-omics finding with cross-validation strength.",
        confidence_in_scoring=0.80,
    )


def _make_mock_llm(response: LLMRCMXTResponse | None = None) -> MockLLMLayer:
    """Create a MockLLMLayer with the given response registered."""
    resp = response or _mock_4axis_response()
    return MockLLMLayer({"sonnet:LLMRCMXTResponse": resp})


# === LLMRCMXTResponse model validation tests ===


class TestLLMRCMXTResponseValidation:
    """Test Pydantic validation of the LLM response model."""

    def test_valid_4axis_response(self):
        resp = _mock_4axis_response()
        assert len(resp.axes) == 4
        assert resp.x_applicable is False
        assert all(0.0 <= ax.score <= 1.0 for ax in resp.axes)

    def test_valid_5axis_response(self):
        resp = _mock_5axis_response()
        assert len(resp.axes) == 5
        assert resp.x_applicable is True
        x_axis = next(ax for ax in resp.axes if ax.axis == "X")
        assert x_axis.score == 0.75

    def test_reject_fewer_than_4_axes(self):
        with pytest.raises(Exception):  # Pydantic ValidationError
            LLMRCMXTResponse(
                claim_text="test",
                axes=[
                    AxisExplanation(axis="R", score=0.5, reasoning="Some reasoning for R axis."),
                    AxisExplanation(axis="C", score=0.5, reasoning="Some reasoning for C axis."),
                ],
                x_applicable=False,
                overall_assessment="test",
                confidence_in_scoring=0.5,
            )

    def test_reject_score_out_of_range(self):
        with pytest.raises(Exception):  # Pydantic ValidationError
            AxisExplanation(axis="R", score=1.5, reasoning="Invalid score above 1.0.")

    def test_reject_empty_reasoning(self):
        with pytest.raises(Exception):  # Pydantic ValidationError
            AxisExplanation(axis="R", score=0.5, reasoning="short")  # min_length=10


# === Constructor tests ===


class TestScorerConstruction:
    """Test mode-based construction and validation."""

    def test_default_heuristic_mode(self):
        scorer = RCMXTScorer()
        assert scorer._mode == "heuristic"

    def test_llm_mode_requires_layer(self):
        with pytest.raises(ValueError, match="llm_layer is required"):
            RCMXTScorer(mode="llm")

    def test_hybrid_mode_requires_layer(self):
        with pytest.raises(ValueError, match="llm_layer is required"):
            RCMXTScorer(mode="hybrid")

    def test_llm_mode_with_layer(self):
        mock = _make_mock_llm()
        scorer = RCMXTScorer(mode="llm", llm_layer=mock)
        assert scorer._mode == "llm"
        assert scorer._llm is mock

    def test_heuristic_mode_ignores_layer(self):
        mock = _make_mock_llm()
        scorer = RCMXTScorer(mode="heuristic", llm_layer=mock)
        assert scorer._mode == "heuristic"


# === Mode dispatch tests ===


class TestModeDispatch:
    """Test that the correct scoring path is used based on mode."""

    @pytest.mark.asyncio
    async def test_heuristic_mode_no_llm_call(self):
        mock = _make_mock_llm()
        scorer = RCMXTScorer(mode="heuristic", llm_layer=mock)
        scorer.load_step_data(search_output={"papers": _make_papers(5)})
        score = await scorer.score_claim_async("test claim")
        assert score.scorer_version == "v0.1-heuristic"
        assert len(mock.call_log) == 0  # No LLM call

    @pytest.mark.asyncio
    async def test_llm_mode_calls_llm(self):
        mock = _make_mock_llm()
        scorer = RCMXTScorer(mode="llm", llm_layer=mock)
        scorer.load_step_data(search_output={"papers": _make_papers(5)})
        score = await scorer.score_claim_async("test claim")
        assert score.scorer_version == "v0.2-llm"
        assert len(mock.call_log) == 1
        assert mock.call_log[0]["model_tier"] == "sonnet"

    @pytest.mark.asyncio
    async def test_hybrid_mode_tries_llm(self):
        mock = _make_mock_llm()
        scorer = RCMXTScorer(mode="hybrid", llm_layer=mock)
        scorer.load_step_data(search_output={"papers": _make_papers(5)})
        score = await scorer.score_claim_async("test claim")
        assert score.scorer_version == "v0.2-llm"
        assert len(mock.call_log) == 1


# === LLM response conversion tests ===


class TestLLMResponseConversion:
    """Test conversion from LLMRCMXTResponse to RCMXTScore."""

    @pytest.mark.asyncio
    async def test_4axis_conversion_x_none(self):
        mock = _make_mock_llm(_mock_4axis_response())
        scorer = RCMXTScorer(mode="llm", llm_layer=mock)
        score = await scorer.score_claim_async("Test claim")
        assert score.X is None
        assert score.R == 0.85
        assert score.C == 0.55
        assert score.M == 0.75
        assert score.T == 0.70

    @pytest.mark.asyncio
    async def test_5axis_conversion_x_present(self):
        mock = _make_mock_llm(_mock_5axis_response())
        scorer = RCMXTScorer(mode="llm", llm_layer=mock)
        score = await scorer.score_claim_async("Multi-omics claim")
        assert score.X == 0.75
        assert score.R == 0.70

    @pytest.mark.asyncio
    async def test_composite_computed_after_conversion(self):
        mock = _make_mock_llm(_mock_4axis_response())
        scorer = RCMXTScorer(mode="llm", llm_layer=mock)
        score = await scorer.score_claim_async("Test claim")
        assert score.composite is not None
        # 4-axis composite: (0.85 + 0.55 + 0.75 + 0.70) / 4 = 0.7125
        assert abs(score.composite - 0.713) < 0.01

    @pytest.mark.asyncio
    async def test_model_version_from_meta(self):
        mock = _make_mock_llm()
        scorer = RCMXTScorer(mode="llm", llm_layer=mock)
        score = await scorer.score_claim_async("Test claim")
        assert score.model_version.startswith("mock-")

    @pytest.mark.asyncio
    async def test_sources_passed_through(self):
        mock = _make_mock_llm()
        scorer = RCMXTScorer(mode="llm", llm_layer=mock)
        scorer.load_step_data(search_output={"papers": _make_papers(3)})
        score = await scorer.score_claim_async("Test claim")
        assert len(score.sources) == 3
        assert all(s.startswith("10.1234/") for s in score.sources)


# === Prompt construction tests ===


class TestPromptConstruction:
    """Test that scoring prompts are correctly built."""

    def test_rubric_contains_all_axes(self):
        assert "### R" in RCMXT_SCORING_RUBRIC
        assert "### C" in RCMXT_SCORING_RUBRIC
        assert "### M" in RCMXT_SCORING_RUBRIC
        assert "### X" in RCMXT_SCORING_RUBRIC
        assert "### T" in RCMXT_SCORING_RUBRIC

    def test_rubric_contains_null_instruction(self):
        assert "x_applicable=false" in RCMXT_SCORING_RUBRIC

    @pytest.mark.asyncio
    async def test_cached_system_used(self):
        mock = _make_mock_llm()
        scorer = RCMXTScorer(mode="llm", llm_layer=mock)
        await scorer.score_claim_async("Test claim")
        # After first call, cached_system should be populated
        assert scorer._cached_system is not None
        assert isinstance(scorer._cached_system, list)

    def test_build_messages_includes_claim(self):
        mock = _make_mock_llm()
        scorer = RCMXTScorer(mode="llm", llm_layer=mock)
        messages = scorer._build_scoring_messages("My test claim", "spaceflight_biology")
        assert len(messages) == 1
        assert "My test claim" in messages[0]["content"]
        assert "spaceflight_biology" in messages[0]["content"]

    def test_build_messages_includes_pipeline_context(self):
        mock = _make_mock_llm()
        scorer = RCMXTScorer(mode="llm", llm_layer=mock)
        scorer.load_step_data(
            search_output={"papers": _make_papers(5, year=2023)},
            extract_output={"papers": _make_extracted(3, organism="human", tech="RNA-seq")},
        )
        messages = scorer._build_scoring_messages("claim", "")
        content = messages[0]["content"]
        assert "5 papers retrieved" in content
        assert "human" in content
        assert "rna-seq" in content
        assert "2023" in content


# === score_all_async tests ===


class TestScoreAllAsync:
    """Test batch scoring via score_all_async."""

    @pytest.mark.asyncio
    async def test_score_all_async_empty(self):
        mock = _make_mock_llm()
        scorer = RCMXTScorer(mode="llm", llm_layer=mock)
        scores = await scorer.score_all_async()
        assert scores == []

    @pytest.mark.asyncio
    async def test_score_all_async_multiple(self):
        mock = _make_mock_llm()
        scorer = RCMXTScorer(mode="llm", llm_layer=mock)
        scorer.load_step_data(
            synthesis_output={"key_findings": ["finding A", "finding B"]},
        )
        scores = await scorer.score_all_async()
        assert len(scores) == 2
        assert len(mock.call_log) == 2

    @pytest.mark.asyncio
    async def test_score_all_async_heuristic(self):
        scorer = RCMXTScorer(mode="heuristic")
        scorer.load_step_data(
            search_output={"papers": _make_papers(5)},
            synthesis_output={"key_findings": ["finding A"]},
        )
        scores = await scorer.score_all_async()
        assert len(scores) == 1
        assert scores[0].scorer_version == "v0.1-heuristic"


# === Benchmark claim scoring tests ===


class TestBenchmarkScoring:
    """Test the score_benchmark_claim method."""

    @pytest.mark.asyncio
    async def test_benchmark_returns_both(self):
        mock = _make_mock_llm()
        scorer = RCMXTScorer(mode="llm", llm_layer=mock)
        score, llm_resp = await scorer.score_benchmark_claim(
            "Test claim", "spaceflight_biology"
        )
        assert isinstance(score, RCMXTScore)
        assert isinstance(llm_resp, LLMRCMXTResponse)
        assert score.scorer_version == "v0.2-llm"

    @pytest.mark.asyncio
    async def test_benchmark_heuristic_returns_none_resp(self):
        scorer = RCMXTScorer(mode="heuristic")
        score, llm_resp = await scorer.score_benchmark_claim(
            "Test claim", "spaceflight_biology"
        )
        assert isinstance(score, RCMXTScore)
        assert llm_resp is None
        assert score.scorer_version == "v0.1-heuristic"


# === Hybrid fallback tests ===


class TestHybridFallback:
    """Test that hybrid mode falls back to heuristic on LLM failure."""

    @pytest.mark.asyncio
    async def test_hybrid_fallback_on_exception(self):
        """Hybrid falls back to heuristic when LLM raises an exception."""

        class FailingLLMLayer:
            def build_cached_system(self, text):
                return [{"type": "text", "text": text}]

            async def complete_structured(self, **kwargs):
                raise RuntimeError("LLM API unavailable")

        scorer = RCMXTScorer(mode="hybrid", llm_layer=FailingLLMLayer())
        scorer.load_step_data(search_output={"papers": _make_papers(5)})
        score = await scorer.score_claim_async("test claim")
        # Should have fallen back to heuristic
        assert score.scorer_version == "v0.1-heuristic"

    @pytest.mark.asyncio
    async def test_benchmark_hybrid_fallback(self):
        """score_benchmark_claim in hybrid mode falls back gracefully."""

        class FailingLLMLayer:
            def build_cached_system(self, text):
                return [{"type": "text", "text": text}]

            async def complete_structured(self, **kwargs):
                raise RuntimeError("LLM API unavailable")

        scorer = RCMXTScorer(mode="hybrid", llm_layer=FailingLLMLayer())
        score, llm_resp = await scorer.score_benchmark_claim("claim", "domain")
        assert score.scorer_version == "v0.1-heuristic"
        assert llm_resp is None


# === Error handling tests ===


class TestErrorHandling:
    """Test error conditions."""

    @pytest.mark.asyncio
    async def test_llm_mode_no_layer_raises(self):
        """Can't create LLM mode scorer without layer."""
        with pytest.raises(ValueError):
            RCMXTScorer(mode="llm", llm_layer=None)

    @pytest.mark.asyncio
    async def test_temperature_is_zero(self):
        """Verify temperature=0.0 for reproducibility."""
        mock = _make_mock_llm()
        scorer = RCMXTScorer(mode="llm", llm_layer=mock)
        await scorer.score_claim_async("test")
        call = mock.call_log[0]
        assert call.get("temperature") == 0.0

    @pytest.mark.asyncio
    async def test_empty_context_string(self):
        """Scoring with empty context should still work."""
        mock = _make_mock_llm()
        scorer = RCMXTScorer(mode="llm", llm_layer=mock)
        score = await scorer.score_claim_async("test claim", context="")
        assert score.scorer_version == "v0.2-llm"


# === Backward compatibility ===


class TestBackwardCompatibility:
    """Verify v0.1 heuristic behavior is totally unchanged."""

    def test_default_constructor(self):
        """Default constructor produces heuristic scorer."""
        scorer = RCMXTScorer()
        assert scorer._mode == "heuristic"
        assert scorer._llm is None

    def test_sync_score_claim(self):
        """sync score_claim still works."""
        scorer = RCMXTScorer()
        scorer.load_step_data(search_output={"papers": _make_papers(10)})
        score = scorer.score_claim("test")
        assert score.scorer_version == "v0.1-heuristic"
        assert score.model_version == "deterministic"

    def test_sync_score_all(self):
        """sync score_all still works."""
        scorer = RCMXTScorer()
        scorer.load_step_data(
            search_output={"papers": _make_papers(5)},
            synthesis_output={"key_findings": ["A", "B"]},
        )
        scores = scorer.score_all()
        assert len(scores) == 2
        assert all(s.scorer_version == "v0.1-heuristic" for s in scores)
