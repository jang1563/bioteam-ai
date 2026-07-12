"""W9 result extractors — convert nested W9 step outputs to flat lists for scoring.

Supports both data-driven and knowledge-only (literature_only) modes.
In knowledge-only mode, Phase B steps are skipped and the extractor falls back
to LLM-based extraction from the research question.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class W9ResultExtractor:
    """Extract flat gene/pathway/direction lists from W9 step_results.

    W9 step results are dict[str, AgentOutput] where each AgentOutput.output
    is a dict matching the corresponding Pydantic model.
    """

    @staticmethod
    def _get_output(step_results: dict[str, Any], step_id: str) -> dict:
        """Safely extract the output dict from a step result."""
        result = step_results.get(step_id)
        if result is None:
            return {}
        # AgentOutput has .output attribute (dict)
        if hasattr(result, "output"):
            out = result.output
            return out if isinstance(out, dict) else {}
        if isinstance(result, dict):
            return result
        return {}

    @staticmethod
    def _extract_genes_from_dict(data: dict, gene_keys: tuple[str, ...]) -> set[str]:
        """Extract gene symbols from a dict using multiple possible key names."""
        genes: set[str] = set()
        for key in gene_keys:
            for g in data.get(key, []):
                if isinstance(g, str):
                    genes.add(g)
                elif isinstance(g, dict):
                    for gk in ("gene", "symbol", "name", "gene_symbol"):
                        if gk in g:
                            genes.add(str(g[gk]))
                            break
        return genes

    @staticmethod
    def extract_gene_list(step_results: dict[str, Any]) -> list[str]:
        """Extract unique gene symbols from all relevant step results."""
        genes: set[str] = set()
        get = W9ResultExtractor._get_output
        _eg = W9ResultExtractor._extract_genes_from_dict

        # EXPRESSION_ANALYSIS: up_regulated + down_regulated
        expr = get(step_results, "EXPRESSION_ANALYSIS")
        for deg_list in (expr.get("up_regulated", []), expr.get("down_regulated", [])):
            for deg in deg_list:
                if isinstance(deg, dict) and "gene" in deg:
                    genes.add(str(deg["gene"]))

        # VARIANT_ANNOTATION: affected_genes
        variant = get(step_results, "VARIANT_ANNOTATION")
        for g in variant.get("affected_genes", []):
            if isinstance(g, str):
                genes.add(g)

        # NETWORK_ANALYSIS: hub_genes
        network = get(step_results, "NETWORK_ANALYSIS")
        for g in network.get("hub_genes", []):
            if isinstance(g, str):
                genes.add(g)

        # PROTEIN_ANALYSIS: differentially_abundant
        protein = get(step_results, "PROTEIN_ANALYSIS")
        for p in protein.get("differentially_abundant", []):
            if isinstance(p, dict) and "gene" in p:
                genes.add(str(p["gene"]))

        # CROSS_OMICS_INTEGRATION: multiple possible schemas
        # CrossOmicsIntegrationResult: shared_genes, causal_candidates
        # IntegrativeAnalysisResult: cross_omics_findings
        cross = get(step_results, "CROSS_OMICS_INTEGRATION")
        genes |= _eg(cross, (
            "key_genes", "integrated_genes", "top_genes",
            "shared_genes", "causal_candidates",
        ))
        # cross_omics_findings is a list of dicts with potential gene info
        for finding in cross.get("cross_omics_findings", []):
            if isinstance(finding, dict):
                genes |= _eg(finding, ("genes", "gene_list", "key_genes"))

        # LITERATURE_COMPARISON: genes mentioned in literature context
        lit = get(step_results, "LITERATURE_COMPARISON")
        genes |= _eg(lit, (
            "genes_mentioned", "validated_genes", "key_genes",
            "papers",  # LiteratureSearchResult may have gene refs
        ))

        # NOVELTY_ASSESSMENT: novel findings may contain genes
        novelty = get(step_results, "NOVELTY_ASSESSMENT")
        for finding in novelty.get("novel_findings", []):
            if isinstance(finding, dict):
                genes |= _eg(finding, ("genes", "gene", "key_genes"))

        return sorted(genes)

    @staticmethod
    def extract_directions(step_results: dict[str, Any]) -> dict[str, str]:
        """Extract DEG direction map: gene → 'up'/'down'."""
        directions: dict[str, str] = {}
        expr = W9ResultExtractor._get_output(step_results, "EXPRESSION_ANALYSIS")

        for deg in expr.get("up_regulated", []):
            if isinstance(deg, dict) and "gene" in deg:
                directions[str(deg["gene"])] = "up"
        for deg in expr.get("down_regulated", []):
            if isinstance(deg, dict) and "gene" in deg:
                directions[str(deg["gene"])] = "down"

        return directions

    @staticmethod
    def extract_pathways(step_results: dict[str, Any]) -> list[str]:
        """Extract pathway names from all relevant step results."""
        pathways: list[str] = []
        enrichment = W9ResultExtractor._get_output(step_results, "PATHWAY_ENRICHMENT")

        for p in enrichment.get("top_pathways", []):
            if isinstance(p, dict) and "name" in p:
                pathways.append(str(p["name"]))
            elif isinstance(p, str):
                pathways.append(p)

        # Also pull from subcategories
        for key in ("go_bp_top5", "go_mf_top5", "reactome_top5", "kegg_top5"):
            for p in enrichment.get(key, []):
                if isinstance(p, dict) and "name" in p:
                    name = str(p["name"])
                    if name not in pathways:
                        pathways.append(name)

        # CROSS_OMICS_INTEGRATION: multiple possible field names
        get = W9ResultExtractor._get_output
        cross = get(step_results, "CROSS_OMICS_INTEGRATION")
        for key in ("pathways", "enriched_pathways", "key_pathways", "pathway_consensus"):
            for p in cross.get(key, []):
                if isinstance(p, str) and p not in pathways:
                    pathways.append(p)
                elif isinstance(p, dict) and "name" in p:
                    name = str(p["name"])
                    if name not in pathways:
                        pathways.append(name)

        # LITERATURE_COMPARISON
        lit = get(step_results, "LITERATURE_COMPARISON")
        for key in ("pathways", "enriched_pathways", "key_pathways"):
            for p in lit.get(key, []):
                if isinstance(p, str) and p not in pathways:
                    pathways.append(p)
                elif isinstance(p, dict) and "name" in p:
                    name = str(p["name"])
                    if name not in pathways:
                        pathways.append(name)

        return pathways

    @staticmethod
    def extract_fold_changes(step_results: dict[str, Any]) -> dict[str, float]:
        """Extract gene → log2FC mapping."""
        fcs: dict[str, float] = {}
        expr = W9ResultExtractor._get_output(step_results, "EXPRESSION_ANALYSIS")

        for deg_list in (expr.get("up_regulated", []), expr.get("down_regulated", [])):
            for deg in deg_list:
                if isinstance(deg, dict) and "gene" in deg:
                    fc = deg.get("log2FC") or deg.get("logFC") or deg.get("log2fc")
                    if fc is not None:
                        try:
                            fcs[str(deg["gene"])] = float(fc)
                        except (ValueError, TypeError):
                            pass

        return fcs
