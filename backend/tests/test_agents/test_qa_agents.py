"""Tests for QA Agents — StatisticalRigorQA, BiologicalPlausibilityQA, ReproducibilityQA."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.qa_agents import (
    BiologicalPlausibilityQA,
    BiologicalPlausibilityResult,
    ReproducibilityQA,
    ReproducibilityResult,
    StatisticalRigorQA,
    StatisticalRigorResult,
)
from app.llm.mock_layer import MockLLMLayer
from app.models.messages import ContextPackage

# === StatisticalRigorQA Tests ===


def make_stat_qa(mock_responses: dict | None = None) -> StatisticalRigorQA:
    """Create a StatisticalRigorQA agent with MockLLMLayer."""
    spec = BaseAgent.load_spec("qa_statistical_rigor")
    mock = MockLLMLayer(mock_responses or {})
    return StatisticalRigorQA(spec=spec, llm=mock)


def test_stat_qa_run_returns_output():
    """StatisticalRigorQA should assess statistical rigor and return AgentOutput."""
    result = StatisticalRigorResult(
        query="DEG analysis with t-test on 3 replicates, no MTC",
        issues_found=[
            {"issue": "No multiple testing correction", "severity": "high"},
            {"issue": "Insufficient replicates for t-test", "severity": "medium"},
        ],
        corrections_needed=["Apply FDR correction (Benjamini-Hochberg)", "Use limma-voom instead of t-test"],
        effect_sizes_valid=False,
        power_adequate=False,
        overall_verdict="Major revisions needed",
        summary="Two critical issues: missing MTC and underpowered analysis with n=3.",
        confidence=0.88,
    )
    agent = make_stat_qa({"sonnet:StatisticalRigorResult": result})

    context = ContextPackage(
        task_description="Review: DEG analysis with t-test on 3 replicates, no multiple testing correction"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert len(output.output["issues_found"]) == 2
    assert output.output["power_adequate"] is False
    assert output.output["overall_verdict"] == "Major revisions needed"
    assert output.model_version.startswith("mock-")
    print("  PASS: stat_qa_run_returns_output")


def test_stat_qa_output_type():
    """StatisticalRigorQA output should have correct output_type."""
    result = StatisticalRigorResult(
        query="Test query",
        summary="Test summary for statistical rigor QA.",
        overall_verdict="Pass",
        confidence=0.75,
    )
    agent = make_stat_qa({"sonnet:StatisticalRigorResult": result})
    context = ContextPackage(task_description="Test statistical rigor query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.output_type == "StatisticalRigorResult"
    print("  PASS: stat_qa_output_type")


def test_stat_qa_summary_populated():
    """StatisticalRigorQA output should have a populated summary."""
    result = StatisticalRigorResult(
        query="ANOVA check",
        summary="ANOVA assumptions met; Tukey post-hoc appropriate; Cohen's d correctly reported.",
        overall_verdict="Pass with minor notes",
        confidence=0.90,
    )
    agent = make_stat_qa({"sonnet:StatisticalRigorResult": result})
    context = ContextPackage(task_description="Check ANOVA on 5 groups with post-hoc Tukey")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.summary
    assert len(output.summary) > 0
    assert "ANOVA" in output.summary
    print("  PASS: stat_qa_summary_populated")


def test_stat_qa_spec_loaded():
    """StatisticalRigorQA spec should have expected fields."""
    spec = BaseAgent.load_spec("qa_statistical_rigor")
    assert spec.id == "qa_statistical_rigor"
    assert spec.tier == "qa"
    assert spec.model_tier == "sonnet"
    assert spec.criticality == "optional"
    assert spec.division == "independent"
    print("  PASS: stat_qa_spec_loaded")


# === BiologicalPlausibilityQA Tests ===


def make_bio_qa(mock_responses: dict | None = None) -> BiologicalPlausibilityQA:
    """Create a BiologicalPlausibilityQA agent with MockLLMLayer."""
    spec = BaseAgent.load_spec("qa_biological_plausibility")
    mock = MockLLMLayer(mock_responses or {})
    return BiologicalPlausibilityQA(spec=spec, llm=mock)


def test_bio_qa_run_returns_output():
    """BiologicalPlausibilityQA should assess biological plausibility and return AgentOutput."""
    result = BiologicalPlausibilityResult(
        query="TP53 upregulated 100-fold in healthy tissue without stress",
        pathway_validity=[
            {"pathway": "p53 signaling", "valid": False, "reason": "100x upregulation without stimulus is artifactual"},
        ],
        artifact_flags=["Potential contamination or batch effect"],
        literature_consistency="Inconsistent with known TP53 regulation",
        overall_verdict="Implausible — likely artifact",
        summary="TP53 100x upregulation without stress stimulus flagged as likely artifact or contamination.",
        confidence=0.92,
    )
    agent = make_bio_qa({"sonnet:BiologicalPlausibilityResult": result})

    context = ContextPackage(
        task_description="Finding: TP53 upregulated 100-fold in healthy tissue with no stress stimulus"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert len(output.output["artifact_flags"]) == 1
    assert output.output["overall_verdict"] == "Implausible — likely artifact"
    assert output.model_version.startswith("mock-")
    print("  PASS: bio_qa_run_returns_output")


def test_bio_qa_output_type():
    """BiologicalPlausibilityQA output should have correct output_type."""
    result = BiologicalPlausibilityResult(
        query="Test query",
        summary="Test summary for biological plausibility QA.",
        overall_verdict="Plausible",
        confidence=0.80,
    )
    agent = make_bio_qa({"sonnet:BiologicalPlausibilityResult": result})
    context = ContextPackage(task_description="Test biological plausibility query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.output_type == "BiologicalPlausibilityResult"
    print("  PASS: bio_qa_output_type")


def test_bio_qa_summary_populated():
    """BiologicalPlausibilityQA output should have a populated summary."""
    result = BiologicalPlausibilityResult(
        query="NF-kB activation leading to muscle atrophy",
        summary="Plausible: NF-kB inflammatory signaling to muscle proteolysis is well-established.",
        overall_verdict="Plausible",
        confidence=0.85,
    )
    agent = make_bio_qa({"sonnet:BiologicalPlausibilityResult": result})
    context = ContextPackage(
        task_description="Claim: spaceflight activates NF-kB leading to muscle atrophy"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.summary
    assert len(output.summary) > 0
    assert "NF-kB" in output.summary
    print("  PASS: bio_qa_summary_populated")


def test_bio_qa_spec_loaded():
    """BiologicalPlausibilityQA spec should have expected fields."""
    spec = BaseAgent.load_spec("qa_biological_plausibility")
    assert spec.id == "qa_biological_plausibility"
    assert spec.tier == "qa"
    assert spec.model_tier == "sonnet"
    assert spec.criticality == "optional"
    assert spec.division == "independent"
    print("  PASS: bio_qa_spec_loaded")


# === ReproducibilityQA Tests ===


def make_repro_qa(mock_responses: dict | None = None) -> ReproducibilityQA:
    """Create a ReproducibilityQA agent with MockLLMLayer."""
    spec = BaseAgent.load_spec("qa_reproducibility")
    mock = MockLLMLayer(mock_responses or {})
    return ReproducibilityQA(spec=spec, llm=mock)


def test_repro_qa_run_returns_output():
    """ReproducibilityQA should assess reproducibility and return AgentOutput."""
    result = ReproducibilityResult(
        query="RNA-seq analysis with no code, GEO accession provided, R version not specified",
        fair_compliance={
            "findable": True,
            "accessible": True,
            "interoperable": False,
            "reusable": False,
        },
        metadata_completeness=0.55,
        code_reproducibility="Not reproducible — no code or scripts provided",
        environment_specified=False,
        overall_verdict="Needs improvement",
        summary="FAIR partially met (F+A); code and environment missing. Verdict: needs improvement.",
        confidence=0.87,
    )
    agent = make_repro_qa({"haiku:ReproducibilityResult": result})

    context = ContextPackage(
        task_description="Check reproducibility: RNA-seq analysis with no code, GEO accession provided"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert output.output["fair_compliance"]["findable"] is True
    assert output.output["fair_compliance"]["reusable"] is False
    assert output.output["metadata_completeness"] == 0.55
    assert output.output["environment_specified"] is False
    assert output.model_version.startswith("mock-")
    print("  PASS: repro_qa_run_returns_output")


def test_repro_qa_output_type():
    """ReproducibilityQA output should have correct output_type."""
    result = ReproducibilityResult(
        query="Test query",
        summary="Test summary for reproducibility QA.",
        overall_verdict="Excellent",
        confidence=0.90,
    )
    agent = make_repro_qa({"haiku:ReproducibilityResult": result})
    context = ContextPackage(task_description="Test reproducibility query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.output_type == "ReproducibilityResult"
    print("  PASS: repro_qa_output_type")


def test_repro_qa_summary_populated():
    """ReproducibilityQA output should have a populated summary."""
    result = ReproducibilityResult(
        query="Jupyter notebook with Docker and Zenodo DOI",
        summary="Excellent reproducibility: Docker image, pinned deps, Zenodo DOI. All FAIR criteria met.",
        overall_verdict="Excellent",
        confidence=0.95,
    )
    agent = make_repro_qa({"haiku:ReproducibilityResult": result})
    context = ContextPackage(
        task_description="Assess: Jupyter notebook with pinned deps, Docker image, data on Zenodo"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.summary
    assert len(output.summary) > 0
    assert "Docker" in output.summary
    print("  PASS: repro_qa_summary_populated")


def test_repro_qa_spec_loaded():
    """ReproducibilityQA spec should have expected fields."""
    spec = BaseAgent.load_spec("qa_reproducibility")
    assert spec.id == "qa_reproducibility"
    assert spec.tier == "qa"
    assert spec.model_tier == "haiku"
    assert spec.criticality == "optional"
    assert spec.division == "independent"
    print("  PASS: repro_qa_spec_loaded")


def test_repro_qa_agent_metadata():
    """ReproducibilityQA output should carry correct agent metadata."""
    agent = make_repro_qa()
    context = ContextPackage(task_description="Test query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.agent_id == "qa_reproducibility"
    assert output.model_tier == "haiku"
    assert output.model_version == "mock-haiku"
    assert output.duration_ms >= 0
    print("  PASS: repro_qa_agent_metadata")


if __name__ == "__main__":
    print("Testing QA Agents:")
    print("\n  StatisticalRigorQA:")
    test_stat_qa_run_returns_output()
    test_stat_qa_output_type()
    test_stat_qa_summary_populated()
    test_stat_qa_spec_loaded()
    print("\n  BiologicalPlausibilityQA:")
    test_bio_qa_run_returns_output()
    test_bio_qa_output_type()
    test_bio_qa_summary_populated()
    test_bio_qa_spec_loaded()
    print("\n  ReproducibilityQA:")
    test_repro_qa_run_returns_output()
    test_repro_qa_output_type()
    test_repro_qa_summary_populated()
    test_repro_qa_spec_loaded()
    test_repro_qa_agent_metadata()
    print("\nAll QA Agent tests passed!")
