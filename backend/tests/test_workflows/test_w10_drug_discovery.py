"""Tests for W10 Drug Discovery runner and report builder."""

from __future__ import annotations

import pytest
from app.engines.w10_report_builder import build_w10_report
from app.models.w10_drug_discovery import (
    DrugDiscoveryScope,
    EfficacyAnalysis,
    GrantRelevanceAssessment,
    LiteratureComparison,
    MechanismReview,
    W10DrugDiscoveryResult,
)
from app.models.workflow import WorkflowInstance
from app.workflows.runners.w10_drug_discovery import (
    W10_STEPS,
    W10DrugDiscoveryRunner,
)


# === Step Definitions Tests ===


class TestW10Steps:
    def test_step_count(self):
        assert len(W10_STEPS) == 12

    def test_step_ids(self):
        ids = [s.id for s in W10_STEPS]
        expected = [
            "SCOPE",
            "COMPOUND_SEARCH",
            "BIOACTIVITY_PROFILE",
            "TARGET_IDENTIFICATION",
            "CLINICAL_TRIALS_SEARCH",
            "EFFICACY_ANALYSIS",
            "SAFETY_PROFILE",
            "DC_PRELIMINARY",
            "MECHANISM_REVIEW",
            "LITERATURE_COMPARISON",
            "GRANT_RELEVANCE",
            "REPORT",
        ]
        assert ids == expected

    def test_step_chain(self):
        """Verify each step points to the next."""
        for i, step in enumerate(W10_STEPS[:-1]):
            assert step.next_step == W10_STEPS[i + 1].id
        assert W10_STEPS[-1].next_step is None

    def test_human_checkpoint_exists(self):
        hc_steps = [s for s in W10_STEPS if s.interaction_type == "HC"]
        assert len(hc_steps) == 1
        assert hc_steps[0].id == "SCOPE"

    def test_dc_exists(self):
        dc_steps = [s for s in W10_STEPS if s.interaction_type == "DC"]
        assert len(dc_steps) == 1
        assert dc_steps[0].id == "DC_PRELIMINARY"
        assert dc_steps[0].dc_auto_continue_minutes == 30

    def test_report_step_is_last(self):
        last = W10_STEPS[-1]
        assert last.id == "REPORT"
        assert last.next_step is None

    def test_estimated_costs_nonnegative(self):
        for step in W10_STEPS:
            assert step.estimated_cost >= 0.0


# === Runner Tests ===


class TestW10DrugDiscoveryRunner:
    @pytest.fixture
    def mock_registry(self):
        from app.agents.registry import create_registry
        from app.llm.mock_layer import MockLLMLayer

        llm = MockLLMLayer()
        return create_registry(llm, memory=None)

    @pytest.fixture
    def runner(self, mock_registry):
        return W10DrugDiscoveryRunner(registry=mock_registry)

    @pytest.fixture
    def instance(self):
        return WorkflowInstance(template="W10", query="imatinib")

    def test_runner_init(self, runner):
        assert runner._registry is not None
        assert runner._chembl is None  # lazy init
        assert runner._ct is None

    def test_chembl_returns_none_when_mcp_disabled(self, runner):
        """When mcp_enabled=False, _get_chembl() returns None."""
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("app.config.settings.mcp_enabled", False)
            result = runner._get_chembl()
        assert result is None

    def test_ct_returns_none_when_mcp_disabled(self, runner):
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("app.config.settings.mcp_enabled", False)
            result = runner._get_ct()
        assert result is None

    @pytest.mark.asyncio
    async def test_step_compound_search_fallback(self, runner):
        """With MCP disabled, compound_search returns fallback dict."""
        runner._chembl = None
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("app.config.settings.mcp_enabled", False)
            result = await runner._step_compound_search("imatinib")
        assert result["source"] == "fallback"
        assert result["compounds"] == []
        assert "imatinib" in result["summary"]

    @pytest.mark.asyncio
    async def test_step_bioactivity_fallback(self, runner):
        runner._chembl = None
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("app.config.settings.mcp_enabled", False)
            result = await runner._step_bioactivity("imatinib")
        assert result["source"] == "fallback"
        assert result["activities"] == []

    @pytest.mark.asyncio
    async def test_step_clinical_trials_fallback(self, runner):
        runner._ct = None
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("app.config.settings.mcp_enabled", False)
            result = await runner._step_clinical_trials("imatinib")
        assert result["source"] == "fallback"
        assert result["trials"] == []

    @pytest.mark.asyncio
    async def test_step_safety_fallback(self, runner):
        runner._chembl = None
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("app.config.settings.mcp_enabled", False)
            result = await runner._step_safety("imatinib")
        assert result["source"] == "fallback"
        assert "MCP disabled" in result["admet_summary"]

    @pytest.mark.asyncio
    async def test_step_scope_returns_model(self, runner, instance):
        scope = await runner._step_scope("imatinib", instance)
        assert isinstance(scope, DrugDiscoveryScope)
        # Mock layer returns something; at minimum the query should survive
        assert scope is not None

    @pytest.mark.asyncio
    async def test_step_report_builds_markdown(self, runner, instance):
        """_step_report should produce a non-empty report_markdown."""
        # Pre-populate step_results so report has content
        runner._step_results = {
            "SCOPE": DrugDiscoveryScope(
                research_question="Does imatinib inhibit BCR-ABL?",
                target_compound_or_class="imatinib",
                therapeutic_area="Oncology",
                key_objectives=["Assess potency", "Review safety"],
                search_strategy="ChEMBL + ClinicalTrials",
            ),
            "COMPOUND_SEARCH": {"summary": "Imatinib (CHEMBL941)", "compounds": []},
            "BIOACTIVITY_PROFILE": {"summary": "IC50 = 100 nM vs BCR-ABL", "activities": []},
            "TARGET_IDENTIFICATION": {"target_summary": "BCR-ABL tyrosine kinase"},
            "CLINICAL_TRIALS_SEARCH": {"summary": "Phase 4 trials active", "trials": []},
            "EFFICACY_ANALYSIS": EfficacyAnalysis(
                summary="Strong efficacy in CML.",
                key_findings=["IC50 < 1 uM"],
                potency_assessment="strong",
            ),
            "SAFETY_PROFILE": {"admet_summary": "Well tolerated. CYP3A4 substrate."},
            "MECHANISM_REVIEW": MechanismReview(
                primary_mechanism="Competitive ATP inhibition",
                target_pathway="BCR-ABL/STAT5",
            ),
            "LITERATURE_COMPARISON": LiteratureComparison(
                novelty_assessment="First-in-class TKI for CML."
            ),
            "GRANT_RELEVANCE": GrantRelevanceAssessment(
                relevance_score=0.9,
                funding_agencies=["NCI"],
                mechanism_fit="R01",
            ),
        }
        result = await runner._step_report("imatinib", instance)
        assert "report_markdown" in result
        md = result["report_markdown"]
        assert len(md) > 100
        assert "imatinib" in md.lower() or "Drug Discovery" in md


# === Report Builder Tests ===


class TestW10ReportBuilder:
    @pytest.fixture
    def minimal_result(self):
        return W10DrugDiscoveryResult(
            workflow_id="test-001",
            query="aspirin",
        )

    @pytest.fixture
    def full_result(self):
        return W10DrugDiscoveryResult(
            workflow_id="test-002",
            query="imatinib",
            scope=DrugDiscoveryScope(
                research_question="Efficacy of imatinib in CML",
                target_compound_or_class="imatinib",
                therapeutic_area="Oncology",
                key_objectives=["Assess potency", "Safety profile"],
                search_strategy="ChEMBL MCP",
            ),
            target_summary="BCR-ABL tyrosine kinase, encoded by ABL1 gene",
            efficacy_analysis=EfficacyAnalysis(
                summary="Imatinib shows strong efficacy.",
                key_findings=["IC50 = 100 nM", "High selectivity"],
                potency_assessment="strong",
                selectivity_notes="Selective for BCR-ABL, KIT, PDGFR",
                limitations=["CML blast crisis resistance"],
            ),
            safety_profile_summary="Good safety profile. CYP3A4 substrate.",
            mechanism_review=MechanismReview(
                primary_mechanism="ATP-competitive inhibition of BCR-ABL",
                target_pathway="BCR-ABL → STAT5 → proliferation",
                on_target_evidence=["Cellular IC50 = 0.1 uM"],
                off_target_risks=["KIT inhibition → edema"],
                mechanistic_gaps=["Blast crisis mechanisms unclear"],
            ),
            literature_comparison=LiteratureComparison(
                similar_compounds=["dasatinib", "nilotinib"],
                novelty_assessment="First approved TKI for CML.",
                key_differences=["Better selectivity than dasatinib"],
                relevant_papers=["Druker 2001 NEJM", "O'Brien 2003 NEJM"],
            ),
            grant_relevance=GrantRelevanceAssessment(
                relevance_score=0.92,
                funding_agencies=["NCI", "ASCO"],
                mechanism_fit="R01",
                innovation_statement="First-in-class kinase inhibitor",
                rationale="High clinical impact in hematologic malignancies",
            ),
            mcp_used=True,
        )

    def test_minimal_result_builds(self, minimal_result):
        md = build_w10_report(minimal_result)
        assert isinstance(md, str)
        assert len(md) > 50
        assert "Drug Discovery Analysis Report" in md
        assert "aspirin" in md

    def test_full_result_sections(self, full_result):
        md = build_w10_report(full_result)
        assert "## Research Scope" in md
        assert "## Target Identification" in md
        assert "## Bioactivity Profile" in md or "## Efficacy Analysis" in md
        assert "## Mechanism of Action" in md
        assert "## Literature Comparison" in md
        assert "## Grant Funding Potential" in md

    def test_efficacy_potency_capitalized(self, full_result):
        md = build_w10_report(full_result)
        assert "Strong" in md  # potency_assessment capitalized

    def test_grant_score_formatted(self, full_result):
        md = build_w10_report(full_result)
        assert "0.92" in md

    def test_mcp_footer_note(self, full_result):
        md = build_w10_report(full_result)
        assert "ChEMBL + ClinicalTrials.gov MCP" in md

    def test_no_mcp_footer_note(self, minimal_result):
        minimal_result.mcp_used = False
        md = build_w10_report(minimal_result)
        assert "direct database queries" in md

    def test_date_in_header(self, minimal_result):
        import re
        md = build_w10_report(minimal_result)
        assert re.search(r"\d{4}-\d{2}-\d{2}", md)

    def test_key_findings_as_list(self, full_result):
        md = build_w10_report(full_result)
        assert "IC50 = 100 nM" in md

    def test_similar_compounds_listed(self, full_result):
        md = build_w10_report(full_result)
        assert "dasatinib" in md or "nilotinib" in md

    def test_on_target_evidence(self, full_result):
        md = build_w10_report(full_result)
        assert "On-Target Evidence" in md

    def test_off_target_risks(self, full_result):
        md = build_w10_report(full_result)
        assert "Off-Target Risks" in md

    def test_limitations_listed(self, full_result):
        md = build_w10_report(full_result)
        assert "Limitations" in md or "blast crisis" in md.lower()

    def test_empty_compounds_fallback_text(self, full_result):
        full_result.compound_profiles = []
        md = build_w10_report(full_result)
        assert "ChEMBL" in md

    def test_empty_trials_fallback_text(self, full_result):
        full_result.trial_summaries = []
        md = build_w10_report(full_result)
        assert "ClinicalTrials.gov" in md
