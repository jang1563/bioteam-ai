"""W3 Data Analysis Runner — 11-step pipeline for comprehensive data analysis.

Steps:
  INGEST → QC → PLAN → EXECUTE → INTEGRATE → VALIDATE
    KM     T04   RD(Opus)  T04    IntBio     StatRigQA
  → [HUMAN CHECKPOINT at PLAN]
  → PLAUSIBILITY → INTERPRET → CONTRADICTION_CHECK → AUDIT → REPORT
      BioPlausQA    RD(Opus)        AE               ReproQA  code_only

Code-only steps: REPORT.
PLAN has a human checkpoint for Director review.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.base import observe
from app.agents.registry import AgentRegistry
from app.api.v1.sse import SSEHub
from app.config import settings
from app.cost.tracker import COST_PER_1K_INPUT, COST_PER_1K_OUTPUT
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from app.models.workflow import WorkflowInstance, WorkflowStepDef
from app.workflows.engine import WorkflowEngine

logger = logging.getLogger(__name__)


def _estimate_step_cost(model_tier: str, est_input_tokens: int, est_output_tokens: int) -> float:
    """Estimate step cost from model tier and expected token counts."""
    input_rate = COST_PER_1K_INPUT.get(model_tier, 0.0)
    output_rate = COST_PER_1K_OUTPUT.get(model_tier, 0.0)
    return (est_input_tokens / 1000) * input_rate + (est_output_tokens / 1000) * output_rate


# === Step Definitions ===

W3_STEPS: list[WorkflowStepDef] = [
    WorkflowStepDef(
        id="INGEST",
        agent_id="knowledge_manager",
        output_schema="DataIngestionResult",
        next_step="QC",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=200, est_output_tokens=100),
    ),
    WorkflowStepDef(
        id="QC",
        agent_id="t04_biostatistics",
        output_schema="QualityControlResult",
        next_step="PLAN",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=2000, est_output_tokens=1000),
    ),
    WorkflowStepDef(
        id="PLAN",
        agent_id="research_director",
        output_schema="SynthesisReport",
        next_step="EXECUTE",
        is_human_checkpoint=True,
        estimated_cost=_estimate_step_cost("opus", est_input_tokens=6000, est_output_tokens=2000),
    ),
    WorkflowStepDef(
        id="EXECUTE",
        agent_id="t04_biostatistics",
        output_schema="AnalysisResult",
        next_step="INTEGRATE",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=3000, est_output_tokens=1500),
    ),
    WorkflowStepDef(
        id="INTEGRATE",
        agent_id="integrative_biologist",
        output_schema="IntegrationResult",
        next_step="VALIDATE",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=2000, est_output_tokens=1000),
    ),
    WorkflowStepDef(
        id="VALIDATE",
        agent_id="statistical_rigor_qa",
        output_schema="ValidationResult",
        next_step="PLAUSIBILITY",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=2000, est_output_tokens=1000),
    ),
    WorkflowStepDef(
        id="PLAUSIBILITY",
        agent_id="biological_plausibility_qa",
        output_schema="PlausibilityResult",
        next_step="INTERPRET",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=2000, est_output_tokens=1000),
    ),
    WorkflowStepDef(
        id="INTERPRET",
        agent_id="research_director",
        output_schema="SynthesisReport",
        next_step="CONTRADICTION_CHECK",
        estimated_cost=_estimate_step_cost("opus", est_input_tokens=8000, est_output_tokens=3000),
    ),
    WorkflowStepDef(
        id="CONTRADICTION_CHECK",
        agent_id="ambiguity_engine",
        output_schema="ContradictionAnalysis",
        next_step="AUDIT",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=3000, est_output_tokens=1000),
    ),
    WorkflowStepDef(
        id="AUDIT",
        agent_id="reproducibility_qa",
        output_schema="ReproducibilityAudit",
        next_step="REPORT",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=200, est_output_tokens=100),
    ),
    WorkflowStepDef(
        id="REPORT",
        agent_id="code_only",
        output_schema="dict",
        next_step=None,
        estimated_cost=0.0,
    ),
]

# Method routing: step_id -> (agent_id, method_name)
_METHOD_MAP: dict[str, tuple[str, str]] = {
    "INGEST": ("knowledge_manager", "run"),
    "QC": ("t04_biostatistics", "run"),
    "PLAN": ("research_director", "synthesize"),
    "EXECUTE": ("t04_biostatistics", "run"),
    "INTEGRATE": ("integrative_biologist", "run"),
    "VALIDATE": ("statistical_rigor_qa", "run"),
    "PLAUSIBILITY": ("biological_plausibility_qa", "run"),
    "INTERPRET": ("research_director", "synthesize"),
    "CONTRADICTION_CHECK": ("ambiguity_engine", "detect_contradictions"),
    "AUDIT": ("reproducibility_qa", "run"),
}


def get_step_by_id(step_id: str) -> WorkflowStepDef | None:
    """Get a step definition by ID."""
    for step in W3_STEPS:
        if step.id == step_id:
            return step
    return None


class W3DataAnalysisRunner:
    """Orchestrates the W3 Data Analysis pipeline.

    Manages the 11-step pipeline, routing calls to the correct
    agent method, handling code-only steps, and managing human checkpoints.

    Usage:
        runner = W3DataAnalysisRunner(
            registry=registry,
            engine=WorkflowEngine(),
            sse_hub=sse_hub,
        )
        result = await runner.run(query="Analyze RNA-seq data from spaceflight samples")
    """

    def __init__(
        self,
        registry: AgentRegistry,
        engine: WorkflowEngine | None = None,
        sse_hub: SSEHub | None = None,
        lab_kb=None,  # LabKBEngine — optional
        persist_fn=None,  # async callable(WorkflowInstance) -> None
    ) -> None:
        self.registry = registry
        self.engine = engine or WorkflowEngine()
        self.sse_hub = sse_hub
        self.lab_kb = lab_kb
        self._persist_fn = persist_fn
        # Store step results for inter-step data flow
        self._step_results: dict[str, AgentOutput] = {}

    async def _persist(self, instance: WorkflowInstance) -> None:
        """Persist workflow state to storage (if callback provided)."""
        if self._persist_fn:
            await self._persist_fn(instance)

    @observe(name="workflow.w3_data_analysis")
    async def run(
        self,
        query: str,
        instance: WorkflowInstance | None = None,
        budget: float = 10.0,
    ) -> dict[str, Any]:
        """Execute the full W3 pipeline.

        Returns a dict with all step results and the final report.
        Pauses at PLAN for human checkpoint.
        """
        if instance is None:
            instance = WorkflowInstance(
                template="W3",
                budget_total=budget,
                budget_remaining=budget,
            )

        self.engine.start(instance, first_step="INGEST")
        await self._persist(instance)
        self._step_results = {}

        # Run steps sequentially up to PLAN checkpoint
        for step in W3_STEPS:
            if instance.state not in ("RUNNING",):
                break

            # Broadcast step start
            if self.sse_hub:
                await self.sse_hub.broadcast_dict(
                    event_type="workflow.step_started",
                    workflow_id=instance.id,
                    step_id=step.id,
                    agent_id=step.agent_id,
                    payload={"step": step.id},
                )

            if step.id == "REPORT":
                # Code-only step
                result = await self._run_code_step(step, query, instance)
                self._step_results[step.id] = result
                self.engine.advance(instance, step.id, step_result={"type": "code_only"})
                await self._persist(instance)
            elif step.id in _METHOD_MAP:
                # Agent steps — call specific method
                result = await self._run_agent_step(step, query, instance)
                self._step_results[step.id] = result

                if not result.is_success:
                    self.engine.fail(instance, result.error or "Agent step failed")
                    await self._persist(instance)
                    if self.sse_hub:
                        await self.sse_hub.broadcast_dict(
                            event_type="workflow.failed",
                            workflow_id=instance.id,
                            step_id=step.id,
                            payload={"error": result.error or "Agent step failed"},
                        )
                    break

                # Record cost
                if result.cost > 0:
                    self.engine.deduct_budget(instance, result.cost)

                self.engine.advance(instance, step.id)
                await self._persist(instance)

                # Broadcast step completion
                if self.sse_hub:
                    await self.sse_hub.broadcast_dict(
                        event_type="workflow.step_completed",
                        workflow_id=instance.id,
                        step_id=step.id,
                        agent_id=step.agent_id,
                        payload={
                            "step": step.id,
                            "cost": result.cost,
                            "summary": result.summary[:200] if result.summary else "",
                        },
                    )

                # Human checkpoint at PLAN
                if step.is_human_checkpoint:
                    self.engine.request_human(instance)
                    await self._persist(instance)
                    logger.info("W3 paused at %s for human review", step.id)
                    break

        return {
            "instance": instance,
            "step_results": {k: v.model_dump(mode="json") if hasattr(v, "model_dump") else v
                             for k, v in self._step_results.items()},
            "paused_at": instance.current_step if instance.state == "WAITING_HUMAN" else None,
        }

    @observe(name="workflow.w3_data_analysis.resume")
    async def resume_after_human(
        self,
        instance: WorkflowInstance,
        query: str,
    ) -> dict[str, Any]:
        """Resume after human approval at PLAN checkpoint.

        Continues from EXECUTE through REPORT.
        Note: Caller is responsible for transitioning state to RUNNING first.
        """
        # Ensure we're in RUNNING state (caller should have done this)
        if instance.state != "RUNNING":
            self.engine.resume(instance)

        # Run remaining steps after human checkpoint
        remaining_ids = (
            "EXECUTE", "INTEGRATE", "VALIDATE", "PLAUSIBILITY",
            "INTERPRET", "CONTRADICTION_CHECK", "AUDIT", "REPORT",
        )
        remaining_steps = [s for s in W3_STEPS if s.id in remaining_ids]

        for step in remaining_steps:
            if instance.state not in ("RUNNING",):
                break

            if self.sse_hub:
                await self.sse_hub.broadcast_dict(
                    event_type="workflow.step_started",
                    workflow_id=instance.id,
                    step_id=step.id,
                    agent_id=step.agent_id,
                )

            if step.id == "REPORT":
                result = await self._run_code_step(step, query, instance)
                self._step_results[step.id] = result
                self.engine.advance(instance, step.id, step_result={"type": "code_only"})
                await self._persist(instance)
            else:
                result = await self._run_agent_step(step, query, instance)
                self._step_results[step.id] = result
                if not result.is_success:
                    self.engine.fail(instance, result.error or "Agent step failed")
                    await self._persist(instance)
                    break
                if result.cost > 0:
                    self.engine.deduct_budget(instance, result.cost)
                self.engine.advance(instance, step.id)
                await self._persist(instance)

            if self.sse_hub:
                await self.sse_hub.broadcast_dict(
                    event_type="workflow.step_completed",
                    workflow_id=instance.id,
                    step_id=step.id,
                    agent_id=step.agent_id,
                )

        # Mark completed if all steps done
        if instance.state == "RUNNING":
            self.engine.complete(instance)
            await self._persist(instance)

        return {
            "instance": instance,
            "step_results": {k: v.model_dump(mode="json") if hasattr(v, "model_dump") else v
                             for k, v in self._step_results.items()},
            "completed": instance.state == "COMPLETED",
        }

    async def _run_agent_step(
        self,
        step: WorkflowStepDef,
        query: str,
        instance: WorkflowInstance,
    ) -> AgentOutput:
        """Run an agent step using the method routing map."""
        agent_id, method_name = _METHOD_MAP[step.id]
        agent = self.registry.get(agent_id)

        if agent is None:
            return AgentOutput(
                agent_id=agent_id,
                error=f"Agent {agent_id} not found in registry",
            )

        # Build context with prior step outputs
        prior_outputs = []
        for sid, result in self._step_results.items():
            if hasattr(result, "model_dump"):
                prior_outputs.append(result.model_dump())
            elif isinstance(result, dict):
                prior_outputs.append(result)

        # Extract negative results if available from prior steps
        negative_results: list[dict] = []

        context = ContextPackage(
            task_description=query,
            prior_step_outputs=prior_outputs,
            negative_results=negative_results,
            constraints={"workflow_id": instance.id},
        )

        # Apply pending director notes to context
        from app.workflows.note_processor import NoteProcessor
        pending = NoteProcessor.get_pending_notes(instance, step.id)
        if pending:
            context = NoteProcessor.apply_to_context(pending, context, self._step_results)
            NoteProcessor.mark_processed(instance, [n["_index"] for n in pending])
            await self._persist(instance)

        # Call the specific method on the agent
        method = getattr(agent, method_name, None)
        if method is None:
            return AgentOutput(
                agent_id=agent_id,
                error=f"Agent {agent_id} has no method {method_name}",
            )

        result = await method(context)

        # Apply iterative refinement at INTERPRET step
        if step.id == "INTERPRET" and result.is_success:
            result, refine_cost = await self._maybe_refine(
                agent, context, result, instance,
            )

        return result

    async def _maybe_refine(
        self,
        agent,
        context: ContextPackage,
        output: AgentOutput,
        instance: WorkflowInstance,
    ) -> tuple[AgentOutput, float]:
        """Apply iterative refinement if enabled. Returns (output, extra_cost)."""
        if not settings.refinement_enabled:
            return output, 0.0

        llm = agent.llm if hasattr(agent, "llm") else None
        if llm is None:
            return output, 0.0

        from app.workflows.refinement import RefinementLoop, config_from_settings

        loop = RefinementLoop(llm=llm, config=config_from_settings())
        refined_output, result_meta = await loop.refine(
            agent=agent, context=context, initial_output=output,
        )
        if result_meta.total_cost > 0:
            self.engine.deduct_budget(instance, result_meta.total_cost)
        logger.info(
            "W3 refinement: %d iterations, score %.2f→%.2f, cost $%.4f, stopped: %s",
            result_meta.iterations_used,
            result_meta.quality_scores[0] if result_meta.quality_scores else 0,
            result_meta.quality_scores[-1] if result_meta.quality_scores else 0,
            result_meta.total_cost,
            result_meta.stopped_reason,
        )
        return refined_output, result_meta.total_cost

    async def _run_code_step(
        self,
        step: WorkflowStepDef,
        query: str,
        instance: WorkflowInstance,
    ) -> AgentOutput:
        """Run a code-only step."""
        if step.id == "REPORT":
            return self._generate_report(query, instance)
        return AgentOutput(agent_id="code_only", error=f"Unknown code step: {step.id}")

    def _generate_report(self, query: str, instance: WorkflowInstance) -> AgentOutput:
        """Assemble final W3 analysis report with interpretation, validation, and audit."""
        # Gather results from each step
        ingest_result = self._step_results.get("INGEST")
        qc_result = self._step_results.get("QC")
        plan_result = self._step_results.get("PLAN")
        execute_result = self._step_results.get("EXECUTE")
        integrate_result = self._step_results.get("INTEGRATE")
        validate_result = self._step_results.get("VALIDATE")
        plausibility_result = self._step_results.get("PLAUSIBILITY")
        interpret_result = self._step_results.get("INTERPRET")
        contradiction_result = self._step_results.get("CONTRADICTION_CHECK")
        audit_result = self._step_results.get("AUDIT")

        def _extract_output(result: AgentOutput | None) -> dict:
            """Safely extract output dict from an AgentOutput."""
            if result and hasattr(result, "output") and isinstance(result.output, dict):
                return result.output
            return {}

        def _extract_summary(result: AgentOutput | None) -> str:
            """Safely extract summary from an AgentOutput."""
            if result and hasattr(result, "summary") and result.summary:
                return result.summary
            return ""

        # Build comprehensive report
        report = {
            "step": "REPORT",
            "query": query,
            "workflow_id": instance.id,
            # Data ingestion and quality
            "data_ingestion": _extract_output(ingest_result),
            "quality_control": _extract_output(qc_result),
            "qc_summary": _extract_summary(qc_result),
            # Analysis plan (Director-approved)
            "analysis_plan": _extract_output(plan_result),
            # Execution results
            "analysis_results": _extract_output(execute_result),
            # Multi-omics integration
            "integration": _extract_output(integrate_result),
            # Validation layers
            "statistical_validation": _extract_output(validate_result),
            "biological_plausibility": _extract_output(plausibility_result),
            # Interpretation
            "interpretation": _extract_output(interpret_result),
            "interpretation_summary": _extract_summary(interpret_result),
            # Contradiction check vs literature
            "contradiction_check": _extract_output(contradiction_result),
            # Reproducibility audit
            "reproducibility_audit": _extract_output(audit_result),
            "audit_summary": _extract_summary(audit_result),
            # Budget
            "budget_used": instance.budget_total - instance.budget_remaining,
        }

        # Store on session manifest
        instance.session_manifest = instance.session_manifest or {}
        instance.session_manifest["analysis_report"] = report

        return AgentOutput(
            agent_id="code_only",
            output=report,
            output_type="DataAnalysisReport",
            summary=(
                f"W3 complete: analysis of '{query[:60]}' with "
                f"validation={bool(_extract_output(validate_result))}, "
                f"plausibility={bool(_extract_output(plausibility_result))}, "
                f"audit={bool(_extract_output(audit_result))}"
            ),
        )
