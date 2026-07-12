"""Peer review models for W8 Paper Review workflow.

Includes: PaperClaim, PaperClaimsExtraction, MethodologyAssessment,
ReviewComment, PeerReviewSynthesis, W8PeerReviewReport.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class PaperClaim(BaseModel):
    """A single claim extracted from a paper."""

    claim_text: str = Field(description="The claim statement")
    section: str = Field(description="Paper section where claim appears")
    claim_type: Literal["main_finding", "methodology", "interpretation", "background"] = Field(
        description="Classification of the claim"
    )
    supporting_refs: list[str] = Field(
        default_factory=list,
        description="DOI/PMID references cited for this claim",
    )
    verbatim_quote: str = Field(
        default="",
        description="Exact quote from the paper supporting this claim",
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Extraction confidence",
    )


class PaperClaimsExtraction(BaseModel):
    """Instructor response_model for EXTRACT_CLAIMS step."""

    claims: list[PaperClaim] = Field(default_factory=list)
    paper_type: Literal[
        "original_research", "review", "methods", "case_report", "commentary"
    ] = "original_research"
    stated_hypothesis: str | None = Field(
        default=None,
        description="The paper's stated hypothesis, if any",
    )
    key_methods: list[str] = Field(
        default_factory=list,
        description="Key experimental methods used",
    )


class MethodologyAssessment(BaseModel):
    """Instructor response_model for METHODOLOGY_REVIEW step."""

    study_design_critique: str = Field(
        description="Assessment of overall study design (e.g., randomized, observational, case-control)"
    )
    statistical_methods: str = Field(
        description="Evaluation of statistical approaches used"
    )
    controls_adequacy: str = Field(
        description="Assessment of experimental controls"
    )
    sample_size_assessment: str = Field(
        description="Evaluation of sample sizes and power"
    )
    potential_biases: list[str] = Field(
        default_factory=list,
        description="Identified potential biases",
    )
    reproducibility_concerns: list[str] = Field(
        default_factory=list,
        description="Concerns about reproducibility",
    )
    domain_specific_issues: list[str] = Field(
        default_factory=list,
        description="Domain-specific methodological issues (e.g., radiation dose, microgravity duration)",
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="Methodological strengths",
    )
    overall_methodology_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Overall methodology quality score",
    )


class ReviewComment(BaseModel):
    """A single review comment."""

    category: Literal["major", "minor", "suggestion", "question"] = Field(
        description="Comment severity/type"
    )
    section: str = Field(description="Paper section this comment addresses")
    comment: str = Field(description="The review comment text")
    evidence_basis: str = Field(
        default="",
        description="Analysis that led to this comment",
    )


class PeerReviewSynthesis(BaseModel):
    """Instructor response_model for SYNTHESIZE_REVIEW step."""

    summary_assessment: str = Field(
        description="2-3 paragraph overall assessment of the paper"
    )
    decision: Literal["accept", "minor_revision", "major_revision", "reject"] = Field(
        description="Recommended editorial decision"
    )
    decision_reasoning: str = Field(
        description="Justification for the recommended decision"
    )
    comments: list[ReviewComment] = Field(
        default_factory=list,
        description="Structured review comments",
    )
    confidence_in_conclusions: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Confidence in the paper's main conclusions",
    )


class NoveltyAssessment(BaseModel):
    """Novelty assessment comparing paper claims vs. recent landmark literature."""

    novelty_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="0.0=fully replicates existing work, 1.0=entirely novel",
    )
    already_established: list[str] = Field(
        default_factory=list,
        description="Findings already reported in prior landmark studies, with specific citations",
    )
    unique_contributions: list[str] = Field(
        default_factory=list,
        description="Genuinely novel aspects not previously reported",
    )
    landmark_papers_missing: list[str] = Field(
        default_factory=list,
        description="Key recent papers authors should cite/compare against (with suggested action)",
    )
    novelty_recommendation: str = Field(
        default="",
        description="Specific recommendation for authors on how to frame novelty",
    )


class W8PeerReviewReport(BaseModel):
    """Final assembled peer review report."""

    paper_title: str = ""
    review_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    claims_extracted: list[PaperClaim] = Field(default_factory=list)
    citation_report: dict = Field(default_factory=dict)
    literature_comparison: dict = Field(default_factory=dict)
    novelty_assessment: NoveltyAssessment | None = None
    integrity_audit: dict = Field(default_factory=dict)
    contradiction_findings: dict = Field(default_factory=dict)
    methodology_assessment: MethodologyAssessment | None = None
    rcmxt_scores: list[dict] = Field(default_factory=list)
    synthesis: PeerReviewSynthesis | None = None
    session_manifest: dict = Field(default_factory=dict)
    markdown_report: str = ""
