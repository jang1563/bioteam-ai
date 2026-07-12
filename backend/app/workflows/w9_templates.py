"""W9 analysis templates — pre-configured profiles for common analysis types.

Each template specifies which steps to skip, budget defaults, and which steps
enable agentic multi-turn mode. Templates allow researchers to run focused
analyses at lower cost instead of the full 21-step multi-omics pipeline.

Usage:
    from app.workflows.w9_templates import W9_TEMPLATES, resolve_skip_steps
    tpl = W9_TEMPLATES["rnaseq_dea"]
    effective_skips = resolve_skip_steps(tpl.skip_steps)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class W9Template:
    """Configuration profile for a W9 analysis variant."""

    name: str
    description: str
    skip_steps: frozenset[str]          # Steps to skip entirely
    model_overrides: dict[str, str] = field(default_factory=dict)  # step_id → model tier
    budget_default: float = 25.0
    agentic_steps: frozenset[str] = field(default_factory=frozenset)  # Enable agentic loop
    required_data_types: list[str] = field(default_factory=list)


# Step dependency map: if a dependency is skipped, dependents are also skipped
STEP_DEPENDENCIES: dict[str, list[str]] = {
    "VARIANT_ANNOTATION": ["GENOMIC_ANALYSIS"],
    "INTEGRITY_AUDIT": ["EXPRESSION_ANALYSIS"],
}


def resolve_skip_steps(template_skip: frozenset[str]) -> frozenset[str]:
    """Expand skip_steps with cascaded dependencies.

    If GENOMIC_ANALYSIS is skipped, VARIANT_ANNOTATION is automatically skipped too.
    """
    result = set(template_skip)
    changed = True
    while changed:
        changed = False
        for step, deps in STEP_DEPENDENCIES.items():
            if step not in result and any(d in result for d in deps):
                result.add(step)
                changed = True
    return frozenset(result)


# ── Template Definitions ──────────────────────────────────────────────────

W9_TEMPLATES: dict[str, W9Template] = {
    "rnaseq_dea": W9Template(
        name="rnaseq_dea",
        description="RNA-seq Differential Expression Analysis — focused on transcriptomics + pathway enrichment",
        skip_steps=frozenset({
            "GENOMIC_ANALYSIS", "VARIANT_ANNOTATION", "PROTEIN_ANALYSIS",
        }),
        budget_default=8.0,
        agentic_steps=frozenset({"EXPRESSION_ANALYSIS", "PATHWAY_ENRICHMENT"}),
        required_data_types=["count_matrix"],
    ),
    "variant_annotation": W9Template(
        name="variant_annotation",
        description="Genomic Variant Annotation — VEP + ClinVar + gene impact analysis",
        skip_steps=frozenset({
            "EXPRESSION_ANALYSIS", "PROTEIN_ANALYSIS",
            "PATHWAY_ENRICHMENT", "NETWORK_ANALYSIS",
        }),
        budget_default=10.0,
        agentic_steps=frozenset({"GENOMIC_ANALYSIS"}),
        required_data_types=["vcf", "gene_list"],
    ),
    "pathway_analysis": W9Template(
        name="pathway_analysis",
        description="Pathway & Network Analysis — GO/Reactome/KEGG enrichment + STRING PPI",
        skip_steps=frozenset({
            "GENOMIC_ANALYSIS", "VARIANT_ANNOTATION", "PROTEIN_ANALYSIS",
        }),
        budget_default=10.0,
        agentic_steps=frozenset({"PATHWAY_ENRICHMENT", "NETWORK_ANALYSIS"}),
        required_data_types=["gene_list"],
    ),
    "scrnaseq_clustering": W9Template(
        name="scrnaseq_clustering",
        description="scRNA-seq Cell Type Analysis — expression + pathway per cluster",
        skip_steps=frozenset({
            "GENOMIC_ANALYSIS", "VARIANT_ANNOTATION", "PROTEIN_ANALYSIS",
        }),
        budget_default=12.0,
        agentic_steps=frozenset({"EXPRESSION_ANALYSIS"}),
        required_data_types=["count_matrix"],
    ),
    "multi_omics": W9Template(
        name="multi_omics",
        description="Full Multi-Omics Analysis — all 21 steps (default)",
        skip_steps=frozenset(),
        budget_default=25.0,
        agentic_steps=frozenset({"GENOMIC_ANALYSIS"}),
        required_data_types=["count_matrix", "vcf"],
    ),
    "literature_only": W9Template(
        name="literature_only",
        description="Literature-Only Analysis — skip all wet-lab data steps, focus on interpretation",
        skip_steps=frozenset({
            "GENOMIC_ANALYSIS", "EXPRESSION_ANALYSIS", "PROTEIN_ANALYSIS",
            "VARIANT_ANNOTATION", "PATHWAY_ENRICHMENT", "NETWORK_ANALYSIS",
        }),
        budget_default=5.0,
        agentic_steps=frozenset(),
        required_data_types=[],
    ),
}
