"""W10 Drug Discovery workflow models.

Pydantic models for the W10 12-step drug discovery pipeline.
Uses ChEMBL MCP (compound, bioactivity, ADMET) + ClinicalTrials MCP.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CompoundProfile(BaseModel):
    """Profile of a drug compound from ChEMBL."""

    chembl_id: str = ""
    name: str = ""
    smiles: str = ""
    molecular_formula: str = ""
    molecular_weight: float | None = None
    hba: int | None = None   # H-bond acceptors
    hbd: int | None = None   # H-bond donors
    logp: float | None = None
    max_phase: int | None = None  # Clinical development phase (0-4)
    indication: str = ""


class BioactivitySummary(BaseModel):
    """Summary of compound bioactivity against a target."""

    target_id: str = ""
    target_name: str = ""
    gene_symbol: str = ""
    activity_type: str = ""  # IC50, EC50, Ki, Kd, etc.
    value_nm: float | None = None  # Activity value in nM
    relation: str = ""  # "=", "<", ">", "~"
    assay_description: str = ""
    confidence_score: int | None = None  # ChEMBL assay confidence (0-9)


class ClinicalTrialSummary(BaseModel):
    """Summary of a relevant clinical trial."""

    nct_id: str = ""
    title: str = ""
    phase: str = ""
    status: str = ""
    condition: str = ""
    intervention: str = ""
    enrollment: int | None = None
    primary_endpoint: str = ""
    sponsor: str = ""


class DrugDiscoveryScope(BaseModel):
    """Scope definition from SCOPE step."""

    research_question: str = ""
    target_compound_or_class: str = ""
    therapeutic_area: str = ""
    key_objectives: list[str] = Field(default_factory=list)
    search_strategy: str = ""


class EfficacyAnalysis(BaseModel):
    """Efficacy analysis from EFFICACY_ANALYSIS step."""

    summary: str = ""
    key_findings: list[str] = Field(default_factory=list)
    potency_assessment: str = ""  # "strong", "moderate", "weak", "unknown"
    selectivity_notes: str = ""
    limitations: list[str] = Field(default_factory=list)


class MechanismReview(BaseModel):
    """Mechanism of action review from MECHANISM_REVIEW step."""

    primary_mechanism: str = ""
    target_pathway: str = ""
    on_target_evidence: list[str] = Field(default_factory=list)
    off_target_risks: list[str] = Field(default_factory=list)
    mechanistic_gaps: list[str] = Field(default_factory=list)


class LiteratureComparison(BaseModel):
    """Literature comparison result."""

    similar_compounds: list[str] = Field(default_factory=list)
    novelty_assessment: str = ""
    key_differences: list[str] = Field(default_factory=list)
    relevant_papers: list[str] = Field(default_factory=list)


class GrantRelevanceAssessment(BaseModel):
    """Grant relevance assessment from GRANT_RELEVANCE step."""

    relevance_score: float = 0.0  # 0.0-1.0
    funding_agencies: list[str] = Field(default_factory=list)
    mechanism_fit: str = ""
    innovation_statement: str = ""
    rationale: str = ""


class W10DrugDiscoveryResult(BaseModel):
    """Full result of the W10 Drug Discovery workflow."""

    workflow_id: str = ""
    query: str = ""

    # Step results
    scope: DrugDiscoveryScope | None = None
    compound_profiles: list[CompoundProfile] = Field(default_factory=list)
    bioactivity_data: list[BioactivitySummary] = Field(default_factory=list)
    target_summary: str = ""
    trial_summaries: list[ClinicalTrialSummary] = Field(default_factory=list)
    efficacy_analysis: EfficacyAnalysis | None = None
    safety_profile_summary: str = ""  # ADMET text summary from ChEMBL
    mechanism_review: MechanismReview | None = None
    literature_comparison: LiteratureComparison | None = None
    grant_relevance: GrantRelevanceAssessment | None = None

    # Final report
    report_markdown: str = ""
    cost_usd: float = 0.0
    mcp_used: bool = False
