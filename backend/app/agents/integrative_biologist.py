"""Integrative Biologist Agent — cross-omics synthesis and multi-layer analysis.

Responsibilities:
1. Multi-omics data integration and cross-layer analysis
2. Pathway consensus identification across omics layers
3. Mechanistic link inference from integrated datasets
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field

# === Output Models ===


class IntegrativeAnalysisResult(BaseModel):
    """Result of a multi-omics integrative analysis."""

    query: str = ""
    omics_layers: list[str] = Field(default_factory=list)
    cross_omics_findings: list[dict] = Field(default_factory=list)
    pathway_consensus: list[str] = Field(default_factory=list)
    mechanistic_links: list[str] = Field(default_factory=list)
    confidence_per_layer: dict = Field(default_factory=dict)
    summary: str = ""
    confidence: float = 0.0
    caveats: list[str] = Field(default_factory=list)


# === Agent Implementation ===


class IntegrativeBiologistAgent(BaseAgent):
    """Cross-cutting agent for multi-omics integration and systems-level synthesis.

    Bridges findings across genomics, transcriptomics, proteomics,
    metabolomics, and epigenomics to identify convergent biological
    mechanisms and pathway-level consensus.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Perform integrative multi-omics analysis."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Perform an integrative multi-omics analysis for:\n\n"
                    f"{context.task_description}\n\n"
                    f"Identify cross-omics findings, pathway consensus, "
                    f"mechanistic links between layers, and confidence "
                    f"assessments per omics layer. Note any caveats."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=IntegrativeAnalysisResult,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="IntegrativeAnalysisResult",
            summary=result.summary[:200] if result.summary else f"Integration: {context.task_description[:100]}",
            llm_response=meta,
        )
