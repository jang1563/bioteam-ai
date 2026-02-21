"""W1 Literature Review Runner — 10-step pipeline for systematic literature review.

Steps:
  SCOPE → SEARCH → SCREEN → EXTRACT → NEGATIVE_CHECK → SYNTHESIZE
    RD      KM      T02       T02       LabKB(code)       RD(Opus)
  → [HUMAN CHECKPOINT]
  → CITATION_CHECK → RCMXT_SCORE → NOVELTY_CHECK → REPORT
      code              code            KM            code(+SessionManifest)

Code-only steps: NEGATIVE_CHECK, CITATION_CHECK, RCMXT_SCORE, REPORT.
SYNTHESIZE has a human checkpoint for Director review.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.agents.registry import AgentRegistry
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from app.models.workflow import WorkflowInstance, WorkflowStepDef
from app.workflows.engine import WorkflowEngine
from app.workflows.runners.async_runner import AsyncWorkflowRunner
from app.api.v1.sse import SSEHub

logger = logging.getLogger(__name__)


# === Step Definitions ===

W1_STEPS: list[WorkflowStepDef] = [
    WorkflowStepDef(
        id="SCOPE",
        agent_id="research_director",
        output_schema="SynthesisReport",
        next_step="SEARCH",
        estimated_cost=0.05,
    ),
    WorkflowStepDef(
        id="SEARCH",
        agent_id="knowledge_manager",
        output_schema="LiteratureSearchResult",
        next_step="SCREEN",
        estimated_cost=0.10,
    ),
    WorkflowStepDef(
        id="SCREEN",
        agent_id="t02_transcriptomics",
        output_schema="ScreeningResult",
        next_step="EXTRACT",
        estimated_cost=0.15,
    ),
    WorkflowStepDef(
        id="EXTRACT",
        agent_id="t02_transcriptomics",
        output_schema="ExtractionResult",
        next_step="NEGATIVE_CHECK",
        estimated_cost=0.15,
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
        next_step="CITATION_CHECK",
        is_human_checkpoint=True,
        estimated_cost=0.50,
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
        next_step="NOVELTY_CHECK",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="NOVELTY_CHECK",
        agent_id="knowledge_manager",
        output_schema="NoveltyAssessment",
        next_step="REPORT",
        estimated_cost=0.10,
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
    ) -> None:
        self.registry = registry
        self.engine = engine or WorkflowEngine()
        self.sse_hub = sse_hub
        self.lab_kb = lab_kb
        self._persist_fn = persist_fn
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

            if step.id in ("NEGATIVE_CHECK", "CITATION_CHECK", "RCMXT_SCORE", "REPORT"):
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
            "step_results": {k: v.model_dump() if hasattr(v, 'model_dump') else v
                             for k, v in self._step_results.items()},
            "paused_at": instance.current_step if instance.state == "WAITING_HUMAN" else None,
        }

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
        remaining_ids = ("CITATION_CHECK", "RCMXT_SCORE", "NOVELTY_CHECK", "REPORT")
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

            if step.id in ("CITATION_CHECK", "RCMXT_SCORE", "REPORT"):
                result = await self._run_code_step(step, query, instance)
                self._step_results[step.id] = result
                self.engine.advance(instance, step.id)
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

        # Store Tier 1 results on instance before completing
        self._store_tier1_results(instance)

        # Mark completed if all steps done
        if instance.state == "RUNNING":
            self.engine.complete(instance)
            await self._persist(instance)

        return {
            "instance": instance,
            "step_results": {k: v.model_dump() if hasattr(v, 'model_dump') else v
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

        context = ContextPackage(
            task_description=query,
            prior_step_outputs=prior_outputs,
        )

        # Call the specific method on the agent
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
        """Run a code-only step."""
        if step.id == "NEGATIVE_CHECK":
            return await self._negative_check(query)
        elif step.id == "CITATION_CHECK":
            return self._citation_check()
        elif step.id == "RCMXT_SCORE":
            return self._rcmxt_score()
        elif step.id == "REPORT":
            return self._generate_report(query, instance)
        return AgentOutput(agent_id="code_only", error=f"Unknown code step: {step.id}")

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

    def _rcmxt_score(self) -> AgentOutput:
        """Score key findings using RCMXT heuristics."""
        from app.engines.rcmxt_scorer import RCMXTScorer

        scorer = RCMXTScorer()

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
        citation_result = self._step_results.get("CITATION_CHECK")
        if citation_result and hasattr(citation_result, 'output') and isinstance(citation_result.output, dict):
            instance.citation_report = citation_result.output

        rcmxt_result = self._step_results.get("RCMXT_SCORE")
        if rcmxt_result and hasattr(rcmxt_result, 'output') and isinstance(rcmxt_result.output, dict):
            instance.rcmxt_scores = rcmxt_result.output.get("scores", [])

    def _generate_report(self, query: str, instance: WorkflowInstance) -> AgentOutput:
        """Assemble the final W1 report from all step results, including SessionManifest."""
        report = {
            "title": f"W1 Literature Review: {query}",
            "query": query,
            "workflow_id": instance.id,
            "steps_completed": list(self._step_results.keys()),
            "budget_used": instance.budget_total - instance.budget_remaining,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Add step summaries
        for step_id, result in self._step_results.items():
            if hasattr(result, 'summary'):
                report[f"{step_id.lower()}_summary"] = result.summary
            elif hasattr(result, 'output') and result.output:
                report[f"{step_id.lower()}_summary"] = str(result.output)[:200]

        # Build and attach SessionManifest
        manifest = self._build_session_manifest(query, instance)
        report["session_manifest"] = manifest
        instance.session_manifest = manifest

        return AgentOutput(
            agent_id="code_only",
            output=report,
            output_type="W1Report",
            summary=f"W1 Report: {query[:100]}",
        )

    def _build_session_manifest(self, query: str, instance: WorkflowInstance) -> dict:
        """Aggregate LLM metadata from all step results into a SessionManifest."""
        from app.models.evidence import SessionManifest, PRISMAFlow

        llm_calls = []
        total_input = 0
        total_output = 0
        total_cost = 0.0
        model_versions: set[str] = set()

        for step_id, result in self._step_results.items():
            if not hasattr(result, 'model_version'):
                continue
            if result.model_version and result.model_version != "deterministic":
                model_versions.add(result.model_version)
                llm_calls.append({
                    "step_id": step_id,
                    "agent_id": result.agent_id,
                    "model_version": result.model_version,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "cached_input_tokens": result.cached_input_tokens,
                    "cost": result.cost,
                })
                total_input += result.input_tokens
                total_output += result.output_tokens
                total_cost += result.cost

        prisma = self._build_prisma_flow()

        manifest = SessionManifest(
            workflow_id=instance.id,
            template=instance.template,
            query=query,
            started_at=instance.created_at,
            completed_at=datetime.now(timezone.utc),
            llm_calls=llm_calls,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_cost=total_cost,
            model_versions=sorted(model_versions),
            seed_papers=instance.seed_papers,
            system_version="v0.5",
            prisma=prisma,
        )
        return manifest.model_dump(mode="json")

    def _build_prisma_flow(self) -> "PRISMAFlow":
        """Build PRISMA flow diagram data from step results."""
        from app.models.evidence import PRISMAFlow

        prisma = PRISMAFlow()

        search_result = self._step_results.get("SEARCH")
        if search_result and hasattr(search_result, 'output') and isinstance(search_result.output, dict):
            prisma.records_identified = search_result.output.get("total_found", 0)
            prisma.records_from_databases = search_result.output.get("total_found", 0)

        screen_result = self._step_results.get("SCREEN")
        if screen_result and hasattr(screen_result, 'output') and isinstance(screen_result.output, dict):
            prisma.records_screened = screen_result.output.get("total_screened", 0)
            prisma.records_excluded_screening = screen_result.output.get("excluded", 0)

        extract_result = self._step_results.get("EXTRACT")
        if extract_result and hasattr(extract_result, 'output') and isinstance(extract_result.output, dict):
            prisma.full_text_assessed = extract_result.output.get("total_extracted", 0)
            prisma.studies_included = extract_result.output.get("total_extracted", 0)

        neg_result = self._step_results.get("NEGATIVE_CHECK")
        if neg_result and hasattr(neg_result, 'output') and isinstance(neg_result.output, dict):
            prisma.negative_results_found = neg_result.output.get("negative_results_found", 0)

        return prisma
