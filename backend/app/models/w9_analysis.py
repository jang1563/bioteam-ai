"""W9 Deep Bioinformatics Analysis — Pydantic models.

These models structure the outputs of each phase in the W9 pipeline:
Phase A: Scoping & Ingestion
Phase B: Domain Analysis
Phase C: Integration
Phase D: Interpretation
Phase E: Output
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Phase A: Scoping & Ingestion
# ---------------------------------------------------------------------------


class ResearchScopeDefinition(BaseModel):
    """Output of SCOPE step — defines the research question and analysis boundaries."""

    research_question: str = ""
    analysis_type: Literal[
        "variant_analysis", "expression_analysis", "multi_omics",
        "pathway_analysis", "structural_analysis", "literature_only"
    ] = "multi_omics"
    target_genes: list[str] = Field(default_factory=list)
    target_pathways: list[str] = Field(default_factory=list)
    organism: str = "Homo sapiens"
    tissue_context: list[str] = Field(default_factory=list)
    relevant_phenotypes: list[str] = Field(default_factory=list)
    scope_rationale: str = ""
    estimated_cost_usd: float = 0.0
    scope_confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    unverified_bio_claims: list[str] = Field(
        default_factory=list,
        description="Biological facts stated without grounding in provided data",
    )


class DataManifest(BaseModel):
    """Output of INGEST_DATA step — describes loaded input files."""

    files_loaded: list[dict] = Field(default_factory=list)  # {path, type, size_mb, checksum}
    sample_count: int = 0
    data_types: list[str] = Field(default_factory=list)  # vcf, fastq, count_matrix, etc.
    total_size_mb: float = 0.0
    quality_flags: list[str] = Field(default_factory=list)
    ingest_warnings: list[str] = Field(default_factory=list)


class QCReport(BaseModel):
    """Output of QC step — data quality gate."""

    passed: bool = True
    samples_passed: int = 0
    samples_failed: int = 0
    failure_reasons: list[str] = Field(default_factory=list)
    qc_metrics: dict = Field(default_factory=dict)  # {metric_name: value}
    recommendations: list[str] = Field(default_factory=list)
    qc_summary: str = ""


# ---------------------------------------------------------------------------
# Phase B: Domain Analysis
# ---------------------------------------------------------------------------


class VariantAnnotationResult(BaseModel):
    """Output of VARIANT_ANNOTATION step."""

    total_variants: int = 0
    high_impact_variants: list[dict] = Field(default_factory=list)  # VEP results
    pathogenic_variants: list[dict] = Field(default_factory=list)   # ClinVar
    novel_variants: list[dict] = Field(default_factory=list)        # Not in ClinVar/gnomAD
    affected_genes: list[str] = Field(default_factory=list)
    acmg_classifications: dict = Field(default_factory=dict)  # gene → classification
    summary: str = ""
    unverified_bio_claims: list[str] = Field(default_factory=list)


class ExpressionAnalysisResult(BaseModel):
    """Output of EXPRESSION_ANALYSIS step."""

    total_degs: int = 0
    up_regulated: list[dict] = Field(default_factory=list)   # {gene, log2FC, padj}
    down_regulated: list[dict] = Field(default_factory=list)
    top_degs: list[dict] = Field(default_factory=list)       # Top 20 by |log2FC|
    normalization_method: str = ""
    comparison: str = ""  # e.g., "treated vs control"
    sample_sizes: dict = Field(default_factory=dict)
    summary: str = ""
    unverified_bio_claims: list[str] = Field(default_factory=list)


class ProteinAnalysisResult(BaseModel):
    """Output of PROTEIN_ANALYSIS step."""

    proteins_analyzed: int = 0
    differentially_abundant: list[dict] = Field(default_factory=list)
    key_interactions: list[dict] = Field(default_factory=list)  # STRING results
    functional_domains: list[dict] = Field(default_factory=list)
    summary: str = ""
    unverified_bio_claims: list[str] = Field(default_factory=list)


class PathwayEnrichmentResult(BaseModel):
    """Output of PATHWAY_ENRICHMENT step — GO/Reactome/KEGG results."""

    top_pathways: list[dict] = Field(default_factory=list)  # Formatted g:Profiler results
    go_bp_top5: list[dict] = Field(default_factory=list)
    go_mf_top5: list[dict] = Field(default_factory=list)
    reactome_top5: list[dict] = Field(default_factory=list)
    kegg_top5: list[dict] = Field(default_factory=list)
    genes_submitted: int = 0
    significant_terms: int = 0
    enrichment_summary: str = ""
    unverified_bio_claims: list[str] = Field(default_factory=list)


class NetworkAnalysisResult(BaseModel):
    """Output of NETWORK_ANALYSIS step — STRING PPI network."""

    hub_genes: list[str] = Field(default_factory=list)
    high_confidence_interactions: list[dict] = Field(default_factory=list)
    modules_identified: int = 0
    network_summary: str = ""
    unverified_bio_claims: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase C: Integration
# ---------------------------------------------------------------------------


class CrossOmicsIntegrationResult(BaseModel):
    """Output of CROSS_OMICS_INTEGRATION step."""

    shared_genes: list[str] = Field(
        default_factory=list,
        description="Genes altered at both genomic and expression level",
    )
    discordant_signals: list[dict] = Field(
        default_factory=list,
        description="Genes with unexpected omics layer disagreement",
    )
    causal_candidates: list[dict] = Field(
        default_factory=list,
        description="Genes/variants with strongest causal evidence",
    )
    protein_mrna_correlation: list[dict] = Field(
        default_factory=list,
        description="Spearman correlation for protein-mRNA pairs (expected ≥0.4)",
    )
    low_correlation_flags: list[str] = Field(
        default_factory=list,
        description="Genes with correlation <0.2 without PTM explanation",
    )
    integration_summary: str = ""
    unverified_bio_claims: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase D: Interpretation
# ---------------------------------------------------------------------------


class NoveltyAssessment(BaseModel):
    """Output of NOVELTY_ASSESSMENT step."""

    novel_findings: list[dict] = Field(default_factory=list)
    confirmed_findings: list[dict] = Field(default_factory=list)
    contradictory_findings: list[dict] = Field(default_factory=list)
    novelty_score: float = Field(default=0.5, ge=0.0, le=1.0)
    impact_assessment: str = ""
    literature_gaps: list[str] = Field(default_factory=list)
    unverified_bio_claims: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase E: Output
# ---------------------------------------------------------------------------


class ExperimentalDesignPlan(BaseModel):
    """Output of EXPERIMENTAL_DESIGN step."""

    priority_experiments: list[dict] = Field(default_factory=list)  # {name, rationale, est_cost}
    validation_approaches: list[str] = Field(default_factory=list)
    estimated_timeline_months: int = 0
    resource_requirements: list[str] = Field(default_factory=list)
    design_rationale: str = ""


class GrantRelevanceAnalysis(BaseModel):
    """Output of GRANT_RELEVANCE step."""

    nih_mechanisms: list[dict] = Field(default_factory=list)  # {mechanism, rationale, foa}
    nsf_programs: list[dict] = Field(default_factory=list)
    funding_landscape: str = ""
    significance_statement: str = ""
    innovation_statement: str = ""
    approach_brief: str = ""


class W9BioinformaticsReport(BaseModel):
    """Complete W9 analysis report — assembled by w9_report_builder.py."""

    workflow_id: str = ""
    query: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Phase A
    scope: ResearchScopeDefinition = Field(default_factory=ResearchScopeDefinition)
    data_manifest: DataManifest = Field(default_factory=DataManifest)
    qc_report: QCReport = Field(default_factory=QCReport)

    # Phase B
    variant_annotation: VariantAnnotationResult = Field(default_factory=VariantAnnotationResult)
    expression_analysis: ExpressionAnalysisResult = Field(default_factory=ExpressionAnalysisResult)
    protein_analysis: ProteinAnalysisResult = Field(default_factory=ProteinAnalysisResult)
    pathway_enrichment: PathwayEnrichmentResult = Field(default_factory=PathwayEnrichmentResult)
    network_analysis: NetworkAnalysisResult = Field(default_factory=NetworkAnalysisResult)

    # Phase C
    cross_omics: CrossOmicsIntegrationResult = Field(default_factory=CrossOmicsIntegrationResult)

    # Phase D
    novelty_assessment: NoveltyAssessment = Field(default_factory=NoveltyAssessment)

    # Phase E
    experimental_design: ExperimentalDesignPlan = Field(default_factory=ExperimentalDesignPlan)
    grant_relevance: GrantRelevanceAnalysis = Field(default_factory=GrantRelevanceAnalysis)

    # Summary
    executive_summary: str = ""
    key_findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    total_cost_usd: float = 0.0

    # Anti-hallucination: aggregate unverified claims across all phases
    all_unverified_claims: list[str] = Field(default_factory=list)
