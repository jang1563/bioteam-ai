"""W1 Literature Review Runner — 13-step pipeline for systematic literature review.

Steps:
  SCOPE → SEARCH → SCREEN → EXTRACT → NEGATIVE_CHECK → SYNTHESIZE
    RD      KM      T02       T02       LabKB(code)       RD(Opus)
  → [HUMAN CHECKPOINT]
  → CONTRADICTION_CHECK → CITATION_CHECK → RCMXT_SCORE → INTEGRITY_CHECK
        AmbiguityEngine       code              code            DIA(quick)
  → NOVELTY_CHECK → REPORT
        KM            code(+SessionManifest)

Code-only steps: NEGATIVE_CHECK, CITATION_CHECK, RCMXT_SCORE, INTEGRITY_CHECK, REPORT.
SYNTHESIZE has a human checkpoint for Director review.
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
from app.workflows.runners.async_runner import AsyncWorkflowRunner

logger = logging.getLogger(__name__)


def _estimate_step_cost(model_tier: str, est_input_tokens: int, est_output_tokens: int) -> float:
    """Estimate step cost from model tier and expected token counts.

    Uses the per-1K-token pricing from CostTracker. Returns 0.0 for code-only steps.
    """
    input_rate = COST_PER_1K_INPUT.get(model_tier, 0.0)
    output_rate = COST_PER_1K_OUTPUT.get(model_tier, 0.0)
    return (est_input_tokens / 1000) * input_rate + (est_output_tokens / 1000) * output_rate


# === Step Definitions ===
# estimated_cost is derived from model tier × expected token counts

W1_STEPS: list[WorkflowStepDef] = [
    WorkflowStepDef(
        id="SCOPE",
        agent_id="research_director",
        output_schema="SynthesisReport",
        next_step="SEARCH",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=800, est_output_tokens=400),
    ),
    WorkflowStepDef(
        id="SEARCH",
        agent_id="knowledge_manager",
        output_schema="LiteratureSearchResult",
        next_step="SCREEN",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=600, est_output_tokens=200),
    ),
    WorkflowStepDef(
        id="SCREEN",
        agent_id="t02_transcriptomics",
        output_schema="ScreeningResult",
        next_step="EXTRACT",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=4000, est_output_tokens=1000),
    ),
    WorkflowStepDef(
        id="EXTRACT",
        agent_id="t02_transcriptomics",
        output_schema="ExtractionResult",
        next_step="NEGATIVE_CHECK",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=4000, est_output_tokens=1500),
    ),
    WorkflowStepDef(
        id="NEGATIVE_CHECK",
        agent_id="code_only",  # No LLM, handled directly
        output_schema="dict",
        next_step="SYNTHESIZE",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="SYNTHESIZE",
        agent_id="research_director",
        output_schema="SynthesisReport",
        next_step="CONTRADICTION_CHECK",
        is_human_checkpoint=True,
        estimated_cost=_estimate_step_cost("opus", est_input_tokens=6000, est_output_tokens=2000),
    ),
    WorkflowStepDef(
        id="CONTRADICTION_CHECK",
        agent_id="ambiguity_engine",
        output_schema="ContradictionAnalysis",
        next_step="CITATION_CHECK",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=3000, est_output_tokens=1000),
    ),
    WorkflowStepDef(
        id="CITATION_CHECK",
        agent_id="code_only",
        output_schema="dict",
        next_step="RCMXT_SCORE",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="RCMXT_SCORE",
        agent_id="code_only",
        output_schema="dict",
        next_step="INTEGRITY_CHECK",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="INTEGRITY_CHECK",
        agent_id="code_only",  # Uses data_integrity_auditor.quick_check (deterministic, no LLM)
        output_schema="IntegrityAnalysis",
        next_step="NOVELTY_CHECK",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="NOVELTY_CHECK",
        agent_id="knowledge_manager",
        output_schema="NoveltyAssessment",
        next_step="REPORT",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=1000, est_output_tokens=300),
    ),
    WorkflowStepDef(
        id="REPORT",
        agent_id="code_only",  # No LLM, assembles final output
        output_schema="dict",
        next_step=None,
        estimated_cost=0.0,
    ),
]

# Method routing: step_id → (agent_id, method_name)
_METHOD_MAP: dict[str, tuple[str, str]] = {
    "SCOPE": ("research_director", "synthesize"),
    "SEARCH": ("knowledge_manager", "search_literature"),
    "SCREEN": ("t02_transcriptomics", "screen_papers"),
    "EXTRACT": ("t02_transcriptomics", "extract_data"),
    "SYNTHESIZE": ("research_director", "synthesize"),
    "CONTRADICTION_CHECK": ("ambiguity_engine", "detect_contradictions"),
    "NOVELTY_CHECK": ("knowledge_manager", "assess_novelty"),
}


def get_step_by_id(step_id: str) -> WorkflowStepDef | None:
    """Get a step definition by ID."""
    for step in W1_STEPS:
        if step.id == step_id:
            return step
    return None


class W1LiteratureReviewRunner:
    """Orchestrates the W1 Literature Review pipeline.

    Manages the 8-step pipeline, routing calls to the correct
    agent method, handling code-only steps, and managing human checkpoints.

    Usage:
        runner = W1LiteratureReviewRunner(
            registry=registry,
            engine=WorkflowEngine(),
            sse_hub=sse_hub,
        )
        result = await runner.run(query="spaceflight-induced anemia mechanisms")
    """

    def __init__(
        self,
        registry: AgentRegistry,
        engine: WorkflowEngine | None = None,
        sse_hub: SSEHub | None = None,
        lab_kb=None,  # LabKBEngine — optional, for NEGATIVE_CHECK
        persist_fn=None,  # async callable(WorkflowInstance) → None
        rcmxt_mode: str = "heuristic",  # "heuristic" | "llm" | "hybrid"
        llm_layer=None,  # LLMLayer — required for llm/hybrid RCMXT scoring
    ) -> None:
        self.registry = registry
        self.engine = engine or WorkflowEngine()
        self.sse_hub = sse_hub
        self.lab_kb = lab_kb
        self._persist_fn = persist_fn
        self._rcmxt_mode = rcmxt_mode
        self._llm_layer = llm_layer
        self.async_runner = AsyncWorkflowRunner(
            engine=self.engine,
            registry=self.registry,
            sse_hub=self.sse_hub,
        )
        # Store step results for inter-step data flow
        self._step_results: dict[str, AgentOutput] = {}

    async def _persist(self, instance: WorkflowInstance) -> None:
        """Persist workflow state to storage (if callback provided)."""
        if self._persist_fn:
            await self._persist_fn(instance)

    @observe(name="workflow.w1_literature_review")
    async def run(
        self,
        query: str,
        instance: WorkflowInstance | None = None,
        budget: float = 5.0,
    ) -> dict[str, Any]:
        """Execute the full W1 pipeline.

        Returns a dict with all step results and the final report.
        Pauses at SYNTHESIZE for human checkpoint.
        """
        if instance is None:
            instance = WorkflowInstance(
                template="W1",
                budget_total=budget,
                budget_remaining=budget,
            )

        self.engine.start(instance, first_step="SCOPE")
        await self._persist(instance)
        self._step_results = {}

        # Run steps sequentially up to SYNTHESIZE checkpoint
        for step in W1_STEPS:
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

            if step.id in ("NEGATIVE_CHECK", "CITATION_CHECK", "RCMXT_SCORE", "INTEGRITY_CHECK", "REPORT"):
                # Code-only steps
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

                # Human checkpoint at SYNTHESIZE
                if step.is_human_checkpoint:
                    self.engine.request_human(instance)
                    await self._persist(instance)
                    logger.info("W1 paused at %s for human review", step.id)
                    break

        return {
            "instance": instance,
            "step_results": {k: v.model_dump(mode="json") if hasattr(v, 'model_dump') else v
                             for k, v in self._step_results.items()},
            "paused_at": instance.current_step if instance.state == "WAITING_HUMAN" else None,
        }

    @observe(name="workflow.w1_literature_review.resume")
    async def resume_after_human(
        self,
        instance: WorkflowInstance,
        query: str,
    ) -> dict[str, Any]:
        """Resume after human approval at SYNTHESIZE checkpoint.

        Continues from CITATION_CHECK through REPORT.
        Note: Caller is responsible for transitioning state to RUNNING first.
        """
        # Ensure we're in RUNNING state (caller should have done this)
        if instance.state != "RUNNING":
            self.engine.resume(instance)

        # Run remaining steps after human checkpoint
        remaining_ids = ("CONTRADICTION_CHECK", "CITATION_CHECK", "RCMXT_SCORE", "INTEGRITY_CHECK", "NOVELTY_CHECK", "REPORT")
        remaining_steps = [s for s in W1_STEPS if s.id in remaining_ids]

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

            if step.id in ("CITATION_CHECK", "RCMXT_SCORE", "INTEGRITY_CHECK", "REPORT"):
                result = await self._run_code_step(step, query, instance)
                self._step_results[step.id] = result
                self.engine.advance(instance, step.id)
                await self._persist(instance)
            else:
                # Graceful degradation: skip optional agents if unavailable
                agent_id = _METHOD_MAP.get(step.id, (None, None))[0]
                if agent_id and not self.registry.is_available(agent_id):
                    agent = self.registry.get(agent_id)
                    deg_mode = agent.spec.degradation_mode if agent else None
                    if deg_mode == "skip":
                        logger.warning("Skipping %s: agent %s unavailable (degradation=skip)", step.id, agent_id)
                        self.engine.advance(instance, step.id)
                        await self._persist(instance)
                        continue

                result = await self._run_agent_step(step, query, instance)
                self._step_results[step.id] = result
                if not result.is_success:
                    # For optional agents with degradation_mode="skip", skip on failure
                    agent_obj = self.registry.get(agent_id) if agent_id else None
                    if agent_obj and agent_obj.spec.degradation_mode == "skip":
                        logger.warning("Skipping failed %s (degradation=skip): %s", step.id, result.error)
                        self.engine.advance(instance, step.id)
                        await self._persist(instance)
                        continue
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

        # Store Tier 1 results on instance before completing
        self._store_tier1_results(instance)

        # Mark completed if all steps done
        if instance.state == "RUNNING":
            self.engine.complete(instance)
            await self._persist(instance)

        return {
            "instance": instance,
            "step_results": {k: v.model_dump(mode="json") if hasattr(v, 'model_dump') else v
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
            if hasattr(result, 'model_dump'):
                prior_outputs.append(result.model_dump())
            elif isinstance(result, dict):
                prior_outputs.append(result)

        # Extract negative results from NEGATIVE_CHECK for downstream steps
        negative_results: list[dict] = []
        neg_check = self._step_results.get("NEGATIVE_CHECK")
        if neg_check and hasattr(neg_check, 'output') and isinstance(neg_check.output, dict):
            negative_results = neg_check.output.get("results", [])

        context = ContextPackage(
            task_description=query,
            prior_step_outputs=prior_outputs,
            negative_results=negative_results,
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

        # Apply iterative refinement at SYNTHESIZE step
        if step.id == "SYNTHESIZE" and result.is_success:
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

        llm = self._llm_layer or (agent.llm if hasattr(agent, "llm") else None)
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
            "W1 refinement: %d iterations, score %.2f→%.2f, cost $%.4f, stopped: %s",
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
        if step.id == "NEGATIVE_CHECK":
            return await self._negative_check(query)
        elif step.id == "CITATION_CHECK":
            return self._citation_check()
        elif step.id == "RCMXT_SCORE":
            return await self._rcmxt_score()
        elif step.id == "INTEGRITY_CHECK":
            return await self._integrity_check(query, instance)
        elif step.id == "REPORT":
            return self._generate_report(query, instance)
        return AgentOutput(agent_id="code_only", error=f"Unknown code step: {step.id}")

    async def _integrity_check(self, query: str, instance: WorkflowInstance) -> AgentOutput:
        """Run deterministic integrity checks (quick_check — no LLM) on synthesis text."""
        import re

        agent = self.registry.get("data_integrity_auditor")
        if agent is None:
            logger.warning("DataIntegrityAuditorAgent not available, skipping INTEGRITY_CHECK")
            return AgentOutput(
                agent_id="data_integrity_auditor",
                output={"step": "INTEGRITY_CHECK", "skipped": True, "reason": "agent_unavailable"},
                output_type="IntegrityQuickCheck",
                summary="Integrity check skipped: agent not available",
            )

        # Gather text from synthesis + extracted data
        text_parts = []
        for sid in ("SYNTHESIZE", "EXTRACT", "SEARCH"):
            step_result = self._step_results.get(sid)
            if step_result and hasattr(step_result, "output") and isinstance(step_result.output, dict):
                for key in ("summary", "text", "synthesis", "data"):
                    val = step_result.output.get(key)
                    if val and isinstance(val, str):
                        text_parts.append(val)

        text = "\n\n".join(text_parts) if text_parts else query

        # Extract DOIs from accumulated text for retraction checking
        doi_pattern = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
        dois = list(set(doi_pattern.findall(text)))

        try:
            output = await agent.quick_check(text, dois=dois or None)
            # Store integrity findings in session_manifest
            if output.output and isinstance(output.output, dict):
                instance.session_manifest["integrity_quick_check"] = output.output

                # Persist findings to DB
                findings_list = output.output.get("findings", [])
                if findings_list:
                    self._persist_integrity_findings(findings_list, instance.id)

            return AgentOutput(
                agent_id="data_integrity_auditor",
                output={"step": "INTEGRITY_CHECK", **output.output} if output.output else {"step": "INTEGRITY_CHECK"},
                output_type="IntegrityQuickCheck",
                summary=output.summary or "Integrity quick check completed",
            )
        except Exception as e:
            logger.warning("INTEGRITY_CHECK failed (degradation=skip): %s", e)
            return AgentOutput(
                agent_id="data_integrity_auditor",
                output={"step": "INTEGRITY_CHECK", "skipped": True, "error": str(e)},
                output_type="IntegrityQuickCheck",
                summary=f"Integrity check skipped: {e}",
            )

    @staticmethod
    def _persist_integrity_findings(findings_list: list[dict], workflow_id: str) -> None:
        """Persist integrity findings from W1 quick_check to the database."""
        try:
            from app.db.database import engine as db_engine
            from app.models.integrity import AuditFinding, AuditRun
            from sqlmodel import Session

            with Session(db_engine) as session:
                for f in findings_list:
                    db_finding = AuditFinding(
                        category=f.get("category", "unknown"),
                        severity=f.get("severity", "info"),
                        title=f.get("title", ""),
                        description=f.get("description", ""),
                        source_text=f.get("source_text", ""),
                        suggestion=f.get("suggestion", ""),
                        confidence=f.get("confidence", 0.8),
                        checker=f.get("checker", ""),
                        finding_metadata=f.get("metadata", {}),
                        workflow_id=workflow_id,
                        paper_doi=f.get("doi", None),
                    )
                    session.add(db_finding)

                # Create an audit run record
                by_severity: dict[str, int] = {}
                by_category: dict[str, int] = {}
                for f in findings_list:
                    sev = f.get("severity", "info")
                    cat = f.get("category", "unknown")
                    by_severity[sev] = by_severity.get(sev, 0) + 1
                    by_category[cat] = by_category.get(cat, 0) + 1

                run = AuditRun(
                    workflow_id=workflow_id,
                    trigger="w1_step",
                    total_findings=len(findings_list),
                    findings_by_severity=by_severity,
                    findings_by_category=by_category,
                    overall_level=(
                        "critical" if by_severity.get("critical", 0) > 0
                        else "significant_issues" if by_severity.get("error", 0) > 0
                        else "minor_issues" if by_severity.get("warning", 0) > 0
                        else "clean"
                    ),
                    summary=f"W1 quick check: {len(findings_list)} findings",
                )
                session.add(run)
                session.commit()
        except Exception as e:
            logger.warning("Failed to persist integrity findings: %s", e)

    async def _negative_check(self, query: str) -> AgentOutput:
        """Check Lab KB for relevant negative results."""
        negative_results = []
        if self.lab_kb:
            try:
                results = self.lab_kb.search(query)
                negative_results = [
                    {"id": r.id, "claim": r.claim, "outcome": r.outcome,
                     "organism": r.organism, "confidence": r.confidence}
                    for r in results
                ]
            except Exception as e:
                logger.warning("Lab KB search failed: %s", e)

        return AgentOutput(
            agent_id="code_only",
            output={
                "step": "NEGATIVE_CHECK",
                "query": query,
                "negative_results_found": len(negative_results),
                "results": negative_results,
            },
            output_type="NegativeCheckResult",
            summary=f"Found {len(negative_results)} negative results for: {query[:80]}",
        )

    def _citation_check(self) -> AgentOutput:
        """Validate citations in SYNTHESIZE output against SEARCH sources."""
        from app.engines.citation_validator import CitationValidator

        validator = CitationValidator()

        # Register sources from SEARCH step
        search_result = self._step_results.get("SEARCH")
        if search_result and hasattr(search_result, 'output') and isinstance(search_result.output, dict):
            papers = search_result.output.get("papers", [])
            validator.register_sources(papers)

        # Get synthesis text and cited sources from SYNTHESIZE step
        synth_result = self._step_results.get("SYNTHESIZE")
        synthesis_text = ""
        inline_refs = None
        if synth_result and hasattr(synth_result, 'output') and isinstance(synth_result.output, dict):
            synthesis_text = synth_result.output.get("summary", "")
            sources_cited = synth_result.output.get("sources_cited", [])
            if sources_cited:
                inline_refs = [{"doi": s} for s in sources_cited if isinstance(s, str) and s.startswith("10.")]

        report = validator.validate(synthesis_text, inline_refs=inline_refs)

        report_dict = {
            "step": "CITATION_CHECK",
            "total_citations": report.total_citations,
            "verified": report.verified,
            "verification_rate": report.verification_rate,
            "is_clean": report.is_clean,
            "issues": [
                {
                    "citation_ref": issue.citation_ref,
                    "issue_type": issue.issue_type,
                    "context": issue.context,
                    "suggestion": issue.suggestion,
                }
                for issue in report.issues
            ],
        }

        return AgentOutput(
            agent_id="code_only",
            output=report_dict,
            output_type="CitationReport",
            summary=f"Citations: {report.verified}/{report.total_citations} verified ({report.verification_rate:.0%})",
        )

    async def _rcmxt_score(self) -> AgentOutput:
        """Score key findings using RCMXT (heuristic, LLM, or hybrid)."""
        from app.engines.rcmxt_scorer import RCMXTScorer

        scorer = RCMXTScorer(mode=self._rcmxt_mode, llm_layer=self._llm_layer)

        # Load data from prior steps
        search_output = None
        extract_output = None
        synthesis_output = None

        search_result = self._step_results.get("SEARCH")
        if search_result and hasattr(search_result, 'output') and isinstance(search_result.output, dict):
            search_output = search_result.output

        extract_result = self._step_results.get("EXTRACT")
        if extract_result and hasattr(extract_result, 'output') and isinstance(extract_result.output, dict):
            extract_output = extract_result.output

        synth_result = self._step_results.get("SYNTHESIZE")
        if synth_result and hasattr(synth_result, 'output') and isinstance(synth_result.output, dict):
            synthesis_output = synth_result.output

        scorer.load_step_data(search_output, extract_output, synthesis_output)

        if self._rcmxt_mode in ("llm", "hybrid"):
            scores = await scorer.score_all_async()
        else:
            scores = scorer.score_all()

        scores_dicts = [s.model_dump(mode="json") for s in scores]

        return AgentOutput(
            agent_id="code_only",
            output={
                "step": "RCMXT_SCORE",
                "scores": scores_dicts,
                "total_scored": len(scores),
            },
            output_type="RCMXTScores",
            summary=f"RCMXT scored {len(scores)} findings",
        )

    def _store_tier1_results(self, instance: WorkflowInstance) -> None:
        """Store citation report and RCMXT scores on the workflow instance."""
        from app.engines.report_builder import store_tier1_results
        store_tier1_results(instance, self._step_results)

    def _generate_report(self, query: str, instance: WorkflowInstance) -> AgentOutput:
        """Assemble the final W1 report from all step results, including SessionManifest."""
        from app.engines.report_builder import generate_report
        return generate_report(query, instance, self._step_results)
