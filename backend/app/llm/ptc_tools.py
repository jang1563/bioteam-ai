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
