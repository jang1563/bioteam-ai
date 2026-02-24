"""Evidence and scoring models.

Includes: Evidence, RCMXTScore, OmicsLayerStatus, ContradictionEntry, DataRegistry.
All defined per plan_v4.md Section "Data Models".

v4.2 changes:
- Evidence: added verbatim_quote for claim-source fidelity anchoring
- ContradictionEntry: type changed from str to list[str] for multi-label support
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlmodel import SQLModel, Field as SQLField, Column, JSON


# === SQL Tables (persisted in SQLite) ===


class Evidence(SQLModel, table=True):
    """A single piece of evidence from literature or internal sources."""

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    claim: str
    source_doi: str | None = None
    source_pmid: str | None = None
    source_type: str  # "primary_literature" | "preprint" | "internal_synthesis" | "lab_kb" | "clinical_trial"
    text: str
    verbatim_quote: str | None = None  # v4.2: exact quote from source for claim-source fidelity
    organism: str | None = None
    cell_type: str | None = None
    condition: str | None = None
    sample_size: int | None = None
    methodology: str | None = None
    findings: list[str] = SQLField(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str  # Agent ID or "human"


class ContradictionEntry(SQLModel, table=True):
    """A detected contradiction between two claims."""

    __tablename__ = "contradiction_entry"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    claim_a: str
    claim_b: str
    types: list[str] = SQLField(default_factory=list, sa_column=Column(JSON))  # v4.2: multi-label — list of ContradictionType values
    resolution_hypotheses: list[str] = SQLField(default_factory=list, sa_column=Column(JSON))
    rcmxt_a: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    rcmxt_b: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    discriminating_experiment: str | None = None
    detected_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    detected_by: str  # Agent ID
    workflow_id: str | None = None


class DataRegistry(SQLModel, table=True):
    """Tracks all data files referenced by the system."""

    __tablename__ = "data_registry"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str
    file_path: str
    file_type: str  # "csv" | "tsv" | "h5ad" | "fastq" | "bam" | "vcf" | "other"
    organism: str | None = None
    data_type: str | None = None  # "rnaseq" | "scrnaseq" | etc.
    sample_count: int | None = None
    columns: list[str] | None = SQLField(default=None, sa_column=Column(JSON))
    size_bytes: int = 0
    checksum: str = ""  # SHA256
    registered_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    registered_by: str = "human"
    notes: str | None = None


# === Pydantic-only models (not persisted to SQL, used in agent I/O) ===


EvidenceSourceType = Literal[
    "primary_literature",
    "preprint",
    "internal_synthesis",
    "lab_kb",
    "clinical_trial",
]

ContradictionType = Literal[
    "conditional_truth",
    "technical_artifact",
    "interpretive_framing",
    "statistical_noise",
    "temporal_dynamics",
]


class RCMXTScore(BaseModel):
    """5-axis evidence confidence vector."""

    claim: str
    R: float = Field(ge=0.0, le=1.0, description="Reproducibility")
    C: float = Field(ge=0.0, le=1.0, description="Condition Specificity")
    M: float = Field(ge=0.0, le=1.0, description="Methodological Robustness")
    X: float | None = Field(default=None, ge=0.0, le=1.0, description="Cross-Omics (NULL if unavailable)")
    T: float = Field(ge=0.0, le=1.0, description="Temporal Stability")
    composite: float | None = None
    sources: list[str] = Field(default_factory=list, description="Evidence IDs used")
    provenance: Literal["primary_literature", "internal_synthesis"] = "primary_literature"
    scored_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scorer_version: str = "v0.1"
    model_version: str = ""

    def compute_composite(self) -> float | None:
        """Average across available axes."""
        axes = [self.R, self.C, self.M, self.T]
        if self.X is not None:
            axes.append(self.X)
        self.composite = round(sum(axes) / len(axes), 3)
        return self.composite


class AxisExplanation(BaseModel):
    """Per-axis scoring explanation from LLM."""

    axis: Literal["R", "C", "M", "X", "T"]
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(description="2-3 sentence justification for this score", min_length=10)
    key_evidence: list[str] = Field(
        default_factory=list,
        description="Source DOIs or PMIDs supporting this score",
    )


class LLMRCMXTResponse(BaseModel):
    """Structured LLM output for RCMXT scoring.

    Used as response_model for LLMLayer.complete_structured().
    Includes per-axis explanations for audit trails and calibration.
    """

    claim_text: str = Field(description="The claim being scored (echoed back)")
    axes: list[AxisExplanation] = Field(
        min_length=4,
        max_length=5,
        description="Scores for each axis. 4 axes (R,C,M,T) if X not applicable, 5 if applicable.",
    )
    x_applicable: bool = Field(
        description="True if multi-omics data is available/relevant for this claim",
    )
    overall_assessment: str = Field(
        description="1-2 sentence summary of overall evidence quality",
    )
    confidence_in_scoring: float = Field(
        ge=0.0, le=1.0,
        description="Self-assessed confidence in scoring accuracy",
    )


class OmicsLayerStatus(BaseModel):
    """Status of multi-omics evidence for a claim."""

    layers_available: list[str] = Field(default_factory=list)
    layers_agreeing: list[str] = Field(default_factory=list)
    layers_contradicting: list[str] = Field(default_factory=list)
    multi_omics_available: bool = False


# === v4.2: Session Manifest, PRISMA, Export models ===


class PRISMAFlow(BaseModel):
    """PRISMA-style flow diagram data for systematic reviews (W1).

    Auto-generated from W1 Literature Review workflow steps.
    """

    records_identified: int = 0         # SEARCH step output
    records_from_databases: int = 0     # PubMed + S2 + bioRxiv
    records_from_lab_kb: int = 0        # Lab KB entries
    duplicates_removed: int = 0         # Dedup by DOI/PMID
    records_screened: int = 0           # SCREEN step input
    records_excluded_screening: int = 0 # SCREEN step rejects
    full_text_assessed: int = 0         # EXTRACT step input
    full_text_excluded: int = 0         # EXTRACT step rejects
    full_text_exclusion_reasons: dict[str, int] = Field(default_factory=dict)
    studies_included: int = 0           # Final included
    negative_results_found: int = 0     # NR Module matches


class SessionManifest(BaseModel):
    """Reproducibility manifest for a workflow run.

    v4.2: Auto-generated at workflow completion. Captures every
    parameter needed to reproduce or audit a session.
    """

    workflow_id: str
    template: str
    query: str
    started_at: datetime
    completed_at: datetime | None = None

    # LLM call log
    llm_calls: list[dict] = Field(default_factory=list)  # List of LLMResponse-like dicts
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0

    # Model versions used
    model_versions: list[str] = Field(default_factory=list)  # Unique model IDs seen
    temperature_settings: dict[str, float] = Field(default_factory=dict)  # step_id -> temperature

    # Data provenance
    search_queries: list[str] = Field(default_factory=list)
    databases_searched: list[str] = Field(default_factory=list)
    papers_retrieved: list[str] = Field(default_factory=list)  # DOIs
    seed_papers: list[str] = Field(default_factory=list)       # User-provided DOIs

    # System version
    system_version: str = ""
    config_snapshot: dict = Field(default_factory=dict)

    # PRISMA (for W1)
    prisma: PRISMAFlow | None = None


class ExportBibTeX(BaseModel):
    """BibTeX export data for cited sources."""

    entries: list[dict] = Field(default_factory=list)  # Each dict has: key, type, fields

    def render(self) -> str:
        """Render to BibTeX string."""
        lines = []
        for entry in self.entries:
            etype = entry.get("type", "article")
            key = entry.get("key", "unknown")
            lines.append(f"@{etype}{{{key},")
            for k, v in entry.get("fields", {}).items():
                lines.append(f"  {k} = {{{v}}},")
            lines.append("}")
            lines.append("")
        return "\n".join(lines)


class ExportMarkdown(BaseModel):
    """Markdown export of a workflow report."""

    title: str = ""
    sections: list[dict] = Field(default_factory=list)  # {heading, content, level}
    ai_disclosure: str = ""  # Auto-generated disclosure statement
    session_manifest_summary: str = ""

    def render(self) -> str:
        """Render to Markdown string."""
        lines = []
        if self.title:
            lines.append(f"# {self.title}\n")
        for section in self.sections:
            level = section.get("level", 2)
            heading = section.get("heading", "")
            content = section.get("content", "")
            lines.append(f"{'#' * level} {heading}\n")
            lines.append(f"{content}\n")
        if self.ai_disclosure:
            lines.append("## AI Disclosure\n")
            lines.append(f"{self.ai_disclosure}\n")
        return "\n".join(lines)
