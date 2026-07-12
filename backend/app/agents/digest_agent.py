"""DigestAgent — LLM-powered research digest summarization.

Lightweight agent that takes a batch of discovered papers/repos
and produces a structured summary report. Does NOT perform fetching —
that is handled by the DigestPipeline.

Supports two LLM providers (configurable via DIGEST_LLM_PROVIDER):
- "gemini" (default): Google Gemini 2.5 Flash free tier — $0 cost
- "anthropic": Claude Haiku — ~$0.01 per digest

Responsibilities:
- Summarize a batch of papers/repos into an executive summary
- Identify highlights and trends across sources
- Recommend top papers to read in full
"""

from __future__ import annotations

import logging

from app.agents.base import BaseAgent
from app.config import settings
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DigestHighlight(BaseModel):
    """A single highlight entry in the digest."""

    title: str
    source: str  # "arxiv", "pubmed", etc.
    one_liner: str
    why_important: str = ""
    url: str = ""


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

    Default: Gemini 2.5 Flash (free). Set DIGEST_LLM_PROVIDER=anthropic for Claude.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._gemini_layer = None

    def _get_gemini_layer(self):
        """Lazy-init GeminiLayer for digest summarization."""
        if self._gemini_layer is None:
            from app.llm.gemini_layer import GeminiLayer
            self._gemini_layer = GeminiLayer()
        return self._gemini_layer

    @property
    def _use_gemini(self) -> bool:
        """Check if Gemini should be used for digest summarization."""
        # Keep tests deterministic when using MockLLMLayer fixtures.
        if self.llm.__class__.__name__ == "MockLLMLayer":
            return False
        return (
            settings.digest_llm_provider == "gemini"
            and bool(settings.google_api_key)
        )

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Summarize a batch of papers into a digest report.

        Expects context.task_description to contain a JSON string with:
        - topic_name: str
        - entries: list of dicts with {title, source, abstract, authors, ...}
        """
        return await self.summarize(context)

    async def summarize(self, context: ContextPackage) -> AgentOutput:
        """Generate a structured digest summary from paper entries.

        Uses Gemini (free) when configured, falls back to Claude (paid).

        Args:
            context: ContextPackage where task_description contains JSON
                     of entries to summarize.

        Returns:
            AgentOutput with DigestSummary as output.
        """
        task_desc = context.task_description

        user_message = (
            f"Summarize the following research papers and repositories "
            f"into a digest report.\n\n{task_desc}"
        )

        if self._use_gemini:
            return await self._summarize_with_gemini(user_message)

        return await self._summarize_with_anthropic(user_message)

    async def _summarize_with_gemini(self, user_message: str) -> AgentOutput:
        """Summarize using Gemini 2.0 Flash (free tier)."""
        gemini = self._get_gemini_layer()

        try:
            result, meta = await gemini.complete_structured(
                messages=[{"role": "user", "content": user_message}],
                response_model=DigestSummary,
                system=self._system_prompt,
            )

            return AgentOutput(
                agent_id=self.agent_id,
                output=result.model_dump(),
                output_type="DigestSummary",
                summary=result.executive_summary[:200],
                model_tier="haiku",  # Equivalent tier for tracking
                model_version=meta.model_version,
                input_tokens=meta.input_tokens,
                output_tokens=meta.output_tokens,
                cost=0.0,  # Free tier
            )
        except Exception as e:
            logger.warning("Gemini digest failed, falling back to Anthropic: %s", e)
            return await self._summarize_with_anthropic(user_message)

    async def _summarize_with_anthropic(self, user_message: str) -> AgentOutput:
        """Summarize using Claude (paid, original implementation)."""
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
