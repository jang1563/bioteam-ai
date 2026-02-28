"""W10 Drug Discovery Runner — 12-step compound screening + clinical analysis pipeline.

Steps:
  SCOPE[HC] → COMPOUND_SEARCH[ChEMBL] → BIOACTIVITY_PROFILE[ChEMBL]
  → TARGET_IDENTIFICATION[LLM] → CLINICAL_TRIALS_SEARCH[CT.gov]
  → EFFICACY_ANALYSIS[LLM] → SAFETY_PROFILE[ChEMBL] → DC_PRELIMINARY[DC]
  → MECHANISM_REVIEW[LLM] → LITERATURE_COMPARISON[LLM]
  → GRANT_RELEVANCE[LLM] → REPORT

Budget: ~$15 default.
MCP-enabled: uses ChEMBL + ClinicalTrials MCP connectors (gracefully degrades if disabled).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from app.agents.registry import AgentRegistry
from app.api.v1.sse import SSEHub
from app.config import settings
from app.models.messages import ContextPackage
from app.models.w10_drug_discovery import (
    DrugDiscoveryScope,
    EfficacyAnalysis,
    GrantRelevanceAssessment,
    LiteratureComparison,
    MechanismReview,
    W10DrugDiscoveryResult,
)
from app.models.workflow import WorkflowInstance, WorkflowStepDef
from app.workflows.engine import WorkflowEngine

logger = logging.getLogger(__name__)


# === Step Definitions ===

W10_STEPS: list[WorkflowStepDef] = [
    WorkflowStepDef(
        id="SCOPE",
        agent_id="research_director",
        output_schema="DrugDiscoveryScope",
        next_step="COMPOUND_SEARCH",
        estimated_cost=0.003,
        is_human_checkpoint=True,
        interaction_type="HC",
    ),
    WorkflowStepDef(
        id="COMPOUND_SEARCH",
        agent_id="code_only",
        output_schema="dict",
        next_step="BIOACTIVITY_PROFILE",
        estimated_cost=0.005,  # MCP call cost
    ),
    WorkflowStepDef(
        id="BIOACTIVITY_PROFILE",
        agent_id="code_only",
        output_schema="dict",
        next_step="TARGET_IDENTIFICATION",
        estimated_cost=0.005,
    ),
    WorkflowStepDef(
        id="TARGET_IDENTIFICATION",
        agent_id="knowledge_manager",
        output_schema="dict",
        next_step="CLINICAL_TRIALS_SEARCH",
        estimated_cost=0.003,
    ),
    WorkflowStepDef(
        id="CLINICAL_TRIALS_SEARCH",
        agent_id="code_only",
        output_schema="dict",
        next_step="EFFICACY_ANALYSIS",
        estimated_cost=0.005,
    ),
    WorkflowStepDef(
        id="EFFICACY_ANALYSIS",
        agent_id="research_director",
        output_schema="EfficacyAnalysis",
        next_step="SAFETY_PROFILE",
        estimated_cost=0.005,
    ),
    WorkflowStepDef(
        id="SAFETY_PROFILE",
        agent_id="code_only",
        output_schema="dict",
        next_step="DC_PRELIMINARY",
        estimated_cost=0.003,
    ),
    WorkflowStepDef(
        id="DC_PRELIMINARY",
        agent_id="code_only",
        output_schema="dict",
        next_step="MECHANISM_REVIEW",
        estimated_cost=0.0,
        interaction_type="DC",
        dc_auto_continue_minutes=30,
    ),
    WorkflowStepDef(
        id="MECHANISM_REVIEW",
        agent_id="methodology_reviewer",
        output_schema="MechanismReview",
        next_step="LITERATURE_COMPARISON",
        estimated_cost=0.005,
    ),
    WorkflowStepDef(
        id="LITERATURE_COMPARISON",
        agent_id="knowledge_manager",
        output_schema="LiteratureComparison",
        next_step="GRANT_RELEVANCE",
        estimated_cost=0.004,
    ),
    WorkflowStepDef(
        id="GRANT_RELEVANCE",
        agent_id="grant_writer",
        output_schema="GrantRelevanceAssessment",
        next_step="REPORT",
        estimated_cost=0.002,
    ),
    WorkflowStepDef(
        id="REPORT",
        agent_id="code_only",
        output_schema="dict",
        next_step=None,
        estimated_cost=0.0,
    ),
]


class W10DrugDiscoveryRunner:
    """Orchestrates the W10 Drug Discovery 12-step pipeline.

    Uses ChEMBL MCP for compound/bioactivity/ADMET data and
    ClinicalTrials MCP for trial data. Falls back gracefully
    when settings.mcp_enabled=False.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        engine: WorkflowEngine | None = None,
        sse_hub: SSEHub | None = None,
        persist_fn=None,
        lab_kb=None,
        checkpoint_manager=None,  # CheckpointManager — optional, for step persistence
    ) -> None:
        self._registry = registry
        self._engine = engine
        self._sse = sse_hub
        self._persist = persist_fn
        self._lab_kb = lab_kb
        self._checkpoint_manager = checkpoint_manager

        # Accumulated results across steps
        self._step_results: dict[str, Any] = {}
        self._total_tokens_in: int = 0
        self._total_tokens_out: int = 0

        # MCP clients (lazy init on first use)
        self._chembl: Any | None = None
        self._ct: Any | None = None

    def _get_chembl(self):
        if self._chembl is None and settings.mcp_enabled:
            try:
                from app.integrations.mcp_chembl import MCPChEMBLClient
                self._chembl = MCPChEMBLClient()
            except Exception as e:
                logger.warning("W10: ChEMBL MCP init failed: %s", e)
        return self._chembl

    def _get_ct(self):
        if self._ct is None and settings.mcp_enabled:
            try:
                from app.integrations.mcp_clinical_trials import MCPClinicalTrialsClient
                self._ct = MCPClinicalTrialsClient()
            except Exception as e:
                logger.warning("W10: ClinicalTrials MCP init failed: %s", e)
        return self._ct

    async def run(self, instance: WorkflowInstance) -> WorkflowInstance:
        """Run the full W10 pipeline."""
        self._step_results = {}
        self._total_tokens_in = 0
        self._total_tokens_out = 0

        instance.state = "RUNNING"
        query = instance.query

        step_index = {s.id: s for s in W10_STEPS}
        current_step_id = W10_STEPS[0].id

        while current_step_id:
            step = step_index[current_step_id]
            instance.current_step = step.id

            # HC check: pause and wait for human approval
            if step.interaction_type == "HC" and step.id != W10_STEPS[0].id:
                instance.state = "WAITING_HUMAN"
                if self._persist:
                    await self._persist(instance)
                return instance  # resume via resume endpoint

            # DC check: broadcast and auto-continue
            if step.interaction_type == "DC":
                if self._sse:
                    await self._sse.broadcast_dict(
                        event_type="workflow.direction_check",
                        workflow_id=instance.id,
                        step_id=step.id,
                        auto_continue_minutes=step.dc_auto_continue_minutes,
                    )
                # Record DC as instant step
                instance.step_history.append({
                    "step_id": step.id,
                    "agent_id": "direction_check",
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "duration_ms": 0,
                })
                current_step_id = step.next_step
                if self._persist:
                    await self._persist(instance)
                continue

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
                self._step_results[step.id] = result

                instance.step_history.append({
                    "step_id": step.id,
                    "agent_id": step.agent_id if isinstance(step.agent_id, str) else "multi",
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "duration_ms": duration_ms,
                })

            except Exception as e:
                logger.error("W10 step %s failed: %s", step.id, e, exc_info=True)
                duration_ms = int((time.time() - start_time) * 1000)
                instance.step_history.append({
                    "step_id": step.id,
                    "agent_id": step.agent_id if isinstance(step.agent_id, str) else "multi",
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "duration_ms": duration_ms,
                    "error": str(e),
                })
                instance.state = "FAILED"
                if self._persist:
                    await self._persist(instance)
                return instance

            # Broadcast step complete
            if self._sse:
                await self._sse.broadcast_dict(
                    event_type="workflow.step_complete",
                    workflow_id=instance.id,
                    step_id=step.id,
                )

            current_step_id = step.next_step
            if self._persist:
                await self._persist(instance)

        instance.state = "COMPLETED"
        if self._persist:
            await self._persist(instance)
        return instance

    async def _run_step(self, step: WorkflowStepDef, query: str, instance: WorkflowInstance) -> Any:
        """Dispatch a single step to the appropriate handler."""
        if step.id == "SCOPE":
            return await self._step_scope(query, instance)
        elif step.id == "COMPOUND_SEARCH":
            return await self._step_compound_search(query)
        elif step.id == "BIOACTIVITY_PROFILE":
            return await self._step_bioactivity(query)
        elif step.id == "TARGET_IDENTIFICATION":
            return await self._step_target_id(query)
        elif step.id == "CLINICAL_TRIALS_SEARCH":
            return await self._step_clinical_trials(query)
        elif step.id == "EFFICACY_ANALYSIS":
            return await self._step_efficacy(query)
        elif step.id == "SAFETY_PROFILE":
            return await self._step_safety(query)
        elif step.id == "MECHANISM_REVIEW":
            return await self._step_mechanism(query)
        elif step.id == "LITERATURE_COMPARISON":
            return await self._step_literature(query)
        elif step.id == "GRANT_RELEVANCE":
            return await self._step_grant(query)
        elif step.id == "REPORT":
            return await self._step_report(query, instance)
        return {}

    async def _step_scope(self, query: str, instance: WorkflowInstance) -> DrugDiscoveryScope:
        agent = self._registry.get("research_director")
        ctx = ContextPackage(
            task_description=(
                f"Define the drug discovery research scope for: {query}\n"
                "Identify: research question, target compound or compound class, therapeutic area, "
                "key objectives (3-5), and initial search strategy. "
                "Be specific about what compound(s) to investigate."
            ),
            metadata={"workflow_id": instance.id},
        )
        out = await agent.run(context=ctx)
        self._track_tokens(out)
        raw = out.output if isinstance(out.output, dict) else {}
        return DrugDiscoveryScope(
            research_question=raw.get("research_question", query),
            target_compound_or_class=raw.get("target_compound_or_class", query),
            therapeutic_area=raw.get("therapeutic_area", ""),
            key_objectives=raw.get("key_objectives", []),
            search_strategy=raw.get("search_strategy", ""),
        )

    async def _step_compound_search(self, query: str) -> dict:
        chembl = self._get_chembl()
        if chembl is None:
            logger.info("W10 COMPOUND_SEARCH: MCP disabled, using fallback text.")
            return {"compounds": [], "source": "fallback", "summary": f"Compound search for: {query}"}

        result = await chembl.compound_search(query, max_results=10)
        self._total_tokens_in += result.input_tokens
        self._total_tokens_out += result.output_tokens
        return {"source": "chembl_mcp", "summary": result.llm_summary, "compounds": []}

    async def _step_bioactivity(self, query: str) -> dict:
        chembl = self._get_chembl()
        if chembl is None:
            return {"activities": [], "source": "fallback"}

        result = await chembl.get_bioactivity(query, max_results=15)
        self._total_tokens_in += result.input_tokens
        self._total_tokens_out += result.output_tokens
        return {"source": "chembl_mcp", "summary": result.llm_summary, "activities": []}

    async def _step_target_id(self, query: str) -> dict:
        agent = self._registry.get("knowledge_manager")
        compound_summary = self._step_results.get("COMPOUND_SEARCH", {}).get("summary", "")
        bioactivity_summary = self._step_results.get("BIOACTIVITY_PROFILE", {}).get("summary", "")
        ctx = ContextPackage(
            task_description=(
                f"Identify biological targets for: {query}\n"
                "Based on the compound and bioactivity data, identify the primary biological targets. "
                "List target names, gene symbols, and relevance to the therapeutic area.\n"
                f"Compound data: {compound_summary[:800]}\n"
                f"Bioactivity data: {bioactivity_summary[:800]}"
            ),
            metadata={
                "compound_data": compound_summary[:1000],
                "bioactivity_data": bioactivity_summary[:1000],
            },
        )
        out = await agent.run(context=ctx)
        self._track_tokens(out)
        summary = out.summary or (str(out.output) if out.output else "")
        return {"target_summary": summary}

    async def _step_clinical_trials(self, query: str) -> dict:
        ct = self._get_ct()
        if ct is None:
            return {"trials": [], "source": "fallback"}

        result = await ct.search_trials(condition=query, max_results=10)
        self._total_tokens_in += result.input_tokens
        self._total_tokens_out += result.output_tokens
        return {"source": "ct_mcp", "summary": result.llm_summary, "trials": []}

    async def _step_efficacy(self, query: str) -> EfficacyAnalysis:
        agent = self._registry.get("research_director")
        compound_data = self._step_results.get("COMPOUND_SEARCH", {}).get("summary", "")
        bioactivity_data = self._step_results.get("BIOACTIVITY_PROFILE", {}).get("summary", "")
        trial_data = self._step_results.get("CLINICAL_TRIALS_SEARCH", {}).get("summary", "")
        ctx = ContextPackage(
            task_description=(
                f"Assess efficacy of {query} based on available data.\n"
                "Synthesize the compound bioactivity and clinical trial data to assess efficacy. "
                "Provide: summary, key findings, potency assessment (strong/moderate/weak/unknown), "
                "selectivity notes, and known limitations.\n"
                f"Compound data: {compound_data[:600]}\n"
                f"Bioactivity: {bioactivity_data[:600]}\n"
                f"Trial data: {trial_data[:600]}"
            ),
            metadata={
                "compound_data": compound_data[:800],
                "bioactivity_data": bioactivity_data[:800],
                "trial_data": trial_data[:800],
            },
        )
        out = await agent.run(context=ctx)
        self._track_tokens(out)
        raw = out.output if isinstance(out.output, dict) else {}
        return EfficacyAnalysis(
            summary=raw.get("summary", out.summary or ""),
            key_findings=raw.get("key_findings", []),
            potency_assessment=raw.get("potency_assessment", "unknown"),
            selectivity_notes=raw.get("selectivity_notes", ""),
            limitations=raw.get("limitations", []),
        )

    async def _step_safety(self, query: str) -> dict:
        chembl = self._get_chembl()
        if chembl is None:
            return {"admet_summary": "ADMET data unavailable (MCP disabled).", "source": "fallback"}

        result = await chembl.get_admet(query)
        self._total_tokens_in += result.input_tokens
        self._total_tokens_out += result.output_tokens
        return {"source": "chembl_mcp", "admet_summary": result.llm_summary}

    async def _step_mechanism(self, query: str) -> MechanismReview:
        agent = self._registry.get("methodology_reviewer")
        compound_data = self._step_results.get("COMPOUND_SEARCH", {}).get("summary", "")
        bioactivity_data = self._step_results.get("BIOACTIVITY_PROFILE", {}).get("summary", "")
        ctx = ContextPackage(
            task_description=(
                f"Review mechanism of action for {query}.\n"
                "Based on compound structure and bioactivity data, identify: primary mechanism, "
                "target pathway, on-target evidence, off-target risks, and mechanistic gaps.\n"
                f"Compound data: {compound_data[:600]}\n"
                f"Bioactivity: {bioactivity_data[:600]}"
            ),
            metadata={
                "compound_data": compound_data[:800],
                "bioactivity_data": bioactivity_data[:800],
            },
        )
        out = await agent.run(context=ctx)
        self._track_tokens(out)
        raw = out.output if isinstance(out.output, dict) else {}
        return MechanismReview(
            primary_mechanism=raw.get("primary_mechanism", out.summary or ""),
            target_pathway=raw.get("target_pathway", ""),
            on_target_evidence=raw.get("on_target_evidence", []),
            off_target_risks=raw.get("off_target_risks", []),
            mechanistic_gaps=raw.get("mechanistic_gaps", []),
        )

    async def _step_literature(self, query: str) -> LiteratureComparison:
        agent = self._registry.get("knowledge_manager")
        ctx = ContextPackage(
            task_description=(
                f"Compare {query} to similar compounds and existing literature.\n"
                "Search the knowledge base for similar compounds, related mechanisms, and prior art. "
                "Assess novelty: what makes this compound distinct from known alternatives? "
                "List similar compounds, key differences, and relevant papers."
            ),
            metadata={},
        )
        out = await agent.run(context=ctx)
        self._track_tokens(out)
        raw = out.output if isinstance(out.output, dict) else {}
        return LiteratureComparison(
            similar_compounds=raw.get("similar_compounds", []),
            novelty_assessment=raw.get("novelty_assessment", out.summary or ""),
            key_differences=raw.get("key_differences", []),
            relevant_papers=raw.get("relevant_papers", []),
        )

    async def _step_grant(self, query: str) -> GrantRelevanceAssessment:
        agent = self._registry.get("grant_writer")
        efficacy = self._step_results.get("EFFICACY_ANALYSIS")
        efficacy_summary = efficacy.summary if isinstance(efficacy, EfficacyAnalysis) else ""
        ctx = ContextPackage(
            task_description=(
                f"Assess grant funding potential for this drug discovery project: {query}\n"
                "Provide: relevance score (0.0-1.0), relevant funding agencies (NIH, NCI, etc.), "
                "mechanism fit (R01/R21/SBIR/etc.), innovation statement, and rationale.\n"
                f"Efficacy summary: {efficacy_summary[:600]}"
            ),
            metadata={"efficacy_summary": efficacy_summary[:600]},
        )
        out = await agent.run(context=ctx)
        self._track_tokens(out)
        raw = out.output if isinstance(out.output, dict) else {}
        return GrantRelevanceAssessment(
            relevance_score=float(raw.get("relevance_score", 0.5)),
            funding_agencies=raw.get("funding_agencies", []),
            mechanism_fit=raw.get("mechanism_fit", ""),
            innovation_statement=raw.get("innovation_statement", ""),
            rationale=raw.get("rationale", out.summary or ""),
        )

    async def _step_report(self, query: str, instance: WorkflowInstance) -> dict:
        from app.engines.w10_report_builder import build_w10_report

        scope = self._step_results.get("SCOPE")
        efficacy = self._step_results.get("EFFICACY_ANALYSIS")
        mechanism = self._step_results.get("MECHANISM_REVIEW")
        literature = self._step_results.get("LITERATURE_COMPARISON")
        grant = self._step_results.get("GRANT_RELEVANCE")
        target_data = self._step_results.get("TARGET_IDENTIFICATION", {})
        safety_data = self._step_results.get("SAFETY_PROFILE", {})

        result = W10DrugDiscoveryResult(
            workflow_id=instance.id,
            query=query,
            scope=scope if isinstance(scope, DrugDiscoveryScope) else None,
            compound_profiles=[],
            bioactivity_data=[],
            target_summary=target_data.get("target_summary", ""),
            trial_summaries=[],
            efficacy_analysis=efficacy if isinstance(efficacy, EfficacyAnalysis) else None,
            safety_profile_summary=safety_data.get("admet_summary", ""),
            mechanism_review=mechanism if isinstance(mechanism, MechanismReview) else None,
            literature_comparison=literature if isinstance(literature, LiteratureComparison) else None,
            grant_relevance=grant if isinstance(grant, GrantRelevanceAssessment) else None,
            cost_usd=0.0,
            mcp_used=settings.mcp_enabled,
        )

        report_md = build_w10_report(result)
        result.report_markdown = report_md

        # Store report in session_manifest
        instance.session_manifest["w10_report"] = report_md[:4000]

        return {"report_markdown": report_md, "status": "complete"}

    def _track_tokens(self, out: Any) -> None:
        if hasattr(out, "tokens_used") and isinstance(out.tokens_used, dict):
            self._total_tokens_in += out.tokens_used.get("input", 0)
            self._total_tokens_out += out.tokens_used.get("output", 0)
