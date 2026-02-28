"""W6 Ambiguity Resolution Runner — standalone contradiction resolution workflow.

5-step pipeline:
  EVIDENCE_LANDSCAPE → CLASSIFY → MINE_NEGATIVES → RESOLUTION_HYPOTHESES → PRESENT
        KM              AE           code_only            AE             code_only

Budget: $5 max, ~6-10 Sonnet calls.
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
    input_rate = COST_PER_1K_INPUT.get(model_tier, 0.0)
    output_rate = COST_PER_1K_OUTPUT.get(model_tier, 0.0)
    return (est_input_tokens / 1000) * input_rate + (est_output_tokens / 1000) * output_rate


W6_STEPS: list[WorkflowStepDef] = [
    WorkflowStepDef(
        id="EVIDENCE_LANDSCAPE",
        agent_id="knowledge_manager",
        output_schema="MemoryRetrievalResult",
        next_step="CLASSIFY",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=600, est_output_tokens=200),
    ),
    WorkflowStepDef(
        id="CLASSIFY",
        agent_id="ambiguity_engine",
        output_schema="ContradictionAnalysis",
        next_step="MINE_NEGATIVES",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=5000, est_output_tokens=2000),
    ),
    WorkflowStepDef(
        id="MINE_NEGATIVES",
        agent_id="code_only",
        output_schema="dict",
        next_step="RESOLUTION_HYPOTHESES",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="RESOLUTION_HYPOTHESES",
        agent_id="ambiguity_engine",
        output_schema="ContradictionAnalysis",
        next_step="PRESENT",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=3000, est_output_tokens=1500),
    ),
    WorkflowStepDef(
        id="PRESENT",
        agent_id="code_only",
        output_schema="dict",
        next_step=None,
        estimated_cost=0.0,
    ),
]

_METHOD_MAP: dict[str, tuple[str, str]] = {
    "EVIDENCE_LANDSCAPE": ("knowledge_manager", "retrieve_memory"),
    "CLASSIFY": ("ambiguity_engine", "detect_contradictions"),
    "RESOLUTION_HYPOTHESES": ("ambiguity_engine", "detect_contradictions"),
}


def get_step_by_id(step_id: str) -> WorkflowStepDef | None:
    for step in W6_STEPS:
        if step.id == step_id:
            return step
    return None


class W6AmbiguityRunner:
    """Orchestrates the W6 Ambiguity Resolution pipeline.

    Usage:
        runner = W6AmbiguityRunner(registry=registry, engine=engine)
        result = await runner.run(query="Do VEGF levels increase or decrease in spaceflight?")
    """

    def __init__(
        self,
        registry: AgentRegistry,
        engine: WorkflowEngine | None = None,
        sse_hub: SSEHub | None = None,
        lab_kb=None,
        persist_fn=None,
        checkpoint_manager=None,  # CheckpointManager — optional, for step persistence
    ) -> None:
        self.registry = registry
        self.engine = engine or WorkflowEngine()
        self.sse_hub = sse_hub
        self.lab_kb = lab_kb
        self._persist_fn = persist_fn
        self._checkpoint_manager = checkpoint_manager
        self._step_results: dict[str, AgentOutput] = {}

    async def _persist(self, instance: WorkflowInstance) -> None:
        if self._persist_fn:
            await self._persist_fn(instance)

    @observe(name="workflow.w6_ambiguity_resolution")
    async def run(
        self,
        query: str,
        instance: WorkflowInstance | None = None,
        budget: float = 5.0,
    ) -> dict[str, Any]:
        """Execute the full W6 pipeline."""
        if instance is None:
            instance = WorkflowInstance(
                template="W6",
                budget_total=budget,
                budget_remaining=budget,
            )

        self.engine.start(instance, first_step="EVIDENCE_LANDSCAPE")
        await self._persist(instance)
        self._step_results = {}

        for step in W6_STEPS:
            if instance.state not in ("RUNNING",):
                break

            if self.sse_hub:
                await self.sse_hub.broadcast_dict(
                    event_type="workflow.step_started",
                    workflow_id=instance.id,
                    step_id=step.id,
                    agent_id=step.agent_id,
                    payload={"step": step.id},
                )

            if step.id in ("MINE_NEGATIVES", "PRESENT"):
                result = await self._run_code_step(step, query, instance)
                self._step_results[step.id] = result
                self.engine.advance(instance, step.id, step_result={"type": "code_only"})
                await self._persist(instance)
            elif step.id in _METHOD_MAP:
                result = await self._run_agent_step(step, query, instance)

                # Apply refinement at RESOLUTION_HYPOTHESES step
                if step.id == "RESOLUTION_HYPOTHESES" and result.is_success:
                    agent = self.registry.get(_METHOD_MAP[step.id][0])
                    if agent is not None:
                        context = ContextPackage(
                            task_description=query,
                            prior_step_outputs=[
                                r.model_dump() if hasattr(r, "model_dump") else r
                                for r in self._step_results.values()
                            ],
                            constraints={"workflow_id": instance.id},
                        )
                        result, extra_cost = await self._maybe_refine(
                            agent, context, result, instance,
                        )

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
                        payload={
                            "step": step.id,
                            "cost": result.cost,
                            "summary": result.summary[:200] if result.summary else "",
                        },
                    )

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
            "W6 refinement: %d iterations, score %.2f→%.2f, cost $%.4f, stopped: %s",
            result_meta.iterations_used,
            result_meta.quality_scores[0] if result_meta.quality_scores else 0,
            result_meta.quality_scores[-1] if result_meta.quality_scores else 0,
            result_meta.total_cost,
            result_meta.stopped_reason,
        )
        return refined_output, result_meta.total_cost

    async def _run_agent_step(
        self,
        step: WorkflowStepDef,
        query: str,
        instance: WorkflowInstance,
    ) -> AgentOutput:
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

        # Include negative results from MINE_NEGATIVES if available
        negative_results: list[dict] = []
        neg_check = self._step_results.get("MINE_NEGATIVES")
        if neg_check and hasattr(neg_check, "output") and isinstance(neg_check.output, dict):
            negative_results = neg_check.output.get("results", [])

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

        method = getattr(agent, method_name, None)
        if method is None:
            return AgentOutput(
                agent_id=agent_id,
                error=f"Agent {agent_id} has no method {method_name}",
            )

        return await method(context)

    async def _run_code_step(
        self,
        step: WorkflowStepDef,
        query: str,
        instance: WorkflowInstance,
    ) -> AgentOutput:
        if step.id == "MINE_NEGATIVES":
            return await self._mine_negatives(query)
        elif step.id == "PRESENT":
            return self._present_report(query, instance)
        return AgentOutput(agent_id="code_only", error=f"Unknown code step: {step.id}")

    async def _mine_negatives(self, query: str) -> AgentOutput:
        """Search Lab KB for related negative results."""
        negative_results = []
        if self.lab_kb:
            try:
                results = self.lab_kb.search(query)
                negative_results = [
                    {
                        "id": r.id,
                        "claim": r.claim,
                        "outcome": r.outcome,
                        "organism": r.organism,
                        "confidence": r.confidence,
                    }
                    for r in results
                ]
            except Exception as e:
                logger.warning("Lab KB search failed: %s", e)

        return AgentOutput(
            agent_id="code_only",
            output={
                "step": "MINE_NEGATIVES",
                "query": query,
                "negative_results_found": len(negative_results),
                "results": negative_results,
            },
            output_type="NegativeResultsMined",
            summary=f"Found {len(negative_results)} related negative results",
        )

    def _present_report(self, query: str, instance: WorkflowInstance) -> AgentOutput:
        """Assemble final ambiguity resolution report."""
        classify_result = self._step_results.get("CLASSIFY")
        resolution_result = self._step_results.get("RESOLUTION_HYPOTHESES")
        neg_result = self._step_results.get("MINE_NEGATIVES")

        # Extract classification analysis
        classify_data = {}
        if classify_result and hasattr(classify_result, "output") and isinstance(classify_result.output, dict):
            classify_data = classify_result.output

        # Extract resolution data
        resolution_data = {}
        if resolution_result and hasattr(resolution_result, "output") and isinstance(resolution_result.output, dict):
            resolution_data = resolution_result.output

        # Extract negative results
        neg_data = {}
        if neg_result and hasattr(neg_result, "output") and isinstance(neg_result.output, dict):
            neg_data = neg_result.output

        report = {
            "step": "PRESENT",
            "query": query,
            "workflow_id": instance.id,
            "contradictions_found": classify_data.get("contradictions_found", 0),
            "ambiguity_level": classify_data.get("overall_ambiguity_level", "low"),
            "entries": classify_data.get("entries", []),
            "resolution_entries": resolution_data.get("entries", []),
            "negative_results": neg_data.get("results", []),
            "summary": classify_data.get("summary", ""),
            "recommended_action": classify_data.get("recommended_action", ""),
            "budget_used": instance.budget_total - instance.budget_remaining,
        }

        # Store on session manifest
        instance.session_manifest = instance.session_manifest or {}
        instance.session_manifest["ambiguity_report"] = report

        return AgentOutput(
            agent_id="code_only",
            output=report,
            output_type="AmbiguityResolutionReport",
            summary=f"W6 complete: {report['contradictions_found']} contradictions, level={report['ambiguity_level']}",
        )
