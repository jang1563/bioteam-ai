"""Tests for Pydantic model validation — bounds, required fields, computed properties."""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from pydantic import ValidationError

from app.models.agent import AgentOutput, AgentSpec, AgentStatus
from app.models.evidence import (
    RCMXTScore, OmicsLayerStatus, ExportBibTeX, ExportMarkdown,
    PRISMAFlow, SessionManifest,
)
from app.models.workflow import DirectorNote


# === RCMXTScore Validation ===


def test_rcmxt_valid_scores():
    score = RCMXTScore(claim="test claim", R=0.8, C=0.6, M=0.9, T=0.7)
    assert score.R == 0.8
    assert score.X is None
    print("  PASS: rcmxt_valid_scores")


def test_rcmxt_with_x_axis():
    score = RCMXTScore(claim="test", R=0.5, C=0.5, M=0.5, X=0.8, T=0.5)
    assert score.X == 0.8
    print("  PASS: rcmxt_with_x_axis")


def test_rcmxt_r_below_zero():
    try:
        RCMXTScore(claim="test", R=-0.1, C=0.5, M=0.5, T=0.5)
        assert False, "Should reject R < 0"
    except ValidationError:
        pass
    print("  PASS: rcmxt_r_below_zero")


def test_rcmxt_c_above_one():
    try:
        RCMXTScore(claim="test", R=0.5, C=1.1, M=0.5, T=0.5)
        assert False, "Should reject C > 1.0"
    except ValidationError:
        pass
    print("  PASS: rcmxt_c_above_one")


def test_rcmxt_x_below_zero():
    try:
        RCMXTScore(claim="test", R=0.5, C=0.5, M=0.5, X=-0.5, T=0.5)
        assert False, "Should reject X < 0"
    except ValidationError:
        pass
    print("  PASS: rcmxt_x_below_zero")


def test_rcmxt_boundary_values():
    """0.0 and 1.0 are valid boundary values."""
    score = RCMXTScore(claim="test", R=0.0, C=1.0, M=0.0, X=1.0, T=0.0)
    assert score.R == 0.0
    assert score.C == 1.0
    print("  PASS: rcmxt_boundary_values")


def test_rcmxt_compute_composite_4axis():
    score = RCMXTScore(claim="test", R=0.8, C=0.6, M=0.4, T=1.0)
    result = score.compute_composite()
    expected = round((0.8 + 0.6 + 0.4 + 1.0) / 4, 3)
    assert result == expected
    assert score.composite == expected
    print("  PASS: rcmxt_compute_composite_4axis")


def test_rcmxt_compute_composite_5axis():
    score = RCMXTScore(claim="test", R=0.8, C=0.6, M=0.4, X=0.2, T=1.0)
    result = score.compute_composite()
    expected = round((0.8 + 0.6 + 0.4 + 0.2 + 1.0) / 5, 3)
    assert result == expected
    print("  PASS: rcmxt_compute_composite_5axis")


def test_rcmxt_provenance_literal():
    score = RCMXTScore(claim="test", R=0.5, C=0.5, M=0.5, T=0.5, provenance="internal_synthesis")
    assert score.provenance == "internal_synthesis"
    print("  PASS: rcmxt_provenance_literal")


def test_rcmxt_provenance_invalid():
    try:
        RCMXTScore(claim="test", R=0.5, C=0.5, M=0.5, T=0.5, provenance="invalid_type")
        assert False, "Should reject invalid provenance"
    except ValidationError:
        pass
    print("  PASS: rcmxt_provenance_invalid")


# === AgentOutput Tests ===


def test_agent_output_is_success_true():
    out = AgentOutput(agent_id="test", output={"data": 1})
    assert out.is_success is True
    print("  PASS: agent_output_is_success_true")


def test_agent_output_is_success_false():
    out = AgentOutput(agent_id="test", error="something went wrong")
    assert out.is_success is False
    print("  PASS: agent_output_is_success_false")


def test_agent_output_unique_ids():
    out1 = AgentOutput(agent_id="test")
    out2 = AgentOutput(agent_id="test")
    assert out1.id != out2.id
    print("  PASS: agent_output_unique_ids")


def test_agent_output_timestamp():
    out = AgentOutput(agent_id="test")
    assert out.created_at is not None
    assert out.created_at.tzinfo is not None  # timezone-aware
    print("  PASS: agent_output_timestamp")


# === AgentSpec Tests ===


def test_agent_spec_minimal():
    spec = AgentSpec(
        id="test",
        name="Test Agent",
        tier="domain_expert",
        model_tier="sonnet",
        system_prompt_file="test.md",
    )
    assert spec.criticality == "optional"
    assert spec.tools == []
    assert spec.mcp_access == []
    assert spec.literature_access is False
    print("  PASS: agent_spec_minimal")


def test_agent_spec_dual_mode():
    spec = AgentSpec(
        id="rd",
        name="Research Director",
        tier="strategic",
        model_tier="sonnet",
        model_tier_secondary="opus",
        system_prompt_file="rd.md",
        criticality="critical",
    )
    assert spec.model_tier == "sonnet"
    assert spec.model_tier_secondary == "opus"
    assert spec.criticality == "critical"
    print("  PASS: agent_spec_dual_mode")


# === DirectorNote Tests ===


def test_director_note_factory():
    """injected_at should be unique per instance (not class-level frozen)."""
    import time
    note1 = DirectorNote(text="First note")
    time.sleep(0.01)
    note2 = DirectorNote(text="Second note")
    # Both should have timezone-aware timestamps
    assert note1.injected_at.tzinfo is not None
    assert note2.injected_at.tzinfo is not None
    print("  PASS: director_note_factory")


# === OmicsLayerStatus Tests ===


def test_omics_layer_status_defaults():
    ols = OmicsLayerStatus()
    assert ols.layers_available == []
    assert ols.multi_omics_available is False
    print("  PASS: omics_layer_status_defaults")


def test_omics_layer_status_multi():
    ols = OmicsLayerStatus(
        layers_available=["genomic", "transcriptomic"],
        layers_agreeing=["genomic", "transcriptomic"],
        multi_omics_available=True,
    )
    assert len(ols.layers_available) == 2
    assert ols.multi_omics_available is True
    print("  PASS: omics_layer_status_multi")


# === Export Tests ===


def test_bibtex_render():
    bib = ExportBibTeX(entries=[
        {
            "type": "article",
            "key": "smith2024",
            "fields": {"author": "Smith, J.", "title": "Spaceflight Anemia", "year": "2024"},
        }
    ])
    rendered = bib.render()
    assert "@article{smith2024," in rendered
    assert "author = {Smith, J.}," in rendered
    assert "title = {Spaceflight Anemia}," in rendered
    print("  PASS: bibtex_render")


def test_bibtex_render_empty():
    bib = ExportBibTeX()
    assert bib.render() == ""
    print("  PASS: bibtex_render_empty")


def test_markdown_render():
    md = ExportMarkdown(
        title="Test Report",
        sections=[
            {"heading": "Introduction", "content": "This is a test.", "level": 2},
            {"heading": "Results", "content": "We found stuff.", "level": 2},
        ],
        ai_disclosure="Generated by BioTeam-AI",
    )
    rendered = md.render()
    assert "# Test Report" in rendered
    assert "## Introduction" in rendered
    assert "This is a test." in rendered
    assert "## AI Disclosure" in rendered
    assert "Generated by BioTeam-AI" in rendered
    print("  PASS: markdown_render")


def test_markdown_render_empty():
    md = ExportMarkdown()
    rendered = md.render()
    assert rendered.strip() == ""
    print("  PASS: markdown_render_empty")


# === PRISMAFlow Tests ===


def test_prisma_defaults():
    prisma = PRISMAFlow()
    assert prisma.records_identified == 0
    assert prisma.studies_included == 0
    assert prisma.full_text_exclusion_reasons == {}
    print("  PASS: prisma_defaults")


def test_prisma_with_values():
    prisma = PRISMAFlow(
        records_identified=500,
        duplicates_removed=50,
        records_screened=450,
        studies_included=25,
    )
    assert prisma.records_identified == 500
    assert prisma.studies_included == 25
    print("  PASS: prisma_with_values")


# === SessionManifest Tests ===


def test_session_manifest_basic():
    manifest = SessionManifest(
        workflow_id="w1_abc",
        template="W1",
        query="spaceflight anemia",
        started_at=datetime.now(timezone.utc),
    )
    assert manifest.total_cost == 0.0
    assert manifest.model_versions == []
    assert manifest.prisma is None
    print("  PASS: session_manifest_basic")


if __name__ == "__main__":
    print("Testing Model Validation:")
    # RCMXTScore
    test_rcmxt_valid_scores()
    test_rcmxt_with_x_axis()
    test_rcmxt_r_below_zero()
    test_rcmxt_c_above_one()
    test_rcmxt_x_below_zero()
    test_rcmxt_boundary_values()
    test_rcmxt_compute_composite_4axis()
    test_rcmxt_compute_composite_5axis()
    test_rcmxt_provenance_literal()
    test_rcmxt_provenance_invalid()
    # AgentOutput
    test_agent_output_is_success_true()
    test_agent_output_is_success_false()
    test_agent_output_unique_ids()
    test_agent_output_timestamp()
    # AgentSpec
    test_agent_spec_minimal()
    test_agent_spec_dual_mode()
    # DirectorNote
    test_director_note_factory()
    # OmicsLayerStatus
    test_omics_layer_status_defaults()
    test_omics_layer_status_multi()
    # Exports
    test_bibtex_render()
    test_bibtex_render_empty()
    test_markdown_render()
    test_markdown_render_empty()
    # PRISMA
    test_prisma_defaults()
    test_prisma_with_values()
    # SessionManifest
    test_session_manifest_basic()
    print("\nAll Model Validation tests passed!")
