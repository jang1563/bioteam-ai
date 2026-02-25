"""W7 Data Integrity Audit Runner — 8-step pipeline for systematic integrity checking.

Steps:
  COLLECT → GENE_CHECK → STAT_CHECK → RETRACTION_CHECK → METADATA_CHECK
    → IMAGE_CHECK → LLM_CONTEXTUALIZE → REPORT

Code-only steps: GENE_CHECK, STAT_CHECK, RETRACTION_CHECK, METADATA_CHECK, IMAGE_CHECK, REPORT.
LLM steps: COLLECT (KM), LLM_CONTEXTUALIZE (DIA).
Budget: $3 max, ~2 Sonnet calls.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.agents.base import observe
from app.agents.registry import AgentRegistry
from app.api.v1.sse import SSEHub
from app.config import settings
from app.cost.tracker import COST_PER_1K_INPUT, COST_PER_1K_OUTPUT
from app.engines.integrity.finding_models import ImageInput
from app.engines.integrity.gene_name_checker import GeneNameChecker
from app.engines.integrity.image_checker import ImageChecker
from app.engines.integrity.metadata_validator import MetadataValidator
from app.engines.integrity.retraction_checker import RetractionChecker
from app.engines.integrity.statistical_checker import StatisticalChecker
from app.models.agent import AgentOutput
from app.models.workflow import WorkflowInstance, WorkflowStepDef
from app.workflows.engine import WorkflowEngine

logger = logging.getLogger(__name__)


def _estimate_step_cost(model_tier: str, est_input_tokens: int, est_output_tokens: int) -> float:
    input_rate = COST_PER_1K_INPUT.get(model_tier, 0.0)
    output_rate = COST_PER_1K_OUTPUT.get(model_tier, 0.0)
    return (est_input_tokens / 1000) * input_rate + (est_output_tokens / 1000) * output_rate


W7_STEPS: list[WorkflowStepDef] = [
    WorkflowStepDef(
        id="COLLECT",
        agent_id="knowledge_manager",
        output_schema="MemoryRetrievalResult",
        next_step="GENE_CHECK",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=600, est_output_tokens=200),
    ),
    WorkflowStepDef(
        id="GENE_CHECK",
        agent_id="code_only",
        output_schema="dict",
        next_step="STAT_CHECK",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="STAT_CHECK",
        agent_id="code_only",
        output_schema="dict",
        next_step="RETRACTION_CHECK",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="RETRACTION_CHECK",
        agent_id="code_only",
        output_schema="dict",
        next_step="METADATA_CHECK",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="METADATA_CHECK",
        agent_id="code_only",
        output_schema="dict",
        next_step="IMAGE_CHECK",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="IMAGE_CHECK",
        agent_id="code_only",
        output_schema="dict",
        next_step="LLM_CONTEXTUALIZE",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="LLM_CONTEXTUALIZE",
        agent_id="data_integrity_auditor",
        output_schema="IntegrityAnalysis",
        next_step="REPORT",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=3000, est_output_tokens=1000),
    ),
    WorkflowStepDef(
        id="REPORT",
        agent_id="code_only",
        output_schema="dict",
        next_step=None,
        estimated_cost=0.0,
    ),
]

_METHOD_MAP: dict[str, tuple[str, str]] = {
    "COLLECT": ("knowledge_manager", "run"),
    "LLM_CONTEXTUALIZE": ("data_integrity_auditor", "contextualize_only"),
}


class W7IntegrityRunner:
    """Orchestrates the W7 Data Integrity Audit pipeline.

    8-step pipeline:
      COLLECT -> GENE_CHECK -> STAT_CHECK -> RETRACTION_CHECK
      -> METADATA_CHECK -> IMAGE_CHECK -> LLM_CONTEXTUALIZE -> REPORT
    """

    def __init__(
        self,
        registry: AgentRegistry,
        engine: WorkflowEngine | None = None,
        sse_hub: SSEHub | None = None,
    ) -> None:
        self._registry = registry
        self._engine = engine
        self._sse = sse_hub

        # Deterministic checkers
        self._gene_checker = GeneNameChecker()
        self._stat_checker = StatisticalChecker()
        self._retraction_checker = RetractionChecker()
        self._metadata_validator = MetadataValidator()
        self._image_checker = ImageChecker()

        # Accumulated results
        self._all_findings: list[dict] = []
        self._collected_text: str = ""
        self._collected_dois: list[str] = []
        self._collected_images: list[ImageInput] = []

    async def run(self, instance: WorkflowInstance) -> WorkflowInstance:
        """Run the full W7 pipeline."""
        # Reset accumulated state from any previous run
        self._all_findings = []
        self._collected_text = ""
        self._collected_dois = []
        self._collected_images = []

        instance.state = "RUNNING"
        query = instance.query

        step_index = {s.id: s for s in W7_STEPS}
        current_step_id = W7_STEPS[0].id

        while current_step_id:
            step = step_index[current_step_id]
            instance.current_step = step.id

            # Broadcast step start
            if self._sse:
                await self._sse.broadcast_dict(
                    event_type="workflow.step_start",
                    workflow_id=instance.id,
                    step_id=step.id,
                )

            start_time = time.time()
            try:
                result = await self._run_step(step, query, instance)
                duration_ms = int((time.time() - start_time) * 1000)

                # Record step completion
                instance.step_history.append({
                    "step_id": step.id,
                    "agent_id": step.agent_id,
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "duration_ms": duration_ms,
                    "result_summary": self._summarize_result(result),
                })

            except Exception as e:
                logger.error("W7 step %s failed: %s", step.id, e)
                duration_ms = int((time.time() - start_time) * 1000)
                instance.step_history.append({
                    "step_id": step.id,
                    "agent_id": step.agent_id,
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "duration_ms": duration_ms,
                    "error": str(e),
                })
                instance.state = "FAILED"
                return instance

            # Broadcast step complete
            if self._sse:
                await self._sse.broadcast_dict(
                    event_type="workflow.step_complete",
                    workflow_id=instance.id,
                    step_id=step.id,
                )

            current_step_id = step.next_step

        instance.state = "COMPLETED"
        return instance

    async def _run_step(
        self,
        step: WorkflowStepDef,
        query: str,
        instance: WorkflowInstance,
    ) -> dict:
        """Execute a single step."""

        if step.id == "COLLECT":
            return await self._step_collect(query, instance)
        elif step.id == "GENE_CHECK":
            return self._step_gene_check()
        elif step.id == "STAT_CHECK":
            return self._step_stat_check()
        elif step.id == "RETRACTION_CHECK":
            return await self._step_retraction_check()
        elif step.id == "METADATA_CHECK":
            return self._step_metadata_check()
        elif step.id == "IMAGE_CHECK":
            return self._step_image_check()
        elif step.id == "LLM_CONTEXTUALIZE":
            return await self._step_llm_contextualize(query, instance)
        elif step.id == "REPORT":
            return self._step_report(instance)
        else:
            raise ValueError(f"Unknown step: {step.id}")

    async def _step_collect(self, query: str, instance: WorkflowInstance) -> dict:
        """COLLECT: Retrieve relevant text from memory via Knowledge Manager."""
        agent = self._registry.get("knowledge_manager")
        if agent is None:
            logger.warning("Knowledge Manager not available, using query as text")
            self._collected_text = query
            return {"text": query, "source": "query"}

        context = ContextPackage(
            task_description=f"Retrieve text and DOIs for integrity audit: {query}",
            prior_step_outputs=[],
        )
        output = await agent.execute(context)
        instance.budget_remaining -= output.cost

        # Extract text from output
        result = output.output or {}
        if isinstance(result, dict):
            texts = result.get("texts", [])
            self._collected_text = "\n\n".join(str(t) for t in texts) if texts else query
        else:
            self._collected_text = query

        return {"text_length": len(self._collected_text), "cost": output.cost}

    def _step_gene_check(self) -> dict:
        """GENE_CHECK: Run GeneNameChecker on collected text."""
        findings = self._gene_checker.check_text(self._collected_text)
        for f in findings:
            self._all_findings.append(f.model_dump(mode="json"))
        return {"gene_findings": len(findings)}

    def _step_stat_check(self) -> dict:
        """STAT_CHECK: Run StatisticalChecker on collected text."""
        findings = self._stat_checker.extract_and_check_stats(self._collected_text)
        for f in findings:
            self._all_findings.append(f.model_dump(mode="json"))
        return {"stat_findings": len(findings)}

    async def _step_retraction_check(self) -> dict:
        """RETRACTION_CHECK: Check DOIs via Crossref/PubPeer."""
        import re
        doi_pattern = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
        self._collected_dois = list(set(doi_pattern.findall(self._collected_text)))

        findings = await self._retraction_checker.check_batch(self._collected_dois)
        for f in findings:
            self._all_findings.append(f.model_dump(mode="json"))
        return {"dois_checked": len(self._collected_dois), "retraction_findings": len(findings)}

    def _step_metadata_check(self) -> dict:
        """METADATA_CHECK: Validate GEO/SRA accessions and genome builds."""
        findings = self._metadata_validator.check_all(self._collected_text)
        for f in findings:
            self._all_findings.append(f.model_dump(mode="json"))
        return {"metadata_findings": len(findings)}

    def _step_image_check(self) -> dict:
        """IMAGE_CHECK: Check collected images for duplicates and manipulation."""
        if not self._collected_images:
            return {"image_findings": 0, "skipped": True}
        findings = self._image_checker.check_all(self._collected_images)
        for f in findings:
            self._all_findings.append(f.model_dump(mode="json"))
        return {"image_findings": len(findings)}

    async def _step_llm_contextualize(self, query: str, instance: WorkflowInstance) -> dict:
        """LLM_CONTEXTUALIZE: Use agent's contextualize_only (LLM-only, no re-run of checkers)."""
        agent = self._registry.get("data_integrity_auditor")
        if agent is None:
            logger.warning("DataIntegrityAuditorAgent not available, skipping LLM contextualization")
            return {"skipped": True}

        # Use contextualize_only to avoid re-running deterministic checkers
        output = await agent.contextualize_only(
            findings_dicts=self._all_findings,
            text=self._collected_text,
            query=query,
        )
        instance.budget_remaining -= output.cost

        # Update findings with LLM-contextualized results
        if output.output and isinstance(output.output, dict):
            llm_findings = output.output.get("findings", [])
            if llm_findings:
                self._all_findings = llm_findings

        return {"cost": output.cost, "findings_after_llm": len(self._all_findings)}

    def _step_report(self, instance: WorkflowInstance) -> dict:
        """REPORT: Assemble final report."""
        total = len(self._all_findings)

        by_severity: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for f in self._all_findings:
            sev = f.get("severity", "info")
            cat = f.get("category", "unknown")
            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_category[cat] = by_category.get(cat, 0) + 1

        # Determine overall level
        if by_severity.get("critical", 0) > 0:
            level = "critical"
        elif by_severity.get("error", 0) > 0:
            level = "significant_issues"
        elif by_severity.get("warning", 0) > 0:
            level = "minor_issues"
        else:
            level = "clean"

        # Store in session_manifest for persistence
        instance.session_manifest["integrity_report"] = {
            "total_findings": total,
            "findings_by_severity": by_severity,
            "findings_by_category": by_category,
            "overall_level": level,
            "findings": self._all_findings,
        }

        return {
            "total_findings": total,
            "findings_by_severity": by_severity,
            "overall_level": level,
        }

    def _summarize_result(self, result: dict) -> str:
        """Create a brief summary of a step result for step_history."""
        if not result:
            return "No result"
        parts = []
        for key, val in result.items():
            if isinstance(val, (int, float, str, bool)):
                parts.append(f"{key}={val}")
        return ", ".join(parts[:5]) if parts else "OK"
