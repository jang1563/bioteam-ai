"""Edge case tests for DataIntegrityAuditorAgent — text extraction, DOI regex, report levels, contextualize_only."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import pytest

from app.agents.base import BaseAgent
from app.agents.data_integrity_auditor import (
    DataIntegrityAuditorAgent,
    IntegrityContextAssessment,
)
from app.engines.integrity.finding_models import IntegrityFinding
from app.llm.mock_layer import MockLLMLayer
from app.models.messages import ContextPackage


@pytest.fixture
def mock_llm():
    return MockLLMLayer({
        "sonnet:IntegrityContextAssessment": IntegrityContextAssessment(
            finding_id="test",
            is_likely_real=True,
            adjusted_severity="warning",
            biological_context="This appears to be a genuine issue.",
            confidence=0.85,
        ),
    })


@pytest.fixture
def agent(mock_llm):
    spec = BaseAgent.load_spec("data_integrity_auditor")
    return DataIntegrityAuditorAgent(spec=spec, llm=mock_llm)


# === Text Extraction ===


class TestTextExtraction:
    """Test _extract_text with various ContextPackage structures."""

    def test_task_description_only(self, agent):
        context = ContextPackage(task_description="Hello world", prior_step_outputs=[])
        text = agent._extract_text(context)
        assert text == "Hello world"

    def test_empty_context(self, agent):
        context = ContextPackage(task_description="", prior_step_outputs=[])
        text = agent._extract_text(context)
        assert text == ""

    def test_prior_outputs_text_key(self, agent):
        context = ContextPackage(
            task_description="Main query",
            prior_step_outputs=[{"text": "Step 1 output text"}],
        )
        text = agent._extract_text(context)
        assert "Main query" in text
        assert "Step 1 output text" in text

    def test_prior_outputs_content_key(self, agent):
        context = ContextPackage(
            task_description="",
            prior_step_outputs=[{"content": "Paper abstract here"}],
        )
        text = agent._extract_text(context)
        assert "Paper abstract here" in text

    def test_prior_outputs_nested_output_dict(self, agent):
        context = ContextPackage(
            task_description="",
            prior_step_outputs=[{"output": {"abstract": "Nested abstract"}}],
        )
        text = agent._extract_text(context)
        assert "Nested abstract" in text

    def test_prior_outputs_list_value(self, agent):
        context = ContextPackage(
            task_description="",
            prior_step_outputs=[{"text": ["Finding 1", "Finding 2"]}],
        )
        text = agent._extract_text(context)
        assert "Finding 1" in text
        assert "Finding 2" in text

    def test_prior_outputs_mixed_keys(self, agent):
        context = ContextPackage(
            task_description="Query",
            prior_step_outputs=[
                {"text": "Text part", "summary": "Summary part"},
                {"content": "Content part", "key_findings": "Findings part"},
            ],
        )
        text = agent._extract_text(context)
        assert "Text part" in text
        assert "Summary part" in text
        assert "Content part" in text
        assert "Findings part" in text

    def test_prior_outputs_empty_strings(self, agent):
        context = ContextPackage(
            task_description="",
            prior_step_outputs=[{"text": "", "content": "", "abstract": ""}],
        )
        text = agent._extract_text(context)
        assert text == ""

    def test_prior_outputs_non_string_value(self, agent):
        """Non-string values in 'text' key should be skipped."""
        context = ContextPackage(
            task_description="",
            prior_step_outputs=[{"text": 42}],
        )
        text = agent._extract_text(context)
        # 42 is not a string, should be skipped; also not a list → skipped
        assert "42" not in text

    def test_prior_outputs_empty_dict(self, agent):
        """Empty dict in prior_step_outputs should not contribute text."""
        context = ContextPackage(
            task_description="",
            prior_step_outputs=[{}],
        )
        text = agent._extract_text(context)
        assert text == ""

    def test_unicode_task_description(self, agent):
        """Korean text in task_description should work."""
        context = ContextPackage(
            task_description="유전자 발현 분석에서 1-Mar 탐지",
            prior_step_outputs=[],
        )
        text = agent._extract_text(context)
        assert "유전자" in text
        assert "1-Mar" in text


# === DOI Extraction ===


class TestDOIExtraction:
    """Test DOI regex edge cases."""

    def test_standard_doi(self, agent):
        dois = agent._extract_dois("See 10.1038/s41586-020-2521-4.")
        assert len(dois) == 1

    def test_doi_with_parentheses(self, agent):
        dois = agent._extract_dois("DOI: 10.1002/(SICI)test")
        assert len(dois) >= 1

    def test_multiple_identical_dois_deduplicated(self, agent):
        text = "10.1038/test and 10.1038/test again"
        dois = agent._extract_dois(text)
        assert len(dois) == 1

    def test_multiple_different_dois(self, agent):
        text = "See 10.1038/abc and 10.1126/xyz."
        dois = agent._extract_dois(text)
        assert len(dois) == 2

    def test_no_doi_in_text(self, agent):
        dois = agent._extract_dois("No DOIs here at all.")
        assert dois == []

    def test_doi_at_text_boundary(self, agent):
        dois = agent._extract_dois("10.1038/test")
        assert len(dois) == 1

    def test_doi_with_underscore(self, agent):
        dois = agent._extract_dois("DOI: 10.1038/test_paper_2024")
        assert len(dois) == 1

    def test_doi_with_semicolons(self, agent):
        dois = agent._extract_dois("DOI: 10.1038/test;2024")
        assert len(dois) == 1

    def test_short_doi_prefix_rejected(self, agent):
        """DOI with <4 digits after 10. should not match."""
        dois = agent._extract_dois("10.12/test")
        # Regex requires \d{4,9}, so "12" (2 digits) should not match
        assert len(dois) == 0

    def test_doi_lowercase_letters(self, agent):
        """DOI regex is case-insensitive — lowercase should match."""
        dois = agent._extract_dois("10.1038/s41586-020-2521-4")
        assert len(dois) == 1


# === Report Building ===


class TestReportBuilding:
    """Edge cases for _build_report and helper methods."""

    def test_empty_findings(self, agent):
        report = agent._build_report([], "test")
        assert report.total_findings == 0
        assert report.overall_level == "clean"
        assert "No data integrity issues" in report.summary

    def test_info_only_level(self, agent):
        """Info-level findings only should give 'clean'."""
        findings = [
            IntegrityFinding(category="gene_name_error", severity="info"),
        ]
        report = agent._build_report(findings, "test")
        assert report.overall_level == "clean"

    def test_warning_level(self, agent):
        findings = [
            IntegrityFinding(category="gene_name_error", severity="warning"),
        ]
        report = agent._build_report(findings, "test")
        assert report.overall_level == "minor_issues"

    def test_error_level(self, agent):
        findings = [
            IntegrityFinding(category="retracted_reference", severity="error"),
        ]
        report = agent._build_report(findings, "test")
        assert report.overall_level == "significant_issues"

    def test_critical_level(self, agent):
        findings = [
            IntegrityFinding(category="retracted_reference", severity="critical"),
        ]
        report = agent._build_report(findings, "test")
        assert report.overall_level == "critical"

    def test_all_severities_present(self, agent):
        """When all severity levels are present, critical takes precedence."""
        findings = [
            IntegrityFinding(category="gene_name_error", severity="info"),
            IntegrityFinding(category="gene_name_error", severity="warning"),
            IntegrityFinding(category="retracted_reference", severity="error"),
            IntegrityFinding(category="retracted_reference", severity="critical"),
        ]
        report = agent._build_report(findings, "test")
        assert report.overall_level == "critical"
        assert report.total_findings == 4
        assert report.findings_by_severity == {
            "info": 1, "warning": 1, "error": 1, "critical": 1,
        }

    def test_multiple_categories_counted(self, agent):
        findings = [
            IntegrityFinding(category="gene_name_error", severity="warning"),
            IntegrityFinding(category="gene_name_error", severity="warning"),
            IntegrityFinding(category="statistical_inconsistency", severity="error"),
        ]
        report = agent._build_report(findings, "test")
        assert report.findings_by_category == {
            "gene_name_error": 2, "statistical_inconsistency": 1,
        }

    def test_summary_format(self, agent):
        """Summary should list counts by severity."""
        findings = [
            IntegrityFinding(category="gene_name_error", severity="warning"),
            IntegrityFinding(category="retracted_reference", severity="critical"),
        ]
        report = agent._build_report(findings, "test")
        assert "2 integrity issue" in report.summary
        assert "1 critical" in report.summary
        assert "1 warning" in report.summary

    def test_recommended_action_for_each_level(self, agent):
        assert "No action" in agent._recommend_action("clean")
        assert "convenient" in agent._recommend_action("minor_issues")
        assert "before relying" in agent._recommend_action("significant_issues")
        assert "Immediate" in agent._recommend_action("critical")


# === contextualize_only ===


class TestContextualizeOnly:
    """Edge cases for contextualize_only method."""

    @pytest.mark.asyncio
    async def test_empty_findings_dicts(self, agent):
        """Empty findings list should return clean report."""
        output = await agent.contextualize_only([], "some text")
        assert output.output["total_findings"] == 0
        assert output.output["overall_level"] == "clean"

    @pytest.mark.asyncio
    async def test_valid_finding_dict(self, agent):
        """Valid dict should be reconstructed as IntegrityFinding."""
        findings = [
            {
                "category": "gene_name_error",
                "severity": "warning",
                "title": "Gene error",
                "description": "1-Mar detected",
                "confidence": 0.85,
            }
        ]
        output = await agent.contextualize_only(findings, "text with 1-Mar")
        assert output.output["total_findings"] == 1

    @pytest.mark.asyncio
    async def test_invalid_finding_dict_fallback(self, agent):
        """Invalid dict should fall back to minimal IntegrityFinding."""
        findings = [
            {
                "category": "gene_name_error",
                "severity": "warning",
                "title": "Gene error",
                "invalid_extra_field_that_is_not_in_model": True,
                "another_invalid": 42,
            }
        ]
        output = await agent.contextualize_only(findings, "text")
        # Should not crash — falls back to minimal construction
        assert output.output["total_findings"] == 1

    @pytest.mark.asyncio
    async def test_missing_required_fields_fallback(self, agent):
        """Dict missing required fields should use fallback defaults."""
        findings = [
            {"title": "No category or severity"}
        ]
        output = await agent.contextualize_only(findings, "text")
        # Fallback uses category="metadata_error", severity="warning"
        assert output.output["total_findings"] == 1

    @pytest.mark.asyncio
    async def test_info_only_not_contextualized(self, agent, mock_llm):
        """Info-level findings should NOT be sent to LLM."""
        findings = [
            {
                "category": "gene_name_error",
                "severity": "info",
                "title": "Minor issue",
                "confidence": 0.3,
            }
        ]
        output = await agent.contextualize_only(findings, "text")
        assert output.output["total_findings"] == 1
        # No LLM calls for info-level findings
        assert len(mock_llm.call_log) == 0


# === quick_check ===


class TestQuickCheckEdgeCases:

    @pytest.mark.asyncio
    async def test_quick_check_only_whitespace(self, agent):
        """Whitespace-only text should return clean."""
        output = await agent.quick_check("   \n\t  ")
        assert output.output["total_findings"] == 0

    @pytest.mark.asyncio
    async def test_quick_check_combined_issues(self, agent):
        """Text with multiple issue types should find all of them."""
        text = (
            "Gene 1-Mar was detected in Table 1. "
            "We aligned reads to hg19. Analysis used hg38."
        )
        output = await agent.quick_check(text)
        # Should find gene name error AND genome build mixing
        assert output.output["total_findings"] >= 2

    @pytest.mark.asyncio
    async def test_quick_check_with_dois(self, agent):
        """quick_check with DOIs list should not crash (no clients configured)."""
        output = await agent.quick_check(
            "Some text",
            dois=["10.1038/test"],
        )
        # No retraction client configured, so retraction check returns nothing
        assert isinstance(output.output, dict)

    @pytest.mark.asyncio
    async def test_quick_check_very_long_text(self, agent):
        """Very long text should not cause performance issues."""
        text = "BRCA1 is important. " * 5000 + "Gene 1-Mar found."
        output = await agent.quick_check(text)
        assert output.output["total_findings"] >= 1

    @pytest.mark.asyncio
    async def test_quick_check_stats_and_genes(self, agent):
        """Text with both gene errors and statistical issues."""
        text = (
            "Table shows 1-Mar and 7-Sep genes. "
            "F(1, 100) = 50.0, p = .50"
        )
        output = await agent.quick_check(text)
        categories = output.output.get("findings_by_category", {})
        assert categories.get("gene_name_error", 0) >= 2


# === Full Audit ===


class TestAuditEdgeCases:

    @pytest.mark.asyncio
    async def test_audit_empty_context(self, agent):
        """Empty context should return clean report."""
        context = ContextPackage(task_description="", prior_step_outputs=[])
        output = await agent.audit(context)
        assert output.output["overall_level"] == "clean"

    @pytest.mark.asyncio
    async def test_audit_gene_errors_trigger_llm(self, agent, mock_llm):
        """Warning-level gene findings should trigger LLM contextualization."""
        context = ContextPackage(
            task_description="Table shows 1-Mar genes.",
            prior_step_outputs=[],
        )
        output = await agent.audit(context)
        # Gene findings are warning-level → should trigger LLM
        assert len(mock_llm.call_log) >= 1

    @pytest.mark.asyncio
    async def test_audit_output_type(self, agent):
        """Audit output should have correct output_type."""
        context = ContextPackage(task_description="", prior_step_outputs=[])
        output = await agent.audit(context)
        assert output.output_type == "IntegrityAnalysis"
