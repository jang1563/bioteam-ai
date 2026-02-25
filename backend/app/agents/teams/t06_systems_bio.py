"""Systems Biology & Networks Agent (Team 6) — Pathway analysis, network inference, multi-omics integration.

Responsibilities:
1. Pathway enrichment and network analysis (default run)
2. Hub gene and module identification
3. Multi-omics data integration at the systems level
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field

# === Output Models ===


class NetworkAnalysisResult(BaseModel):
    """Result of a systems biology / network analysis query."""

    query: str
    enriched_pathways: list[dict] = Field(default_factory=list)
    hub_genes: list[str] = Field(default_factory=list)
    network_modules: list[dict] = Field(default_factory=list)
    databases_used: list[str] = Field(default_factory=list)
    methodology: str = ""
    summary: str = ""
    confidence: float = 0.0
    caveats: list[str] = Field(default_factory=list)


# === Agent Implementation ===


class SystemsBiologyAgent(BaseAgent):
    """Specialist agent for systems biology and biological network analysis.

    Covers pathway enrichment, gene regulatory network inference,
    protein-protein interaction networks, WGCNA, and multi-omics integration.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Answer a systems biology or network analysis query."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Analyze this systems biology / network query:\n\n"
                    f"{context.task_description}\n\n"
                    f"Provide a structured analysis including enriched pathways, "
                    f"hub genes, network modules, databases consulted, methodology, "
                    f"and confidence level."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=NetworkAnalysisResult,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="NetworkAnalysisResult",
            summary=result.summary[:200] if result.summary else f"Analyzed: {context.task_description[:100]}",
            llm_response=meta,
        )
