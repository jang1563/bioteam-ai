"""Tests for W7 Data Integrity Audit Runner — step definitions, pipeline execution, state reset."""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.data_integrity_auditor import DataIntegrityAuditorAgent
from app.agents.registry import create_registry
from app.llm.mock_layer import MockLLMLayer
from app.models.agent import AgentOutput
from app.models.workflow import WorkflowInstance
from app.workflows.runners.w7_integrity import (
    _METHOD_MAP,
    W7_STEPS,
    W7IntegrityRunner,
)

# === Step Definition Tests ===


def test_step_count():
    """W7 should have exactly 8 steps."""
    assert len(W7_STEPS) == 8


def test_step_order():
    """Steps should be in correct pipeline order."""
    expected = [
        "COLLECT", "GENE_CHECK", "STAT_CHECK", "RETRACTION_CHECK",
        "METADATA_CHECK", "IMAGE_CHECK", "LLM_CONTEXTUALIZE", "REPORT",
    ]
    actual = [s.id for s in W7_STEPS]
    assert actual == expected


def test_code_only_steps():
    """Deterministic steps should be code_only with zero cost."""
    code_steps = ("GENE_CHECK", "STAT_CHECK", "RETRACTION_CHECK", "METADATA_CHECK", "IMAGE_CHECK", "REPORT")
    for step in W7_STEPS:
        if step.id in code_steps:
            assert step.agent_id == "code_only", f"{step.id} should be code_only"
            assert step.estimated_cost == 0.0, f"{step.id} should have zero cost"


def test_llm_steps():
    """LLM steps should reference agents, not code_only."""
    llm_steps = {"COLLECT": "knowledge_manager", "LLM_CONTEXTUALIZE": "data_integrity_auditor"}
    for step in W7_STEPS:
        if step.id in llm_steps:
            assert step.agent_id == llm_steps[step.id], f"{step.id} agent mismatch"
            assert step.estimated_cost > 0.0, f"{step.id} should have nonzero cost"


def test_method_map_coverage():
    """All non-code_only steps should have method routing."""
    agent_steps = [s for s in W7_STEPS if s.agent_id != "code_only"]
    for step in agent_steps:
        assert step.id in _METHOD_MAP, f"{step.id} missing from _METHOD_MAP"


def test_step_chaining():
    """Each step's next_step should reference the following step (except last)."""
    for i, step in enumerate(W7_STEPS[:-1]):
        assert step.next_step == W7_STEPS[i + 1].id, \
            f"{step.id}.next_step should be {W7_STEPS[i + 1].id}, got {step.next_step}"
    assert W7_STEPS[-1].next_step is None, "Last step should have next_step=None"


# === Pipeline Execution Tests ===


def _make_runner_with_mocks():
    """Create a W7 runner with a mocked registry."""
    mock_llm = MockLLMLayer({})
    registry = create_registry(mock_llm)
    runner = W7IntegrityRunner(registry=registry)
    return runner


@pytest.mark.asyncio
async def test_gene_check_step():
    """GENE_CHECK step should detect Excel-corrupted gene names."""
    runner = _make_runner_with_mocks()
    runner._collected_text = "Table 1 shows 1-Mar and 7-Sep were upregulated in the dataset."

    result = runner._step_gene_check()
    assert isinstance(result, dict)
    assert result["gene_findings"] >= 2
    assert len(runner._all_findings) >= 2

    # Verify findings contain expected gene names
    titles = [f.get("title", "") for f in runner._all_findings]
    assert any("MARCH" in t for t in titles)
    assert any("SEPT" in t for t in titles)


@pytest.mark.asyncio
async def test_stat_check_step_no_stats():
    """STAT_CHECK with no statistical text should return 0 findings."""
    runner = _make_runner_with_mocks()
    runner._collected_text = "BRCA1 is a tumor suppressor gene."

    result = runner._step_stat_check()
    assert result["stat_findings"] == 0


@pytest.mark.asyncio
async def test_metadata_check_step():
    """METADATA_CHECK on text with genome build inconsistency."""
    runner = _make_runner_with_mocks()
    runner._collected_text = "We aligned reads to hg19 reference. The variants were called against hg38."

    result = runner._step_metadata_check()
    assert isinstance(result, dict)
    # Should detect genome build mixing (hg19 + hg38)
    assert result["metadata_findings"] >= 1


@pytest.mark.asyncio
async def test_retraction_check_no_dois():
    """RETRACTION_CHECK with no DOIs returns 0 findings."""
    runner = _make_runner_with_mocks()
    runner._collected_text = "No DOIs in this text."

    result = await runner._step_retraction_check()
    assert result["dois_checked"] == 0
    assert result["retraction_findings"] == 0


def test_image_check_step_no_images():
    """IMAGE_CHECK with no collected images should skip gracefully."""
    runner = _make_runner_with_mocks()
    runner._collected_images = []

    result = runner._step_image_check()
    assert result["image_findings"] == 0
    assert result["skipped"] is True


def test_report_step_assembles_findings():
    """REPORT step should assemble findings into session_manifest."""
    runner = _make_runner_with_mocks()
    runner._all_findings = [
        {"category": "gene_name_error", "severity": "warning", "title": "Gene error"},
        {"category": "grim_failure", "severity": "error", "title": "GRIM failure"},
    ]
    instance = WorkflowInstance(template="W7", budget_total=3.0, budget_remaining=3.0)

    result = runner._step_report(instance)
    assert result["total_findings"] == 2
    assert result["findings_by_severity"]["warning"] == 1
    assert result["findings_by_severity"]["error"] == 1
    assert result["overall_level"] == "significant_issues"

    # Check session_manifest
    report = instance.session_manifest.get("integrity_report")
    assert report is not None
    assert report["total_findings"] == 2
    assert len(report["findings"]) == 2


def test_state_reset_between_runs():
    """Runner instance state should be reset at the start of each run."""
    runner = _make_runner_with_mocks()

    # Simulate leftover state from a previous run
    runner._all_findings = [{"category": "gene_name_error", "severity": "warning"}]
    runner._collected_text = "Old text from previous run"
    runner._collected_dois = ["10.1234/old"]

    # Create an instance
    instance = WorkflowInstance(template="W7", budget_total=3.0, budget_remaining=3.0)

    # The run method should reset state (we can't run the full pipeline easily
    # without mocking all agents, but we can verify the reset happens)
    # We'll use a partial approach: call run and let it fail on COLLECT (no agent),
    # but the reset should have happened first
    try:
        asyncio.get_event_loop().run_until_complete(runner.run(instance))
    except Exception:
        pass

    # State should be reset regardless of whether the full pipeline completed
    assert runner._all_findings == []
    assert runner._collected_text == ""
    assert runner._collected_dois == []
    assert runner._collected_images == []


def test_summarize_result():
    """_summarize_result should produce concise summaries."""
    runner = _make_runner_with_mocks()

    assert runner._summarize_result({}) == "No result"
    assert runner._summarize_result(None) == "No result"

    summary = runner._summarize_result({"gene_findings": 3, "cost": 0.05})
    assert "gene_findings=3" in summary
    assert "cost=0.05" in summary


class TestContextualizeOnlyIntegration:
    """Test the W7 → agent.contextualize_only integration."""

    @pytest.mark.asyncio
    async def test_contextualize_only_no_findings(self):
        """contextualize_only with empty findings returns clean report."""
        mock_llm = MockLLMLayer({})
        spec = BaseAgent.load_spec("data_integrity_auditor")
        agent = DataIntegrityAuditorAgent(spec=spec, llm=mock_llm)

        output = await agent.contextualize_only(
            findings_dicts=[],
            text="Some text",
            query="test",
        )
        assert isinstance(output, AgentOutput)
        assert output.output["total_findings"] == 0
        assert output.output["overall_level"] == "clean"

    @pytest.mark.asyncio
    async def test_contextualize_only_passes_findings_through(self):
        """contextualize_only with info-only findings (no LLM needed) passes them through."""
        mock_llm = MockLLMLayer({})
        spec = BaseAgent.load_spec("data_integrity_auditor")
        agent = DataIntegrityAuditorAgent(spec=spec, llm=mock_llm)

        findings = [
            {
                "category": "gene_name_error",
                "severity": "info",
                "title": "Minor gene issue",
                "description": "Low confidence finding",
                "confidence": 0.3,
            }
        ]
        output = await agent.contextualize_only(
            findings_dicts=findings,
            text="Gene 1-Mar detected",
            query="test",
        )
        assert output.output["total_findings"] == 1
        # Info-level findings are not sent to LLM, so pass through unchanged
        assert len(mock_llm.call_log) == 0


if __name__ == "__main__":
    print("Testing W7 Integrity Runner:")
    test_step_count()
    print("  PASS: step_count")
    test_step_order()
    print("  PASS: step_order")
    test_code_only_steps()
    print("  PASS: code_only_steps")
    test_llm_steps()
    print("  PASS: llm_steps")
    test_method_map_coverage()
    print("  PASS: method_map_coverage")
    test_step_chaining()
    print("  PASS: step_chaining")
    test_report_step_assembles_findings()
    print("  PASS: report_step_assembles_findings")
    test_state_reset_between_runs()
    print("  PASS: state_reset_between_runs")
    test_summarize_result()
    print("  PASS: summarize_result")
    print("\nAll W7 Integrity Runner tests passed!")
