"""Claim Extractor Agent — extract structured scientific claims from paper text.

Used by W8 Paper Review workflow (EXTRACT_CLAIMS step) to identify and
categorize all substantive claims in a research paper.
"""

from __future__ import annotations

import logging

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from app.models.peer_review import PaperClaimsExtraction

logger = logging.getLogger(__name__)


class ClaimExtractorAgent(BaseAgent):
    """Extract structured claims from scientific paper text.

    Receives parsed paper text (full or per-section) in context.task_description
    and returns a PaperClaimsExtraction with all claims, paper type, and methods.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Extract claims from paper text.

        Expects context.task_description to contain the paper text
        (full or section-structured) for claim extraction.
        """
        paper_text = context.task_description
        if not paper_text or len(paper_text.strip()) < 50:
            return self.build_output(
                output=PaperClaimsExtraction().model_dump(),
                summary="No paper text provided for claim extraction",
            )

        # Truncate very long papers to avoid token limits
        max_chars = 80_000
        if len(paper_text) > max_chars:
            paper_text = paper_text[:max_chars] + "\n\n[TEXT TRUNCATED]"

        result, meta = await self.llm.complete_structured(
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Extract all scientific claims from the following paper text. "
                        "Identify the paper type, stated hypothesis, and key methods. "
                        "Focus on the most important claims (main findings and key methodology "
                        "claims). Limit to 30 claims maximum.\n\n"
                        f"--- PAPER TEXT ---\n{paper_text}\n--- END ---"
                    ),
                },
            ],
            model_tier=self.model_tier,
            response_model=PaperClaimsExtraction,
            system=self.system_prompt_cached,
            max_tokens=16384,
        )

        n_claims = len(result.claims)
        n_main = sum(1 for c in result.claims if c.claim_type == "main_finding")
        summary = (
            f"Extracted {n_claims} claims ({n_main} main findings) "
            f"from {result.paper_type} paper"
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="PaperClaimsExtraction",
            summary=summary,
            llm_response=meta,
        )
