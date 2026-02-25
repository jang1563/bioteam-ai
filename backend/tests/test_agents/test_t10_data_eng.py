"""Tests for Data Engineering Agent (Team 10) — run, assess_quality."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.teams.t10_data_eng import (
    DataEngineeringAgent,
    DataQualityReport,
    PipelineSpec,
    PipelineStep,
    QualityMetric,
)
from app.llm.mock_layer import MockLLMLayer
from app.models.messages import ContextPackage


def make_agent(mock_responses: dict | None = None) -> DataEngineeringAgent:
    """Create a DataEngineeringAgent with MockLLMLayer."""
    spec = BaseAgent.load_spec("t10_data_eng")
    mock = MockLLMLayer(mock_responses or {})
    return DataEngineeringAgent(spec=spec, llm=mock)


def test_run_pipeline_design():
    """T10 should design a bioinformatics pipeline."""
    result = PipelineSpec(
        name="GeneLab RNA-seq Pipeline",
        framework="nextflow",
        description="Bulk RNA-seq processing for GeneLab spaceflight data.",
        steps=[
            PipelineStep(name="QC", tool="FastQC", tool_version="0.12.1", cpu=2, memory_gb=4),
            PipelineStep(name="Trim", tool="fastp", tool_version="0.23.4", cpu=4, memory_gb=8),
            PipelineStep(name="Align", tool="STAR", tool_version="2.7.11a", cpu=8, memory_gb=32),
            PipelineStep(name="Count", tool="featureCounts", tool_version="2.0.6", cpu=4, memory_gb=8),
        ],
        estimated_cost_usd=12.50,
        estimated_runtime_hours=3.5,
    )
    agent = make_agent({"haiku:PipelineSpec": result})

    context = ContextPackage(
        task_description="Design a pipeline for processing bulk RNA-seq from GeneLab"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert output.output_type == "PipelineSpec"
    assert output.output["name"] == "GeneLab RNA-seq Pipeline"
    assert len(output.output["steps"]) == 4
    assert output.model_version.startswith("mock-")
    print("  PASS: run_pipeline_design")


def test_assess_quality():
    """T10 should assess data quality and return a report."""
    result = DataQualityReport(
        dataset_id="GSE123456",
        overall_status="warn",
        metrics=[
            QualityMetric(name="Read count", value="25M avg", status="pass"),
            QualityMetric(name="GC content", value="52%", status="pass"),
            QualityMetric(name="Duplication rate", value="45%", status="warn", threshold="<30%"),
        ],
        samples_total=12,
        samples_passing=10,
        recommendations=["Re-sequence samples S3 and S7 — low read count"],
        summary="10/12 samples pass QC; 2 flagged for low read count.",
    )
    agent = make_agent({"haiku:DataQualityReport": result})

    context = ContextPackage(
        task_description="Assess the quality of GeneLab scRNA-seq dataset GSE123456"
    )

    output = asyncio.run(agent.assess_quality(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert output.output_type == "DataQualityReport"
    assert output.output["overall_status"] == "warn"
    assert output.output["samples_passing"] == 10
    print("  PASS: assess_quality")


def test_agent_metadata():
    """T10 output should carry correct agent metadata."""
    agent = make_agent()
    context = ContextPackage(task_description="Test query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.agent_id == "t10_data_eng"
    assert output.model_tier == "haiku"
    assert output.model_version == "mock-haiku"
    print("  PASS: agent_metadata")


def test_spec_loaded_correctly():
    """T10 spec should have expected fields."""
    spec = BaseAgent.load_spec("t10_data_eng")
    assert spec.id == "t10_data_eng"
    assert spec.tier == "domain_expert"
    assert spec.model_tier == "haiku"
    assert spec.criticality == "optional"
    assert spec.division == "translation"
    print("  PASS: spec_loaded_correctly")


if __name__ == "__main__":
    print("Testing Data Engineering Agent (T10):")
    test_run_pipeline_design()
    test_assess_quality()
    test_agent_metadata()
    test_spec_loaded_correctly()
    print("\nAll Data Engineering Agent tests passed!")
