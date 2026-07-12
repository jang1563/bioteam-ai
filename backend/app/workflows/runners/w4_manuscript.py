"""W4 Manuscript Writing Runner — 12-step pipeline for manuscript preparation.

Steps:
  OUTLINE [HC] -> STORY_ANCHOR -> ASSEMBLE -> DRAFT -> NARRATIVE_CHECK_DRAFT
    RD(synth)       code_only       KM         T08          code_only
  -> FIGURES -> STATISTICAL_REVIEW -> PLAUSIBILITY_REVIEW -> REPRODUCIBILITY_CHECK
       T08          StatQA                BioQA                   ReproQA
  -> REVISION -> NARRATIVE_CHECK_FINAL -> REPORT
      RD(synth)        code_only           code_only

OUTLINE has a human checkpoint for Director review of the manuscript plan.
STORY_ANCHOR loads a StoryFrame from W11 or auto-generates one via Haiku.
NARRATIVE_CHECK_DRAFT/FINAL emit SSE warnings on drift (never pause).
Code-only steps: STORY_ANCHOR, NARRATIVE_CHECK_*, REPORT.
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
        next_step="STORY_ANCHOR",
        is_human_checkpoint=True,
        estimated_cost=_estimate_step_cost("opus", est_input_tokens=4000, est_output_tokens=3000),
    ),
    WorkflowStepDef(
        id="STORY_ANCHOR",
        agent_id="code_only",  # Loads StoryFrame from W11 or auto-generates via Haiku
        output_schema="StoryFrame",
        next_step="ASSEMBLE",
        estimated_cost=_estimate_step_cost("haiku", est_input_tokens=1000, est_output_tokens=500),
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
        next_step="NARRATIVE_CHECK_DRAFT",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=6000, est_output_tokens=4000),
    ),
    WorkflowStepDef(
        id="NARRATIVE_CHECK_DRAFT",
        agent_id="code_only",  # Haiku consistency check — SSE warning only, always continues
        output_schema="NarrativeDriftReport",
        next_step="FIGURES",
        estimated_cost=_estimate_step_cost("haiku", est_input_tokens=1000, est_output_tokens=256),
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
        next_step="NARRATIVE_CHECK_FINAL",
        estimated_cost=_estimate_step_cost("opus", est_input_tokens=8000, est_output_tokens=4000),
    ),
    WorkflowStepDef(
        id="NARRATIVE_CHECK_FINAL",
        agent_id="code_only",  # Final narrative alignment check — SSE warning only
        output_schema="NarrativeDriftReport",
        next_step="REPORT",
        estimated_cost=_estimate_step_cost("haiku", est_input_tokens=1000, est_output_tokens=256),
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

    Manages the 12-step pipeline, routing calls to the correct
    agent method, handling code-only steps, and managing human checkpoints.

    Pipeline: OUTLINE[HC] → STORY_ANCHOR → ASSEMBLE → DRAFT → NARRATIVE_CHECK_DRAFT
              → FIGURES → STATISTICAL_REVIEW → PLAUSIBILITY_REVIEW → REPRODUCIBILITY_CHECK
              → REVISION → NARRATIVE_CHECK_FINAL → REPORT

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
        # Narrative consistency checker (Haiku-based, lazy init from research_director.llm)
        self._narrative_checker = None

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
                query=query,
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

            if step.agent_id == "code_only":
                # Code-only step (STORY_ANCHOR, NARRATIVE_CHECK_*, REPORT)
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

        Continues from STORY_ANCHOR through REPORT (11 remaining steps).
        Note: Caller is responsible for transitioning state to RUNNING first.
        """
        # Ensure we're in RUNNING state (caller should have done this)
        if instance.state != "RUNNING":
            self.engine.resume(instance)

        # Run remaining steps after human checkpoint (OUTLINE HC)
        # STORY_ANCHOR is first: loads StoryFrame from W11 or auto-generates
        remaining_ids = (
            "STORY_ANCHOR", "ASSEMBLE", "DRAFT", "NARRATIVE_CHECK_DRAFT",
            "FIGURES", "STATISTICAL_REVIEW", "PLAUSIBILITY_REVIEW", "REPRODUCIBILITY_CHECK",
            "REVISION", "NARRATIVE_CHECK_FINAL", "REPORT",
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

            if step.agent_id == "code_only":
                # Code-only steps: STORY_ANCHOR, NARRATIVE_CHECK_*, REPORT
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

        # Anchor writing steps to StoryFrame (prepend frame info to task_description)
        anchored_query = query
        if step.id in ("DRAFT", "FIGURES", "REVISION"):
            sf = (instance.session_manifest or {}).get("story_frame")
            if sf and sf.get("hook"):
                anchored_query = (
                    f"[Narrative Frame for this manuscript]\n"
                    f"Hook: {sf.get('hook', '')}\n"
                    f"Core Claim: {sf.get('core_claim', '')}\n"
                    f"Central Tension: {sf.get('central_tension', '')}\n"
                    f"Target Tier: {sf.get('target_tier', '')}\n"
                    f"\n---\n{query}"
                )

        context = ContextPackage(
            task_description=anchored_query,
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
        if step.id == "STORY_ANCHOR":
            return await self._run_story_anchor(instance, query)
        elif step.id == "NARRATIVE_CHECK_DRAFT":
            text = self._extract_section_text("DRAFT")
            return await self._run_narrative_check("DRAFT", text, instance)
        elif step.id == "NARRATIVE_CHECK_FINAL":
            text = self._extract_section_text("REVISION")
            return await self._run_narrative_check("REVISION", text, instance)
        elif step.id == "REPORT":
            return self._generate_report(query, instance)
        return AgentOutput(agent_id="code_only", error=f"Unknown code step: {step.id}")

    async def _run_story_anchor(self, instance: WorkflowInstance, query: str) -> AgentOutput:
        """Load StoryFrame from W11 session_manifest or auto-generate via Haiku fallback.

        Priority order:
        1. Already present in session_manifest["story_frame"] (e.g. injected by test or prior run)
        2. Loaded from W11 workflow via story_frame_workflow_id
        3. Auto-generated via Haiku fallback
        """
        manifest = instance.session_manifest or {}
        story_frame_wf_id = manifest.get("story_frame_workflow_id")

        # Priority 1: already present (pre-injected by test/UI or set by prior resume)
        story_frame: dict | None = manifest.get("story_frame")
        source = "pre-existing"

        # Priority 2: load from W11 workflow
        if story_frame is None and story_frame_wf_id:
            story_frame = await self._load_frame_from_w11(story_frame_wf_id)
            source = "W11"

        # Priority 3: auto-generate via Haiku fallback
        if story_frame is None:
            story_frame = await self._auto_generate_frame(query, instance)
            source = "auto-generated"

        # Store frame in session_manifest for downstream steps
        manifest["story_frame"] = story_frame
        instance.session_manifest = manifest

        narrative_type = story_frame.get("narrative_type", "unknown")
        hook_preview = story_frame.get("hook", "")[:80]
        return AgentOutput(
            agent_id="code_only",
            output={"story_frame": story_frame},
            output_type="StoryFrame",
            summary=f"Story anchor ({source}): [{narrative_type}] {hook_preview}",
        )

    async def _load_frame_from_w11(self, w11_workflow_id: str) -> dict | None:
        """Load selected StoryFrame from a completed W11 workflow's session_manifest."""
        try:
            from app.db.database import engine as db_engine
            from sqlmodel import Session as DBSession
            with DBSession(db_engine) as sess:
                w11 = sess.get(WorkflowInstance, w11_workflow_id)
                if w11 and w11.session_manifest:
                    frame = w11.session_manifest.get("selected_story_frame")
                    if frame:
                        logger.info("W4: loaded StoryFrame %s from W11 %s",
                                    frame.get("frame_id"), w11_workflow_id)
                        return frame
        except Exception as e:
            logger.warning("W4: failed to load StoryFrame from W11 %s: %s", w11_workflow_id, e)
        return None

    async def _auto_generate_frame(self, query: str, instance: WorkflowInstance) -> dict:
        """Auto-generate a single StoryFrame via Haiku when no W11 input is available."""
        llm = getattr(self.registry.get("research_director"), "llm", None)
        if llm is None:
            return self._default_story_frame(query)

        from app.models.story_frame import StoryFrameSet
        messages = [{"role": "user", "content": (
            f"Generate exactly ONE StoryFrame for this research manuscript:\n\n"
            f"Research topic: {query[:500]}\n\n"
            f"Focus on the most likely mechanism_discovery or paradigm_challenge angle."
        )}]
        try:
            frame_set, meta = await llm.complete_structured(
                messages=messages,
                model_tier="haiku",
                response_model=StoryFrameSet,
                system=(
                    "You are a scientific editor. Generate a single StoryFrame for a manuscript. "
                    "Be concise. Set frame_id to 'SF-001'."
                ),
                temperature=0.3,
                max_tokens=1024,
            )
            if meta and hasattr(meta, "cost") and meta.cost > 0:
                self.engine.deduct_budget(instance, meta.cost)
            if frame_set.frames:
                frame = frame_set.frames[0]
                if not frame.frame_id:
                    frame.frame_id = "SF-001"
                return frame.model_dump(mode="json")
        except Exception as e:
            logger.warning("W4: auto-generate StoryFrame failed: %s — using default", e)
        return self._default_story_frame(query)

    def _default_story_frame(self, query: str) -> dict:
        """Minimal default frame when LLM is unavailable."""
        return {
            "frame_id": "SF-001",
            "narrative_type": "mechanism_discovery",
            "hook": f"This study investigates the mechanisms underlying {query[:80]}.",
            "central_tension": "The underlying mechanism was unclear; this work provides clarity.",
            "core_claim": f"We characterize the key mechanisms of {query[:60]}.",
            "supporting_findings": [],
            "figure_sequence": [],
            "target_tier": "specialty",
            "novelty_rationale": "First systematic characterization of this phenomenon.",
            "blind_spots": [],
            "impact_score": 0.7,
            "version": 1,
        }

    async def _run_narrative_check(
        self,
        section_id: str,
        section_text: str,
        instance: WorkflowInstance,
    ) -> AgentOutput:
        """Check narrative consistency between section and StoryFrame.

        Uses Haiku (~$0.01). Emits SSE warning if score < 0.75. Always continues.
        """
        manifest = instance.session_manifest or {}
        story_frame = manifest.get("story_frame")

        if not story_frame:
            return AgentOutput(
                agent_id="code_only",
                output={"skipped": True, "reason": "no story_frame in session_manifest"},
                output_type="NarrativeDriftReport",
                summary="Narrative check skipped (no story frame)",
            )

        # Lazy-init checker
        if self._narrative_checker is None:
            llm = getattr(self.registry.get("research_director"), "llm", None)
            if llm:
                from app.engines.narrative_consistency import NarrativeConsistencyChecker
                self._narrative_checker = NarrativeConsistencyChecker(llm)

        if self._narrative_checker is None:
            return AgentOutput(
                agent_id="code_only",
                output={"skipped": True, "reason": "LLM unavailable"},
                output_type="NarrativeDriftReport",
                summary="Narrative check skipped (no LLM)",
            )

        report = await self._narrative_checker.check(section_id, section_text, story_frame)

        # Emit SSE warning if drifting (never pause)
        if self.sse_hub and report.consistency_score < 0.75:
            await self.sse_hub.broadcast_dict(
                event_type="workflow.narrative_warning",
                workflow_id=instance.id,
                step_id=section_id,
                payload={
                    "consistency_score": report.consistency_score,
                    "drift_summary": report.drift_summary,
                    "recommendation": report.recommendation,
                    "severity": "major" if report.consistency_score < 0.50 else "minor",
                },
            )

        # Store drift report in session_manifest for later review
        # Key uses uppercase section_id to match _generate_report() reads:
        #   "narrative_drift_DRAFT" and "narrative_drift_REVISION"
        drift_key = f"narrative_drift_{section_id}"
        manifest[drift_key] = report.model_dump()
        instance.session_manifest = manifest

        return AgentOutput(
            agent_id="code_only",
            output=report.model_dump(),
            output_type="NarrativeDriftReport",
            summary=f"Narrative consistency ({section_id}): {report.consistency_score:.2f} — {report.recommendation}",
        )

    def _extract_section_text(self, step_id: str) -> str:
        """Extract text content from a completed step result for narrative checking."""
        result = self._step_results.get(step_id)
        if result is None:
            return ""
        if hasattr(result, "output") and isinstance(result.output, dict):
            # Try common text field names
            for field in ("content", "text", "manuscript_text", "draft_text", "synthesis"):
                if result.output.get(field):
                    return str(result.output[field])[:3000]
        if result.summary:
            return result.summary
        return ""

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

        # Pull narrative data from session_manifest (set by STORY_ANCHOR + NARRATIVE_CHECK steps)
        manifest = instance.session_manifest or {}
        story_frame = manifest.get("story_frame")
        narrative_drift_draft = manifest.get("narrative_drift_DRAFT")
        narrative_drift_final = manifest.get("narrative_drift_REVISION")

        report = {
            "step": "REPORT",
            "query": query,
            "workflow_id": instance.id,
            "outline": outline_data,
            "story_frame": story_frame,  # StoryFrame used as narrative anchor
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
            "narrative_consistency": {
                "draft": narrative_drift_draft,    # NarrativeDriftReport after DRAFT
                "final": narrative_drift_final,    # NarrativeDriftReport after REVISION
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
