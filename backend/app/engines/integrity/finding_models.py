"""Pydantic models for data integrity findings.

Shared across all integrity checkers (gene name, statistical, retraction, metadata).
"""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

# === Type aliases ===

IntegritySeverity = Literal["info", "warning", "error", "critical"]

IntegrityCategory = Literal[
    "gene_name_error",
    "statistical_inconsistency",
    "retracted_reference",
    "corrected_reference",
    "pubpeer_flagged",
    "metadata_error",
    "sample_size_mismatch",
    "genome_build_inconsistency",
    "p_value_mismatch",
    "benford_anomaly",
    "grim_failure",
]


# === Base finding ===


class IntegrityFinding(BaseModel):
    """Base finding from any integrity checker."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    category: IntegrityCategory
    severity: IntegritySeverity = "warning"
    title: str = ""
    description: str = ""
    source_text: str = ""
    suggestion: str = ""
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    checker: str = ""
    metadata: dict = Field(default_factory=dict)


# === Gene name findings ===


class GeneNameFinding(IntegrityFinding):
    """Gene name error finding (Excel corruption, deprecated symbol, etc.)."""

    category: IntegrityCategory = "gene_name_error"
    original_text: str = ""
    corrected_symbol: str = ""
    hgnc_id: str = ""
    error_type: str = ""  # "excel_date", "deprecated", "alias", "ocr"


# === Statistical findings ===


class GRIMResult(BaseModel):
    """Result of a single GRIM test."""

    mean: float
    n: int
    decimals: int = 2
    is_consistent: bool = True
    explanation: str = ""


class BenfordResult(BaseModel):
    """Result of Benford's Law analysis."""

    n_values: int = 0
    chi_squared: float = 0.0
    p_value: float = 1.0
    is_anomalous: bool = False
    digit_distribution: dict[str, float] = Field(default_factory=dict)
    expected_distribution: dict[str, float] = Field(default_factory=dict)


class PValueCheckResult(BaseModel):
    """Result of p-value consistency check."""

    test_type: str = ""  # "t", "F", "chi2", "r"
    reported_statistic: float = 0.0
    reported_df: str = ""  # e.g. "1,23" or "45"
    reported_p: float = 0.0
    recalculated_p: float = 0.0
    discrepancy: float = 0.0
    is_consistent: bool = True


class StatisticalFinding(IntegrityFinding):
    """Statistical inconsistency finding (GRIM, Benford, p-value)."""

    category: IntegrityCategory = "statistical_inconsistency"
    grim_result: GRIMResult | None = None
    benford_result: BenfordResult | None = None
    p_value_result: PValueCheckResult | None = None


# === Retraction / publication findings ===


class RetractionStatus(BaseModel):
    """Retraction/correction status for a single DOI."""

    doi: str = ""
    is_retracted: bool = False
    is_corrected: bool = False
    has_expression_of_concern: bool = False
    retraction_doi: str | None = None
    correction_doi: str | None = None
    retraction_date: str | None = None
    publisher: str = ""


class PubPeerStatus(BaseModel):
    """PubPeer commentary status for a single DOI."""

    doi: str = ""
    comment_count: int = 0
    has_comments: bool = False
    url: str = ""


class RetractionFinding(IntegrityFinding):
    """Retracted or corrected reference finding."""

    category: IntegrityCategory = "retracted_reference"
    doi: str = ""
    retraction_status: RetractionStatus | None = None
    pubpeer_status: PubPeerStatus | None = None


# === Metadata findings ===


class AccessionFinding(IntegrityFinding):
    """Invalid or suspicious data repository accession."""

    category: IntegrityCategory = "metadata_error"
    accession: str = ""
    accession_type: str = ""  # "GEO", "SRA", "dbGaP"


class GenomeBuildFinding(IntegrityFinding):
    """Genome build inconsistency finding."""

    category: IntegrityCategory = "genome_build_inconsistency"
    builds_found: list[str] = Field(default_factory=list)


class SampleSizeFinding(IntegrityFinding):
    """Sample size mismatch finding."""

    category: IntegrityCategory = "sample_size_mismatch"
    stated_n: int = 0
    computed_n: int = 0


# === Aggregated report ===


class IntegrityReport(BaseModel):
    """Aggregated report from all integrity checkers."""

    total_findings: int = 0
    findings_by_severity: dict[str, int] = Field(default_factory=dict)
    findings_by_category: dict[str, int] = Field(default_factory=dict)
    findings: list[IntegrityFinding] = Field(default_factory=list)
    overall_level: Literal["clean", "minor_issues", "significant_issues", "critical"] = "clean"
    summary: str = ""
    recommended_action: str = ""
