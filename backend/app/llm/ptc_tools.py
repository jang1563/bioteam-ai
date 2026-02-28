"""PTC tool definitions for BioTeam-AI internal capabilities.

These tools are callable from within Claude's code_execution sandbox
via Programmatic Tool Calling (PTC). Tool results stay in the sandbox;
only print() output enters Claude's context window.

Toggle: settings.ptc_enabled (default False).

CONSTRAINTS:
- Cannot combine with MCP tools in the same API call
- Cannot combine with Instructor structured outputs (strict: true)
- Custom tools must have allowed_callers: ["code_execution_20260120"]
"""

from __future__ import annotations

PTC_CODE_EXECUTION_TYPE = "code_execution_20260120"

# ChromaDB memory search tool
CHROMADB_SEARCH_TOOL: dict = {
    "name": "search_memory",
    "description": (
        "Search the ChromaDB semantic memory for relevant documents. "
        "Returns JSON array of {id, text, source, relevance_score, metadata}."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Semantic search query",
            },
            "collection": {
                "type": "string",
                "enum": ["literature", "synthesis", "lab_kb"],
                "description": "Which ChromaDB collection to search",
            },
            "n_results": {
                "type": "integer",
                "description": "Number of results to return (default 10)",
                "default": 10,
            },
        },
        "required": ["query", "collection"],
    },
    "allowed_callers": [PTC_CODE_EXECUTION_TYPE],
}

# DOI/PMID deduplication tool
DEDUP_TOOL: dict = {
    "name": "deduplicate_papers",
    "description": (
        "Deduplicate a list of papers by DOI and PMID. "
        "Returns the deduplicated list preserving first occurrence order."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "papers": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of paper dicts with optional doi/pmid fields",
            },
        },
        "required": ["papers"],
    },
    "allowed_callers": [PTC_CODE_EXECUTION_TYPE],
}

# Store evidence tool
STORE_EVIDENCE_TOOL: dict = {
    "name": "store_evidence",
    "description": (
        "Store a paper or finding in ChromaDB for future retrieval. "
        "Returns {stored: true/false, doc_id: string}."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "Unique document ID (e.g. PMID or DOI)",
            },
            "text": {
                "type": "string",
                "description": "Text content to store (title + abstract)",
            },
            "collection": {
                "type": "string",
                "enum": ["literature", "synthesis", "lab_kb"],
                "description": "Target collection (default: literature)",
                "default": "literature",
            },
            "metadata": {
                "type": "object",
                "description": "Optional metadata (title, authors, year, etc.)",
            },
        },
        "required": ["doc_id", "text"],
    },
    "allowed_callers": [PTC_CODE_EXECUTION_TYPE],
}


# ---------------------------------------------------------------------------
# Bioinformatics PTC tools (Phase 4)
# ---------------------------------------------------------------------------

# Gene name validation (HGNC + Excel sentinel detection)
GENE_NAME_CHECKER_TOOL: dict = {
    "name": "check_gene_names",
    "description": (
        "Validate a list of gene symbols against HGNC 2025 approved names. "
        "Detects Excel date conversions (SEPT1→SEP1), deprecated symbols (DEC1→BHLHE40), "
        "and ambiguous identifiers. "
        "Returns JSON: {issues: [{gene, issue_type, suggestion}], total_issues, genes_checked}."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "gene_list": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of gene symbols to validate (max 500)",
            },
        },
        "required": ["gene_list"],
    },
    "allowed_callers": [PTC_CODE_EXECUTION_TYPE],
}

# Statistical integrity checker (GRIM test + p-value checks)
STATISTICAL_CHECKER_TOOL: dict = {
    "name": "check_statistics",
    "description": (
        "Run statistical integrity checks on reported results. "
        "Includes GRIM test (mean/n consistency), p-value plausibility, "
        "and Benford's law for large datasets. "
        "Returns JSON: {issues: [{stat_type, reported_value, issue, severity}], total_issues}."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "stats": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "mean": {"type": "number"},
                        "n": {"type": "integer"},
                        "sd": {"type": "number"},
                        "p_value": {"type": "number"},
                        "label": {"type": "string"},
                    },
                },
                "description": "List of statistical values to check",
            },
        },
        "required": ["stats"],
    },
    "allowed_callers": [PTC_CODE_EXECUTION_TYPE],
}

# NCBI BLAST (sequence similarity search)
BLAST_TOOL: dict = {
    "name": "run_blast",
    "description": (
        "Run NCBI BLAST to find sequence similarity. "
        "Supports blastn (nucleotide), blastp (protein), blastx, tblastn, tblastx. "
        "Returns JSON: {hits: [{title, accession, e_value, identity_pct}], total_hits}. "
        "Note: May be slow (NCBI BLAST API). Consider run_vep for variant-specific queries."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sequence": {
                "type": "string",
                "description": "DNA or protein sequence (FASTA or raw)",
            },
            "program": {
                "type": "string",
                "enum": ["blastn", "blastp", "blastx", "tblastn", "tblastx"],
                "default": "blastn",
            },
            "database": {
                "type": "string",
                "description": "NCBI database (nt, nr, refseq_rna, etc.)",
                "default": "nt",
            },
            "hitlist_size": {
                "type": "integer",
                "default": 10,
            },
        },
        "required": ["sequence"],
    },
    "allowed_callers": [PTC_CODE_EXECUTION_TYPE],
}

# Ensembl VEP variant annotation
VEP_TOOL: dict = {
    "name": "run_vep",
    "description": (
        "Annotate genomic variants using Ensembl VEP (GRCh38). "
        "Supports HGVS notation or genomic coordinates. "
        "Returns CADD, AlphaMissense, SpliceRegion, canonical transcript. "
        "Returns JSON: {vep_results: [{most_severe_consequence, transcript_consequences}]}."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hgvs": {
                "type": "string",
                "description": "HGVS notation (e.g., '9:g.107545939A>T')",
            },
            "chrom": {"type": "string"},
            "pos": {"type": "integer"},
            "ref": {"type": "string"},
            "alt": {"type": "string"},
            "variants": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Batch of variants — list of {hgvs} dicts (up to 200)",
            },
        },
    },
    "allowed_callers": [PTC_CODE_EXECUTION_TYPE],
}

# g:Profiler GO/pathway enrichment
GO_ENRICHMENT_TOOL: dict = {
    "name": "run_go_enrichment",
    "description": (
        "Run g:Profiler functional enrichment on a gene list (GO, Reactome, KEGG). "
        "Uses g:SCS multiple testing correction. "
        "Returns JSON: {enrichment_results: [{source, native, name, p_value, "
        "intersection_size, gene_ratio}], total_significant}."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "gene_list": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of HGNC gene symbols",
            },
            "organism": {
                "type": "string",
                "default": "hsapiens",
            },
            "sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Databases: GO:BP, GO:MF, GO:CC, REAC, KEGG",
            },
            "top_n": {
                "type": "integer",
                "default": 20,
            },
        },
        "required": ["gene_list"],
    },
    "allowed_callers": [PTC_CODE_EXECUTION_TYPE],
}


# PTC code execution tool (always required alongside custom PTC tools)
CODE_EXECUTION_TOOL: dict = {
    "type": PTC_CODE_EXECUTION_TYPE,
    "name": "code_execution",
}


def get_all_ptc_tools() -> list[dict]:
    """Return all PTC tool definitions including the code_execution tool."""
    return [
        CODE_EXECUTION_TOOL,
        CHROMADB_SEARCH_TOOL,
        DEDUP_TOOL,
        STORE_EVIDENCE_TOOL,
        GENE_NAME_CHECKER_TOOL,
        STATISTICAL_CHECKER_TOOL,
        BLAST_TOOL,
        VEP_TOOL,
        GO_ENRICHMENT_TOOL,
    ]


def get_bio_ptc_tools() -> list[dict]:
    """Return only the bioinformatics PTC tool definitions (Phase 4 additions)."""
    return [
        CODE_EXECUTION_TOOL,
        GENE_NAME_CHECKER_TOOL,
        STATISTICAL_CHECKER_TOOL,
        BLAST_TOOL,
        VEP_TOOL,
        GO_ENRICHMENT_TOOL,
    ]


def ensure_allowed_callers(tools: list[dict]) -> list[dict]:
    """Ensure all custom tools have allowed_callers set for PTC."""
    prepared = []
    for tool in tools:
        # Skip the code_execution tool itself
        if tool.get("type") == PTC_CODE_EXECUTION_TYPE:
            prepared.append(tool)
            continue
        t = dict(tool)
        if "allowed_callers" not in t:
            t["allowed_callers"] = [PTC_CODE_EXECUTION_TYPE]
        prepared.append(t)
    return prepared
