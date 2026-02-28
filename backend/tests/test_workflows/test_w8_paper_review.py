"""Tests for W8 Paper Review runner and report builder."""

from __future__ import annotations

import pytest

from app.engines.w8_report_builder import (
    build_peer_review_report,
    build_w8_session_manifest,
    render_markdown_report,
)
from app.models.agent import AgentOutput
from app.models.peer_review import (
    MethodologyAssessment,
    PaperClaim,
    PeerReviewSynthesis,
    ReviewComment,
    W8PeerReviewReport,
)
from app.models.workflow import WorkflowInstance
from app.workflows.runners.w8_paper_review import (
    W8PaperReviewRunner,
    W8_STEPS,
    _CODE_STEPS,
    _METHOD_MAP,
)


# === Step Definitions Tests ===

class TestW8Steps:
    def test_step_count(self):
        assert len(W8_STEPS) == 13

    def test_step_ids(self):
        ids = [s.id for s in W8_STEPS]
        expected = [
            "INGEST", "PARSE_SECTIONS", "EXTRACT_CLAIMS", "CITE_VALIDATION",
            "BACKGROUND_LIT", "NOVELTY_CHECK", "INTEGRITY_AUDIT", "CONTRADICTION_CHECK",
            "METHODOLOGY_REVIEW", "EVIDENCE_GRADE", "HUMAN_CHECKPOINT",
            "SYNTHESIZE_REVIEW", "REPORT",
        ]
        assert ids == expected

    def test_step_chain(self):
        """Verify each step points to the next."""
        for i, step in enumerate(W8_STEPS[:-1]):
            assert step.next_step == W8_STEPS[i + 1].id
        assert W8_STEPS[-1].next_step is None

    def test_human_checkpoint_exists(self):
        checkpoint = [s for s in W8_STEPS if s.is_human_checkpoint]
        assert len(checkpoint) == 1
        assert checkpoint[0].id == "HUMAN_CHECKPOINT"

    def test_code_steps_match(self):
        for step in W8_STEPS:
            if step.agent_id == "code_only":
                assert step.id in _CODE_STEPS

    def test_agent_steps_have_method_map(self):
        for step in W8_STEPS:
            if step.agent_id != "code_only" and step.id != "HUMAN_CHECKPOINT":
                assert step.id in _METHOD_MAP, f"{step.id} missing from _METHOD_MAP"


# === Runner Tests ===

class TestW8PaperReviewRunner:
    @pytest.fixture
    def mock_registry(self):
        from app.agents.registry import create_registry
        from app.llm.mock_layer import MockLLMLayer
        llm = MockLLMLayer()
        return create_registry(llm, memory=None)

    @pytest.fixture
    def runner(self, mock_registry):
        return W8PaperReviewRunner(registry=mock_registry)

    def test_runner_init(self, runner):
        assert runner.registry is not None
        assert runner.engine is not None
        assert runner._step_results == {}

    def test_step_ingest_no_path(self, runner):
        result = runner._step_ingest("")
        assert not result.is_success
        assert "No PDF path" in result.error

    def test_step_ingest_missing_file(self, runner):
        result = runner._step_ingest("/nonexistent/file.pdf")
        assert not result.is_success
        assert "not found" in result.error

    def test_step_ingest_non_pdf(self, runner, tmp_path):
        txt = tmp_path / "test.txt"
        txt.write_text("hello")
        result = runner._step_ingest(str(txt))
        assert not result.is_success
        assert "Not a PDF or DOCX" in result.error

    def test_step_ingest_valid_pdf(self, runner, tmp_path):
        """Test with a minimal valid PDF."""
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Test Paper Title\n\nAbstract\nThis is a test paper.")
        pdf_path = tmp_path / "test.pdf"
        doc.save(str(pdf_path))
        doc.close()

        result = runner._step_ingest(str(pdf_path))
        assert result.is_success
        assert result.output["size_kb"] > 0
        assert runner._pdf_bytes != b""

    def test_step_parse_without_ingest(self, runner):
        result = runner._step_parse()
        assert not result.is_success
        assert "No PDF bytes" in result.error

    def test_step_parse_after_ingest(self, runner, tmp_path):
        """Test parse after successful ingest."""
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Test Paper\n\nAbstract\nThis is a test.\n\nIntroduction\nSome intro.")
        pdf_path = tmp_path / "test.pdf"
        doc.save(str(pdf_path))
        doc.close()

        runner._step_ingest(str(pdf_path))
        result = runner._step_parse()
        assert result.is_success
        assert runner._parsed_paper is not None
        assert runner._paper_title != ""

    def test_build_task_description_extract_claims(self, runner):
        from app.engines.pdf.parser import ParsedPaper, ParsedSection
        runner._parsed_paper = ParsedPaper(
            title="Test",
            sections=[
                ParsedSection(heading="Results", text="Gene X upregulated."),
            ],
            full_text="Gene X upregulated.",
            page_count=1,
        )
        desc = runner._build_task_description("EXTRACT_CLAIMS", {})
        assert "Results" in desc
        assert "Gene X" in desc

    def test_build_task_description_background_lit(self, runner):
        runner._paper_title = "Space Biology Paper"
        prior = {
            "EXTRACT_CLAIMS": {
                "claims": [
                    {"claim_text": "Bone loss occurs", "claim_type": "main_finding"},
                ],
                "stated_hypothesis": "Microgravity causes bone loss",
            }
        }
        desc = runner._build_task_description("BACKGROUND_LIT", prior)
        assert "Microgravity" in desc or "Bone loss" in desc

    def test_build_task_description_synthesize_review(self, runner):
        runner._paper_title = "Test Paper"
        prior = {
            "EXTRACT_CLAIMS": {
                "claims": [
                    {"claim_text": "Finding A", "claim_type": "main_finding"},
                ]
            },
            "CITE_VALIDATION": {"total_citations": 10, "verified": 8},
        }
        desc = runner._build_task_description("SYNTHESIZE_REVIEW", prior)
        assert "Test Paper" in desc
        assert "Finding A" in desc


# === Report Builder Tests ===

class TestW8ReportBuilder:
    @pytest.fixture
    def instance(self):
        return WorkflowInstance(template="W8", query="test review")

    @pytest.fixture
    def step_results(self):
        return {
            "EXTRACT_CLAIMS": AgentOutput(
                agent_id="claim_extractor",
                output={
                    "claims": [
                        {
                            "claim_text": "Gene X upregulated",
                            "section": "Results",
                            "claim_type": "main_finding",
                            "supporting_refs": ["10.1234/test"],
                            "verbatim_quote": "Gene X was upregulated 2-fold",
                            "confidence": 0.9,
                        }
                    ],
                    "paper_type": "original_research",
                    "key_methods": ["RNA-seq"],
                },
            ),
            "CITE_VALIDATION": AgentOutput(
                agent_id="code_only",
                output={
                    "total_citations": 10,
                    "verified": 8,
                    "verification_rate": 0.8,
                    "is_clean": False,
                    "issues": [],
                },
            ),
            "METHODOLOGY_REVIEW": AgentOutput(
                agent_id="methodology_reviewer",
                output={
                    "study_design_critique": "Randomized controlled",
                    "statistical_methods": "DESeq2",
                    "controls_adequacy": "Adequate",
                    "sample_size_assessment": "n=12, sufficient",
                    "potential_biases": ["Batch effects"],
                    "strengths": ["Large sample"],
                    "reproducibility_concerns": [],
                    "domain_specific_issues": [],
                    "overall_methodology_score": 0.8,
                },
            ),
            "SYNTHESIZE_REVIEW": AgentOutput(
                agent_id="research_director",
                output={
                    "summary_assessment": "A solid study.",
                    "decision": "minor_revision",
                    "decision_reasoning": "Minor issues to address.",
                    "comments": [
                        {
                            "category": "major",
                            "section": "Methods",
                            "comment": "Please clarify sample processing.",
                            "evidence_basis": "Integrity audit finding",
                        },
                        {
                            "category": "minor",
                            "section": "Results",
                            "comment": "Typo in Figure 2 caption.",
                            "evidence_basis": "",
                        },
                    ],
                    "confidence_in_conclusions": 0.75,
                },
            ),
        }

    def test_build_session_manifest(self, instance, step_results):
        manifest = build_w8_session_manifest(instance, step_results)
        assert manifest["template"] == "W8"
        assert manifest["workflow_id"] == instance.id
        assert "total_cost" in manifest

    def test_build_peer_review_report(self, instance, step_results):
        report = build_peer_review_report(instance, step_results, "Test Paper")
        assert report.paper_title == "Test Paper"
        assert len(report.claims_extracted) == 1
        assert report.methodology_assessment is not None
        assert report.methodology_assessment.overall_methodology_score == 0.8
        assert report.synthesis is not None
        assert report.synthesis.decision == "minor_revision"
        assert report.markdown_report != ""

    def test_render_markdown_report(self):
        report = W8PeerReviewReport(
            paper_title="Test Paper",
            synthesis=PeerReviewSynthesis(
                summary_assessment="Good study.",
                decision="accept",
                decision_reasoning="High quality.",
                comments=[
                    ReviewComment(category="minor", section="Results", comment="Minor typo"),
                ],
            ),
            methodology_assessment=MethodologyAssessment(
                study_design_critique="Excellent",
                statistical_methods="Appropriate",
                controls_adequacy="Good",
                sample_size_assessment="Adequate",
                strengths=["Well-designed"],
                overall_methodology_score=0.9,
            ),
        )
        md = render_markdown_report(report)
        assert "# Peer Review Report: Test Paper" in md
        assert "Accept" in md
        assert "Good study." in md
        assert "Methodology Assessment" in md
        # AI Disclosure and Pipeline cost are intentionally omitted for journal submission
        assert "AI Disclosure" not in md
        assert "Pipeline cost" not in md
        # Basis lines (internal provenance) are not rendered in public report
        assert "Basis:" not in md

    def test_render_empty_report(self):
        report = W8PeerReviewReport(paper_title="Empty")
        md = render_markdown_report(report)
        assert "# Peer Review Report: Empty" in md
        assert "AI Disclosure" not in md

    def test_build_report_handles_missing_steps(self, instance):
        """Report builder handles gracefully when steps are missing."""
        report = build_peer_review_report(instance, {}, "Missing Steps Paper")
        assert report.paper_title == "Missing Steps Paper"
        assert report.claims_extracted == []
        assert report.synthesis is None
        assert report.methodology_assessment is None


# === Integration Tests ===

@pytest.mark.asyncio
class TestW8Integration:
    async def test_full_pipeline_with_valid_pdf(self, tmp_path):
        """Integration test: run full W8 pipeline with a mock PDF."""
        import fitz
        from app.agents.registry import create_registry
        from app.llm.mock_layer import MockLLMLayer

        # Create a test PDF
        doc = fitz.open()
        page = doc.new_page()
        text = (
            "Effects of Microgravity on Gene Expression\n\n"
            "Abstract\n"
            "We investigated gene expression changes in spaceflight.\n\n"
            "Introduction\n"
            "Space biology is an emerging field. Previous studies have shown immune changes.\n\n"
            "Methods\n"
            "We performed RNA-seq on 12 astronaut blood samples.\n\n"
            "Results\n"
            "Gene X was upregulated 2.5-fold (p<0.001, n=12).\n\n"
            "Discussion\n"
            "Our findings suggest spaceflight affects gene regulation.\n\n"
            "References\n"
            "1. Smith et al. 2020. 10.1234/test\n"
        )
        page.insert_text((72, 72), text)
        pdf_path = tmp_path / "test_paper.pdf"
        doc.save(str(pdf_path))
        doc.close()

        llm = MockLLMLayer()
        registry = create_registry(llm, memory=None)
        runner = W8PaperReviewRunner(registry=registry, llm_layer=llm)

        result = await runner.run(
            pdf_path=str(pdf_path),
            budget=5.0,
        )

        assert "instance" in result
        instance = result["instance"]
        # Should pause at HUMAN_CHECKPOINT or complete
        assert instance.state in ("WAITING_HUMAN", "COMPLETED", "FAILED")
        # Should have processed at least the first few steps
        assert len(instance.step_history) >= 2

    async def test_pipeline_no_pdf_fails_gracefully(self):
        """Pipeline with empty pdf_path fails at INGEST."""
        from app.agents.registry import create_registry
        from app.llm.mock_layer import MockLLMLayer

        llm = MockLLMLayer()
        registry = create_registry(llm, memory=None)
        runner = W8PaperReviewRunner(registry=registry, llm_layer=llm)

        result = await runner.run(pdf_path="", budget=3.0)
        instance = result["instance"]
        assert instance.state == "FAILED"
