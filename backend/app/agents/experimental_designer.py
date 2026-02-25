"""Experimental Designer Agent — cross-cutting experiment design and power analysis.

Responsibilities:
1. Experimental design specification (groups, controls, randomization)
2. Sample size and power analysis guidance
3. Statistical test selection and blocking strategy
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field

# === Output Models ===


class ExperimentalDesignResult(BaseModel):
    """Result of an experimental design task."""

    query: str = ""
    design_type: str = ""
    groups: list[dict] = Field(default_factory=list)
    sample_size: int = 0
    power_analysis: str = ""
    controls: list[str] = Field(default_factory=list)
    randomization: str = ""
    blocking_strategy: str = ""
    statistical_tests: list[str] = Field(default_factory=list)
    summary: str = ""
    confidence: float = 0.0
    caveats: list[str] = Field(default_factory=list)


# === Agent Implementation ===


class ExperimentalDesignerAgent(BaseAgent):
    """Cross-cutting agent for experimental design and statistical planning.

    Provides rigorous experimental designs with appropriate controls,
    randomization strategies, power calculations, and statistical
    test recommendations across all biological domains.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Design an experiment based on the research question."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Design an experiment for this research question:\n\n"
                    f"{context.task_description}\n\n"
                    f"Provide the experimental design type, group definitions, "
                    f"sample size with power analysis justification, controls, "
                    f"randomization strategy, blocking, and recommended "
                    f"statistical tests."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=ExperimentalDesignResult,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="ExperimentalDesignResult",
            summary=result.summary[:200] if result.summary else f"Design: {context.task_description[:100]}",
            llm_response=meta,
        )
