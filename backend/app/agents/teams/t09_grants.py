"""Grant Writing & Funding Agent (Team 9) — proposal strategy, aims, budgets.

Responsibilities:
1. Grant proposal drafting (Specific Aims, Significance, Innovation, Approach)
2. Funding agency and mechanism identification
3. Budget planning and justification
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field

# === Output Models ===


class GrantWritingResult(BaseModel):
    """Result of a grant writing or funding strategy task."""

    query: str = ""
    agency: str = ""
    mechanism: str = ""
    specific_aims: list[str] = Field(default_factory=list)
    significance: str = ""
    innovation: str = ""
    approach_summary: str = ""
    budget_considerations: list[str] = Field(default_factory=list)
    summary: str = ""
    confidence: float = 0.0
    caveats: list[str] = Field(default_factory=list)


# === Agent Implementation ===


class GrantWritingAgent(BaseAgent):
    """Specialist agent for grant writing and funding strategy.

    Drafts grant sections, identifies appropriate funding mechanisms,
    and provides budget guidance aligned with agency expectations.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Draft grant content or provide funding strategy advice."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Handle this grant writing / funding task:\n\n"
                    f"{context.task_description}\n\n"
                    f"Provide the appropriate grant sections including "
                    f"specific aims, significance, innovation, approach summary, "
                    f"funding agency and mechanism recommendations, "
                    f"and budget considerations."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=GrantWritingResult,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="GrantWritingResult",
            summary=result.summary[:200] if result.summary else f"Grant: {context.task_description[:100]}",
            llm_response=meta,
        )
