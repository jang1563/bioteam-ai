"""Genomics & Epigenomics Agent (Team 1) — WGS, WES, WGBS, ChIP-seq, ATAC-seq analysis.

Responsibilities:
1. Variant analysis and interpretation (default run)
2. Epigenetic mark characterization
3. Pathway enrichment from genomic data
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field

# === Output Models ===


class GenomicsAnalysisResult(BaseModel):
    """Result of a genomics / epigenomics analysis query."""

    query: str
    variants_analyzed: list[str] = Field(default_factory=list)
    epigenetic_marks: list[str] = Field(default_factory=list)
    pathways: list[str] = Field(default_factory=list)
    methodology: str = ""
    datasets_used: list[str] = Field(default_factory=list)
    summary: str = ""
    confidence: float = 0.0
    caveats: list[str] = Field(default_factory=list)


# === Agent Implementation ===


class GenomicsAgent(BaseAgent):
    """Specialist agent for genomics and epigenomics analysis.

    Covers whole-genome sequencing, exome sequencing, bisulfite sequencing,
    ChIP-seq, ATAC-seq, and variant interpretation.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Answer a genomics or epigenomics analysis query."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Analyze this genomics/epigenomics query:\n\n"
                    f"{context.task_description}\n\n"
                    f"Provide a structured analysis including variants or epigenetic "
                    f"marks identified, affected pathways, methodology, datasets "
                    f"consulted, and confidence level."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=GenomicsAnalysisResult,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="GenomicsAnalysisResult",
            summary=result.summary[:200] if result.summary else f"Analyzed: {context.task_description[:100]}",
            llm_response=meta,
        )
