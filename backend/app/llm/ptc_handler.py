"""PTC (Programmatic Tool Calling) dispatcher for bioinformatics tools.

Routes tool_use requests from Claude's code execution sandbox to the
appropriate bioinformatics API clients or integrity engines.

All handlers return JSON strings with provenance (_source, _retrieved_at) fields.

Usage (in layer.py):
    from app.llm.ptc_handler import handle_ptc_tool_call
    tool_implementations = {"run_vep": handle_ptc_tool_call}

The dispatcher is called with (tool_name, tool_input) and routes internally.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)


async def handle_ptc_tool_call(tool_name: str, tool_input: dict) -> str:
    """Dispatch a PTC tool call to the appropriate handler.

    Args:
        tool_name: The tool name from the PTC tool definition (e.g., "run_vep")
        tool_input: Dict of arguments from Claude's code execution

    Returns:
        JSON string with results (always includes _source and _retrieved_at).
        Returns error JSON on failure — never raises.
    """
    handlers = {
        "run_vep": _handle_vep,
        "check_gene_names": _handle_gene_name_check,
        "check_statistics": _handle_statistical_check,
        "run_blast": _handle_blast,
        "run_go_enrichment": _handle_go_enrichment,
        # Legacy ChromaDB tools
        "search_memory": _handle_search_memory,
        "store_evidence": _handle_store_evidence,
        "deduplicate_papers": _handle_deduplicate_papers,
    }

    handler = handlers.get(tool_name)
    if handler is None:
        return json.dumps({"error": f"Unknown PTC tool: {tool_name}", "_source": "ptc_handler"})

    try:
        result = await handler(tool_input)
        return result if isinstance(result, str) else json.dumps(result)
    except Exception as e:
        logger.warning("PTC handler failed for tool %s: %s", tool_name, e)
        return json.dumps({
            "error": str(e),
            "tool": tool_name,
            "_source": "ptc_handler",
            "_retrieved_at": datetime.now(timezone.utc).isoformat(),
        })


# ---------------------------------------------------------------------------
# VEP / Variant Annotation
# ---------------------------------------------------------------------------

async def _handle_vep(tool_input: dict) -> str:
    """Annotate a variant via Ensembl VEP.

    Input schema: {"hgvs": "..."} or {"chrom": "17", "pos": 41234451, "ref": "A", "alt": "G"}
    """
    from app.integrations.ensembl import EnsemblClient

    client = EnsemblClient()

    if "hgvs" in tool_input:
        results = await client.vep_hgvs(tool_input["hgvs"])
    elif all(k in tool_input for k in ("chrom", "pos", "ref", "alt")):
        results = await client.vep_region(
            chrom=str(tool_input["chrom"]),
            pos=int(tool_input["pos"]),
            ref=tool_input["ref"],
            alt=tool_input["alt"],
        )
    elif "variants" in tool_input and isinstance(tool_input["variants"], list):
        results = await client.vep_batch(tool_input["variants"])
    else:
        return json.dumps({"error": "VEP requires 'hgvs', ('chrom','pos','ref','alt'), or 'variants' input"})

    return json.dumps({
        "vep_results": results,
        "count": len(results),
        "_source": "Ensembl VEP v112",
        "_retrieved_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# Gene Name Checker
# ---------------------------------------------------------------------------

async def _handle_gene_name_check(tool_input: dict) -> str:
    """Validate gene symbols against HGNC 2025 and check for Excel conversions.

    Input schema: {"gene_list": ["BRCA1", "TP53", "SEPT9", "DEC1"]}
    """
    from app.engines.integrity.gene_name_checker import GeneNameChecker

    gene_list = tool_input.get("gene_list", [])
    if not gene_list:
        return json.dumps({"error": "gene_list is required"})

    checker = GeneNameChecker()
    # Run checker on a minimal finding structure
    from app.models.finding_models import Finding

    finding = Finding(
        gene_list=gene_list,
        source="ptc_tool_call",
    )
    try:
        results = await checker.check(finding)
        return json.dumps({
            "issues": [r.model_dump(mode="json") if hasattr(r, "model_dump") else r for r in results],
            "total_issues": len(results),
            "genes_checked": len(gene_list),
            "_source": "HGNC 2025 + Excel Sentinel Check",
            "_retrieved_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.debug("Gene name check failed: %s", e)
        return json.dumps({
            "error": str(e),
            "genes_checked": len(gene_list),
            "_source": "HGNC 2025",
            "_retrieved_at": datetime.now(timezone.utc).isoformat(),
        })


# ---------------------------------------------------------------------------
# Statistical Checker
# ---------------------------------------------------------------------------

async def _handle_statistical_check(tool_input: dict) -> str:
    """Run GRIM test and p-value plausibility checks.

    Input schema: {"stats": [{"mean": 3.5, "n": 20, "sd": 1.2}, ...]}
    """
    from app.engines.integrity.statistical_checker import StatisticalChecker

    stats = tool_input.get("stats", [])
    if not stats:
        return json.dumps({"error": "stats list is required"})

    checker = StatisticalChecker()
    from app.models.finding_models import Finding

    finding = Finding(
        statistics=stats,
        source="ptc_tool_call",
    )
    try:
        results = await checker.check(finding)
        return json.dumps({
            "issues": [r.model_dump(mode="json") if hasattr(r, "model_dump") else r for r in results],
            "total_issues": len(results),
            "stats_checked": len(stats),
            "_source": "GRIM + Statistical Integrity Checker",
            "_retrieved_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.debug("Statistical check failed: %s", e)
        return json.dumps({
            "error": str(e),
            "stats_checked": len(stats),
            "_source": "GRIM",
            "_retrieved_at": datetime.now(timezone.utc).isoformat(),
        })


# ---------------------------------------------------------------------------
# BLAST / Sequence Similarity
# ---------------------------------------------------------------------------

async def _handle_blast(tool_input: dict) -> str:
    """Run NCBI BLAST for sequence similarity search.

    Input schema: {
        "sequence": "ATGCGT...",
        "program": "blastn",          # blastn|blastp|blastx|tblastn|tblastx
        "database": "nt",             # nt|nr|refseq_rna|...
        "hitlist_size": 10
    }

    Note: Requires biopython. Falls back gracefully if unavailable.
    """
    try:
        from Bio.Blast import NCBIWWW, NCBIXML  # type: ignore[import]
    except ImportError:
        return json.dumps({
            "error": "biopython is required for BLAST. Install with: uv add biopython",
            "_source": "NCBI BLAST",
            "_retrieved_at": datetime.now(timezone.utc).isoformat(),
        })

    sequence = tool_input.get("sequence", "")
    if not sequence:
        return json.dumps({"error": "sequence is required"})

    program = tool_input.get("program", "blastn")
    database = tool_input.get("database", "nt")
    hitlist_size = int(tool_input.get("hitlist_size", 10))

    try:
        import asyncio
        # NCBIWWW.qblast is sync — run in thread to avoid blocking event loop
        result_handle = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: NCBIWWW.qblast(
                program=program,
                database=database,
                sequence=sequence,
                hitlist_size=hitlist_size,
                email=settings.ncbi_email or "bioteam@example.com",
            ),
        )
        blast_records = list(NCBIXML.parse(result_handle))
        hits = []
        for record in blast_records:
            for alignment in record.alignments[:hitlist_size]:
                hsp = alignment.hsps[0] if alignment.hsps else None
                if hsp:
                    hits.append({
                        "title": alignment.title[:200],
                        "accession": alignment.accession,
                        "length": alignment.length,
                        "e_value": hsp.expect,
                        "score": hsp.score,
                        "identity_pct": round(hsp.identities / hsp.align_length * 100, 1),
                        "gaps_pct": round(hsp.gaps / hsp.align_length * 100, 1),
                    })

        return json.dumps({
            "hits": hits,
            "total_hits": len(hits),
            "program": program,
            "database": database,
            "_source": f"NCBI BLAST ({program} vs {database})",
            "_retrieved_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.debug("BLAST failed: %s", e)
        return json.dumps({
            "error": str(e),
            "program": program,
            "_source": "NCBI BLAST",
            "_retrieved_at": datetime.now(timezone.utc).isoformat(),
        })


# ---------------------------------------------------------------------------
# GO / Pathway Enrichment
# ---------------------------------------------------------------------------

async def _handle_go_enrichment(tool_input: dict) -> str:
    """Run g:Profiler GO/KEGG/Reactome enrichment analysis.

    Input schema: {
        "gene_list": ["BRCA1", "TP53", "ATM"],
        "organism": "hsapiens",          # optional, default hsapiens
        "sources": ["GO:BP", "REAC"],    # optional, default GO:BP+GO:MF+REAC+KEGG
        "top_n": 20                      # optional, default 20
    }
    """
    from app.integrations.go_enrichment import GOEnrichmentClient

    gene_list = tool_input.get("gene_list", [])
    if not gene_list:
        return json.dumps({"error": "gene_list is required"})

    organism = tool_input.get("organism", "hsapiens")
    sources = tool_input.get("sources")
    top_n = int(tool_input.get("top_n", 20))

    client = GOEnrichmentClient()
    raw_results = await client.run_enrichment(gene_list, organism=organism, sources=sources)
    formatted = client.format_for_agent(raw_results, top_n=top_n)

    return json.dumps({
        "enrichment_results": formatted,
        "total_significant": len(formatted),
        "genes_submitted": len(gene_list),
        "organism": organism,
        "_source": "g:Profiler v0.3 (g:SCS correction)",
        "_retrieved_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# Legacy ChromaDB tools (already existed in ptc_tools.py — re-dispatched here)
# ---------------------------------------------------------------------------

async def _handle_search_memory(tool_input: dict) -> str:
    """Proxy to ChromaDB semantic memory search."""
    try:
        from app.memory.semantic import SemanticMemory

        memory = SemanticMemory()
        query = tool_input.get("query", "")
        collection = tool_input.get("collection", "literature")
        n_results = int(tool_input.get("n_results", 10))
        results = await memory.search(query, collection=collection, n_results=n_results)
        return json.dumps({"results": results, "_source": "ChromaDB"})
    except Exception as e:
        return json.dumps({"error": str(e), "_source": "ChromaDB"})


async def _handle_store_evidence(tool_input: dict) -> str:
    """Proxy to ChromaDB store operation."""
    try:
        from app.memory.semantic import SemanticMemory

        memory = SemanticMemory()
        doc_id = tool_input.get("doc_id", "")
        text = tool_input.get("text", "")
        collection = tool_input.get("collection", "literature")
        metadata = tool_input.get("metadata", {})
        await memory.store(doc_id=doc_id, text=text, collection=collection, metadata=metadata)
        return json.dumps({"stored": True, "doc_id": doc_id, "_source": "ChromaDB"})
    except Exception as e:
        return json.dumps({"stored": False, "error": str(e), "_source": "ChromaDB"})


async def _handle_deduplicate_papers(tool_input: dict) -> str:
    """Deduplicate a paper list by DOI and PMID."""
    papers = tool_input.get("papers", [])
    seen_dois: set[str] = set()
    seen_pmids: set[str] = set()
    deduped = []
    for paper in papers:
        doi = (paper.get("doi") or "").strip().lower()
        pmid = (paper.get("pmid") or paper.get("pubmed_id") or "").strip()
        if doi and doi in seen_dois:
            continue
        if pmid and pmid in seen_pmids:
            continue
        if doi:
            seen_dois.add(doi)
        if pmid:
            seen_pmids.add(pmid)
        deduped.append(paper)
    return json.dumps({
        "papers": deduped,
        "original_count": len(papers),
        "deduplicated_count": len(deduped),
        "_source": "ptc_handler",
    })


# ---------------------------------------------------------------------------
# Convenience: build tool_implementations dict for complete_with_ptc()
# ---------------------------------------------------------------------------

def build_tool_implementations(tool_names: list[str] | None = None) -> dict:
    """Build the tool_implementations dict for complete_with_ptc().

    Args:
        tool_names: If provided, only include listed tools. Default: all tools.

    Returns:
        Dict of {tool_name: async callable} for use in LLMLayer.complete_with_ptc().
    """
    all_impl = {
        "run_vep": lambda inp: handle_ptc_tool_call("run_vep", inp),
        "check_gene_names": lambda inp: handle_ptc_tool_call("check_gene_names", inp),
        "check_statistics": lambda inp: handle_ptc_tool_call("check_statistics", inp),
        "run_blast": lambda inp: handle_ptc_tool_call("run_blast", inp),
        "run_go_enrichment": lambda inp: handle_ptc_tool_call("run_go_enrichment", inp),
        "search_memory": lambda inp: handle_ptc_tool_call("search_memory", inp),
        "store_evidence": lambda inp: handle_ptc_tool_call("store_evidence", inp),
        "deduplicate_papers": lambda inp: handle_ptc_tool_call("deduplicate_papers", inp),
    }
    if tool_names is None:
        return all_impl
    return {k: v for k, v in all_impl.items() if k in tool_names}
