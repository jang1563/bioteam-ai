"""AgenticToolExecutor — routes tool_use calls to integration clients.

Used by BaseAgent.run_with_tools() to handle multi-turn agentic tool calls.
Each tool name maps to an async handler that calls the appropriate integration.

All handlers return JSON strings and never raise — errors are returned as JSON.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class AgenticToolExecutor:
    """Routes standard tool_use calls to async integration clients."""

    async def __call__(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool call and return the result as a string.

        Args:
            tool_name: The tool name from the tool_use block.
            tool_input: The input dict from the tool_use block.

        Returns:
            JSON string with results. Never raises.
        """
        handlers = {
            "search_pubmed": self._search_pubmed,
            "search_semantic_scholar": self._search_s2,
            "query_ensembl_vep": self._query_vep,
            "query_string_db": self._query_string,
            "query_uniprot": self._query_uniprot,
            "query_go_enrichment": self._query_go,
        }

        handler = handlers.get(tool_name)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        try:
            return await handler(tool_input)
        except Exception as e:
            logger.warning("Agentic tool %s failed: %s", tool_name, e)
            return json.dumps({
                "error": str(e),
                "tool": tool_name,
                "_retrieved_at": datetime.now(timezone.utc).isoformat(),
            })

    async def _search_pubmed(self, inp: dict) -> str:
        from app.integrations.pubmed import PubMedClient

        client = PubMedClient()
        query = inp.get("query", "")
        max_results = int(inp.get("max_results", 10))
        papers = await client.search(query, max_results=max_results)
        return json.dumps({
            "papers": papers[:max_results],
            "total": len(papers),
            "_source": "PubMed",
        })

    async def _search_s2(self, inp: dict) -> str:
        from app.integrations.semantic_scholar import SemanticScholarClient

        client = SemanticScholarClient()
        query = inp.get("query", "")
        limit = int(inp.get("limit", 10))
        papers = await client.search(query, limit=limit)
        return json.dumps({
            "papers": papers[:limit],
            "total": len(papers),
            "_source": "Semantic Scholar",
        })

    async def _query_vep(self, inp: dict) -> str:
        from app.integrations.ensembl import EnsemblClient

        client = EnsemblClient()
        hgvs = inp.get("hgvs", "")
        results = await client.vep_hgvs(hgvs)
        return json.dumps({
            "vep_results": results,
            "_source": "Ensembl VEP",
        })

    async def _query_string(self, inp: dict) -> str:
        from app.integrations.stringdb import STRINGClient

        client = STRINGClient()
        genes = inp.get("genes", [])
        min_score = int(inp.get("min_score", 700))
        interactions = await client.get_interactions(genes, min_score=min_score)
        return json.dumps({
            "interactions": interactions[:20],
            "total": len(interactions),
            "_source": "STRING DB v12",
        })

    async def _query_uniprot(self, inp: dict) -> str:
        from app.integrations.uniprot import UniProtClient

        client = UniProtClient()
        gene = inp.get("gene", "")
        results = await client.search_by_gene(gene, organism=9606, limit=1, reviewed_only=True)
        if not results:
            return json.dumps({"error": f"No UniProt entry found for {gene}", "_source": "UniProt"})
        entry = results[0]
        name = entry.get("proteinDescription", {}).get("recommendedName", {})
        full_name = name.get("fullName", {}).get("value", "") if name else ""
        acc = entry.get("primaryAccession", "")
        return json.dumps({
            "accession": acc,
            "gene": gene,
            "protein_name": full_name,
            "_source": "UniProt",
        })

    async def _query_go(self, inp: dict) -> str:
        from app.integrations.go_enrichment import GOEnrichmentClient

        client = GOEnrichmentClient()
        gene_list = inp.get("gene_list", [])
        organism = inp.get("organism", "hsapiens")
        results = await client.run_enrichment(gene_list, organism=organism)
        formatted = client.format_for_agent(results, top_n=15)
        return json.dumps({
            "enrichment_results": formatted,
            "total_significant": len(formatted),
            "_source": "g:Profiler",
        })
