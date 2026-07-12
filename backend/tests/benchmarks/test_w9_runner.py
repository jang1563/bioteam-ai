"""Tests for W9 BioinformaticsRunner — cross-step data flow, templates, and cost modes.

Tests cover:
- Cross-step data propagation via _step_results and ContextPackage.metadata["prior_steps"]
- Template skip logic and dependency cascading
- Cost mode routing (quick → Gemini, standard → Anthropic agents)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.models.agent import AgentOutput
from app.models.workflow import WorkflowInstance

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent_output(output: dict, agent_id: str = "test") -> AgentOutput:
    """Create an AgentOutput with given output dict."""
    return AgentOutput(agent_id=agent_id, output=output, summary="test")


def _make_runner(**kwargs):
    """Create a W9BioinformaticsRunner with a mock registry."""
    from app.workflows.runners.w9_bioinformatics import W9BioinformaticsRunner

    registry = kwargs.pop("registry", MagicMock())
    return W9BioinformaticsRunner(registry=registry, **kwargs)


# ---------------------------------------------------------------------------
# Cross-Step Data Flow Tests
# ---------------------------------------------------------------------------


class TestW9CrossStepDataFlow:
    """Verify cross-step data propagation through the W9 pipeline."""

    @pytest.mark.asyncio
    async def test_prior_steps_populated(self):
        """Agent steps receive prior_steps in context metadata."""
        from app.workflows.runners.w9_bioinformatics import W9_STEPS

        # Create mock agent that captures the ContextPackage
        captured_context = {}
        mock_agent = MagicMock()

        async def capture_run(context):
            captured_context["metadata"] = context.metadata
            return AgentOutput(agent_id="t06_systems_bio", output={"result": "ok"}, summary="done")

        mock_agent.run = capture_run

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_agent

        runner = _make_runner(registry=mock_registry)

        # Pre-populate step results (simulating completed upstream steps)
        runner._step_results = {
            "EXPRESSION_ANALYSIS": _make_agent_output(
                {"up_regulated": [{"gene": "BRCA1"}]}, agent_id="t02_transcriptomics"
            ),
            "GENOMIC_ANALYSIS": _make_agent_output(
                {"variants": [{"id": "rs123"}]}, agent_id="t01_genomics"
            ),
        }

        # Find the PATHWAY_ENRICHMENT step def
        pe_step = next(s for s in W9_STEPS if s.id == "PATHWAY_ENRICHMENT")
        instance = WorkflowInstance(template="W9", query="test query", budget_total=25.0)

        # Call _run_agent_step directly
        with patch("app.workflows.runners.w9_bioinformatics.settings") as mock_settings:
            mock_settings.agentic_enabled = False
            await runner._run_agent_step(pe_step, instance)

        # Verify prior_steps contains upstream results
        assert "metadata" in captured_context
        prior = captured_context["metadata"]["prior_steps"]
        assert "EXPRESSION_ANALYSIS" in prior
        assert "GENOMIC_ANALYSIS" in prior
        assert prior["EXPRESSION_ANALYSIS"]["up_regulated"][0]["gene"] == "BRCA1"

    @pytest.mark.asyncio
    async def test_dc_hc_steps_excluded_from_prior(self):
        """DC_PHASE_B, DC_NOVELTY, HC_INTEGRATION excluded from prior_steps."""
        from app.workflows.runners.w9_bioinformatics import W9_STEPS

        captured_context = {}
        mock_agent = MagicMock()

        async def capture_run(context):
            captured_context["metadata"] = context.metadata
            return AgentOutput(agent_id="research_director", output={}, summary="done")

        mock_agent.run = capture_run

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_agent

        runner = _make_runner(registry=mock_registry)
        runner._step_results = {
            "EXPRESSION_ANALYSIS": _make_agent_output({"data": "real"}),
            "DC_PHASE_B": _make_agent_output({"status": "checkpoint"}),
            "DC_NOVELTY": _make_agent_output({"status": "checkpoint"}),
            "HC_INTEGRATION": _make_agent_output({"status": "checkpoint"}),
        }

        # Use NOVELTY_ASSESSMENT step (Phase D, agent step)
        na_step = next(s for s in W9_STEPS if s.id == "NOVELTY_ASSESSMENT")
        instance = WorkflowInstance(template="W9", query="test")

        with patch("app.workflows.runners.w9_bioinformatics.settings") as mock_settings:
            mock_settings.agentic_enabled = False
            await runner._run_agent_step(na_step, instance)

        prior = captured_context["metadata"]["prior_steps"]
        assert "EXPRESSION_ANALYSIS" in prior
        assert "DC_PHASE_B" not in prior
        assert "DC_NOVELTY" not in prior
        assert "HC_INTEGRATION" not in prior

    @pytest.mark.asyncio
    async def test_skipped_steps_produce_empty_output(self):
        """Template-skipped steps produce AgentOutput with empty dict and template name."""
        from app.workflows.runners.w9_bioinformatics import W9_STEPS

        runner = _make_runner()
        runner._skip_steps = frozenset({"GENOMIC_ANALYSIS"})
        runner._template_name = "rnaseq_dea"

        # Simulate skip logic from the run() loop
        step = next(s for s in W9_STEPS if s.id == "GENOMIC_ANALYSIS")
        if step.id in runner._skip_steps:
            runner._step_results[step.id] = AgentOutput(
                agent_id=str(step.agent_id),
                output={},
                summary=f"Skipped by template {runner._template_name}",
                cost=0.0,
            )

        result = runner._step_results["GENOMIC_ANALYSIS"]
        assert result.output == {}
        assert "rnaseq_dea" in result.summary
        assert result.is_success  # error is None -> True

    @pytest.mark.asyncio
    async def test_agent_not_registered_returns_error(self):
        """When an agent is not in the registry, _run_agent_step returns error output."""
        from app.workflows.runners.w9_bioinformatics import W9_STEPS

        mock_registry = MagicMock()
        mock_registry.get.return_value = None  # Agent not found

        runner = _make_runner(registry=mock_registry)
        step = next(s for s in W9_STEPS if s.id == "SCOPE")
        instance = WorkflowInstance(template="W9", query="test")

        result = await runner._run_agent_step(step, instance)
        assert not result.is_success
        assert "not registered" in result.error


# ---------------------------------------------------------------------------
# Template & Cost Mode Scenario Tests
# ---------------------------------------------------------------------------


class TestW9TemplateScenarios:
    """Test template skip logic and cost mode behavior."""

    def test_rnaseq_dea_skips_genomics(self):
        """rnaseq_dea template skips GENOMIC_ANALYSIS, VARIANT_ANNOTATION, PROTEIN_ANALYSIS."""
        from app.workflows.w9_templates import W9_TEMPLATES, resolve_skip_steps

        tpl = W9_TEMPLATES["rnaseq_dea"]
        skips = resolve_skip_steps(tpl.skip_steps)
        assert "GENOMIC_ANALYSIS" in skips
        assert "VARIANT_ANNOTATION" in skips  # cascaded dependency
        assert "PROTEIN_ANALYSIS" in skips
        assert "EXPRESSION_ANALYSIS" not in skips

    def test_literature_only_skips_all_wet_lab(self):
        """literature_only skips all 6 Phase B steps."""
        from app.workflows.w9_templates import W9_TEMPLATES, resolve_skip_steps

        tpl = W9_TEMPLATES["literature_only"]
        skips = resolve_skip_steps(tpl.skip_steps)
        for step in (
            "GENOMIC_ANALYSIS", "EXPRESSION_ANALYSIS", "PROTEIN_ANALYSIS",
            "VARIANT_ANNOTATION", "PATHWAY_ENRICHMENT", "NETWORK_ANALYSIS",
        ):
            assert step in skips

    def test_all_templates_have_valid_step_ids(self):
        """All skip_steps and agentic_steps reference valid W9 step IDs."""
        from app.workflows.runners.w9_bioinformatics import W9_STEPS
        from app.workflows.w9_templates import W9_TEMPLATES

        valid_ids = {s.id for s in W9_STEPS}
        for tpl_name, tpl in W9_TEMPLATES.items():
            for step_id in tpl.skip_steps:
                assert step_id in valid_ids, f"{tpl_name} skip_steps has invalid: {step_id}"
            for step_id in tpl.agentic_steps:
                assert step_id in valid_ids, f"{tpl_name} agentic_steps has invalid: {step_id}"

    def test_dependency_cascade(self):
        """VARIANT_ANNOTATION auto-skipped when GENOMIC_ANALYSIS is skipped."""
        from app.workflows.w9_templates import resolve_skip_steps

        skips = resolve_skip_steps(frozenset({"GENOMIC_ANALYSIS"}))
        assert "VARIANT_ANNOTATION" in skips

    def test_dependency_cascade_integrity(self):
        """INTEGRITY_AUDIT auto-skipped when EXPRESSION_ANALYSIS is skipped."""
        from app.workflows.w9_templates import resolve_skip_steps

        skips = resolve_skip_steps(frozenset({"EXPRESSION_ANALYSIS"}))
        assert "INTEGRITY_AUDIT" in skips

    def test_no_cascade_when_no_dependencies(self):
        """Skipping PROTEIN_ANALYSIS does not cascade to others."""
        from app.workflows.w9_templates import resolve_skip_steps

        skips = resolve_skip_steps(frozenset({"PROTEIN_ANALYSIS"}))
        assert skips == frozenset({"PROTEIN_ANALYSIS"})

    def test_quick_mode_uses_gemini(self):
        """In quick mode, non-code steps should route to Gemini."""
        from app.workflows.runners.w9_bioinformatics import _CODE_STEPS, W9_STEPS, W9BioinformaticsRunner

        runner = W9BioinformaticsRunner(registry=MagicMock())
        runner._cost_mode = "quick"

        non_code = next(s for s in W9_STEPS if s.id not in _CODE_STEPS)
        assert runner._should_use_gemini(non_code) is True

        code_step = next(s for s in W9_STEPS if s.id in _CODE_STEPS)
        assert runner._should_use_gemini(code_step) is False

    def test_standard_mode_no_gemini(self):
        """In standard mode, no steps should route to Gemini."""
        from app.workflows.runners.w9_bioinformatics import W9_STEPS, W9BioinformaticsRunner

        runner = W9BioinformaticsRunner(registry=MagicMock())
        runner._cost_mode = "standard"
        for step in W9_STEPS:
            assert runner._should_use_gemini(step) is False

    def test_multi_omics_skips_nothing(self):
        """multi_omics template has no skip_steps."""
        from app.workflows.w9_templates import W9_TEMPLATES, resolve_skip_steps

        tpl = W9_TEMPLATES["multi_omics"]
        skips = resolve_skip_steps(tpl.skip_steps)
        assert len(skips) == 0

    def test_template_budgets_are_reasonable(self):
        """All template budgets are positive and <= 50."""
        from app.workflows.w9_templates import W9_TEMPLATES

        for name, tpl in W9_TEMPLATES.items():
            assert 0 < tpl.budget_default <= 50.0, f"{name} budget out of range: {tpl.budget_default}"


# ---------------------------------------------------------------------------
# DC Summary Builder Tests
# ---------------------------------------------------------------------------


class TestW9DCSummaryBuilder:
    """Test Direction Check summary building."""

    def test_dc_ingest_with_files(self):
        runner = _make_runner()
        runner._step_results = {
            "INGEST_DATA": _make_agent_output({
                "files_loaded": [{"path": "/tmp/a.tsv"}, {"path": "/tmp/b.vcf"}],
            }),
        }
        summary = runner._build_dc_summary("INGEST_DATA")
        assert "2 files loaded" in summary

    def test_dc_ingest_empty(self):
        runner = _make_runner()
        runner._step_results = {
            "INGEST_DATA": _make_agent_output({}),
        }
        summary = runner._build_dc_summary("INGEST_DATA")
        assert "0 files loaded" in summary

    def test_dc_phase_b(self):
        runner = _make_runner()
        runner._step_results = {
            "VARIANT_ANNOTATION": _make_agent_output({"total_variants": 150}),
            "PATHWAY_ENRICHMENT": _make_agent_output({"significant_terms": 12}),
        }
        summary = runner._build_dc_summary("DC_PHASE_B")
        assert "150 variants" in summary
        assert "12 enriched pathways" in summary

    def test_dc_novelty(self):
        runner = _make_runner()
        runner._step_results = {
            "NOVELTY_ASSESSMENT": _make_agent_output({
                "novel_findings": [{"id": "f1"}, {"id": "f2"}],
            }),
        }
        summary = runner._build_dc_summary("DC_NOVELTY")
        assert "2 novel findings" in summary

    def test_dc_unknown_step(self):
        runner = _make_runner()
        summary = runner._build_dc_summary("UNKNOWN_STEP")
        assert "Phase checkpoint" in summary
