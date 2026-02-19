"""Data Engineering Agent (Team 10) — pipeline design, data quality, infrastructure.

Responsibilities:
1. Bioinformatics pipeline specification (Nextflow/Snakemake)
2. Data quality assessment and reporting
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage


# === Output Models ===


class PipelineStep(BaseModel):
    """A single step in a bioinformatics pipeline."""

    name: str = ""
    tool: str = ""
    tool_version: str = ""
    container: str = ""
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    cpu: int = 1
    memory_gb: int = 4
    estimated_minutes: int = 30


class PipelineSpec(BaseModel):
    """Specification for a bioinformatics analysis pipeline."""

    name: str = ""
    framework: str = "nextflow"  # "nextflow" | "snakemake" | "wdl"
    description: str = ""
    steps: list[PipelineStep] = Field(default_factory=list)
    input_format: str = ""
    output_format: str = ""
    estimated_cost_usd: float = 0.0
    estimated_runtime_hours: float = 0.0
    notes: list[str] = Field(default_factory=list)


class QualityMetric(BaseModel):
    """A single data quality metric."""

    name: str = ""
    value: str = ""
    status: str = "pass"  # "pass" | "warn" | "fail"
    threshold: str = ""
    note: str = ""


class DataQualityReport(BaseModel):
    """Report on data quality assessment."""

    dataset_id: str = ""
    overall_status: str = "pass"  # "pass" | "warn" | "fail"
    metrics: list[QualityMetric] = Field(default_factory=list)
    samples_total: int = 0
    samples_passing: int = 0
    recommendations: list[str] = Field(default_factory=list)
    summary: str = ""


# === Agent Implementation ===


class DataEngineeringAgent(BaseAgent):
    """Specialist agent for bioinformatics data engineering.

    Supports 2 execution modes:
    - run(): Default — design a pipeline based on query
    - assess_quality(): Evaluate data quality
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Design a bioinformatics pipeline based on the query."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Design a bioinformatics pipeline for:\n\n"
                    f"{context.task_description}\n\n"
                    f"Specify the framework, steps with tools and versions, "
                    f"resource requirements, and estimated cost/runtime."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=PipelineSpec,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="PipelineSpec",
            summary=f"Pipeline '{result.name}': {len(result.steps)} steps, ~{result.estimated_runtime_hours}h",
            llm_response=meta,
        )

    async def assess_quality(self, context: ContextPackage) -> AgentOutput:
        """Assess data quality for a given dataset."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Assess the data quality for:\n\n"
                    f"{context.task_description}\n\n"
                    f"Check completeness, format compliance, and flag any issues."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=DataQualityReport,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="DataQualityReport",
            summary=f"Quality: {result.overall_status} — {result.samples_passing}/{result.samples_total} samples pass",
            llm_response=meta,
        )
