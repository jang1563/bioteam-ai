"""Methodology Reviewer Agent — deep methodological assessment for peer review.

Used by W8 Paper Review workflow (METHODOLOGY_REVIEW step) to provide
structured evaluation of study design, statistics, controls, and biases.

Uses Opus model tier for deep analysis.
"""

from __future__ import annotations

import logging

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from app.models.peer_review import MethodologyAssessment

logger = logging.getLogger(__name__)


class MethodologyReviewerAgent(BaseAgent):
    """Deep methodological assessment of a research paper.

    Receives paper sections + extracted claims + background literature context
    and returns a MethodologyAssessment with detailed critique.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Assess paper methodology.

        Expects context.task_description to contain the paper methods section
        and related context. context.prior_step_outputs should include
        extracted claims and background literature results.
        """
        paper_context = context.task_description
        if not paper_context or len(paper_context.strip()) < 50:
            return self.build_output(
                output=MethodologyAssessment(
                    study_design_critique="No paper text provided",
                    statistical_methods="N/A",
                    controls_adequacy="N/A",
                    sample_size_assessment="N/A",
                ).model_dump(),
                summary="No paper text provided for methodology review",
            )

        # Build comprehensive prompt with prior step context
        prompt_parts = [
            "Perform a detailed methodology review of the following paper. "
            "Assess study design, statistical methods, controls, sample sizes, "
            "potential biases, and reproducibility.\n"
        ]

        # Include prior outputs if available (list[dict] format)
        if context.prior_step_outputs:
            for entry in context.prior_step_outputs:
                if not isinstance(entry, dict):
                    continue
                step_id = entry.get("step_id", "")
                output = entry.get("output", entry)

                if step_id == "EXTRACT_CLAIMS" and isinstance(output, dict):
                    claims_summary = output.get("claims", [])
                    if claims_summary:
                        prompt_parts.append(
                            f"\n--- EXTRACTED CLAIMS ({len(claims_summary)} total) ---\n"
                        )
                        for i, claim in enumerate(claims_summary[:20], 1):
                            ct = claim.get("claim_text", "")
                            prompt_parts.append(f"{i}. [{claim.get('claim_type', '?')}] {ct}")
                        prompt_parts.append("--- END CLAIMS ---\n")

                elif step_id == "BACKGROUND_LIT" and isinstance(output, dict):
                    lit_summary = output.get("summary", "")
                    if lit_summary:
                        prompt_parts.append(
                            f"\n--- BACKGROUND LITERATURE ---\n{lit_summary[:5000]}\n--- END ---\n"
                        )

        prompt_parts.append(f"\n--- PAPER TEXT ---\n{paper_context}\n--- END ---")

        result, meta = await self.llm.complete_structured(
            messages=[
                {"role": "user", "content": "\n".join(prompt_parts)},
            ],
            model_tier=self.model_tier,
            response_model=MethodologyAssessment,
            system=self.system_prompt_cached,
        )

        n_biases = len(result.potential_biases)
        n_strengths = len(result.strengths)
        summary = (
            f"Methodology score: {result.overall_methodology_score:.2f} — "
            f"{n_strengths} strengths, {n_biases} biases identified"
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="MethodologyAssessment",
            summary=summary,
            llm_response=meta,
        )
