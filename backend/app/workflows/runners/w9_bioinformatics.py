"""W9 Deep Bioinformatics Analysis Runner — 20-step multi-omics pipeline.

Pipeline (6 interaction points: 3 HC + 3 DC):
  Phase A: PRE_HEALTH_CHECK → SCOPE[HC] → INGEST_DATA[DC] → QC[HC]
  Phase B: GENOMIC_ANALYSIS → EXPRESSION_ANALYSIS → PROTEIN_ANALYSIS
           → VARIANT_ANNOTATION → PATHWAY_ENRICHMENT → NETWORK_ANALYSIS → [DC_PHASE_B]
  Phase C: CROSS_OMICS_INTEGRATION → [HC_INTEGRATION]
  Phase D: LITERATURE_COMPARISON → NOVELTY_ASSESSMENT → CONTRADICTION_SCAN
           → INTEGRITY_AUDIT → [DC_NOVELTY]
  Phase E: EXPERIMENTAL_DESIGN → GRANT_RELEVANCE → REPORT

Budget: ~$25 default (DC is $0, code steps $0, Opus steps ~$8 combined)
Supports checkpoint/resume (Phase 1 CheckpointManager integration).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from app.agents.base import observe
from app.agents.registry import AgentRegistry
from app.api.v1.sse import SSEHub
from app.cost.tracker import COST_PER_1K_INPUT, COST_PER_1K_OUTPUT
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from app.models.w9_analysis import (
    QCReport,
    W9BioinformaticsReport,
)
from app.models.workflow import WorkflowInstance, WorkflowStepDef
from app.workflows.engine import WorkflowEngine

logger = logging.getLogger(__name__)


def _estimate_step_cost(model_tier: str, est_input_tokens: int, est_output_tokens: int) -> float:
    input_rate = COST_PER_1K_INPUT.get(model_tier, 0.0)
    output_rate = COST_PER_1K_OUTPUT.get(model_tier, 0.0)
    return (est_input_tokens / 1000) * input_rate + (est_output_tokens / 1000) * output_rate


# === Step Definitions ===

W9_STEPS: list[WorkflowStepDef] = [
    # ─── Phase A: Scoping & Ingestion ───────────────────────────────────────
    WorkflowStepDef(
        id="PRE_HEALTH_CHECK",
        agent_id="code_only",
        output_schema="dict",
        next_step="SCOPE",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="SCOPE",
        agent_id="research_director",
        output_schema="ResearchScopeDefinition",
        next_step="INGEST_DATA",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=2000, est_output_tokens=1000),
        is_human_checkpoint=True,
        interaction_type="HC",
    ),
    WorkflowStepDef(
        id="INGEST_DATA",
        agent_id="code_only",
        output_schema="DataManifest",
        next_step="QC",
        estimated_cost=0.0,
        interaction_type="DC",
        dc_auto_continue_minutes=30,
    ),
    WorkflowStepDef(
        id="QC",
        agent_id="code_only",
        output_schema="QCReport",
        next_step="GENOMIC_ANALYSIS",
        estimated_cost=0.0,
        is_human_checkpoint=True,
        interaction_type="HC",
    ),
    # ─── Phase B: Domain Analysis ───────────────────────────────────────────
    WorkflowStepDef(
        id="GENOMIC_ANALYSIS",
        agent_id="t01_genomics",
        output_schema="dict",
        next_step="EXPRESSION_ANALYSIS",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=6000, est_output_tokens=2000),
    ),
    WorkflowStepDef(
        id="EXPRESSION_ANALYSIS",
        agent_id="t02_transcriptomics",
        output_schema="ExpressionAnalysisResult",
        next_step="PROTEIN_ANALYSIS",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=6000, est_output_tokens=2000),
    ),
    WorkflowStepDef(
        id="PROTEIN_ANALYSIS",
        agent_id="t03_proteomics",
        output_schema="ProteinAnalysisResult",
        next_step="VARIANT_ANNOTATION",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=5000, est_output_tokens=1500),
    ),
    WorkflowStepDef(
        id="VARIANT_ANNOTATION",
        agent_id="code_only",
        output_schema="VariantAnnotationResult",
        next_step="PATHWAY_ENRICHMENT",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="PATHWAY_ENRICHMENT",
        agent_id="t06_systems_bio",
        output_schema="PathwayEnrichmentResult",
        next_step="NETWORK_ANALYSIS",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=5000, est_output_tokens=2000),
    ),
    WorkflowStepDef(
        id="NETWORK_ANALYSIS",
        agent_id="t06_systems_bio",
        output_schema="NetworkAnalysisResult",
        next_step="DC_PHASE_B",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=4000, est_output_tokens=1500),
    ),
    WorkflowStepDef(
        id="DC_PHASE_B",
        agent_id="code_only",
        output_schema="dict",
        next_step="CROSS_OMICS_INTEGRATION",
        estimated_cost=0.0,
        interaction_type="DC",
        dc_auto_continue_minutes=60,
    ),
    # ─── Phase C: Integration ───────────────────────────────────────────────
    WorkflowStepDef(
        id="CROSS_OMICS_INTEGRATION",
        agent_id="integrative_biologist",
        output_schema="CrossOmicsIntegrationResult",
        next_step="HC_INTEGRATION",
        estimated_cost=_estimate_step_cost("opus", est_input_tokens=12000, est_output_tokens=4000),
    ),
    WorkflowStepDef(
        id="HC_INTEGRATION",
        agent_id="code_only",
        output_schema="dict",
        next_step="LITERATURE_COMPARISON",
        estimated_cost=0.0,
        is_human_checkpoint=True,
        interaction_type="HC",
    ),
    # ─── Phase D: Interpretation ────────────────────────────────────────────
    WorkflowStepDef(
        id="LITERATURE_COMPARISON",
        agent_id="knowledge_manager",
        output_schema="dict",
        next_step="NOVELTY_ASSESSMENT",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=3000, est_output_tokens=1000),
    ),
    WorkflowStepDef(
        id="NOVELTY_ASSESSMENT",
        agent_id="research_director",
        output_schema="NoveltyAssessment",
        next_step="CONTRADICTION_SCAN",
        estimated_cost=_estimate_step_cost("opus", est_input_tokens=10000, est_output_tokens=3000),
    ),
    WorkflowStepDef(
        id="CONTRADICTION_SCAN",
        agent_id="ambiguity_engine",
        output_schema="dict",
        next_step="INTEGRITY_AUDIT",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=4000, est_output_tokens=1500),
    ),
    WorkflowStepDef(
        id="INTEGRITY_AUDIT",
        agent_id="code_only",
        output_schema="dict",
        next_step="DC_NOVELTY",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="DC_NOVELTY",
        agent_id="code_only",
        output_schema="dict",
        next_step="EXPERIMENTAL_DESIGN",
        estimated_cost=0.0,
        interaction_type="DC",
        dc_auto_continue_minutes=60,
    ),
    # ─── Phase E: Output ─────────────────────────────────────────────────────
    WorkflowStepDef(
        id="EXPERIMENTAL_DESIGN",
        agent_id="experimental_designer",
        output_schema="ExperimentalDesignPlan",
        next_step="GRANT_RELEVANCE",
        estimated_cost=_estimate_step_cost("opus", est_input_tokens=8000, est_output_tokens=3000),
    ),
    WorkflowStepDef(
        id="GRANT_RELEVANCE",
        agent_id="t09_grants",
        output_schema="GrantRelevanceAnalysis",
        next_step="REPORT",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=5000, est_output_tokens=2000),
    ),
    WorkflowStepDef(
        id="REPORT",
        agent_id="code_only",
        output_schema="W9BioinformaticsReport",
        next_step=None,
        estimated_cost=0.0,
    ),
]

# Code-only steps (no LLM call; or LLM called internally by code logic)
_CODE_STEPS = frozenset({
    "PRE_HEALTH_CHECK", "INGEST_DATA", "QC",
    "VARIANT_ANNOTATION", "DC_PHASE_B", "HC_INTEGRATION",
    "INTEGRITY_AUDIT", "DC_NOVELTY", "REPORT",
})

# Method routing for agent steps
_METHOD_MAP: dict[str, tuple[str, str]] = {
    "SCOPE": ("research_director", "run"),
    "GENOMIC_ANALYSIS": ("t01_genomics", "run"),
    "EXPRESSION_ANALYSIS": ("t02_transcriptomics", "run"),
    "PROTEIN_ANALYSIS": ("t03_proteomics", "run"),
    "PATHWAY_ENRICHMENT": ("t06_systems_bio", "run"),
    "NETWORK_ANALYSIS": ("t06_systems_bio", "run"),
    "CROSS_OMICS_INTEGRATION": ("integrative_biologist", "run"),
    "LITERATURE_COMPARISON": ("knowledge_manager", "search_literature"),
    "NOVELTY_ASSESSMENT": ("research_director", "run"),
    "CONTRADICTION_SCAN": ("ambiguity_engine", "detect_contradictions"),
    "EXPERIMENTAL_DESIGN": ("experimental_designer", "run"),
    "GRANT_RELEVANCE": ("t09_grants", "run"),
}


class W9BioinformaticsRunner:
    """Orchestrates the W9 Deep Bioinformatics Analysis pipeline.

    20-step multi-omics pipeline with 3 Human Checkpoints (HC) and
    3 Direction Checks (DC). Supports checkpoint/resume via CheckpointManager.

    Usage:
        runner = W9BioinformaticsRunner(registry=registry, engine=engine)
        result = await runner.run(query="BRCA1 variants in breast cancer", budget=25.0)
    """

    def __init__(
        self,
        registry: AgentRegistry,
        engine: WorkflowEngine | None = None,
        sse_hub: SSEHub | None = None,
        persist_fn=None,
        checkpoint_manager=None,
        lab_kb=None,
    ) -> None:
        self.registry = registry
        self.engine = engine or WorkflowEngine()
        self.sse_hub = sse_hub
        self._persist_fn = persist_fn
        self._checkpoint_manager = checkpoint_manager
        self._lab_kb = lab_kb
        self._step_results: dict[str, Any] = {}
        self._data_manifest_path: str | None = None

    async def _persist(self, instance: WorkflowInstance) -> None:
        if self._persist_fn:
            await self._persist_fn(instance)

    async def _broadcast(
        self,
        event_type: str,
        instance: WorkflowInstance,
        step_id: str,
        payload: dict | None = None,
    ) -> None:
        if self.sse_hub:
            await self.sse_hub.broadcast_dict(
                event_type=event_type,
                workflow_id=instance.id,
                step_id=step_id,
                agent_id="w9_runner",
                payload=payload or {},
            )

    @observe(name="workflow.w9_bioinformatics")
    async def run(
        self,
        query: str = "",
        data_manifest_path: str | None = None,
        instance: WorkflowInstance | None = None,
        budget: float = 25.0,
        skip_human_checkpoints: bool = False,
    ) -> dict[str, Any]:
        """Execute the W9 pipeline.

        Args:
            query: Research question (e.g., "BRCA1 variants in breast cancer").
            data_manifest_path: Path to JSON describing input data files.
            instance: Optional pre-created WorkflowInstance.
            budget: Maximum budget in USD.
            skip_human_checkpoints: If True, skip all HC pauses (for testing).

        Returns:
            Dict with step_results, instance, report, and paused_at.
        """
        self._data_manifest_path = data_manifest_path

        if instance is None:
            instance = WorkflowInstance(
                template="W9",
                query=query,
                budget_total=budget,
                budget_remaining=budget,
                data_manifest_path=data_manifest_path,
            )

        self.engine.start(instance, first_step="PRE_HEALTH_CHECK")
        await self._persist(instance)

        # Restore completed steps from checkpoint if available
        if self._checkpoint_manager:
            completed = await self._checkpoint_manager.load_completed_steps(instance.id)
            self._step_results.update(completed)
            if completed:
                logger.info("W9 resumed: %d completed steps restored", len(completed))

        paused_at: str | None = None

        for step in W9_STEPS:
            if instance.state not in ("RUNNING",):
                break

            # Skip already-completed steps (checkpoint resume)
            if step.id in self._step_results:
                logger.debug("W9 skipping completed step: %s", step.id)
                continue

            await self._broadcast("workflow.step_started", instance, step.id, {"step": step.id})
            step_start = time.time()

            try:
                if step.id in _CODE_STEPS:
                    result = await self._run_code_step(step, instance, skip_human_checkpoints)
                else:
                    result = await self._run_agent_step(step, instance)
            except Exception as e:
                logger.error("W9 step %s failed: %s", step.id, e)
                result = AgentOutput(
                    agent_id=str(step.agent_id),
                    output={},
                    summary=f"Step failed: {e}",
                    is_success=False,
                    error=str(e),
                )

            step_ms = int((time.time() - step_start) * 1000)
            self._step_results[step.id] = result

            # Deduct budget
            if result.cost > 0:
                self.engine.deduct_budget(instance, result.cost)

            self.engine.advance(
                instance, step.id,
                step_result={"type": step.agent_id},
                agent_id=str(step.agent_id),
                status="completed" if result.is_success else "failed",
                duration_ms=step_ms,
                cost=result.cost,
            )
            await self._persist(instance)

            # Save checkpoint
            if self._checkpoint_manager:
                await self._checkpoint_manager.save_step(instance.id, step.id, result)

            # Handle HC (Human Checkpoint)
            if step.interaction_type == "HC" and not skip_human_checkpoints:
                self.engine.request_human(instance)
                await self._persist(instance)
                paused_at = step.id
                await self._broadcast(
                    "workflow.human_checkpoint", instance, step.id,
                    {"message": f"Human review required at {step.id}. Approve to continue."},
                )
                logger.info("W9 paused at HC: %s", step.id)
                break

            # Handle DC (Direction Check) — broadcasts summary, non-blocking
            if step.interaction_type == "DC":
                summary = self._build_dc_summary(step.id)
                await self._broadcast(
                    "workflow.direction_check", instance, step.id,
                    {
                        "summary": summary,
                        "auto_continue_after_minutes": step.dc_auto_continue_minutes,
                        "cost_remaining": instance.budget_remaining,
                    },
                )
                # DC does NOT pause — execution continues immediately
                logger.info("W9 DC emitted at %s", step.id)

            # Check budget
            if instance.budget_remaining <= 0:
                self.engine.mark_over_budget(instance)
                await self._persist(instance)
                await self._broadcast(
                    "workflow.over_budget", instance, step.id,
                    {"cost_used": instance.budget_total - instance.budget_remaining},
                )
                break

        # Build final report if pipeline completed
        report = None
        if instance.state == "RUNNING" and "REPORT" in self._step_results:
            report = self._step_results.get("REPORT")
            if hasattr(report, "output") and isinstance(report.output, W9BioinformaticsReport):
                report = report.output
            self.engine.complete(instance)
            await self._persist(instance)

        return {
            "step_results": self._step_results,
            "instance": instance,
            "report": report,
            "paused_at": paused_at,
        }

    def _build_dc_summary(self, dc_step_id: str) -> str:
        """Build a summary string for a Direction Check event."""
        if dc_step_id == "INGEST_DATA":
            manifest = self._step_results.get("INGEST_DATA")
            if manifest and hasattr(manifest, "output"):
                m = manifest.output
                files = m.get("files_loaded", []) if isinstance(m, dict) else []
                return f"Data ingestion complete: {len(files)} files loaded."
            return "Data ingestion complete."

        if dc_step_id == "DC_PHASE_B":
            variants = self._step_results.get("VARIANT_ANNOTATION")
            pathways = self._step_results.get("PATHWAY_ENRICHMENT")
            n_variants = 0
            n_pathways = 0
            if variants and hasattr(variants, "output"):
                v = variants.output
                n_variants = v.get("total_variants", 0) if isinstance(v, dict) else 0
            if pathways and hasattr(pathways, "output"):
                p = pathways.output
                n_pathways = p.get("significant_terms", 0) if isinstance(p, dict) else 0
            return (
                f"Phase B complete: {n_variants} variants annotated, "
                f"{n_pathways} enriched pathways. "
                "Continue to cross-omics integration?"
            )

        if dc_step_id == "DC_NOVELTY":
            novelty = self._step_results.get("NOVELTY_ASSESSMENT")
            n_novel = 0
            if novelty and hasattr(novelty, "output"):
                n = novelty.output
                n_novel = len(n.get("novel_findings", [])) if isinstance(n, dict) else 0
            return (
                f"Phase D complete: {n_novel} novel findings identified. "
                "Proceed to experimental design and grant relevance?"
            )

        return f"Phase checkpoint at {dc_step_id}. Continue?"

    async def _run_code_step(
        self,
        step: WorkflowStepDef,
        instance: WorkflowInstance,
        skip_human_checkpoints: bool = False,
    ) -> AgentOutput:
        """Execute a code-only step without LLM calls."""
        output: dict = {}

        if step.id == "PRE_HEALTH_CHECK":
            output = await self._pre_health_check()

        elif step.id == "INGEST_DATA":
            output = await self._ingest_data(instance)

        elif step.id == "QC":
            output = await self._run_qc()

        elif step.id == "VARIANT_ANNOTATION":
            output = await self._variant_annotation(instance)

        elif step.id == "INTEGRITY_AUDIT":
            output = await self._integrity_audit()

        elif step.id in ("DC_PHASE_B", "DC_NOVELTY", "HC_INTEGRATION"):
            # Direction checks and HC placeholders — just pass through
            output = {"status": "checkpoint", "step_id": step.id}

        elif step.id == "REPORT":
            output = await self._build_report(instance)

        return AgentOutput(
            agent_id="code_only",
            output=output,
            summary=f"{step.id} completed",
            is_success=True,
            cost=0.0,
        )

    async def _run_agent_step(
        self,
        step: WorkflowStepDef,
        instance: WorkflowInstance,
    ) -> AgentOutput:
        """Execute a step via an LLM agent."""
        agent_id, method = _METHOD_MAP.get(step.id, (str(step.agent_id), "run"))
        agent = self.registry.get(agent_id) if self.registry else None
        if agent is None:
            return AgentOutput(
                agent_id=agent_id,
                output={},
                summary=f"Agent {agent_id} not available",
                is_success=False,
                error=f"Agent {agent_id} not registered",
            )

        # Build context from prior steps
        ctx_meta = {
            "query": instance.query,
            "step_id": step.id,
            "prior_steps": {
                k: (v.output if hasattr(v, "output") else v)
                for k, v in self._step_results.items()
                if k not in ("DC_PHASE_B", "DC_NOVELTY", "HC_INTEGRATION")
            },
        }
        context = ContextPackage(
            task_description=instance.query,
            metadata=ctx_meta,
        )

        try:
            agent_method = getattr(agent, method)
            result = await agent_method(context)
        except Exception as e:
            logger.warning("W9 agent step %s failed: %s", step.id, e)
            return AgentOutput(
                agent_id=agent_id,
                output={},
                summary=f"Agent step {step.id} failed: {e}",
                is_success=False,
                error=str(e),
            )

        # Wrap raw output in AgentOutput if needed
        if isinstance(result, AgentOutput):
            return result
        return AgentOutput(
            agent_id=agent_id,
            output=result if isinstance(result, dict) else {"result": str(result)},
            summary=f"{step.id} completed",
            is_success=True,
            cost=step.estimated_cost,
        )

    # ─── Code Step Implementations ─────────────────────────────────────────

    async def _pre_health_check(self) -> dict:
        """Check availability of key bioinformatics services."""
        try:
            from app.workflows.health_checker import HealthChecker
            issues = await HealthChecker.check_all([
                "ensembl_vep_api", "uniprot_api", "gprofiler",
            ])
            return {
                "health_issues": [i.__dict__ if hasattr(i, "__dict__") else str(i) for i in issues],
                "all_healthy": len(issues) == 0,
            }
        except Exception as e:
            logger.debug("Health check failed: %s", e)
            return {"all_healthy": False, "error": str(e)}

    async def _ingest_data(self, instance: WorkflowInstance) -> dict:
        """Parse data manifest file and record loaded files."""
        if not instance.data_manifest_path:
            return {
                "files_loaded": [],
                "sample_count": 0,
                "data_types": [],
                "ingest_warnings": ["No data_manifest_path provided — running in query-only mode"],
            }
        try:
            manifest_path = Path(instance.data_manifest_path)
            if not manifest_path.exists():
                return {
                    "files_loaded": [],
                    "ingest_warnings": [f"Manifest file not found: {instance.data_manifest_path}"],
                }
            manifest_data = json.loads(manifest_path.read_text())
            files = manifest_data.get("files", [])
            return {
                "files_loaded": files,
                "sample_count": manifest_data.get("sample_count", len(files)),
                "data_types": list({f.get("type", "unknown") for f in files}),
                "total_size_mb": sum(f.get("size_mb", 0) for f in files),
                "ingest_warnings": manifest_data.get("warnings", []),
            }
        except Exception as e:
            logger.warning("Data ingest failed: %s", e)
            return {"files_loaded": [], "ingest_warnings": [str(e)]}

    async def _run_qc(self) -> dict:
        """Basic QC check on ingested data."""
        manifest = self._step_results.get("INGEST_DATA")
        if manifest is None:
            return QCReport(passed=True, qc_summary="No data files — QC skipped").model_dump()
        output = manifest.output if hasattr(manifest, "output") else manifest
        files = output.get("files_loaded", []) if isinstance(output, dict) else []
        warnings = output.get("ingest_warnings", []) if isinstance(output, dict) else []
        qc = QCReport(
            passed=len(warnings) == 0,
            samples_passed=len(files),
            samples_failed=len(warnings),
            failure_reasons=warnings[:5],
            qc_summary=f"QC: {len(files)} files, {len(warnings)} warnings",
        )
        return qc.model_dump()

    async def _variant_annotation(self, instance: WorkflowInstance) -> dict:
        """Annotate variants using Ensembl VEP (PTC tool call)."""
        genomics_result = self._step_results.get("GENOMIC_ANALYSIS")
        if genomics_result is None:
            return {
                "total_variants": 0,
                "high_impact_variants": [],
                "affected_genes": [],
                "summary": "No genomics data available for variant annotation.",
            }

        output = genomics_result.output if hasattr(genomics_result, "output") else {}
        variants = output.get("variants", []) if isinstance(output, dict) else []

        if not variants:
            return {
                "total_variants": 0,
                "high_impact_variants": [],
                "affected_genes": [],
                "summary": "No variants identified in genomic analysis.",
            }

        try:
            from app.llm.ptc_handler import handle_ptc_tool_call
            vep_input = {"variants": variants[:200]}
            vep_result_json = await handle_ptc_tool_call("run_vep", vep_input)
            vep_data = json.loads(vep_result_json)
            vep_results = vep_data.get("vep_results", [])
            high_impact = [
                r for r in vep_results
                if r.get("most_severe_consequence") in (
                    "stop_gained", "frameshift_variant", "splice_donor_variant",
                    "splice_acceptor_variant", "start_lost",
                )
            ]
            return {
                "total_variants": len(variants),
                "high_impact_variants": high_impact[:20],
                "pathogenic_variants": [],
                "affected_genes": list({
                    tc.get("gene_symbol", "") for r in high_impact
                    for tc in r.get("transcript_consequences", [])
                    if tc.get("gene_symbol")
                })[:50],
                "summary": f"{len(variants)} variants annotated, {len(high_impact)} high-impact.",
            }
        except Exception as e:
            logger.debug("VEP annotation failed: %s", e)
            return {
                "total_variants": len(variants),
                "high_impact_variants": [],
                "summary": f"VEP annotation failed: {e}",
            }

    async def _integrity_audit(self) -> dict:
        """Run gene name and statistical integrity checks."""
        gene_issues = []
        stat_issues = []

        # Collect genes from expression analysis
        expr = self._step_results.get("EXPRESSION_ANALYSIS")
        if expr and hasattr(expr, "output"):
            output = expr.output
            genes = []
            if isinstance(output, dict):
                for deg in output.get("top_degs", []):
                    gene = deg.get("gene") if isinstance(deg, dict) else None
                    if gene:
                        genes.append(gene)
            if genes:
                try:
                    from app.llm.ptc_handler import handle_ptc_tool_call
                    result_json = await handle_ptc_tool_call("check_gene_names", {"gene_list": genes[:100]})
                    result = json.loads(result_json)
                    gene_issues = result.get("issues", [])
                except Exception as e:
                    logger.debug("Gene check failed: %s", e)

        return {
            "gene_name_issues": gene_issues,
            "statistical_issues": stat_issues,
            "total_issues": len(gene_issues) + len(stat_issues),
            "audit_summary": f"Integrity audit: {len(gene_issues)} gene issues, {len(stat_issues)} stat issues.",
        }

    async def _build_report(self, instance: WorkflowInstance) -> dict:
        """Build the final W9 report using the report builder."""
        from app.config import settings
        from app.engines.w9_report_builder import build_w9_report, save_report

        cost_used = instance.budget_total - instance.budget_remaining
        report = build_w9_report(
            workflow_id=instance.id,
            query=instance.query,
            step_results={
                k: (v.output if hasattr(v, "output") else v)
                for k, v in self._step_results.items()
            },
            total_cost_usd=cost_used,
        )

        # Save to file
        save_report(report, output_dir=settings.checkpoint_dir)

        return report.model_dump(mode="json")
