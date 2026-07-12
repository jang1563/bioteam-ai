"""Tests for DataIntegrityAuditorAgent.

Tests covering:
- Empty context → clean report
- Gene name detection in context
- quick_check (deterministic only, no LLM)
- build_output format
- DOI extraction
- Report level computation
"""

from __future__ import annotations

import pytest
from app.agents.base import BaseAgent
from app.agents.data_integrity_auditor import (
    DataIntegrityAuditorAgent,
    IntegrityContextAssessment,
)
from app.llm.mock_layer import MockLLMLayer
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage


@pytest.fixture
def mock_llm():
    """MockLLMLayer with integrity assessment response."""
    return MockLLMLayer({
        "sonnet:IntegrityContextAssessment": IntegrityContextAssessment(
            finding_id="test",
            is_likely_real=True,
            adjusted_severity="warning",
            biological_context="This is a table context, likely a real gene name error.",
            confidence=0.85,
        ),
    })


@pytest.fixture
def agent(mock_llm):
    """Create a DataIntegrityAuditorAgent with mock LLM."""
    spec = BaseAgent.load_spec("data_integrity_auditor")
    return DataIntegrityAuditorAgent(spec=spec, llm=mock_llm)


class TestAuditEmptyContext:

    @pytest.mark.asyncio
    async def test_empty_context_clean(self, agent):
        """Empty context produces clean report."""
        context = ContextPackage(task_description="", prior_step_outputs=[])
        output = await agent.run(context)

        assert isinstance(output, AgentOutput)
        assert output.output_type == "IntegrityAnalysis"
        analysis = output.output
        assert analysis["total_findings"] == 0
        assert analysis["overall_level"] == "clean"

    @pytest.mark.asyncio
    async def test_no_issues_text(self, agent):
        """Normal text without integrity issues produces clean report."""
        context = ContextPackage(
            task_description="BRCA1 is a tumor suppressor gene involved in DNA repair.",
            prior_step_outputs=[],
        )
        output = await agent.run(context)
        assert output.output["total_findings"] == 0


class TestGeneNameDetection:

    @pytest.mark.asyncio
    async def test_detects_excel_corruption(self, agent):
        """Gene name corruption in text is detected."""
        context = ContextPackage(
            task_description="Table shows 1-Mar and 7-Sep genes were upregulated.",
            prior_step_outputs=[],
        )
        output = await agent.run(context)
        assert output.output["total_findings"] >= 2
        categories = output.output["findings_by_category"]
        assert categories.get("gene_name_error", 0) >= 2


class TestQuickCheck:

    @pytest.mark.asyncio
    async def test_quick_check_no_llm(self, agent, mock_llm):
        """quick_check runs deterministic only, no LLM calls."""
        text = "Gene 1-Mar was expressed in Table 1."
        output = await agent.quick_check(text)

        assert isinstance(output, AgentOutput)
        assert output.output["total_findings"] >= 1
        # No LLM calls should be made
        assert len(mock_llm.call_log) == 0

    @pytest.mark.asyncio
    async def test_quick_check_empty_text(self, agent):
        """quick_check with empty text returns clean report."""
        output = await agent.quick_check("")
        assert output.output["total_findings"] == 0
        assert output.output["overall_level"] == "clean"


class TestDOIExtraction:

    def test_extract_dois(self, agent):
        """DOIs are extracted from text."""
        text = "See 10.1038/s41586-020-2521-4 and 10.1126/science.abc1234."
        dois = agent._extract_dois(text)
        assert len(dois) == 2

    def test_no_dois(self, agent):
        """No DOIs in text returns empty list."""
        dois = agent._extract_dois("No DOIs here.")
        assert dois == []


class TestReportLevels:

    def test_clean_level(self, agent):
        """No findings → clean."""
        report = agent._build_report([], "test")
        assert report.overall_level == "clean"

    def test_critical_level(self, agent):
        """Critical finding → critical level."""
        from app.engines.integrity.finding_models import IntegrityFinding
        findings = [
            IntegrityFinding(
                category="retracted_reference",
                severity="critical",
                title="Retracted",
                description="Paper retracted",
            )
        ]
        report = agent._build_report(findings, "test")
        assert report.overall_level == "critical"

    def test_minor_level(self, agent):
        """Warning finding → minor_issues."""
        from app.engines.integrity.finding_models import IntegrityFinding
        findings = [
            IntegrityFinding(
                category="gene_name_error",
                severity="warning",
                title="Gene error",
                description="Possible gene name error",
            )
        ]
        report = agent._build_report(findings, "test")
        assert report.overall_level == "minor_issues"
