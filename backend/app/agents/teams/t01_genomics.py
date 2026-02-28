"""Genomics & Epigenomics Agent (Team 1) — WGS, WES, WGBS, ChIP-seq, ATAC-seq analysis.

Responsibilities:
1. Variant analysis and interpretation (default run)
2. Epigenetic mark characterization
3. Pathway enrichment from genomic data

Integrations (config-gated):
- Ensembl VEP: variant effect prediction
- GWAS Catalog: trait-associated variants
- NCBI Extended: gene summaries, ClinVar variants
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


# === Integration Helpers ===

_GENE_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]{1,7})\b")
_GENE_STOPWORDS = {
    "RNA", "DNA", "PCR", "WGS", "WES", "ChIP", "ATAC", "SNP", "CNV",
    "GWAS", "QTL", "HLA", "NGS", "WBC", "RBC", "BMI", "SDS", "IQR",
    "AUC", "ROC", "CI", "OR", "HR", "RR", "SE", "SD", "LFC", "FC",
}
_VARIANT_PATTERN = re.compile(r"\brs\d{5,9}\b")


def _extract_gene_candidates(text: str) -> list[str]:
    """Extract likely gene symbols from free text (heuristic)."""
    candidates = _GENE_PATTERN.findall(text)
    return [g for g in candidates if g not in _GENE_STOPWORDS][:6]


def _extract_variant_ids(text: str) -> list[str]:
    """Extract dbSNP rsIDs from text."""
    return _VARIANT_PATTERN.findall(text)[:5]


async def _fetch_genomics_context(genes: list[str], variants: list[str]) -> str:
    """Fetch real data from Ensembl, GWAS Catalog, and NCBI for the given genes/variants.

    Returns a formatted context string to inject into the LLM prompt.
    All integrations are config-gated; failures degrade gracefully.
    """
    parts: list[str] = []

    try:
        from app.integrations.ensembl import EnsemblClient
        from app.integrations.gwas_catalog import GWASCatalogClient
        from app.integrations.ncbi_extended import NCBIExtendedClient

        ensembl = EnsemblClient()
        gwas = GWASCatalogClient()
        ncbi = NCBIExtendedClient()

        async def _fetch_gene(gene: str) -> str:
            gene_parts: list[str] = []
            try:
                # NCBI gene summary (most informative)
                info = await ncbi.search_gene_by_symbol(gene)
                if info:
                    desc = info.get("description", "")
                    summary = (info.get("summary", "") or "")[:300]
                    chrom = info.get("chromosome", "")
                    loc = info.get("maplocation", "")
                    gene_parts.append(
                        f"NCBI Gene [{gene}]: {desc}; Chr{chrom} {loc}. {summary}"
                    )
            except Exception as e:
                logger.debug("NCBI gene lookup failed for %s: %s", gene, e)

            try:
                # GWAS associations
                assocs = await gwas.get_associations_by_gene(gene, limit=5)
                if assocs:
                    traits = list({a.get("trait", "") for a in assocs if a.get("trait")})[:3]
                    gene_parts.append(
                        f"GWAS Catalog [{gene}]: {len(assocs)} associations; traits: {', '.join(traits)}"
                    )
            except Exception as e:
                logger.debug("GWAS lookup failed for %s: %s", gene, e)

            return "\n".join(gene_parts)

        async def _fetch_variant(rsid: str) -> str:
            try:
                vep = await ensembl.vep_hgvs(rsid)
                if vep:
                    consequence = vep[0].get("most_severe_consequence", "") if isinstance(vep, list) else ""
                    return f"Ensembl VEP [{rsid}]: consequence={consequence}"
            except Exception as e:
                logger.debug("VEP lookup failed for %s: %s", rsid, e)
            return ""

        gene_results, variant_results = await asyncio.gather(
            asyncio.gather(*(_fetch_gene(g) for g in genes[:4])),
            asyncio.gather(*(_fetch_variant(v) for v in variants[:3])),
        )

        for r in gene_results:
            if r.strip():
                parts.append(r)
        for r in variant_results:
            if r.strip():
                parts.append(r)

    except ImportError:
        pass  # integrations not installed
    except Exception as e:
        logger.warning("Genomics context fetch failed: %s", e)

    return "\n\n".join(parts)


# === Agent Implementation ===


class GenomicsAgent(BaseAgent):
    """Specialist agent for genomics and epigenomics analysis.

    Covers whole-genome sequencing, exome sequencing, bisulfite sequencing,
    ChIP-seq, ATAC-seq, and variant interpretation.

    Enriches LLM context with live data from Ensembl VEP, GWAS Catalog,
    and NCBI Gene when integrations are enabled.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Answer a genomics or epigenomics analysis query."""
        from app.config import settings as _settings

        if _settings.ptc_enabled and self._get_ptc_tool_names():
            return await self.run_with_ptc(
                context, GenomicsAnalysisResult, output_type="GenomicsAnalysisResult",
            )

        task = context.task_description

        # Attempt real-data enrichment
        genes = _extract_gene_candidates(task)
        variants = _extract_variant_ids(task)
        live_context = ""
        if genes or variants:
            try:
                live_context = await asyncio.wait_for(
                    _fetch_genomics_context(genes, variants),
                    timeout=12.0,
                )
            except asyncio.TimeoutError:
                logger.debug("Genomics integration fetch timed out")

        enrichment_block = (
            f"\n\n--- Live Data Context (Ensembl / GWAS Catalog / NCBI) ---\n{live_context}\n"
            if live_context
            else ""
        )

        messages = [
            {
                "role": "user",
                "content": (
                    f"Analyze this genomics/epigenomics query:\n\n"
                    f"{task}"
                    f"{enrichment_block}\n\n"
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
            summary=result.summary[:200] if result.summary else f"Analyzed: {task[:100]}",
            llm_response=meta,
        )
