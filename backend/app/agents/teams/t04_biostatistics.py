"""Biostatistics Agent (Team 4) — Experimental design, statistical testing, power analysis.

Responsibilities:
1. Statistical method recommendation and analysis (default run)
2. Power and sample size calculations
3. Multiple testing correction guidance
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field

# === Output Models ===


class StatisticalAnalysisResult(BaseModel):
    """Result of a biostatistical analysis or design query."""

    query: str
    methods_recommended: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    sample_size_estimate: int = 0
    effect_size: str = ""
    power: float = 0.0
    corrections: list[str] = Field(default_factory=list)
    summary: str = ""
    confidence: float = 0.0
    caveats: list[str] = Field(default_factory=list)


# === Agent Implementation ===


class BiostatisticsAgent(BaseAgent):
    """Specialist agent for biostatistics and experimental design.

    Covers hypothesis testing, power analysis, multiple testing correction,
    survival analysis, mixed-effects models, and Bayesian approaches.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Answer a biostatistics or experimental design query."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Analyze this biostatistics query:\n\n"
                    f"{context.task_description}\n\n"
                    f"Provide a structured analysis including recommended statistical "
                    f"methods, assumptions to verify, sample size and power estimates, "
                    f"multiple testing corrections, and confidence level."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=StatisticalAnalysisResult,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="StatisticalAnalysisResult",
            summary=result.summary[:200] if result.summary else f"Analyzed: {context.task_description[:100]}",
            llm_response=meta,
        )
