"""Systems Biology & Networks Agent (Team 6) — Pathway analysis, network inference, multi-omics integration.

Responsibilities:
1. Pathway enrichment and network analysis (default run)
2. Hub gene and module identification
3. Multi-omics data integration at the systems level

Integrations (config-gated):
- STRING DB v12: protein-protein interaction networks, PPI scores
- g:Profiler: GO/Reactome/KEGG functional enrichment with g:SCS correction
"""

from __future__ import annotations

import asyncio
import logging
import re

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_GENE_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]{1,7})\b")
_GENE_STOPWORDS = {
    "RNA", "DNA", "PCR", "GO", "BP", "MF", "CC", "KEGG", "REAC",
    "PPI", "CI", "OR", "HR", "FC", "AUC", "ROC", "SD", "SE",
}


def _extract_gene_candidates(text: str) -> list[str]:
    candidates = _GENE_PATTERN.findall(text)
    return [g for g in candidates if g not in _GENE_STOPWORDS][:10]


async def _fetch_network_context(genes: list[str]) -> str:
    """Fetch STRING interactions and GO enrichment for gene candidates."""
    if not genes:
        return ""
    parts: list[str] = []

    async def _fetch_string() -> str:
        try:
            from app.integrations.stringdb import STRINGClient

            client = STRINGClient()
            interactions = await client.get_interactions(genes[:8], min_score=700, limit=20)
            if not interactions:
                return ""
            top = interactions[:10]
            edges = [
                f"{i.get('preferredName_A','?')}↔{i.get('preferredName_B','?')} (score {i.get('score',0):.2f})"
                for i in top
            ]
            return f"STRING DB (high-confidence PPI): {'; '.join(edges)}"
        except Exception as e:
            logger.debug("STRING fetch failed: %s", e)
        return ""

    async def _fetch_go() -> str:
        try:
            from app.integrations.go_enrichment import GOEnrichmentClient

            client = GOEnrichmentClient()
            results = await client.run_enrichment(genes[:10])
            if not results:
                return ""
            formatted = client.format_for_agent(results, top_n=8)
            return f"g:Profiler enrichment:\n{formatted}"
        except Exception as e:
            logger.debug("GO enrichment failed: %s", e)
        return ""

    string_result, go_result = await asyncio.gather(_fetch_string(), _fetch_go())
    if string_result:
        parts.append(string_result)
    if go_result:
        parts.append(go_result)

    return "\n\n".join(parts)


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

    Enriches LLM context with live data from STRING DB and g:Profiler when enabled.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Answer a systems biology or network analysis query."""
        task = context.task_description
        genes = _extract_gene_candidates(task)
        live_context = ""
        if genes:
            try:
                live_context = await asyncio.wait_for(
                    _fetch_network_context(genes), timeout=15.0
                )
            except asyncio.TimeoutError:
                logger.debug("Network context fetch timed out")

        enrichment_block = (
            f"\n\n--- Live Data Context (STRING DB / g:Profiler) ---\n{live_context}\n"
            if live_context
            else ""
        )

        messages = [
            {
                "role": "user",
                "content": (
                    f"Analyze this systems biology / network query:\n\n"
                    f"{task}"
                    f"{enrichment_block}\n\n"
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
            summary=result.summary[:200] if result.summary else f"Analyzed: {task[:100]}",
            llm_response=meta,
        )
