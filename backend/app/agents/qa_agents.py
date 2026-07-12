"""QA Agents — quality assurance agents for statistical rigor, biological plausibility, and reproducibility.

Three independent QA agents in a single module:
1. StatisticalRigorQA — validates statistical methods, effect sizes, and power
2. BiologicalPlausibilityQA — checks pathway validity and artifact flags
3. ReproducibilityQA — assesses FAIR compliance, metadata, and code reproducibility
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field

# === Output Models ===


class StatisticalRigorResult(BaseModel):
    """Result of a statistical rigor quality assessment."""

    query: str = ""
    issues_found: list[dict] = Field(default_factory=list)
    corrections_needed: list[str] = Field(default_factory=list)
    effect_sizes_valid: bool = True
    power_adequate: bool = True
    overall_verdict: str = ""
    summary: str = ""
    confidence: float = 0.0


class BiologicalPlausibilityResult(BaseModel):
    """Result of a biological plausibility quality assessment."""

    query: str = ""
    pathway_validity: list[dict] = Field(default_factory=list)
    artifact_flags: list[str] = Field(default_factory=list)
    literature_consistency: str = ""
    overall_verdict: str = ""
    summary: str = ""
    confidence: float = 0.0


class ReproducibilityResult(BaseModel):
    """Result of a reproducibility quality assessment."""

    query: str = ""
    fair_compliance: dict = Field(default_factory=dict)
    metadata_completeness: float = 0.0
    code_reproducibility: str = ""
    environment_specified: bool = False
    overall_verdict: str = ""
    summary: str = ""
    confidence: float = 0.0


# === Agent Implementations ===


class StatisticalRigorQA(BaseAgent):
    """QA agent that validates statistical methods, effect sizes, and power.

    Reviews analyses for correct test selection, multiple testing correction,
    appropriate effect size reporting, and adequate statistical power.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Assess statistical rigor of an analysis or result."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Assess the statistical rigor of this analysis:\n\n"
                    f"{context.task_description}\n\n"
                    f"Check for: correct test selection, effect size validity, "
                    f"power adequacy, multiple testing corrections, "
                    f"and any statistical issues that need correction."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=StatisticalRigorResult,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="StatisticalRigorResult",
            summary=result.summary[:200] if result.summary else f"StatQA: {result.overall_verdict}",
            llm_response=meta,
        )


class BiologicalPlausibilityQA(BaseAgent):
    """QA agent that checks biological plausibility of findings.

    Validates pathway annotations, flags potential artifacts,
    and checks consistency with established biological knowledge.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Assess biological plausibility of findings."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Assess the biological plausibility of these findings:\n\n"
                    f"{context.task_description}\n\n"
                    f"Check for: pathway validity, potential artifacts, "
                    f"consistency with known biology, and any biologically "
                    f"implausible claims."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=BiologicalPlausibilityResult,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="BiologicalPlausibilityResult",
            summary=result.summary[:200] if result.summary else f"BioQA: {result.overall_verdict}",
            llm_response=meta,
        )


class ReproducibilityQA(BaseAgent):
    """QA agent that assesses reproducibility and FAIR compliance.

    Checks metadata completeness, code reproducibility,
    environment specification, and FAIR data principles adherence.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Assess reproducibility of a study or analysis."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Assess the reproducibility of this study or analysis:\n\n"
                    f"{context.task_description}\n\n"
                    f"Check for: FAIR compliance (Findable, Accessible, "
                    f"Interoperable, Reusable), metadata completeness, "
                    f"code availability and reproducibility, and "
                    f"environment specification."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=ReproducibilityResult,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="ReproducibilityResult",
            summary=result.summary[:200] if result.summary else f"ReproQA: {result.overall_verdict}",
            llm_response=meta,
        )
