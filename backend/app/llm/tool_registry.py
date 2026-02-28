"""Tool registry for deferred tool loading.

Classifies tools as always-loaded (frequently used) or deferred (rarely used)
per agent. When deferred_tools_enabled=True, deferred tools are marked with
defer_loading=True and discovered via BM25 tool search.

Context savings: ~85% reduction for deferred tool definitions.
"""

from __future__ import annotations

# Classification of tools by agent: which are always loaded vs deferred.
# "always_loaded" tools consume context tokens on every call.
# "deferred" tools are only loaded when BM25 tool search matches them.
AGENT_TOOL_CLASSIFICATION: dict[str, dict[str, list[str]]] = {
    "knowledge_manager": {
        "always_loaded": [
            "search_pubmed",
            "search_semantic_scholar",
            "query_chromadb",
            "store_in_chromadb",
        ],
        "deferred": [
            "search_biorxiv",
            "search_clinical_trials",
            "search_chembl",
            "lookup_icd10",
            "check_novelty",
        ],
    },
    "research_director": {
        "always_loaded": [
            "route_to_specialist",
            "decompose_task",
            "synthesize_results",
        ],
        "deferred": [],
    },
    "project_manager": {
        "always_loaded": [
            "create_workflow",
            "get_workflow_status",
        ],
        "deferred": [
            "estimate_cost",
            "generate_report",
        ],
    },
    "ambiguity_engine": {
        "always_loaded": [
            "detect_contradictions",
            "score_evidence",
        ],
        "deferred": [
            "generate_hypothesis",
            "compare_methods",
        ],
    },
    # Bioinformatics domain agents (Phase 4 — PTC tool assignments)
    # always_loaded = tools injected by default for every call
    # deferred = tools available via BM25 tool search (context savings)
    "t01_genomics": {
        "always_loaded": ["run_vep", "check_gene_names"],
        "deferred": ["run_blast"],
    },
    "t02_transcriptomics": {
        "always_loaded": ["check_gene_names", "run_go_enrichment"],
        "deferred": [],
    },
    "t03_proteomics": {
        "always_loaded": ["check_gene_names"],
        "deferred": ["run_go_enrichment"],
    },
    "t04_biostatistics": {
        "always_loaded": ["check_statistics"],
        "deferred": [],
    },
    "t06_systems_bio": {
        "always_loaded": ["run_go_enrichment", "check_gene_names"],
        "deferred": [],
    },
    "t07_structural_bio": {
        "always_loaded": ["run_vep"],
        "deferred": ["run_blast"],
    },
    "data_integrity_auditor": {
        "always_loaded": ["check_gene_names", "check_statistics"],
        "deferred": [],
    },
    # Domain expert agents (t05, t08, t09, t10) use few tools. Default: no deferral.
}


def get_classification(agent_id: str) -> dict[str, list[str]]:
    """Get tool classification for an agent.

    Returns:
        Dict with "always_loaded" and "deferred" lists.
        If agent has no classification, returns empty deferred list.
    """
    return AGENT_TOOL_CLASSIFICATION.get(
        agent_id,
        {"always_loaded": [], "deferred": []},
    )
