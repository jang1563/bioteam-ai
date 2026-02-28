"""W4 Manuscript Writing Runner — 9-step pipeline for manuscript preparation.

Steps:
  OUTLINE -> ASSEMBLE -> DRAFT -> FIGURES -> STATISTICAL_REVIEW
    RD(synth)   KM        T08      T08       StatQA
  -> PLAUSIBILITY_REVIEW -> REPRODUCIBILITY_CHECK -> REVISION -> REPORT
       BioQA                  ReproQA                RD(synth)   code_only

OUTLINE has a human checkpoint for Director review of the manuscript plan.
Code-only step: REPORT (assembles final manuscript package).
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

W4_STEPS: list[WorkflowStepDef] = [
    WorkflowStepDef(
        id="OUTLINE",
        agent_id="research_director",
        output_schema="SynthesisReport",
        next_step="ASSEMBLE",
        is_human_checkpoint=True,
        estimated_cost=_estimate_step_cost("opus", est_input_tokens=4000, est_output_tokens=3000),
    ),
    WorkflowStepDef(
        id="ASSEMBLE",
        agent_id="knowledge_manager",
        output_schema="LiteratureSearchResult",
        next_step="DRAFT",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=2000, est_output_tokens=1000),
    ),
    WorkflowStepDef(
        id="DRAFT",
        agent_id="t08_scicomm",
        output_schema="ManuscriptDraft",
        next_step="FIGURES",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=6000, est_output_tokens=4000),
    ),
    WorkflowStepDef(
        id="FIGURES",
        agent_id="t08_scicomm",
        output_schema="FigureDescriptions",
        next_step="STATISTICAL_REVIEW",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=3000, est_output_tokens=2000),
    ),
    WorkflowStepDef(
        id="STATISTICAL_REVIEW",
        agent_id="statistical_rigor_qa",
        output_schema="QAReviewResult",
        next_step="PLAUSIBILITY_REVIEW",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=4000, est_output_tokens=1000),
    ),
    WorkflowStepDef(
        id="PLAUSIBILITY_REVIEW",
        agent_id="biological_plausibility_qa",
        output_schema="QAReviewResult",
        next_step="REPRODUCIBILITY_CHECK",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=4000, est_output_tokens=1000),
    ),
    WorkflowStepDef(
        id="REPRODUCIBILITY_CHECK",
        agent_id="reproducibility_qa",
        output_schema="QAReviewResult",
        next_step="REVISION",
        estimated_cost=_estimate_step_cost("haiku", est_input_tokens=2000, est_output_tokens=500),
    ),
    WorkflowStepDef(
        id="REVISION",
        agent_id="research_director",
        output_schema="SynthesisReport",
        next_step="REPORT",
        estimated_cost=_estimate_step_cost("opus", est_input_tokens=8000, est_output_tokens=4000),
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
    "OUTLINE": ("research_director", "synthesize"),
    "ASSEMBLE": ("knowledge_manager", "run"),
    "DRAFT": ("t08_scicomm", "run"),
    "FIGURES": ("t08_scicomm", "run"),
    "STATISTICAL_REVIEW": ("statistical_rigor_qa", "run"),
    "PLAUSIBILITY_REVIEW": ("biological_plausibility_qa", "run"),
    "REPRODUCIBILITY_CHECK": ("reproducibility_qa", "run"),
    "REVISION": ("research_director", "synthesize"),
}


def get_step_by_id(step_id: str) -> WorkflowStepDef | None:
    """Get a step definition by ID."""
    for step in W4_STEPS:
        if step.id == step_id:
            return step
    return None


class W4ManuscriptRunner:
    """Orchestrates the W4 Manuscript Writing pipeline.

    Manages the 9-step pipeline, routing calls to the correct
    agent method, handling code-only steps, and managing human checkpoints.

    Usage:
        runner = W4ManuscriptRunner(
            registry=registry,
            engine=WorkflowEngine(),
            sse_hub=sse_hub,
        )
        result = await runner.run(query="Draft manuscript on spaceflight-induced anemia mechanisms")
    """

    def __init__(
        self,
        registry: AgentRegistry,
        engine: WorkflowEngine | None = None,
        sse_hub: SSEHub | None = None,
        lab_kb=None,
        persist_fn=None,  # async callable(WorkflowInstance) -> None
        checkpoint_manager=None,  # CheckpointManager — optional, for step persistence
    ) -> None:
        self.registry = registry
        self.engine = engine or WorkflowEngine()
        self.sse_hub = sse_hub
        self.lab_kb = lab_kb
        self._persist_fn = persist_fn
        self._checkpoint_manager = checkpoint_manager
        # Store step results for inter-step data flow
        self._step_results: dict[str, AgentOutput] = {}

    async def _persist(self, instance: WorkflowInstance) -> None:
        """Persist workflow state to storage (if callback provided)."""
        if self._persist_fn:
            await self._persist_fn(instance)

    @observe(name="workflow.w4_manuscript_writing")
    async def run(
        self,
        query: str,
        instance: WorkflowInstance | None = None,
        budget: float = 25.0,
    ) -> dict[str, Any]:
        """Execute the full W4 pipeline.

        Returns a dict with all step results and the final report.
        Pauses at OUTLINE for human checkpoint.
        """
        if instance is None:
            instance = WorkflowInstance(
                template="W4",
                budget_total=budget,
                budget_remaining=budget,
            )

        self.engine.start(instance, first_step="OUTLINE")
        await self._persist(instance)
        self._step_results = {}

        # Run steps sequentially
        for step in W4_STEPS:
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

                # Human checkpoint at OUTLINE
                if step.is_human_checkpoint:
                    self.engine.request_human(instance)
                    await self._persist(instance)
                    logger.info("W4 paused at %s for human review", step.id)
                    break

        return {
            "instance": instance,
            "step_results": {
                k: v.model_dump(mode="json") if hasattr(v, "model_dump") else v
                for k, v in self._step_results.items()
            },
            "paused_at": instance.current_step if instance.state == "WAITING_HUMAN" else None,
        }

    @observe(name="workflow.w4_manuscript_writing.resume")
    async def resume_after_human(
        self,
        instance: WorkflowInstance,
        query: str,
    ) -> dict[str, Any]:
        """Resume after human approval at OUTLINE checkpoint.

        Continues from ASSEMBLE through REPORT.
        Note: Caller is responsible for transitioning state to RUNNING first.
        """
        # Ensure we're in RUNNING state (caller should have done this)
        if instance.state != "RUNNING":
            self.engine.resume(instance)

        # Run remaining steps after human checkpoint
        remaining_ids = (
            "ASSEMBLE", "DRAFT", "FIGURES",
            "STATISTICAL_REVIEW", "PLAUSIBILITY_REVIEW", "REPRODUCIBILITY_CHECK",
            "REVISION", "REPORT",
        )
        remaining_steps = [s for s in W4_STEPS if s.id in remaining_ids]

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
                    if self.sse_hub:
                        await self.sse_hub.broadcast_dict(
                            event_type="workflow.failed",
                            workflow_id=instance.id,
                            step_id=step.id,
                            payload={"error": result.error or "Agent step failed"},
                        )
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

        # Store results on session manifest before completing
        self._store_manuscript_results(instance)

        # Mark completed if all steps done
        if instance.state == "RUNNING":
            self.engine.complete(instance)
            await self._persist(instance)

        return {
            "instance": instance,
            "step_results": {
                k: v.model_dump(mode="json") if hasattr(v, "model_dump") else v
                for k, v in self._step_results.items()
            },
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

        context = ContextPackage(
            task_description=query,
            prior_step_outputs=prior_outputs,
            constraints={"workflow_id": instance.id, "workflow_template": "W4"},
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

        # Apply iterative refinement at REVISION step
        if step.id == "REVISION" and result.is_success:
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
            "W4 refinement: %d iterations, score %.2f→%.2f, cost $%.4f, stopped: %s",
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

    def _store_manuscript_results(self, instance: WorkflowInstance) -> None:
        """Store manuscript results on the workflow instance session_manifest."""
        instance.session_manifest = instance.session_manifest or {}

        # Store review feedback summaries
        reviews = {}
        for review_step in ("STATISTICAL_REVIEW", "PLAUSIBILITY_REVIEW", "REPRODUCIBILITY_CHECK"):
            result = self._step_results.get(review_step)
            if result and hasattr(result, "output") and isinstance(result.output, dict):
                reviews[review_step] = {
                    "summary": result.summary or "",
                    "output": result.output,
                }
            elif result and result.summary:
                reviews[review_step] = {"summary": result.summary}

        instance.session_manifest["reviews"] = reviews
        instance.session_manifest["workflow_template"] = "W4"

    def _generate_report(self, query: str, instance: WorkflowInstance) -> AgentOutput:
        """Assemble the final W4 manuscript report from all step results."""
        outline_result = self._step_results.get("OUTLINE")
        assemble_result = self._step_results.get("ASSEMBLE")
        draft_result = self._step_results.get("DRAFT")
        figures_result = self._step_results.get("FIGURES")
        stat_review_result = self._step_results.get("STATISTICAL_REVIEW")
        plaus_review_result = self._step_results.get("PLAUSIBILITY_REVIEW")
        repro_check_result = self._step_results.get("REPRODUCIBILITY_CHECK")
        revision_result = self._step_results.get("REVISION")

        # Extract data from each step
        def _extract_output(result: AgentOutput | None) -> dict:
            if result and hasattr(result, "output") and isinstance(result.output, dict):
                return result.output
            return {}

        def _extract_summary(result: AgentOutput | None) -> str:
            if result and result.summary:
                return result.summary
            return ""

        outline_data = _extract_output(outline_result)
        assemble_data = _extract_output(assemble_result)
        draft_data = _extract_output(draft_result)
        figures_data = _extract_output(figures_result)
        stat_review_data = _extract_output(stat_review_result)
        plaus_review_data = _extract_output(plaus_review_result)
        repro_check_data = _extract_output(repro_check_result)
        revision_data = _extract_output(revision_result)

        report = {
            "step": "REPORT",
            "query": query,
            "workflow_id": instance.id,
            "outline": outline_data,
            "references_assembled": assemble_data,
            "manuscript_draft": draft_data,
            "figure_descriptions": figures_data,
            "reviews": {
                "statistical_rigor": stat_review_data,
                "biological_plausibility": plaus_review_data,
                "reproducibility": repro_check_data,
            },
            "review_summaries": {
                "statistical_rigor": _extract_summary(stat_review_result),
                "biological_plausibility": _extract_summary(plaus_review_result),
                "reproducibility": _extract_summary(repro_check_result),
            },
            "revision": revision_data,
            "revision_summary": _extract_summary(revision_result),
            "budget_used": instance.budget_total - instance.budget_remaining,
        }

        # Store on session manifest
        instance.session_manifest = instance.session_manifest or {}
        instance.session_manifest["manuscript_report"] = report

        return AgentOutput(
            agent_id="code_only",
            output=report,
            output_type="ManuscriptReport",
            summary=(
                f"W4 manuscript complete: outline, draft, figures, "
                f"3 reviews, revision assembled. "
                f"Budget used: ${report['budget_used']:.2f}"
            ),
        )
