"""Tests for peer review Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.peer_review import (
    MethodologyAssessment,
    PaperClaim,
    PaperClaimsExtraction,
    PeerReviewSynthesis,
    ReviewComment,
    W8PeerReviewReport,
)


class TestPaperClaim:
    def test_default_values(self):
        claim = PaperClaim(
            claim_text="Gene X is upregulated",
            section="Results",
            claim_type="main_finding",
        )
        assert claim.confidence == 0.8
        assert claim.supporting_refs == []
        assert claim.verbatim_quote == ""

    def test_all_claim_types(self):
        for ct in ("main_finding", "methodology", "interpretation", "background"):
            claim = PaperClaim(
                claim_text="test", section="test", claim_type=ct,
            )
            assert claim.claim_type == ct

    def test_invalid_claim_type_raises(self):
        with pytest.raises(ValidationError):
            PaperClaim(
                claim_text="test", section="test", claim_type="invalid_type",
            )

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            PaperClaim(
                claim_text="test", section="test", claim_type="main_finding",
                confidence=1.5,
            )
        with pytest.raises(ValidationError):
            PaperClaim(
                claim_text="test", section="test", claim_type="main_finding",
                confidence=-0.1,
            )


class TestPaperClaimsExtraction:
    def test_default_values(self):
        extraction = PaperClaimsExtraction()
        assert extraction.claims == []
        assert extraction.paper_type == "original_research"
        assert extraction.stated_hypothesis is None
        assert extraction.key_methods == []

    def test_all_paper_types(self):
        for pt in ("original_research", "review", "methods", "case_report", "commentary"):
            ext = PaperClaimsExtraction(paper_type=pt)
            assert ext.paper_type == pt

    def test_with_claims(self):
        ext = PaperClaimsExtraction(
            claims=[
                PaperClaim(claim_text="Finding A", section="Results", claim_type="main_finding"),
                PaperClaim(claim_text="Finding B", section="Discussion", claim_type="interpretation"),
            ],
            stated_hypothesis="X causes Y",
            key_methods=["RNA-seq", "qPCR"],
        )
        assert len(ext.claims) == 2
        assert ext.stated_hypothesis == "X causes Y"


class TestMethodologyAssessment:
    def test_default_score(self):
        ma = MethodologyAssessment(
            study_design_critique="Good",
            statistical_methods="Appropriate",
            controls_adequacy="Adequate",
            sample_size_assessment="Sufficient",
        )
        assert ma.overall_methodology_score == 0.5
        assert ma.potential_biases == []
        assert ma.strengths == []

    def test_score_bounds(self):
        with pytest.raises(ValidationError):
            MethodologyAssessment(
                study_design_critique="test",
                statistical_methods="test",
                controls_adequacy="test",
                sample_size_assessment="test",
                overall_methodology_score=1.5,
            )

    def test_full_assessment(self):
        ma = MethodologyAssessment(
            study_design_critique="Randomized controlled",
            statistical_methods="DESeq2 with Bonferroni",
            controls_adequacy="Ground controls included",
            sample_size_assessment="n=12 per group, adequate",
            potential_biases=["Selection bias", "Batch effects"],
            reproducibility_concerns=["No code availability"],
            domain_specific_issues=["Short spaceflight duration"],
            strengths=["Large sample size", "Multiple omics layers"],
            overall_methodology_score=0.85,
        )
        assert len(ma.potential_biases) == 2
        assert len(ma.strengths) == 2
        assert ma.overall_methodology_score == 0.85


class TestReviewComment:
    def test_all_categories(self):
        for cat in ("major", "minor", "suggestion", "question"):
            comment = ReviewComment(
                category=cat,
                section="Methods",
                comment="Test comment",
            )
            assert comment.category == cat

    def test_with_evidence_basis(self):
        comment = ReviewComment(
            category="major",
            section="Results",
            comment="The sample size is too small",
            evidence_basis="RCMXT M-score of 0.3",
        )
        assert comment.evidence_basis != ""


class TestPeerReviewSynthesis:
    def test_default_values(self):
        synth = PeerReviewSynthesis(
            summary_assessment="A well-conducted study",
            decision="minor_revision",
            decision_reasoning="Minor issues",
        )
        assert synth.confidence_in_conclusions == 0.7
        assert synth.comments == []

    def test_all_decisions(self):
        for d in ("accept", "minor_revision", "major_revision", "reject"):
            synth = PeerReviewSynthesis(
                summary_assessment="test",
                decision=d,
                decision_reasoning="test",
            )
            assert synth.decision == d

    def test_with_comments(self):
        synth = PeerReviewSynthesis(
            summary_assessment="Promising study with notable limitations.",
            decision="major_revision",
            decision_reasoning="Key methodological concerns need addressing.",
            comments=[
                ReviewComment(category="major", section="Methods", comment="Missing controls"),
                ReviewComment(category="minor", section="Results", comment="Typo in Figure 2"),
            ],
            confidence_in_conclusions=0.6,
        )
        assert len(synth.comments) == 2
        assert synth.confidence_in_conclusions == 0.6


class TestW8PeerReviewReport:
    def test_default_values(self):
        report = W8PeerReviewReport()
        assert report.paper_title == ""
        assert report.claims_extracted == []
        assert report.synthesis is None
        assert report.methodology_assessment is None
        assert report.markdown_report == ""

    def test_full_report(self):
        report = W8PeerReviewReport(
            paper_title="Test Paper",
            claims_extracted=[
                PaperClaim(claim_text="A", section="Results", claim_type="main_finding"),
            ],
            citation_report={"total_citations": 10, "verified": 8},
            methodology_assessment=MethodologyAssessment(
                study_design_critique="Good",
                statistical_methods="Appropriate",
                controls_adequacy="Adequate",
                sample_size_assessment="OK",
            ),
            synthesis=PeerReviewSynthesis(
                summary_assessment="Good paper",
                decision="minor_revision",
                decision_reasoning="Minor issues",
            ),
        )
        assert report.paper_title == "Test Paper"
        assert len(report.claims_extracted) == 1
        assert report.synthesis.decision == "minor_revision"

    def test_json_serialization(self):
        report = W8PeerReviewReport(paper_title="Test")
        data = report.model_dump(mode="json")
        assert data["paper_title"] == "Test"
        assert isinstance(data["review_date"], str)
