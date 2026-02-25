"""DigestAgent — LLM-powered research digest summarization.

Lightweight agent (haiku tier) that takes a batch of discovered papers/repos
and produces a structured summary report. Does NOT perform fetching —
that is handled by the DigestPipeline.

Responsibilities:
- Summarize a batch of papers/repos into an executive summary
- Identify highlights and trends across sources
- Recommend top papers to read in full
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage


class DigestHighlight(BaseModel):
    """A single highlight entry in the digest."""

    title: str
    source: str  # "arxiv", "pubmed", etc.
    one_liner: str
    why_important: str = ""


class DigestSummary(BaseModel):
    """LLM output for digest summarization."""

    executive_summary: str = Field(description="3-5 sentence overview of this digest period")
    highlights: list[DigestHighlight] = Field(
        default_factory=list,
        description="Top 5-8 notable papers/repos with one-line summaries",
    )
    trends: list[str] = Field(
        default_factory=list,
        description="Observed trends across the papers (2-4 trends)",
    )
    recommended_reads: list[str] = Field(
        default_factory=list,
        description="Top 3-5 paper titles recommended for full reading",
    )


class DigestAgent(BaseAgent):
    """Agent for summarizing research digest entries.

    Uses haiku tier for cost efficiency (~$0.01 per digest).
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Summarize a batch of papers into a digest report.

        Expects context.task_description to contain a JSON string with:
        - topic_name: str
        - entries: list of dicts with {title, source, abstract, authors, ...}
        """
        return await self.summarize(context)

    async def summarize(self, context: ContextPackage) -> AgentOutput:
        """Generate a structured digest summary from paper entries.

        Args:
            context: ContextPackage where task_description contains JSON
                     of entries to summarize.

        Returns:
            AgentOutput with DigestSummary as output.
        """
        task_desc = context.task_description

        # Build the user message with the entries
        user_message = (
            f"Summarize the following research papers and repositories "
            f"into a digest report.\n\n{task_desc}"
        )

        result, meta = await self.llm.complete_structured(
            messages=[{"role": "user", "content": user_message}],
            model_tier=self.model_tier,
            response_model=DigestSummary,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="DigestSummary",
            summary=result.executive_summary[:200],
            llm_response=meta,
        )
