"""RefinementLoop — iterative Self-Refine engine for agent output quality.

Implements the produce → critique → revise cycle:
  1. Agent produces initial output
  2. Haiku scores it via QualityCritique
  3. If quality < threshold: inject critique into context, re-run agent
  4. Repeat until quality met or guardrail triggers

Guardrails:
  - Budget cap: total refinement cost cannot exceed budget_cap
  - Max iterations: hard limit on revision cycles (default 2)
  - Diminishing returns: stop if Δscore < min_improvement
  - Quality threshold: skip refinement if initial quality is good enough

Used by W1-W5 runners at synthesis/output steps.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import ModelTier, settings
from app.llm.layer import LLMLayer
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from app.models.refinement import QualityCritique, RefinementConfig, RefinementResult

logger = logging.getLogger(__name__)


def config_from_settings() -> RefinementConfig:
    """Build a RefinementConfig from app settings."""
    return RefinementConfig(
        max_iterations=settings.refinement_max_iterations,
        quality_threshold=settings.refinement_quality_threshold,
        budget_cap=settings.refinement_budget_cap,
        min_improvement=settings.refinement_min_improvement,
        scorer_model=settings.refinement_scorer_model,
    )

# System prompt for the quality scorer (Haiku)
_SCORER_SYSTEM_PROMPT = """You are a quality reviewer for biology research outputs.

Score the output across these dimensions (0.0 = poor, 1.0 = excellent):
- rigor_score: Are claims well-supported by evidence? Are methods sound?
- completeness_score: Are all aspects of the question addressed?
- clarity_score: Is the output clear, well-structured, and actionable?
- accuracy_score: Are biological facts, gene names, pathway references correct?
- overall_score: Holistic quality considering all dimensions.

Also provide:
- issues: Specific problems found that need fixing (list of strings).
- suggestions: Concrete, actionable improvement suggestions (list of strings).
- strengths: What was done well — preserve these in revision (list of strings).

Be rigorous but fair. Focus on factual accuracy and scientific rigor above all."""


class RefinementLoop:
    """Iterative refinement engine using Self-Refine pattern.

    Orchestrates the critique → revise cycle for any agent's output.
    Designed as a stateless helper that runners call at key synthesis steps.

    Usage:
        loop = RefinementLoop(llm=llm_layer)
        refined_output, result = await loop.refine(
            agent=agent,
            context=original_context,
            initial_output=first_pass_output,
        )
    """

    def __init__(
        self,
        llm: LLMLayer,
        config: RefinementConfig | None = None,
    ) -> None:
        self.llm = llm
        self.config = config or RefinementConfig()

    async def refine(
        self,
        agent: Any,  # BaseAgent instance with run(context) method
        context: ContextPackage,
        initial_output: AgentOutput,
    ) -> tuple[AgentOutput, RefinementResult]:
        """Run the iterative refinement loop on an agent's output.

        Args:
            agent: The agent to re-run for revisions.
            context: Original context package for the agent.
            initial_output: The first-pass output to evaluate.

        Returns:
            Tuple of (best AgentOutput, RefinementResult with loop metadata).
        """
        result = RefinementResult()
        best_output = initial_output

        # Guard: skip if initial output errored
        if not initial_output.is_success:
            result.stopped_reason = "skipped"
            return best_output, result

        # Score initial output
        critique, score_cost = await self._score_output(initial_output, context)
        result.total_cost += score_cost
        result.quality_scores.append(critique.overall_score)
        result.critiques.append(critique)

        logger.info(
            "Refinement initial score: %.2f (threshold: %.2f)",
            critique.overall_score,
            self.config.quality_threshold,
        )

        # Guard: already good enough
        if critique.overall_score >= self.config.quality_threshold:
            result.stopped_reason = "quality_met"
            return best_output, result

        # Iterative refinement loop
        for iteration in range(self.config.max_iterations):
            # Guard: budget check
            if result.total_cost >= self.config.budget_cap:
                result.stopped_reason = "budget_exhausted"
                logger.info("Refinement stopped: budget exhausted ($%.4f >= $%.2f)",
                            result.total_cost, self.config.budget_cap)
                break

            # Build revision context with critique feedback
            revision_context = self._build_revision_context(
                context, best_output, critique,
            )

            # Re-run the agent with critique feedback
            try:
                revised_output = await agent.run(revision_context)
            except Exception as e:
                logger.warning("Refinement iteration %d failed: %s", iteration + 1, e)
                result.stopped_reason = "agent_error"
                break

            if not revised_output.is_success:
                logger.warning("Refinement iteration %d returned error: %s",
                               iteration + 1, revised_output.error)
                result.stopped_reason = "agent_error"
                break

            result.total_cost += revised_output.cost
            result.iterations_used += 1

            # Score revised output
            critique, score_cost = await self._score_output(revised_output, context)
            result.total_cost += score_cost
            result.quality_scores.append(critique.overall_score)
            result.critiques.append(critique)

            logger.info(
                "Refinement iteration %d: score %.2f → %.2f",
                iteration + 1,
                result.quality_scores[-2],
                critique.overall_score,
            )

            # Keep the best output seen (strictly better than previous best)
            if critique.overall_score > max(result.quality_scores[:-1]):
                best_output = revised_output

            # Guard: quality met
            if critique.overall_score >= self.config.quality_threshold:
                result.stopped_reason = "quality_met"
                break

            # Guard: diminishing returns
            improvement = critique.overall_score - result.quality_scores[-2]
            if improvement < self.config.min_improvement:
                result.stopped_reason = "diminishing_returns"
                logger.info(
                    "Refinement stopped: diminishing returns (Δ%.3f < %.3f)",
                    improvement, self.config.min_improvement,
                )
                break
        else:
            # Loop completed without breaking
            result.stopped_reason = "max_iterations"

        return best_output, result

    async def _score_output(
        self,
        output: AgentOutput,
        context: ContextPackage,
    ) -> tuple[QualityCritique, float]:
        """Score an agent output using the quality scorer (Haiku).

        Returns:
            Tuple of (QualityCritique, cost_of_scoring).
        """
        scorer_tier: ModelTier = self.config.scorer_model  # type: ignore[assignment]

        # Build scoring prompt from output + original task
        scoring_message = self._build_scoring_message(output, context)

        critique, meta = await self.llm.complete_structured(
            messages=[{"role": "user", "content": scoring_message}],
            model_tier=scorer_tier,
            response_model=QualityCritique,
            system=_SCORER_SYSTEM_PROMPT,
            temperature=0.0,
        )

        return critique, meta.cost

    def _build_scoring_message(
        self,
        output: AgentOutput,
        context: ContextPackage,
    ) -> str:
        """Build the scoring prompt from agent output and original context."""
        parts = [
            "## Original Task\n",
            context.task_description,
            "\n\n## Agent Output to Evaluate\n",
        ]

        # Include the output content
        if isinstance(output.output, dict):
            # Pretty-format dict output
            import json
            parts.append(json.dumps(output.output, indent=2, default=str)[:8000])
        elif isinstance(output.output, str):
            parts.append(output.output[:8000])
        elif output.output is not None:
            parts.append(str(output.output)[:8000])

        if output.summary:
            parts.append(f"\n\n## Summary\n{output.summary}")

        parts.append(
            "\n\n## Instructions\n"
            "Score this output on rigor, completeness, clarity, accuracy, "
            "and overall quality. Identify specific issues and provide "
            "actionable improvement suggestions. Note strengths to preserve."
        )

        return "\n".join(parts)

    def _build_revision_context(
        self,
        original_context: ContextPackage,
        output: AgentOutput,
        critique: QualityCritique,
    ) -> ContextPackage:
        """Build a new context with critique feedback for revision.

        Injects the quality critique into prior_step_outputs so the agent
        sees feedback from the previous iteration.
        """
        # Format critique as a feedback dict
        feedback = {
            "type": "quality_critique",
            "overall_score": critique.overall_score,
            "scores": {
                "rigor": critique.rigor_score,
                "completeness": critique.completeness_score,
                "clarity": critique.clarity_score,
                "accuracy": critique.accuracy_score,
            },
            "issues": critique.issues,
            "suggestions": critique.suggestions,
            "strengths": critique.strengths,
            "instruction": (
                "Your previous output was scored {:.2f}/1.0. "
                "Please revise addressing the issues listed above while "
                "preserving the identified strengths. "
                "Focus especially on: {}".format(
                    critique.overall_score,
                    ", ".join(critique.issues[:3]) if critique.issues else "general quality improvement",
                )
            ),
        }

        # Include previous output so agent can revise it
        previous_output = {
            "type": "previous_output_for_revision",
            "output": output.output,
            "summary": output.summary,
        }

        # Build new context with critique injected
        return ContextPackage(
            task_description=original_context.task_description,
            relevant_memory=original_context.relevant_memory,
            prior_step_outputs=[
                *original_context.prior_step_outputs,
                previous_output,
                feedback,
            ],
            negative_results=original_context.negative_results,
            rcmxt_context=original_context.rcmxt_context,
            constraints={
                **original_context.constraints,
                "refinement_mode": True,
            },
            metadata={**original_context.metadata},  # Preserve available_papers etc.
        )
