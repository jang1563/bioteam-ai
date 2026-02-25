"""W5 Grant Proposal Runner — 8-step pipeline for grant proposal preparation.

Steps:
  OPPORTUNITY -> SPECIFIC_AIMS -> STRATEGY -> PRELIMINARY_DATA
      T09         RD(synth)        T09           KM
  -> BUDGET_PLAN -> MOCK_REVIEW -> REVISION -> REPORT
       PM           parallel(3QA)   RD(synth)   code_only

SPECIFIC_AIMS has a human checkpoint for Director review of aims.
MOCK_REVIEW runs 3 QA agents in parallel.
Code-only step: REPORT (assembles final proposal package).
"""

from __future__ import annotations

import asyncio
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

W5_STEPS: list[WorkflowStepDef] = [
    WorkflowStepDef(
        id="OPPORTUNITY",
        agent_id="t09_grants",
        output_schema="GrantAnalysis",
        next_step="SPECIFIC_AIMS",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=6000, est_output_tokens=4000),
    ),
    WorkflowStepDef(
        id="SPECIFIC_AIMS",
        agent_id="research_director",
        output_schema="SynthesisReport",
        next_step="STRATEGY",
        is_human_checkpoint=True,
        estimated_cost=_estimate_step_cost("opus", est_input_tokens=4000, est_output_tokens=3000),
    ),
    WorkflowStepDef(
        id="STRATEGY",
        agent_id="t09_grants",
        output_schema="GrantStrategy",
        next_step="PRELIMINARY_DATA",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=5000, est_output_tokens=3000),
    ),
    WorkflowStepDef(
        id="PRELIMINARY_DATA",
        agent_id="knowledge_manager",
        output_schema="LiteratureSearchResult",
        next_step="BUDGET_PLAN",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=4000, est_output_tokens=2000),
    ),
    WorkflowStepDef(
        id="BUDGET_PLAN",
        agent_id="project_manager",
        output_schema="ProjectStatus",
        next_step="MOCK_REVIEW",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=4000, est_output_tokens=2000),
    ),
    WorkflowStepDef(
        id="MOCK_REVIEW",
        agent_id=["statistical_rigor_qa", "biological_plausibility_qa", "reproducibility_qa"],
        output_schema="QAReviewResult",
        next_step="REVISION",
        is_parallel=True,
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=4000, est_output_tokens=1000),
    ),
    WorkflowStepDef(
        id="REVISION",
        agent_id="research_director",
        output_schema="SynthesisReport",
        next_step="REPORT",
        estimated_cost=_estimate_step_cost("opus", est_input_tokens=6000, est_output_tokens=3000),
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
# For MOCK_REVIEW, routing is handled specially via parallel execution
_METHOD_MAP: dict[str, tuple[str, str]] = {
    "OPPORTUNITY": ("t09_grants", "run"),
    "SPECIFIC_AIMS": ("research_director", "synthesize"),
    "STRATEGY": ("t09_grants", "run"),
    "PRELIMINARY_DATA": ("knowledge_manager", "run"),
    "BUDGET_PLAN": ("project_manager", "run"),
    "REVISION": ("research_director", "synthesize"),
}

# Parallel step: agent_ids for MOCK_REVIEW
_MOCK_REVIEW_AGENTS: list[str] = [
    "statistical_rigor_qa",
    "biological_plausibility_qa",
    "reproducibility_qa",
]


def get_step_by_id(step_id: str) -> WorkflowStepDef | None:
    """Get a step definition by ID."""
    for step in W5_STEPS:
        if step.id == step_id:
            return step
    return None


class W5GrantProposalRunner:
    """Orchestrates the W5 Grant Proposal pipeline.

    Manages the 8-step pipeline, routing calls to the correct
    agent method, handling code-only steps, parallel execution,
    and managing human checkpoints.

    Usage:
        runner = W5GrantProposalRunner(
            registry=registry,
            engine=WorkflowEngine(),
            sse_hub=sse_hub,
        )
        result = await runner.run(query="NIH R01 proposal for spaceflight anemia mechanisms")
    """

    def __init__(
        self,
        registry: AgentRegistry,
        engine: WorkflowEngine | None = None,
        sse_hub: SSEHub | None = None,
        lab_kb=None,
        persist_fn=None,  # async callable(WorkflowInstance) -> None
    ) -> None:
        self.registry = registry
        self.engine = engine or WorkflowEngine()
        self.sse_hub = sse_hub
        self.lab_kb = lab_kb
        self._persist_fn = persist_fn
        # Store step results for inter-step data flow
        self._step_results: dict[str, AgentOutput | list[AgentOutput]] = {}

    async def _persist(self, instance: WorkflowInstance) -> None:
        """Persist workflow state to storage (if callback provided)."""
        if self._persist_fn:
            await self._persist_fn(instance)

    @observe(name="workflow.w5_grant_proposal")
    async def run(
        self,
        query: str,
        instance: WorkflowInstance | None = None,
        budget: float = 30.0,
    ) -> dict[str, Any]:
        """Execute the full W5 pipeline.

        Returns a dict with all step results and the final report.
        Pauses at SPECIFIC_AIMS for human checkpoint.
        """
        if instance is None:
            instance = WorkflowInstance(
                template="W5",
                budget_total=budget,
                budget_remaining=budget,
            )

        self.engine.start(instance, first_step="OPPORTUNITY")
        await self._persist(instance)
        self._step_results = {}

        # Run steps sequentially
        for step in W5_STEPS:
            if instance.state not in ("RUNNING",):
                break

            # Broadcast step start
            if self.sse_hub:
                await self.sse_hub.broadcast_dict(
                    event_type="workflow.step_started",
                    workflow_id=instance.id,
                    step_id=step.id,
                    agent_id=step.agent_id if isinstance(step.agent_id, str) else ",".join(step.agent_id),
                    payload={"step": step.id},
                )

            if step.id == "REPORT":
                # Code-only step
                result = await self._run_code_step(step, query, instance)
                self._step_results[step.id] = result
                self.engine.advance(instance, step.id, step_result={"type": "code_only"})
                await self._persist(instance)
            elif step.id == "MOCK_REVIEW":
                # Parallel step — run 3 QA agents concurrently
                results = await self._run_parallel_step(step, query, instance)
                self._step_results[step.id] = results

                # Check if any parallel agent failed
                failed = [r for r in results if isinstance(r, AgentOutput) and not r.is_success]
                if failed:
                    error_msg = "; ".join(r.error or "Unknown error" for r in failed)
                    self.engine.fail(instance, f"Mock review failed: {error_msg}")
                    await self._persist(instance)
                    if self.sse_hub:
                        await self.sse_hub.broadcast_dict(
                            event_type="workflow.failed",
                            workflow_id=instance.id,
                            step_id=step.id,
                            payload={"error": error_msg},
                        )
                    break

                # Deduct total cost from all parallel agents
                total_cost = sum(
                    r.cost for r in results
                    if isinstance(r, AgentOutput) and r.cost > 0
                )
                if total_cost > 0:
                    self.engine.deduct_budget(instance, total_cost)

                self.engine.advance(instance, step.id)
                await self._persist(instance)

                # Broadcast step completion
                if self.sse_hub:
                    await self.sse_hub.broadcast_dict(
                        event_type="workflow.step_completed",
                        workflow_id=instance.id,
                        step_id=step.id,
                        agent_id=",".join(_MOCK_REVIEW_AGENTS),
                        payload={
                            "step": step.id,
                            "cost": total_cost,
                            "summary": f"Mock review completed by {len(results)} QA agents",
                        },
                    )
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
                        agent_id=step.agent_id if isinstance(step.agent_id, str) else step.agent_id[0],
                        payload={
                            "step": step.id,
                            "cost": result.cost,
                            "summary": result.summary[:200] if result.summary else "",
                        },
                    )

                # Human checkpoint at SPECIFIC_AIMS
                if step.is_human_checkpoint:
                    self.engine.request_human(instance)
                    await self._persist(instance)
                    logger.info("W5 paused at %s for human review", step.id)
                    break

        return {
            "instance": instance,
            "step_results": self._serialize_step_results(),
            "paused_at": instance.current_step if instance.state == "WAITING_HUMAN" else None,
        }

    @observe(name="workflow.w5_grant_proposal.resume")
    async def resume_after_human(
        self,
        instance: WorkflowInstance,
        query: str,
    ) -> dict[str, Any]:
        """Resume after human approval at SPECIFIC_AIMS checkpoint.

        Continues from STRATEGY through REPORT.
        Note: Caller is responsible for transitioning state to RUNNING first.
        """
        # Ensure we're in RUNNING state (caller should have done this)
        if instance.state != "RUNNING":
            self.engine.resume(instance)

        # Run remaining steps after human checkpoint
        remaining_ids = (
            "STRATEGY", "PRELIMINARY_DATA", "BUDGET_PLAN",
            "MOCK_REVIEW", "REVISION", "REPORT",
        )
        remaining_steps = [s for s in W5_STEPS if s.id in remaining_ids]

        for step in remaining_steps:
            if instance.state not in ("RUNNING",):
                break

            if self.sse_hub:
                await self.sse_hub.broadcast_dict(
                    event_type="workflow.step_started",
                    workflow_id=instance.id,
                    step_id=step.id,
                    agent_id=step.agent_id if isinstance(step.agent_id, str) else ",".join(step.agent_id),
                )

            if step.id == "REPORT":
                result = await self._run_code_step(step, query, instance)
                self._step_results[step.id] = result
                self.engine.advance(instance, step.id, step_result={"type": "code_only"})
                await self._persist(instance)
            elif step.id == "MOCK_REVIEW":
                # Parallel step
                results = await self._run_parallel_step(step, query, instance)
                self._step_results[step.id] = results

                failed = [r for r in results if isinstance(r, AgentOutput) and not r.is_success]
                if failed:
                    error_msg = "; ".join(r.error or "Unknown error" for r in failed)
                    self.engine.fail(instance, f"Mock review failed: {error_msg}")
                    await self._persist(instance)
                    if self.sse_hub:
                        await self.sse_hub.broadcast_dict(
                            event_type="workflow.failed",
                            workflow_id=instance.id,
                            step_id=step.id,
                            payload={"error": error_msg},
                        )
                    break

                total_cost = sum(
                    r.cost for r in results
                    if isinstance(r, AgentOutput) and r.cost > 0
                )
                if total_cost > 0:
                    self.engine.deduct_budget(instance, total_cost)

                self.engine.advance(instance, step.id)
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
                    agent_id=step.agent_id if isinstance(step.agent_id, str) else ",".join(step.agent_id),
                )

        # Store results on session manifest before completing
        self._store_grant_results(instance)

        # Mark completed if all steps done
        if instance.state == "RUNNING":
            self.engine.complete(instance)
            await self._persist(instance)

        return {
            "instance": instance,
            "step_results": self._serialize_step_results(),
            "completed": instance.state == "COMPLETED",
        }

    async def _run_agent_step(
        self,
        step: WorkflowStepDef,
        query: str,
        instance: WorkflowInstance,
        agent_id: str | None = None,
    ) -> AgentOutput:
        """Run an agent step using the method routing map."""
        if agent_id:
            # Override for parallel step individual agents
            aid = agent_id
            method_name = "run"
        else:
            aid, method_name = _METHOD_MAP[step.id]

        agent = self.registry.get(aid)

        if agent is None:
            return AgentOutput(
                agent_id=aid,
                error=f"Agent {aid} not found in registry",
            )

        # Build context with prior step outputs
        prior_outputs = []
        for sid, result in self._step_results.items():
            if isinstance(result, list):
                # Parallel step results
                for r in result:
                    if hasattr(r, "model_dump"):
                        prior_outputs.append(r.model_dump())
                    elif isinstance(r, dict):
                        prior_outputs.append(r)
            elif hasattr(result, "model_dump"):
                prior_outputs.append(result.model_dump())
            elif isinstance(result, dict):
                prior_outputs.append(result)

        context = ContextPackage(
            task_description=query,
            prior_step_outputs=prior_outputs,
            constraints={"workflow_id": instance.id, "workflow_template": "W5"},
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
                agent_id=aid,
                error=f"Agent {aid} has no method {method_name}",
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
            "W5 refinement: %d iterations, score %.2f→%.2f, cost $%.4f, stopped: %s",
            result_meta.iterations_used,
            result_meta.quality_scores[0] if result_meta.quality_scores else 0,
            result_meta.quality_scores[-1] if result_meta.quality_scores else 0,
            result_meta.total_cost,
            result_meta.stopped_reason,
        )
        return refined_output, result_meta.total_cost

    async def _run_parallel_step(
        self,
        step: WorkflowStepDef,
        query: str,
        instance: WorkflowInstance,
    ) -> list[AgentOutput]:
        """Run multiple agents in parallel for a step (e.g., MOCK_REVIEW)."""
        agent_ids = step.agent_id if isinstance(step.agent_id, list) else [step.agent_id]

        results = await asyncio.gather(
            *[self._run_agent_step(step, query, instance, agent_id=aid) for aid in agent_ids],
            return_exceptions=True,
        )

        # Convert exceptions to AgentOutput errors
        processed: list[AgentOutput] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed.append(AgentOutput(
                    agent_id=agent_ids[i],
                    error=f"Parallel agent {agent_ids[i]} raised exception: {result}",
                ))
            else:
                processed.append(result)

        return processed

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

    def _serialize_step_results(self) -> dict[str, Any]:
        """Serialize step results for return, handling both single and parallel results."""
        serialized = {}
        for k, v in self._step_results.items():
            if isinstance(v, list):
                serialized[k] = [
                    r.model_dump(mode="json") if hasattr(r, "model_dump") else r
                    for r in v
                ]
            elif hasattr(v, "model_dump"):
                serialized[k] = v.model_dump(mode="json")
            else:
                serialized[k] = v
        return serialized

    def _store_grant_results(self, instance: WorkflowInstance) -> None:
        """Store grant proposal results on the workflow instance session_manifest."""
        instance.session_manifest = instance.session_manifest or {}

        # Store mock review feedback
        mock_review = self._step_results.get("MOCK_REVIEW")
        if isinstance(mock_review, list):
            reviews = {}
            for result in mock_review:
                if isinstance(result, AgentOutput):
                    reviews[result.agent_id] = {
                        "summary": result.summary or "",
                        "output": result.output if isinstance(result.output, dict) else {},
                    }
            instance.session_manifest["mock_reviews"] = reviews

        instance.session_manifest["workflow_template"] = "W5"

    def _generate_report(self, query: str, instance: WorkflowInstance) -> AgentOutput:
        """Assemble the final W5 grant proposal report from all step results."""
        opportunity_result = self._step_results.get("OPPORTUNITY")
        aims_result = self._step_results.get("SPECIFIC_AIMS")
        strategy_result = self._step_results.get("STRATEGY")
        prelim_result = self._step_results.get("PRELIMINARY_DATA")
        budget_result = self._step_results.get("BUDGET_PLAN")
        mock_review_results = self._step_results.get("MOCK_REVIEW")
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

        opportunity_data = _extract_output(opportunity_result)
        aims_data = _extract_output(aims_result)
        strategy_data = _extract_output(strategy_result)
        prelim_data = _extract_output(prelim_result)
        budget_data = _extract_output(budget_result)
        revision_data = _extract_output(revision_result)

        # Extract mock review feedback from parallel results
        mock_reviews = []
        if isinstance(mock_review_results, list):
            for result in mock_review_results:
                if isinstance(result, AgentOutput):
                    mock_reviews.append({
                        "agent_id": result.agent_id,
                        "summary": result.summary or "",
                        "output": result.output if isinstance(result.output, dict) else {},
                        "cost": result.cost,
                    })

        report = {
            "step": "REPORT",
            "query": query,
            "workflow_id": instance.id,
            "funding_opportunity": opportunity_data,
            "specific_aims": aims_data,
            "research_strategy": strategy_data,
            "preliminary_data": prelim_data,
            "budget_plan": budget_data,
            "mock_review_feedback": mock_reviews,
            "revision": revision_data,
            "revision_summary": _extract_summary(revision_result),
            "budget_used": instance.budget_total - instance.budget_remaining,
        }

        # Store on session manifest
        instance.session_manifest = instance.session_manifest or {}
        instance.session_manifest["grant_report"] = report

        return AgentOutput(
            agent_id="code_only",
            output=report,
            output_type="GrantProposalReport",
            summary=(
                f"W5 grant proposal complete: opportunity analysis, "
                f"{len(mock_reviews)} mock reviews, revision assembled. "
                f"Budget used: ${report['budget_used']:.2f}"
            ),
        )
