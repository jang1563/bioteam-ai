"""Tests for the iterative refinement loop engine.

Verifies:
- Pydantic models (QualityCritique, RefinementConfig, RefinementResult)
- RefinementLoop guardrails (budget, max iterations, quality threshold, diminishing returns)
- Context injection with critique feedback
- Integration with runner _maybe_refine pattern
- config_from_settings factory
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from app.models.refinement import QualityCritique, RefinementConfig, RefinementResult

# === 1. Pydantic Model Tests ===


class TestQualityCritique:
    def test_valid_critique(self):
        critique = QualityCritique(
            rigor_score=0.8,
            completeness_score=0.7,
            clarity_score=0.9,
            accuracy_score=0.85,
            overall_score=0.81,
            issues=["Missing gene name validation"],
            suggestions=["Cross-reference with NCBI Gene"],
            strengths=["Comprehensive literature coverage"],
        )
        assert critique.overall_score == 0.81
        assert len(critique.issues) == 1
        assert len(critique.strengths) == 1

    def test_score_bounds(self):
        """Scores must be 0.0 to 1.0."""
        with pytest.raises(Exception):  # ValidationError
            QualityCritique(
                rigor_score=1.5,  # Out of bounds
                completeness_score=0.5,
                clarity_score=0.5,
                accuracy_score=0.5,
                overall_score=0.5,
            )

    def test_negative_score_rejected(self):
        with pytest.raises(Exception):  # ValidationError
            QualityCritique(
                rigor_score=-0.1,
                completeness_score=0.5,
                clarity_score=0.5,
                accuracy_score=0.5,
                overall_score=0.5,
            )

    def test_default_lists_empty(self):
        critique = QualityCritique(
            rigor_score=0.5,
            completeness_score=0.5,
            clarity_score=0.5,
            accuracy_score=0.5,
            overall_score=0.5,
        )
        assert critique.issues == []
        assert critique.suggestions == []
        assert critique.strengths == []


class TestRefinementConfig:
    def test_defaults(self):
        config = RefinementConfig()
        assert config.max_iterations == 2
        assert config.quality_threshold == 0.7
        assert config.budget_cap == 1.0
        assert config.min_improvement == 0.05
        assert config.scorer_model == "haiku"

    def test_custom_values(self):
        config = RefinementConfig(
            max_iterations=5,
            quality_threshold=0.9,
            budget_cap=2.0,
            min_improvement=0.1,
            scorer_model="sonnet",
        )
        assert config.max_iterations == 5
        assert config.quality_threshold == 0.9

    def test_max_iterations_bounds(self):
        with pytest.raises(Exception):
            RefinementConfig(max_iterations=0)  # ge=1
        with pytest.raises(Exception):
            RefinementConfig(max_iterations=6)  # le=5


class TestRefinementResult:
    def test_defaults(self):
        result = RefinementResult()
        assert result.iterations_used == 0
        assert result.quality_scores == []
        assert result.critiques == []
        assert result.total_cost == 0.0
        assert result.stopped_reason == ""

    def test_with_data(self):
        critique = QualityCritique(
            rigor_score=0.8,
            completeness_score=0.7,
            clarity_score=0.9,
            accuracy_score=0.85,
            overall_score=0.81,
        )
        result = RefinementResult(
            iterations_used=1,
            quality_scores=[0.5, 0.81],
            critiques=[critique],
            total_cost=0.003,
            stopped_reason="quality_met",
        )
        assert result.iterations_used == 1
        assert len(result.quality_scores) == 2
        assert result.stopped_reason == "quality_met"


# === 2. RefinementLoop Tests ===


def _make_critique(overall: float = 0.8, issues: list | None = None) -> QualityCritique:
    """Helper to create a QualityCritique with a given overall score."""
    return QualityCritique(
        rigor_score=overall,
        completeness_score=overall,
        clarity_score=overall,
        accuracy_score=overall,
        overall_score=overall,
        issues=issues or [],
        suggestions=["Improve quality"],
        strengths=["Good structure"],
    )


def _make_output(success: bool = True, cost: float = 0.01) -> AgentOutput:
    """Helper to create an AgentOutput."""
    if success:
        return AgentOutput(
            agent_id="test_agent",
            output={"result": "test synthesis output"},
            summary="Test output summary",
            cost=cost,
        )
    return AgentOutput(
        agent_id="test_agent",
        error="Agent failed",
    )


def _make_context() -> ContextPackage:
    """Helper to create a ContextPackage."""
    return ContextPackage(task_description="Analyze spaceflight-induced anemia mechanisms")


class TestRefinementLoop:
    """Test the core RefinementLoop engine."""

    def test_skip_on_error_output(self):
        """Should skip refinement if initial output has an error."""
        from app.workflows.refinement import RefinementLoop

        mock_llm = MagicMock()
        loop = RefinementLoop(llm=mock_llm)

        error_output = _make_output(success=False)
        context = _make_context()
        mock_agent = MagicMock()

        result_output, result_meta = asyncio.run(
            loop.refine(agent=mock_agent, context=context, initial_output=error_output)
        )
        assert result_meta.stopped_reason == "skipped"
        assert result_meta.iterations_used == 0
        assert result_output == error_output

    def test_quality_already_met(self):
        """Should return immediately if initial quality >= threshold."""
        from app.workflows.refinement import RefinementLoop

        mock_llm = MagicMock()
        high_critique = _make_critique(overall=0.85)

        # Mock the LLM scoring call
        mock_llm.complete_structured = AsyncMock(return_value=(
            high_critique,
            MagicMock(cost=0.001),
        ))

        config = RefinementConfig(quality_threshold=0.7)
        loop = RefinementLoop(llm=mock_llm, config=config)

        good_output = _make_output()
        context = _make_context()
        mock_agent = MagicMock()

        result_output, result_meta = asyncio.run(
            loop.refine(agent=mock_agent, context=context, initial_output=good_output)
        )

        assert result_meta.stopped_reason == "quality_met"
        assert result_meta.iterations_used == 0
        assert result_meta.quality_scores == [0.85]
        assert result_output == good_output

    def test_refinement_improves_quality(self):
        """Should refine once and stop when quality is met on second iteration."""
        from app.workflows.refinement import RefinementLoop

        mock_llm = MagicMock()

        low_critique = _make_critique(overall=0.5, issues=["Missing evidence"])
        high_critique = _make_critique(overall=0.8)

        # First call: low score. Second call: high score
        mock_llm.complete_structured = AsyncMock(side_effect=[
            (low_critique, MagicMock(cost=0.001)),
            (high_critique, MagicMock(cost=0.001)),
        ])

        config = RefinementConfig(quality_threshold=0.7, max_iterations=2)
        loop = RefinementLoop(llm=mock_llm, config=config)

        initial_output = _make_output(cost=0.01)
        revised_output = _make_output(cost=0.02)

        context = _make_context()
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=revised_output)

        result_output, result_meta = asyncio.run(
            loop.refine(agent=mock_agent, context=context, initial_output=initial_output)
        )

        assert result_meta.stopped_reason == "quality_met"
        assert result_meta.iterations_used == 1
        assert len(result_meta.quality_scores) == 2
        assert result_meta.quality_scores[0] == 0.5
        assert result_meta.quality_scores[1] == 0.8

        # Agent was re-run with revision context
        mock_agent.run.assert_called_once()
        revision_ctx = mock_agent.run.call_args[0][0]
        assert isinstance(revision_ctx, ContextPackage)
        # Revision context should contain critique feedback
        feedback_items = [
            o for o in revision_ctx.prior_step_outputs
            if isinstance(o, dict) and o.get("type") == "quality_critique"
        ]
        assert len(feedback_items) == 1
        assert feedback_items[0]["overall_score"] == 0.5

    def test_max_iterations_stop(self):
        """Should stop after max_iterations even if quality not met."""
        from app.workflows.refinement import RefinementLoop

        mock_llm = MagicMock()

        # All scores below threshold, but improving enough to avoid diminishing returns
        critiques = [
            _make_critique(overall=0.3),
            _make_critique(overall=0.45),
            _make_critique(overall=0.55),
        ]
        mock_llm.complete_structured = AsyncMock(side_effect=[
            (c, MagicMock(cost=0.001)) for c in critiques
        ])

        config = RefinementConfig(quality_threshold=0.9, max_iterations=2, min_improvement=0.01)
        loop = RefinementLoop(llm=mock_llm, config=config)

        context = _make_context()
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=_make_output(cost=0.01))

        result_output, result_meta = asyncio.run(
            loop.refine(agent=mock_agent, context=context, initial_output=_make_output())
        )

        assert result_meta.stopped_reason == "max_iterations"
        assert result_meta.iterations_used == 2

    def test_budget_cap_stop(self):
        """Should stop when budget cap is reached."""
        from app.workflows.refinement import RefinementLoop

        mock_llm = MagicMock()

        low_critique = _make_critique(overall=0.3)
        mock_llm.complete_structured = AsyncMock(return_value=(
            low_critique, MagicMock(cost=0.6),  # High scoring cost
        ))

        config = RefinementConfig(budget_cap=0.5, quality_threshold=0.9, max_iterations=3)
        loop = RefinementLoop(llm=mock_llm, config=config)

        context = _make_context()
        mock_agent = MagicMock()

        result_output, result_meta = asyncio.run(
            loop.refine(agent=mock_agent, context=context, initial_output=_make_output())
        )

        assert result_meta.stopped_reason == "budget_exhausted"
        assert result_meta.iterations_used == 0  # Never got to revise

    def test_diminishing_returns_stop(self):
        """Should stop when improvement between iterations is too small."""
        from app.workflows.refinement import RefinementLoop

        mock_llm = MagicMock()

        # Score barely improves: 0.5 → 0.52 (Δ=0.02 < min_improvement=0.05)
        critiques = [
            _make_critique(overall=0.5),
            _make_critique(overall=0.52),
        ]
        mock_llm.complete_structured = AsyncMock(side_effect=[
            (c, MagicMock(cost=0.001)) for c in critiques
        ])

        config = RefinementConfig(
            quality_threshold=0.9,
            max_iterations=3,
            min_improvement=0.05,
        )
        loop = RefinementLoop(llm=mock_llm, config=config)

        context = _make_context()
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=_make_output(cost=0.01))

        result_output, result_meta = asyncio.run(
            loop.refine(agent=mock_agent, context=context, initial_output=_make_output())
        )

        assert result_meta.stopped_reason == "diminishing_returns"
        assert result_meta.iterations_used == 1

    def test_agent_error_during_revision(self):
        """Should stop if agent raises error during revision."""
        from app.workflows.refinement import RefinementLoop

        mock_llm = MagicMock()

        low_critique = _make_critique(overall=0.3)
        mock_llm.complete_structured = AsyncMock(return_value=(
            low_critique, MagicMock(cost=0.001),
        ))

        config = RefinementConfig(quality_threshold=0.7, budget_cap=5.0)
        loop = RefinementLoop(llm=mock_llm, config=config)

        context = _make_context()
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=RuntimeError("LLM call failed"))

        result_output, result_meta = asyncio.run(
            loop.refine(agent=mock_agent, context=context, initial_output=_make_output())
        )

        assert result_meta.stopped_reason == "agent_error"
        assert result_meta.iterations_used == 0  # Revision attempt didn't complete

    def test_keeps_best_output(self):
        """Should keep the best-scoring output across iterations."""
        from app.workflows.refinement import RefinementLoop

        mock_llm = MagicMock()

        # Score goes up then down: 0.3 → 0.6 → 0.55
        critiques = [
            _make_critique(overall=0.3),
            _make_critique(overall=0.6),
            _make_critique(overall=0.55),
        ]
        mock_llm.complete_structured = AsyncMock(side_effect=[
            (c, MagicMock(cost=0.001)) for c in critiques
        ])

        config = RefinementConfig(
            quality_threshold=0.9,
            max_iterations=2,
            min_improvement=0.0,  # Don't stop on diminishing returns
        )
        loop = RefinementLoop(llm=mock_llm, config=config)

        initial = _make_output(cost=0.01)
        better = AgentOutput(
            agent_id="test_agent",
            output={"result": "better version"},
            summary="Better",
            cost=0.02,
        )
        worse = AgentOutput(
            agent_id="test_agent",
            output={"result": "worse version"},
            summary="Worse",
            cost=0.02,
        )

        context = _make_context()
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=[better, worse])

        result_output, result_meta = asyncio.run(
            loop.refine(agent=mock_agent, context=context, initial_output=initial)
        )

        # Should keep "better" (score 0.6) not "worse" (score 0.55)
        assert result_output.output == {"result": "better version"}
        # Score dropped from 0.6 → 0.55 (Δ=-0.05 < min_improvement=0.0)
        assert result_meta.stopped_reason == "diminishing_returns"


# === 3. Context Injection Tests ===


class TestContextInjection:
    def test_revision_context_has_critique(self):
        """Revision context should contain the quality critique."""
        from app.workflows.refinement import RefinementLoop

        loop = RefinementLoop(llm=MagicMock())
        critique = _make_critique(overall=0.5, issues=["Missing evidence"])
        output = _make_output()
        context = _make_context()

        revision = loop._build_revision_context(context, output, critique)

        assert isinstance(revision, ContextPackage)
        assert revision.task_description == context.task_description

        # Should have previous output + critique in prior_step_outputs
        feedback_items = [
            o for o in revision.prior_step_outputs
            if isinstance(o, dict) and o.get("type") == "quality_critique"
        ]
        assert len(feedback_items) == 1
        assert feedback_items[0]["overall_score"] == 0.5
        assert "Missing evidence" in feedback_items[0]["issues"]

    def test_revision_context_has_previous_output(self):
        """Revision context should contain the previous output for reference."""
        from app.workflows.refinement import RefinementLoop

        loop = RefinementLoop(llm=MagicMock())
        critique = _make_critique(overall=0.5)
        output = _make_output()
        context = _make_context()

        revision = loop._build_revision_context(context, output, critique)

        prev_items = [
            o for o in revision.prior_step_outputs
            if isinstance(o, dict) and o.get("type") == "previous_output_for_revision"
        ]
        assert len(prev_items) == 1
        assert prev_items[0]["output"] == output.output

    def test_revision_context_preserves_original_memory(self):
        """Revision context should keep original memory and negative results."""
        from app.workflows.refinement import RefinementLoop

        loop = RefinementLoop(llm=MagicMock())
        critique = _make_critique(overall=0.5)
        output = _make_output()

        context = ContextPackage(
            task_description="Test task",
            negative_results=[{"claim": "X doesn't work"}],
            constraints={"budget": 5.0},
        )

        revision = loop._build_revision_context(context, output, critique)

        assert revision.negative_results == [{"claim": "X doesn't work"}]
        assert revision.constraints["refinement_mode"] is True
        # Original constraint should be preserved too
        assert revision.constraints.get("budget") == 5.0

    def test_refinement_mode_flag(self):
        """Revision context should have refinement_mode=True in constraints."""
        from app.workflows.refinement import RefinementLoop

        loop = RefinementLoop(llm=MagicMock())
        critique = _make_critique(overall=0.5)
        output = _make_output()
        context = _make_context()

        revision = loop._build_revision_context(context, output, critique)
        assert revision.constraints.get("refinement_mode") is True


# === 4. Scoring Message Tests ===


class TestScoringMessage:
    def test_scoring_message_contains_task(self):
        """Scoring message should include the original task description."""
        from app.workflows.refinement import RefinementLoop

        loop = RefinementLoop(llm=MagicMock())
        output = _make_output()
        context = _make_context()

        msg = loop._build_scoring_message(output, context)
        assert "spaceflight-induced anemia" in msg

    def test_scoring_message_contains_output(self):
        """Scoring message should include the agent output."""
        from app.workflows.refinement import RefinementLoop

        loop = RefinementLoop(llm=MagicMock())
        output = _make_output()
        context = _make_context()

        msg = loop._build_scoring_message(output, context)
        assert "test synthesis output" in msg

    def test_scoring_message_contains_summary(self):
        """Scoring message should include the output summary."""
        from app.workflows.refinement import RefinementLoop

        loop = RefinementLoop(llm=MagicMock())
        output = _make_output()
        context = _make_context()

        msg = loop._build_scoring_message(output, context)
        assert "Test output summary" in msg


# === 5. Config Factory Tests ===


class TestConfigFromSettings:
    def test_config_from_settings(self):
        """config_from_settings should read from app settings."""
        from app.workflows.refinement import config_from_settings

        with patch("app.workflows.refinement.settings") as mock_settings:
            mock_settings.refinement_max_iterations = 3
            mock_settings.refinement_quality_threshold = 0.8
            mock_settings.refinement_budget_cap = 2.0
            mock_settings.refinement_min_improvement = 0.1
            mock_settings.refinement_scorer_model = "sonnet"

            config = config_from_settings()

        assert config.max_iterations == 3
        assert config.quality_threshold == 0.8
        assert config.budget_cap == 2.0
        assert config.min_improvement == 0.1
        assert config.scorer_model == "sonnet"


# === 6. Runner Integration Tests ===


class TestRunnerRefinementIntegration:
    """Test that runners call _maybe_refine correctly."""

    def test_w1_maybe_refine_disabled(self):
        """W1 _maybe_refine should skip when refinement disabled."""
        from app.workflows.runners.w1_literature import W1LiteratureReviewRunner

        mock_registry = MagicMock()
        runner = W1LiteratureReviewRunner(registry=mock_registry)

        output = _make_output()
        context = _make_context()
        mock_agent = MagicMock()
        instance = MagicMock()

        with patch("app.workflows.runners.w1_literature.settings") as mock_settings:
            mock_settings.refinement_enabled = False

            result, cost = asyncio.run(
                runner._maybe_refine(mock_agent, context, output, instance)
            )

        assert result == output
        assert cost == 0.0

    def test_w2_maybe_refine_disabled(self):
        """W2 _maybe_refine should skip when refinement disabled."""
        from app.workflows.runners.w2_hypothesis import W2HypothesisRunner

        mock_registry = MagicMock()
        runner = W2HypothesisRunner(registry=mock_registry)

        output = _make_output()
        context = _make_context()
        mock_agent = MagicMock()
        instance = MagicMock()

        with patch("app.workflows.runners.w2_hypothesis.settings") as mock_settings:
            mock_settings.refinement_enabled = False

            result, cost = asyncio.run(
                runner._maybe_refine(mock_agent, context, output, instance)
            )

        assert result == output
        assert cost == 0.0

    def test_maybe_refine_no_llm(self):
        """_maybe_refine should skip when agent has no LLM."""
        from app.workflows.runners.w3_data_analysis import W3DataAnalysisRunner

        mock_registry = MagicMock()
        runner = W3DataAnalysisRunner(registry=mock_registry)

        output = _make_output()
        context = _make_context()
        mock_agent = MagicMock(spec=[])  # No 'llm' attribute
        instance = MagicMock()

        with patch("app.workflows.runners.w3_data_analysis.settings") as mock_settings:
            mock_settings.refinement_enabled = True

            result, cost = asyncio.run(
                runner._maybe_refine(mock_agent, context, output, instance)
            )

        assert result == output
        assert cost == 0.0


# === 7. Cost Tracking Tests ===


class TestCostTracking:
    def test_total_cost_accumulates(self):
        """Total cost should include scoring + agent revision costs."""
        from app.workflows.refinement import RefinementLoop

        mock_llm = MagicMock()

        # Score: 0.4 then 0.8
        critiques = [
            _make_critique(overall=0.4),
            _make_critique(overall=0.8),
        ]
        mock_llm.complete_structured = AsyncMock(side_effect=[
            (critiques[0], MagicMock(cost=0.002)),  # First scoring
            (critiques[1], MagicMock(cost=0.002)),  # Second scoring
        ])

        config = RefinementConfig(quality_threshold=0.7)
        loop = RefinementLoop(llm=mock_llm, config=config)

        revised_output = _make_output(cost=0.05)  # Revision cost
        context = _make_context()
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=revised_output)

        _, result_meta = asyncio.run(
            loop.refine(agent=mock_agent, context=context, initial_output=_make_output())
        )

        # Total cost = scoring1 (0.002) + revision (0.05) + scoring2 (0.002) = 0.054
        assert abs(result_meta.total_cost - 0.054) < 0.001


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
