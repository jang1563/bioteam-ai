"""Scientific Communication Agent (Team 8) — writing, visualization, audience adaptation.

Responsibilities:
1. Scientific document drafting (abstracts, manuscripts, lay summaries)
2. Structure and messaging optimization for target audiences
3. Figure caption and presentation support
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field

# === Output Models ===


class SciCommResult(BaseModel):
    """Result of a scientific communication task."""

    query: str = ""
    document_type: str = ""
    content: str = ""
    structure: list[str] = Field(default_factory=list)
    key_messages: list[str] = Field(default_factory=list)
    target_audience: str = ""
    summary: str = ""
    confidence: float = 0.0
    suggestions: list[str] = Field(default_factory=list)


# === Agent Implementation ===


class SciCommAgent(BaseAgent):
    """Specialist agent for scientific communication and writing.

    Drafts, structures, and refines scientific documents for diverse
    audiences — from journal reviewers to public stakeholders.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Draft or refine a scientific communication document."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Handle this scientific communication task:\n\n"
                    f"{context.task_description}\n\n"
                    f"Provide the document content, a clear structure, "
                    f"key messages, target audience identification, "
                    f"and actionable suggestions for improvement."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=SciCommResult,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="SciCommResult",
            summary=result.summary[:200] if result.summary else f"SciComm: {context.task_description[:100]}",
            llm_response=meta,
        )
