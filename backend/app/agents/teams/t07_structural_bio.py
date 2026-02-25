"""Structural Biology Agent (Team 7) — Protein structure, molecular docking, binding site analysis.

Responsibilities:
1. Protein structure analysis and prediction (default run)
2. Binding site identification and characterization
3. Molecular docking interpretation
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field

# === Output Models ===


class StructuralAnalysisResult(BaseModel):
    """Result of a structural biology analysis query."""

    query: str
    proteins_analyzed: list[str] = Field(default_factory=list)
    structures: list[dict] = Field(default_factory=list)
    binding_sites: list[str] = Field(default_factory=list)
    docking_results: list[dict] = Field(default_factory=list)
    methodology: str = ""
    pdb_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    confidence: float = 0.0
    caveats: list[str] = Field(default_factory=list)


# === Agent Implementation ===


class StructuralBiologyAgent(BaseAgent):
    """Specialist agent for structural biology and molecular modeling.

    Covers protein structure prediction (AlphaFold2), molecular docking,
    binding site analysis, protein-ligand interactions, and structure-based
    drug design.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Answer a structural biology or molecular modeling query."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Analyze this structural biology query:\n\n"
                    f"{context.task_description}\n\n"
                    f"Provide a structured analysis including proteins analyzed, "
                    f"relevant structures (PDB IDs), binding sites, docking results, "
                    f"methodology, and confidence level."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=StructuralAnalysisResult,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="StructuralAnalysisResult",
            summary=result.summary[:200] if result.summary else f"Analyzed: {context.task_description[:100]}",
            llm_response=meta,
        )
