"""Standard tool schemas for the agentic loop (H3).

These wrap existing integration clients (PubMed, S2, Ensembl, STRING, etc.)
as Anthropic tool_use definitions. The AgenticToolExecutor routes calls
to the actual async clients.

Differs from PTC tools:
- PTC: Claude writes Python code that calls tools in a sandbox
- Agentic: Standard tool_use protocol — iterative decide → call → evaluate

These tools are used with LLMLayer.complete_with_tools() for multi-turn reasoning.
"""

from __future__ import annotations

SEARCH_PUBMED: dict = {
    "name": "search_pubmed",
    "description": (
        "Search PubMed for biomedical literature. Returns up to max_results papers "
        "with title, PMID, abstract, authors, and publication year."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "PubMed search query"},
            "max_results": {"type": "integer", "default": 10, "description": "Max papers to return"},
        },
        "required": ["query"],
    },
}

SEARCH_SEMANTIC_SCHOLAR: dict = {
    "name": "search_semantic_scholar",
    "description": (
        "Search Semantic Scholar for academic papers. Returns papers with "
        "title, paperId, abstract, authors, year, citation count, and DOI."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    },
}

QUERY_ENSEMBL_VEP: dict = {
    "name": "query_ensembl_vep",
    "description": (
        "Annotate a genomic variant using Ensembl VEP (GRCh38). "
        "Returns consequence type, CADD score, transcript consequences."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hgvs": {"type": "string", "description": "HGVS notation (e.g. '9:g.107545939A>T')"},
        },
        "required": ["hgvs"],
    },
}

QUERY_STRING_DB: dict = {
    "name": "query_string_db",
    "description": (
        "Get protein-protein interactions from STRING DB. "
        "Returns interaction partners with confidence scores."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "genes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of gene symbols (max 10)",
            },
            "min_score": {"type": "integer", "default": 700, "description": "Min confidence (0-1000)"},
        },
        "required": ["genes"],
    },
}

QUERY_UNIPROT: dict = {
    "name": "query_uniprot",
    "description": (
        "Search UniProt for protein information by gene symbol. "
        "Returns protein name, function, subcellular location."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "gene": {"type": "string", "description": "Gene symbol (e.g. TP53)"},
        },
        "required": ["gene"],
    },
}

QUERY_GO_ENRICHMENT: dict = {
    "name": "query_go_enrichment",
    "description": (
        "Run GO/Reactome/KEGG enrichment analysis on a gene list via g:Profiler. "
        "Returns significant terms with p-values and gene ratios."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "gene_list": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of gene symbols",
            },
            "organism": {"type": "string", "default": "hsapiens"},
        },
        "required": ["gene_list"],
    },
}

# Agent → tool mapping: which agents get which tools in agentic mode
AGENT_AGENTIC_TOOLS: dict[str, list[str]] = {
    "knowledge_manager": ["search_pubmed", "search_semantic_scholar"],
    "t01_genomics": ["query_ensembl_vep", "search_pubmed"],
    "t02_transcriptomics": ["search_pubmed", "query_go_enrichment"],
    "t06_systems_bio": ["query_string_db", "query_go_enrichment", "search_pubmed"],
    "t03_proteomics": ["query_uniprot", "search_pubmed"],
}

ALL_AGENTIC_TOOLS: dict[str, dict] = {
    "search_pubmed": SEARCH_PUBMED,
    "search_semantic_scholar": SEARCH_SEMANTIC_SCHOLAR,
    "query_ensembl_vep": QUERY_ENSEMBL_VEP,
    "query_string_db": QUERY_STRING_DB,
    "query_uniprot": QUERY_UNIPROT,
    "query_go_enrichment": QUERY_GO_ENRICHMENT,
}


def get_tools_for_agent(agent_id: str) -> list[dict]:
    """Get agentic tool definitions for a specific agent."""
    tool_names = AGENT_AGENTIC_TOOLS.get(agent_id, [])
    return [ALL_AGENTIC_TOOLS[name] for name in tool_names if name in ALL_AGENTIC_TOOLS]
