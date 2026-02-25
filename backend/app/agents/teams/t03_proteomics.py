"""Proteomics & Metabolomics Agent (Team 3) — Mass spectrometry, protein quantification, metabolite profiling.

Responsibilities:
1. Protein identification and quantification (default run)
2. Metabolite pathway analysis
3. Multi-omics integration at the protein/metabolite level
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field

# === Output Models ===


class ProteomicsAnalysisResult(BaseModel):
    """Result of a proteomics / metabolomics analysis query."""

    query: str
    proteins_analyzed: list[str] = Field(default_factory=list)
    metabolites: list[str] = Field(default_factory=list)
    pathways: list[str] = Field(default_factory=list)
    methodology: str = ""
    datasets_used: list[str] = Field(default_factory=list)
    summary: str = ""
    confidence: float = 0.0
    caveats: list[str] = Field(default_factory=list)


# === Agent Implementation ===


class ProteomicsAgent(BaseAgent):
    """Specialist agent for proteomics and metabolomics analysis.

    Covers mass spectrometry-based proteomics (TMT, label-free, DIA),
    targeted and untargeted metabolomics, and protein-metabolite integration.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Answer a proteomics or metabolomics analysis query."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Analyze this proteomics/metabolomics query:\n\n"
                    f"{context.task_description}\n\n"
                    f"Provide a structured analysis including proteins or metabolites "
                    f"identified, affected pathways, methodology, datasets consulted, "
                    f"and confidence level."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=ProteomicsAnalysisResult,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="ProteomicsAnalysisResult",
            summary=result.summary[:200] if result.summary else f"Analyzed: {context.task_description[:100]}",
            llm_response=meta,
        )
