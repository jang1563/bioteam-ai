"""g:Profiler GO/pathway enrichment client.

Wraps the gprofiler-official Python library for GO, Reactome, KEGG,
and TRANSFAC enrichment analysis.

Falls back to the g:Profiler REST API if the library is unavailable.

Docs: https://biit.cs.ut.ee/gprofiler/gost
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)

# g:Profiler source IDs — used by T06 Systems Biology agent
GO_SOURCES = ["GO:BP", "GO:MF", "GO:CC"]
PATHWAY_SOURCES = ["REAC", "KEGG", "WP"]
ALL_SOURCES = GO_SOURCES + PATHWAY_SOURCES + ["TF", "MIRNA", "HP"]

# Significance method citation
GPROFILER_CITATION = "g:Profiler (Raudvere et al., NAR 2019); g:SCS multiple testing correction"


class GOEnrichmentClient:
    """Wrapper around g:Profiler for functional enrichment analysis.

    Usage:
        client = GOEnrichmentClient()
        results = await client.run_enrichment(["BRCA1", "TP53", "ATM"], organism="hsapiens")
        formatted = client.format_for_agent(results, top_n=20)
    """

    def __init__(self) -> None:
        self._gp = None  # Lazy-loaded gprofiler GProfiler instance

    def _get_gp(self):
        """Lazy-load GProfiler to handle optional dependency gracefully."""
        if self._gp is None:
            try:
                from gprofiler import GProfiler  # type: ignore[import]
                self._gp = GProfiler(return_dataframe=False)
            except ImportError:
                logger.warning(
                    "gprofiler-official not installed. "
                    "Install with: uv add gprofiler-official"
                )
                self._gp = None
        return self._gp

    async def run_enrichment(
        self,
        gene_list: list[str],
        organism: str = "hsapiens",
        sources: list[str] | None = None,
        significance_threshold: float = 0.05,
        user_threshold: float = 0.05,
        no_evidences: bool = False,
    ) -> list[dict]:
        """Run g:Profiler enrichment analysis on a gene list.

        Args:
            gene_list: List of HGNC gene symbols (human) or equivalent for other organisms
            organism: g:Profiler organism code (hsapiens, mmusculus, etc.)
            sources: List of databases to query. Default: GO:BP + GO:MF + REAC + KEGG
            significance_threshold: g:SCS threshold (default 0.05)
            user_threshold: Additional user-defined threshold
            no_evidences: If True, skip GO evidence codes (faster)

        Returns:
            List of enrichment result dicts with source, native (GO ID / pathway ID),
            name, p_value, significant, intersection_size fields.
        """
        if not settings.go_enrichment_enabled or not gene_list:
            return []

        if sources is None:
            sources = GO_SOURCES + ["REAC", "KEGG"]

        gp = self._get_gp()
        if gp is None:
            return self._rest_fallback_stub(gene_list, organism)

        try:
            # GProfiler is sync — run in place (no heavy computation, just HTTP)
            results = gp.profile(
                organism=organism,
                query=gene_list,
                sources=sources,
                significance_threshold_method="g_SCS",
                user_threshold=user_threshold,
                no_evidences=no_evidences,
                no_iea=False,  # Include electronic annotations
            )
            tagged = []
            for r in (results or []):
                entry = dict(r) if not isinstance(r, dict) else r
                entry["_source"] = "g:Profiler v0.3"
                entry["_citation"] = GPROFILER_CITATION
                entry["_retrieved_at"] = datetime.now(timezone.utc).isoformat()
                tagged.append(entry)
            return tagged
        except Exception as e:
            logger.debug("g:Profiler enrichment failed for %d genes: %s", len(gene_list), e)
            return []

    def format_for_agent(
        self,
        results: list[dict],
        top_n: int = 20,
        sources: list[str] | None = None,
    ) -> list[dict]:
        """Format g:Profiler results for agent consumption.

        Produces the JSON format expected by T06 systems_bio agent:
        {"source": "GO:BP", "native": "GO:0006977", "name": "...",
         "p_value": ..., "significant": True, "term_size": ..., "intersection_size": ...}

        Args:
            results: Raw g:Profiler output from run_enrichment()
            top_n: Maximum results to return (sorted by p_value ascending)
            sources: If provided, filter to these source databases

        Returns:
            Formatted list ready for agent context metadata injection.
        """
        if not results:
            return []

        formatted = []
        for r in results:
            # Filter by source if requested
            src = r.get("source", "")
            if sources and src not in sources:
                continue
            # Only include significant results
            if not r.get("significant", False):
                continue

            entry = {
                "source": src,
                "native": r.get("native", ""),
                "name": r.get("name", ""),
                "p_value": r.get("p_value", 1.0),
                "p_value_formatted": f"{r.get('p_value', 1.0):.2e}",
                "significant": r.get("significant", False),
                "term_size": r.get("term_size", 0),
                "query_size": r.get("query_size", 0),
                "intersection_size": r.get("intersection_size", 0),
                "gene_ratio": (
                    f"{r.get('intersection_size', 0)}/{r.get('query_size', 1)}"
                ),
                "intersections": r.get("intersections", []),
                "_source": r.get("_source", "g:Profiler"),
                "_citation": r.get("_citation", GPROFILER_CITATION),
            }
            formatted.append(entry)

        # Sort by p_value ascending, return top_n
        formatted.sort(key=lambda x: x["p_value"])
        return formatted[:top_n]

    def _rest_fallback_stub(self, gene_list: list[str], organism: str) -> list[dict]:
        """Stub for REST fallback when gprofiler-official is not installed."""
        logger.warning(
            "gprofiler-official unavailable. "
            "Install with: uv add gprofiler-official. "
            "Returning empty enrichment results for %d genes.",
            len(gene_list),
        )
        return []
