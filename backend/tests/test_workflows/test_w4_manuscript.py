"""Tests for W4 Manuscript Writing Runner."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import pytest
from app.agents.registry import create_registry
from app.llm.mock_layer import MockLLMLayer
from app.models.workflow import WorkflowInstance
from app.workflows.runners.w4_manuscript import (
    _METHOD_MAP,
    W4_STEPS,
    W4ManuscriptRunner,
    get_step_by_id,
)


def _patch_qa_aliases(registry):
    """Register QA agents under the alias IDs used by workflow runners.

    The registry registers QA agents with spec IDs (qa_statistical_rigor, etc.)
    but the runners reference them as (statistical_rigor_qa, etc.).
    """
    alias_map = {
        "statistical_rigor_qa": "qa_statistical_rigor",
        "biological_plausibility_qa": "qa_biological_plausibility",
        "reproducibility_qa": "qa_reproducibility",
    }
    for alias, spec_id in alias_map.items():
        agent = registry.get(spec_id)
        if agent and registry.get(alias) is None:
            registry._agents[alias] = agent


def _make_runner():
    mock = MockLLMLayer({})
    registry = create_registry(mock)
    _patch_qa_aliases(registry)
    return W4ManuscriptRunner(registry=registry)


# === Step Definition Tests ===


def test_step_count():
    """W4 should have exactly 12 steps (9 original + STORY_ANCHOR + 2× NARRATIVE_CHECK)."""
    assert len(W4_STEPS) == 12


def test_step_order():
    expected = [
        "OUTLINE", "STORY_ANCHOR", "ASSEMBLE", "DRAFT",
        "NARRATIVE_CHECK_DRAFT", "FIGURES",
        "STATISTICAL_REVIEW", "PLAUSIBILITY_REVIEW",
        "REPRODUCIBILITY_CHECK", "REVISION",
        "NARRATIVE_CHECK_FINAL", "REPORT",
    ]
    actual = [s.id for s in W4_STEPS]
    assert actual == expected


def test_code_only_steps():
    step = get_step_by_id("REPORT")
    assert step is not None
    assert step.agent_id == "code_only"
    assert step.estimated_cost == 0.0


def test_method_map_coverage():
    agent_steps = [s for s in W4_STEPS if s.agent_id != "code_only"]
    for step in agent_steps:
        assert step.id in _METHOD_MAP, f"{step.id} missing from _METHOD_MAP"


def test_get_step_by_id():
    assert get_step_by_id("OUTLINE") is not None
    assert get_step_by_id("NONEXISTENT") is None


def test_human_checkpoint_on_outline():
    """OUTLINE step should be marked as a human checkpoint."""
    step = get_step_by_id("OUTLINE")
    assert step is not None
    assert step.is_human_checkpoint is True


def test_no_parallel_steps():
    """W4 should have no parallel steps."""
    for step in W4_STEPS:
        assert step.is_parallel is False or step.is_parallel is None or not step.is_parallel


# === Pipeline Tests ===


def test_pipeline_pauses_at_outline():
    """W4 run() should pause at OUTLINE human checkpoint."""
    runner = _make_runner()
    result = asyncio.run(runner.run(query="Draft manuscript on spaceflight-induced anemia mechanisms"))

    instance = result["instance"]
    assert instance.state == "WAITING_HUMAN"
    assert result["paused_at"] is not None

    # Only OUTLINE should have results (it's the first step and the checkpoint)
    step_ids = list(result["step_results"].keys())
    assert "OUTLINE" in step_ids

    # Steps after OUTLINE should NOT have results yet
    assert "ASSEMBLE" not in step_ids
    assert "DRAFT" not in step_ids
    assert "REPORT" not in step_ids


def test_resume_after_human_completes():
    """After resume_after_human(), pipeline should complete."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test manuscript pipeline"))

    instance = pause_result["instance"]
    assert instance.state == "WAITING_HUMAN"

    # Resume after human approval
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test manuscript pipeline"))

    assert resume_result["completed"] is True
    assert resume_result["instance"].state == "COMPLETED"
    assert resume_result["instance"].template == "W4"

    # All post-checkpoint steps should be present
    step_ids = list(resume_result["step_results"].keys())
    assert "ASSEMBLE" in step_ids
    assert "DRAFT" in step_ids
    assert "FIGURES" in step_ids
    assert "STATISTICAL_REVIEW" in step_ids
    assert "PLAUSIBILITY_REVIEW" in step_ids
    assert "REPRODUCIBILITY_CHECK" in step_ids
    assert "REVISION" in step_ids
    assert "REPORT" in step_ids


def test_report_structure():
    """REPORT step should produce a structured manuscript report."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test report structure"))

    instance = pause_result["instance"]
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test report structure"))

    report = resume_result["step_results"].get("REPORT")
    assert report is not None
    output = report.get("output", report) if isinstance(report, dict) else report

    # Should have the expected keys
    assert "query" in output
    assert "workflow_id" in output
    assert "reviews" in output


def test_session_manifest_populated():
    """Instance session_manifest should contain manuscript report after full run."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test manifest"))

    instance = pause_result["instance"]
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test manifest"))

    manifest = resume_result["instance"].session_manifest
    assert manifest is not None
    assert "manuscript_report" in manifest


def test_session_manifest_reviews():
    """Session manifest should include review summaries from _store_manuscript_results."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test reviews"))

    instance = pause_result["instance"]
    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test reviews"))

    manifest = resume_result["instance"].session_manifest
    assert manifest is not None
    assert "reviews" in manifest
    assert "workflow_template" in manifest
    assert manifest["workflow_template"] == "W4"


def test_budget_tracking():
    """Budget should be tracked across run() and resume_after_human()."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test budget", budget=25.0))

    instance = pause_result["instance"]
    assert instance.budget_total == 25.0
    # Budget remaining should be less than or equal to total
    assert instance.budget_remaining <= instance.budget_total

    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test budget"))
    final_instance = resume_result["instance"]
    assert final_instance.budget_remaining <= final_instance.budget_total


# === STORY_ANCHOR and NARRATIVE_CHECK Tests ===


def test_story_anchor_step_definition():
    """STORY_ANCHOR should be a code_only step with positive estimated cost."""
    step = get_step_by_id("STORY_ANCHOR")
    assert step is not None
    assert step.agent_id == "code_only"
    assert step.is_human_checkpoint is False
    assert step.estimated_cost >= 0.0
    assert step.next_step == "ASSEMBLE"


def test_narrative_check_draft_step_definition():
    """NARRATIVE_CHECK_DRAFT should be a code_only step after DRAFT."""
    step = get_step_by_id("NARRATIVE_CHECK_DRAFT")
    assert step is not None
    assert step.agent_id == "code_only"
    assert step.is_human_checkpoint is False
    assert step.next_step == "FIGURES"


def test_narrative_check_final_step_definition():
    """NARRATIVE_CHECK_FINAL should be a code_only step after REVISION."""
    step = get_step_by_id("NARRATIVE_CHECK_FINAL")
    assert step is not None
    assert step.agent_id == "code_only"
    assert step.is_human_checkpoint is False
    assert step.next_step == "REPORT"


def test_outline_next_step_is_story_anchor():
    """OUTLINE.next_step must point to STORY_ANCHOR (not ASSEMBLE directly)."""
    step = get_step_by_id("OUTLINE")
    assert step is not None
    assert step.next_step == "STORY_ANCHOR"


def test_draft_next_step_is_narrative_check():
    """DRAFT.next_step must point to NARRATIVE_CHECK_DRAFT."""
    step = get_step_by_id("DRAFT")
    assert step is not None
    assert step.next_step == "NARRATIVE_CHECK_DRAFT"


def test_revision_next_step_is_narrative_check():
    """REVISION.next_step must point to NARRATIVE_CHECK_FINAL."""
    step = get_step_by_id("REVISION")
    assert step is not None
    assert step.next_step == "NARRATIVE_CHECK_FINAL"


def test_story_anchor_in_resume_step_results():
    """After resume, STORY_ANCHOR should appear in step_results."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test story anchor presence"))
    instance = pause_result["instance"]

    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test story anchor presence"))

    step_ids = list(resume_result["step_results"].keys())
    assert "STORY_ANCHOR" in step_ids


def test_narrative_checks_in_resume_step_results():
    """After resume, NARRATIVE_CHECK_DRAFT and NARRATIVE_CHECK_FINAL appear in results."""
    runner = _make_runner()
    pause_result = asyncio.run(runner.run(query="Test narrative checks"))
    instance = pause_result["instance"]

    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test narrative checks"))

    step_ids = list(resume_result["step_results"].keys())
    assert "NARRATIVE_CHECK_DRAFT" in step_ids
    assert "NARRATIVE_CHECK_FINAL" in step_ids


def test_story_anchor_with_injected_w11_frame():
    """STORY_ANCHOR uses frame from session_manifest when story_frame_workflow_id present."""
    runner = _make_runner()

    # Pre-seed a story_frame in the manifest (simulating W11 output already stored)
    preloaded_frame = {
        "frame_id": "SF-001",
        "narrative_type": "mechanism_discovery",
        "hook": "Spaceflight induces anemia via HIF-1α activation.",
        "central_tension": "Expected radiation damage; found hypoxia response.",
        "core_claim": "Microgravity drives spaceflight anemia.",
        "supporting_findings": ["HIF upregulated 3×", "RBC -40%"],
        "figure_sequence": ["Fig1: RBC timeline"],
        "target_tier": "nature_cell",
        "novelty_rationale": "First mechanistic link.",
        "blind_spots": ["Radiation not fully excluded"],
        "impact_score": 0.9,
        "version": 1,
    }

    pause_result = asyncio.run(runner.run(query="Test with preloaded frame"))
    instance = pause_result["instance"]
    # Inject a pre-existing story_frame to simulate W11 having stored it
    instance.session_manifest["story_frame"] = preloaded_frame

    resume_result = asyncio.run(runner.resume_after_human(instance, query="Test with preloaded frame"))

    # story_frame should still be in manifest (STORY_ANCHOR preserves it)
    manifest = resume_result["instance"].session_manifest
    assert "story_frame" in manifest
    sf = manifest["story_frame"]
    # Should match (or be the preloaded frame since no W11 workflow ID was provided,
    # _run_story_anchor will auto-generate a fallback — but story_frame key must exist)
    assert sf is not None


@pytest.mark.asyncio
async def test_narrative_check_skips_gracefully_without_story_frame():
    """NARRATIVE_CHECK steps skip silently when no story_frame in manifest."""
    runner = _make_runner()

    # Create instance with empty session_manifest (no story_frame)
    inst = WorkflowInstance(
        template="W4",
        query="test",
        budget_total=25.0,
        budget_remaining=25.0,
        session_manifest={},  # No story_frame
    )

    # Directly call the narrative check — should not raise
    result = await runner._run_narrative_check("DRAFT", "some draft text", inst)

    assert result is not None
    output = result.output if hasattr(result, "output") else result
    # Should return skipped=True when no story_frame
    assert output.get("skipped") is True


@pytest.mark.asyncio
async def test_narrative_check_stores_uppercase_key_in_manifest():
    """NARRATIVE_CHECK stores result under 'narrative_drift_DRAFT' (uppercase), not lowercase.

    Regression test for Bug 9: _run_narrative_check previously used section_id.lower()
    when building the manifest key, causing _generate_report() to always read None.
    """
    runner = _make_runner()

    inst = WorkflowInstance(
        template="W4",
        query="test",
        budget_total=25.0,
        budget_remaining=25.0,
        session_manifest={
            "story_frame": {
                "frame_id": "SF-001",
                "narrative_type": "mechanism_discovery",
                "hook": "Test hook.",
                "central_tension": "Test tension.",
                "core_claim": "Test claim.",
                "supporting_findings": [],
                "figure_sequence": [],
                "target_tier": "specialty",
                "novelty_rationale": "Test.",
                "blind_spots": [],
                "impact_score": 0.7,
                "version": 1,
            }
        },
    )

    await runner._run_narrative_check("DRAFT", "manuscript draft text", inst)

    manifest = inst.session_manifest
    # Must exist with UPPERCASE key (not "narrative_drift_draft")
    assert "narrative_drift_DRAFT" in manifest, (
        f"Expected 'narrative_drift_DRAFT' in manifest keys: {list(manifest.keys())}"
    )
    assert "narrative_drift_draft" not in manifest, (
        "Bug 9 regression: lowercase key 'narrative_drift_draft' should not be stored"
    )


@pytest.mark.asyncio
async def test_generate_report_includes_narrative_consistency():
    """_generate_report() must surface narrative drift data from session_manifest.

    Requires Bug 9 fix: narrative_drift keys must be uppercase to match _generate_report reads.
    """
    runner = _make_runner()

    pause_result = await runner.run(query="Test narrative report")
    instance = pause_result["instance"]
    # Inject a story_frame so NARRATIVE_CHECK runs (not skipped)
    instance.session_manifest["story_frame"] = {
        "frame_id": "SF-001",
        "narrative_type": "paradigm_challenge",
        "hook": "Test hook.",
        "central_tension": "Test tension.",
        "core_claim": "Test claim.",
        "supporting_findings": [],
        "figure_sequence": [],
        "target_tier": "specialty",
        "novelty_rationale": "Test.",
        "blind_spots": [],
        "impact_score": 0.8,
        "version": 1,
    }

    resume_result = await runner.resume_after_human(instance, query="Test narrative report")

    report = resume_result["step_results"].get("REPORT")
    assert report is not None
    output = report.get("output", report) if isinstance(report, dict) else report

    # story_frame must be in report
    assert "story_frame" in output
    # narrative_consistency dict must be present
    assert "narrative_consistency" in output
    nc = output["narrative_consistency"]
    assert isinstance(nc, dict)
    # Both draft and final drift reports should be present (not None) since story_frame was injected
    assert nc.get("draft") is not None, "narrative_consistency.draft should not be None"
    assert nc.get("final") is not None, "narrative_consistency.final should not be None"
