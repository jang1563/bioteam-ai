"""W2 Hypothesis Generation Runner — 8-step pipeline for hypothesis generation.

Steps:
  CONTEXTUALIZE → GENERATE → NEGATIVE_FILTER → DEBATE → RANK
       KM         T01-T07(par)  code_only      QA(par)   RD(Opus)
  → [HUMAN CHECKPOINT]
  → EVOLVE → RCMXT_PROFILE → PRESENT
      RD        AE             code_only(+SessionManifest)

Code-only steps: NEGATIVE_FILTER, PRESENT.
RANK has a human checkpoint for Director review.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.agents.base import observe
from app.agents.registry import AgentRegistry
from app.api.v1.sse import SSEHub
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

W2_STEPS: list[WorkflowStepDef] = [
    WorkflowStepDef(
        id="CONTEXTUALIZE",
        agent_id="knowledge_manager",
        output_schema="ContextResult",
        next_step="GENERATE",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=800, est_output_tokens=400),
    ),
    WorkflowStepDef(
        id="GENERATE",
        agent_id=[
            "t01_genomics",
            "t03_proteomics",
            "t04_biostatistics",
            "t05_ml_dl",
            "t06_systems_bio",
            "t07_structural_bio",
            "t02_transcriptomics",
        ],
        output_schema="HypothesisSet",
        next_step="NEGATIVE_FILTER",
        is_parallel=True,
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=7000, est_output_tokens=3500),
    ),
    WorkflowStepDef(
        id="NEGATIVE_FILTER",
        agent_id="code_only",
        output_schema="dict",
        next_step="DEBATE",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="DEBATE",
        agent_id=[
            "statistical_rigor_qa",
            "biological_plausibility_qa",
            "reproducibility_qa",
        ],
        output_schema="DebateResult",
        next_step="RANK",
        is_parallel=True,
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=4500, est_output_tokens=1500),
    ),
    WorkflowStepDef(
        id="RANK",
        agent_id="research_director",
        output_schema="SynthesisReport",
        next_step="EVOLVE",
        is_human_checkpoint=True,
        estimated_cost=_estimate_step_cost("opus", est_input_tokens=6000, est_output_tokens=2000),
    ),
    WorkflowStepDef(
        id="EVOLVE",
        agent_id="research_director",
        output_schema="RefinedHypotheses",
        next_step="RCMXT_PROFILE",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=800, est_output_tokens=400),
    ),
    WorkflowStepDef(
        id="RCMXT_PROFILE",
        agent_id="ambiguity_engine",
        output_schema="ContradictionAnalysis",
        next_step="PRESENT",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=3000, est_output_tokens=1000),
    ),
    WorkflowStepDef(
        id="PRESENT",
        agent_id="code_only",
        output_schema="dict",
        next_step=None,
        estimated_cost=0.0,
    ),
]

# Method routing: step_id -> (agent_id, method_name)
_METHOD_MAP: dict[str, tuple[str, str]] = {
    "CONTEXTUALIZE": ("knowledge_manager", "run"),
    "RANK": ("research_director", "synthesize"),
    "EVOLVE": ("research_director", "run"),
    "RCMXT_PROFILE": ("ambiguity_engine", "detect_contradictions"),
}

# Parallel step agent lists (step_id -> list of agent_ids)
_PARALLEL_AGENTS: dict[str, list[str]] = {
    "GENERATE": [
        "t01_genomics",
        "t03_proteomics",
        "t04_biostatistics",
        "t05_ml_dl",
        "t06_systems_bio",
        "t07_structural_bio",
        "t02_transcriptomics",
    ],
    "DEBATE": [
        "statistical_rigor_qa",
        "biological_plausibility_qa",
        "reproducibility_qa",
    ],
}


def get_step_by_id(step_id: str) -> WorkflowStepDef | None:
    """Get a step definition by ID."""
    for step in W2_STEPS:
        if step.id == step_id:
            return step
    return None


class W2HypothesisRunner:
    """Orchestrates the W2 Hypothesis Generation pipeline.

    Manages the 8-step pipeline, routing calls to the correct
    agent method, handling parallel steps, code-only steps,
    and managing human checkpoints.

    Usage:
        runner = W2HypothesisRunner(
            registry=registry,
            engine=WorkflowEngine(),
            sse_hub=sse_hub,
        )
        result = await runner.run(query="novel mechanisms of spaceflight-induced bone loss")
    """

    def __init__(
        self,
        registry: AgentRegistry,
        engine: WorkflowEngine | None = None,
        sse_hub: SSEHub | None = None,
        lab_kb=None,  # LabKBEngine — optional, for NEGATIVE_FILTER
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

    @observe(name="workflow.w2_hypothesis_generation")
    async def run(
        self,
        query: str,
        instance: WorkflowInstance | None = None,
        budget: float = 15.0,
    ) -> dict[str, Any]:
        """Execute the full W2 pipeline.

        Returns a dict with all step results and the final report.
        Pauses at RANK for human checkpoint.
        """
        if instance is None:
            instance = WorkflowInstance(
                template="W2",
                budget_total=budget,
                budget_remaining=budget,
            )

        self.engine.start(instance, first_step="CONTEXTUALIZE")
        await self._persist(instance)
        self._step_results = {}

        # Run steps sequentially up to RANK checkpoint
        for step in W2_STEPS:
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

            if step.id in ("NEGATIVE_FILTER", "PRESENT"):
                # Code-only steps
                result = await self._run_code_step(step, query, instance)
                self._step_results[step.id] = result
                self.engine.advance(instance, step.id, step_result={"type": "code_only"})
                await self._persist(instance)
            elif step.id in _PARALLEL_AGENTS:
                # Parallel agent steps (GENERATE, DEBATE)
                results = await self._run_parallel_step(step, query, instance)
                self._step_results[step.id] = results

                # Check if all agents failed
                successes = [r for r in results if isinstance(r, AgentOutput) and r.is_success]
                if not successes:
                    self.engine.fail(instance, f"All agents failed in parallel step {step.id}")
                    await self._persist(instance)
                    if self.sse_hub:
                        await self.sse_hub.broadcast_dict(
                            event_type="workflow.failed",
                            workflow_id=instance.id,
                            step_id=step.id,
                            payload={"error": f"All agents failed in step {step.id}"},
                        )
                    break

                # Record cost
                total_cost = sum(r.cost for r in results if isinstance(r, AgentOutput) and r.is_success)
                if total_cost > 0:
                    self.engine.deduct_budget(instance, total_cost)

                self.engine.advance(instance, step.id)
                await self._persist(instance)

                if self.sse_hub:
                    await self.sse_hub.broadcast_dict(
                        event_type="workflow.step_completed",
                        workflow_id=instance.id,
                        step_id=step.id,
                        agent_id=step.agent_id,
                        payload={
                            "step": step.id,
                            "cost": total_cost,
                            "summary": f"{len(successes)}/{len(results)} agents succeeded",
                        },
                    )
            elif step.id in _METHOD_MAP:
                # Single agent steps
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

                # Human checkpoint at RANK
                if step.is_human_checkpoint:
                    self.engine.request_human(instance)
                    await self._persist(instance)
                    logger.info("W2 paused at %s for human review", step.id)
                    break

        return {
            "instance": instance,
            "step_results": self._serialize_step_results(),
            "paused_at": instance.current_step if instance.state == "WAITING_HUMAN" else None,
        }

    @observe(name="workflow.w2_hypothesis_generation.resume")
    async def resume_after_human(
        self,
        instance: WorkflowInstance,
        query: str,
    ) -> dict[str, Any]:
        """Resume after human approval at RANK checkpoint.

        Continues from EVOLVE through PRESENT.
        Note: Caller is responsible for transitioning state to RUNNING first.
        """
        # Ensure we're in RUNNING state (caller should have done this)
        if instance.state != "RUNNING":
            self.engine.resume(instance)

        # Run remaining steps after human checkpoint
        remaining_ids = ("EVOLVE", "RCMXT_PROFILE", "PRESENT")
        remaining_steps = [s for s in W2_STEPS if s.id in remaining_ids]

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

            if step.id == "PRESENT":
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
            "step_results": self._serialize_step_results(),
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
        prior_outputs = self._collect_prior_outputs()

        # Extract negative results from CONTEXTUALIZE for downstream steps
        negative_results: list[dict] = []
        ctx_result = self._step_results.get("CONTEXTUALIZE")
        if ctx_result and hasattr(ctx_result, "output") and isinstance(ctx_result.output, dict):
            negative_results = ctx_result.output.get("negative_results", [])

        context = ContextPackage(
            task_description=query,
            prior_step_outputs=prior_outputs,
            negative_results=negative_results,
            constraints={"workflow_id": instance.id},
        )

        # Call the specific method on the agent
        method = getattr(agent, method_name, None)
        if method is None:
            return AgentOutput(
                agent_id=agent_id,
                error=f"Agent {agent_id} has no method {method_name}",
            )

        return await method(context)

    async def _run_parallel_step(
        self,
        step: WorkflowStepDef,
        query: str,
        instance: WorkflowInstance,
    ) -> list[AgentOutput]:
        """Run a parallel agent step using asyncio.gather."""
        agent_ids = _PARALLEL_AGENTS[step.id]

        # Build shared context
        prior_outputs = self._collect_prior_outputs()

        negative_results: list[dict] = []
        ctx_result = self._step_results.get("CONTEXTUALIZE")
        if ctx_result and hasattr(ctx_result, "output") and isinstance(ctx_result.output, dict):
            negative_results = ctx_result.output.get("negative_results", [])

        context = ContextPackage(
            task_description=query,
            prior_step_outputs=prior_outputs,
            negative_results=negative_results,
            constraints={"workflow_id": instance.id},
        )

        async def run_one_agent(aid: str) -> AgentOutput:
            agent = self.registry.get(aid)
            if agent is None:
                return AgentOutput(
                    agent_id=aid,
                    error=f"Agent {aid} not found in registry",
                )
            try:
                return await agent.run(context)
            except Exception as e:
                return AgentOutput(
                    agent_id=aid,
                    error=f"{type(e).__name__}: {e}",
                )

        results = await asyncio.gather(
            *[run_one_agent(aid) for aid in agent_ids],
            return_exceptions=True,
        )

        # Convert exceptions to AgentOutput
        processed: list[AgentOutput] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed.append(AgentOutput(
                    agent_id=agent_ids[i],
                    error=f"{type(result).__name__}: {result}",
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
        if step.id == "NEGATIVE_FILTER":
            return self._negative_filter(query)
        elif step.id == "PRESENT":
            return self._present_report(query, instance)
        return AgentOutput(agent_id="code_only", error=f"Unknown code step: {step.id}")

    def _negative_filter(self, query: str) -> AgentOutput:
        """Filter hypotheses from GENERATE output against negative results from CONTEXTUALIZE."""
        # Gather hypotheses from GENERATE parallel outputs
        generate_results = self._step_results.get("GENERATE", [])
        all_hypotheses: list[dict] = []
        if isinstance(generate_results, list):
            for result in generate_results:
                if isinstance(result, AgentOutput) and result.is_success and result.output:
                    if isinstance(result.output, dict):
                        hypotheses = result.output.get("hypotheses", [])
                        all_hypotheses.extend(hypotheses)
                    elif isinstance(result.output, list):
                        all_hypotheses.extend(result.output)

        # Gather negative results from CONTEXTUALIZE
        negative_results: list[dict] = []
        ctx_result = self._step_results.get("CONTEXTUALIZE")
        if ctx_result and hasattr(ctx_result, "output") and isinstance(ctx_result.output, dict):
            negative_results = ctx_result.output.get("negative_results", [])

        # Also check Lab KB directly if available
        if self.lab_kb:
            try:
                kb_results = self.lab_kb.search(query)
                for r in kb_results:
                    negative_results.append({
                        "id": r.id,
                        "claim": r.claim,
                        "outcome": r.outcome,
                        "organism": r.organism,
                        "confidence": r.confidence,
                    })
            except Exception as e:
                logger.warning("Lab KB search failed during NEGATIVE_FILTER: %s", e)

        # Filter: flag hypotheses that conflict with negative results
        filtered_hypotheses = []
        flagged_count = 0
        negative_claims = [nr.get("claim", "").lower() for nr in negative_results]

        for hyp in all_hypotheses:
            hyp_text = ""
            if isinstance(hyp, dict):
                hyp_text = hyp.get("hypothesis", hyp.get("text", hyp.get("description", ""))).lower()
            elif isinstance(hyp, str):
                hyp_text = hyp.lower()

            # Simple keyword overlap check for flagging
            is_flagged = False
            for claim in negative_claims:
                if claim and hyp_text and len(set(claim.split()) & set(hyp_text.split())) > 3:
                    is_flagged = True
                    flagged_count += 1
                    break

            entry = hyp if isinstance(hyp, dict) else {"hypothesis": hyp}
            entry["negative_flag"] = is_flagged
            filtered_hypotheses.append(entry)

        return AgentOutput(
            agent_id="code_only",
            output={
                "step": "NEGATIVE_FILTER",
                "query": query,
                "total_hypotheses": len(all_hypotheses),
                "negative_results_checked": len(negative_results),
                "flagged_count": flagged_count,
                "hypotheses": filtered_hypotheses,
            },
            output_type="NegativeFilterResult",
            summary=f"Filtered {len(all_hypotheses)} hypotheses, {flagged_count} flagged against {len(negative_results)} negative results",
        )

    def _present_report(self, query: str, instance: WorkflowInstance) -> AgentOutput:
        """Assemble final W2 report with hypotheses, rankings, and RCMXT profile."""
        # Gather results from each step
        rank_result = self._step_results.get("RANK")
        evolve_result = self._step_results.get("EVOLVE")
        rcmxt_result = self._step_results.get("RCMXT_PROFILE")
        neg_filter_result = self._step_results.get("NEGATIVE_FILTER")
        debate_results = self._step_results.get("DEBATE", [])

        # Extract ranking data
        ranking_data = {}
        if rank_result and hasattr(rank_result, "output") and isinstance(rank_result.output, dict):
            ranking_data = rank_result.output

        # Extract refined hypotheses from EVOLVE
        evolved_data = {}
        if evolve_result and hasattr(evolve_result, "output") and isinstance(evolve_result.output, dict):
            evolved_data = evolve_result.output

        # Extract RCMXT profile
        rcmxt_data = {}
        if rcmxt_result and hasattr(rcmxt_result, "output") and isinstance(rcmxt_result.output, dict):
            rcmxt_data = rcmxt_result.output

        # Extract filtered hypotheses
        filtered_data = {}
        if neg_filter_result and hasattr(neg_filter_result, "output") and isinstance(neg_filter_result.output, dict):
            filtered_data = neg_filter_result.output

        # Extract debate critiques
        debate_data = []
        if isinstance(debate_results, list):
            for result in debate_results:
                if isinstance(result, AgentOutput) and result.is_success and result.output:
                    debate_data.append({
                        "agent_id": result.agent_id,
                        "critique": result.output if isinstance(result.output, dict) else {"text": str(result.output)},
                        "summary": result.summary,
                    })

        report = {
            "step": "PRESENT",
            "query": query,
            "workflow_id": instance.id,
            "hypotheses": filtered_data.get("hypotheses", []),
            "total_hypotheses": filtered_data.get("total_hypotheses", 0),
            "flagged_by_negative_results": filtered_data.get("flagged_count", 0),
            "debate_critiques": debate_data,
            "rankings": ranking_data,
            "refined_hypotheses": evolved_data,
            "rcmxt_profile": rcmxt_data,
            "budget_used": instance.budget_total - instance.budget_remaining,
        }

        # Store on session manifest
        instance.session_manifest = instance.session_manifest or {}
        instance.session_manifest["hypothesis_report"] = report

        return AgentOutput(
            agent_id="code_only",
            output=report,
            output_type="HypothesisGenerationReport",
            summary=f"W2 complete: {report['total_hypotheses']} hypotheses generated, {len(debate_data)} QA critiques",
        )

    def _collect_prior_outputs(self) -> list[dict]:
        """Collect prior step outputs for context building."""
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
        return prior_outputs

    def _serialize_step_results(self) -> dict[str, Any]:
        """Serialize step results for return value."""
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
