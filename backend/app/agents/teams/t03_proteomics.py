"""Proteomics & Metabolomics Agent (Team 3) — Mass spectrometry, protein quantification, metabolite profiling.

Responsibilities:
1. Protein identification and quantification (default run)
2. Metabolite pathway analysis
3. Multi-omics integration at the protein/metabolite level

Integrations (config-gated):
- UniProt REST v2: reviewed protein entries, function, subcellular location, interactions
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
    "RNA", "DNA", "PCR", "MS", "LC", "TMT", "DIA", "DDA", "LFQ",
    "AUC", "ROC", "CI", "OR", "HR", "FC", "LFC", "SD", "SE",
}
_UNIPROT_ACC_PATTERN = re.compile(
    r"\b([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})\b"
)


def _extract_gene_candidates(text: str) -> list[str]:
    candidates = _GENE_PATTERN.findall(text)
    return [g for g in candidates if g not in _GENE_STOPWORDS][:5]


def _extract_uniprot_accessions(text: str) -> list[str]:
    return _UNIPROT_ACC_PATTERN.findall(text)[:3]


async def _fetch_uniprot_context(genes: list[str], accessions: list[str]) -> str:
    """Fetch UniProt protein data for given gene symbols and/or accessions."""
    if not genes and not accessions:
        return ""
    parts: list[str] = []
    try:
        from app.integrations.uniprot import UniProtClient

        client = UniProtClient()

        async def _by_gene(gene: str) -> str:
            try:
                results = await client.search_by_gene(gene, organism=9606, limit=1, reviewed_only=True)
                if results:
                    entry = results[0]
                    name = entry.get("proteinDescription", {}).get("recommendedName", {})
                    full_name = name.get("fullName", {}).get("value", "") if name else ""
                    function_texts = []
                    for comment in entry.get("comments", []):
                        if comment.get("commentType") == "FUNCTION":
                            for text_obj in comment.get("texts", []):
                                function_texts.append(text_obj.get("value", "")[:200])
                    acc = entry.get("primaryAccession", "")
                    fn = function_texts[0] if function_texts else ""
                    return f"UniProt [{gene}] ({acc}): {full_name}. {fn}"
            except Exception as e:
                logger.debug("UniProt search failed for %s: %s", gene, e)
            return ""

        async def _by_acc(acc: str) -> str:
            try:
                entry = await client.get_entry(acc)
                if entry:
                    gene_sym = ""
                    for gn in entry.get("genes", []):
                        gene_sym = gn.get("geneName", {}).get("value", "")
                        break
                    return f"UniProt [{acc}] gene={gene_sym}"
            except Exception as e:
                logger.debug("UniProt get_entry failed for %s: %s", acc, e)
            return ""

        gene_results, acc_results = await asyncio.gather(
            asyncio.gather(*(_by_gene(g) for g in genes[:4])),
            asyncio.gather(*(_by_acc(a) for a in accessions[:2])),
        )
        for r in [*gene_results, *acc_results]:
            if r:
                parts.append(r)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("UniProt context fetch failed: %s", e)

    return "\n".join(parts)


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

    Enriches LLM context with live data from UniProt SwissProt when enabled.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Answer a proteomics or metabolomics analysis query."""
        task = context.task_description
        genes = _extract_gene_candidates(task)
        accessions = _extract_uniprot_accessions(task)
        live_context = ""
        if genes or accessions:
            try:
                live_context = await asyncio.wait_for(
                    _fetch_uniprot_context(genes, accessions), timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.debug("UniProt fetch timed out")

        enrichment_block = (
            f"\n\n--- Live Data Context (UniProt SwissProt) ---\n{live_context}\n"
            if live_context
            else ""
        )

        messages = [
            {
                "role": "user",
                "content": (
                    f"Analyze this proteomics/metabolomics query:\n\n"
                    f"{task}"
                    f"{enrichment_block}\n\n"
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
            summary=result.summary[:200] if result.summary else f"Analyzed: {task[:100]}",
            llm_response=meta,
        )
