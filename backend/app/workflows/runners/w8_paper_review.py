"""W8 Paper Review Runner — 12-step pipeline for systematic peer review.

Steps:
  INGEST → PARSE_SECTIONS → EXTRACT_CLAIMS → CITE_VALIDATION
    code       code             ClaimExtractor     code(CitationValidator)
  → BACKGROUND_LIT → INTEGRITY_AUDIT → CONTRADICTION_CHECK
      KM(Sonnet)      code(DIA)          AE(Sonnet)
  → METHODOLOGY_REVIEW → EVIDENCE_GRADE → [HUMAN_CHECKPOINT]
      MethodReviewer(Opus)  code(RCMXT)       pause
  → SYNTHESIZE_REVIEW → REPORT
      RD(Opus)            code(report_builder)

Code-only steps: INGEST, PARSE_SECTIONS, CITE_VALIDATION, INTEGRITY_AUDIT,
                 EVIDENCE_GRADE, REPORT.
HUMAN_CHECKPOINT pauses for reviewer input before final synthesis.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
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
    input_rate = COST_PER_1K_INPUT.get(model_tier, 0.0)
    output_rate = COST_PER_1K_OUTPUT.get(model_tier, 0.0)
    return (est_input_tokens / 1000) * input_rate + (est_output_tokens / 1000) * output_rate


# === Step Definitions ===

W8_STEPS: list[WorkflowStepDef] = [
    WorkflowStepDef(
        id="INGEST",
        agent_id="code_only",
        output_schema="dict",
        next_step="PARSE_SECTIONS",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="PARSE_SECTIONS",
        agent_id="code_only",
        output_schema="ParsedPaper",
        next_step="EXTRACT_CLAIMS",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="EXTRACT_CLAIMS",
        agent_id="claim_extractor",
        output_schema="PaperClaimsExtraction",
        next_step="CITE_VALIDATION",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=8000, est_output_tokens=2000),
    ),
    WorkflowStepDef(
        id="CITE_VALIDATION",
        agent_id="code_only",
        output_schema="dict",
        next_step="BACKGROUND_LIT",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="BACKGROUND_LIT",
        agent_id="knowledge_manager",
        output_schema="LiteratureSearchResult",
        next_step="NOVELTY_CHECK",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=2000, est_output_tokens=500),
    ),
    WorkflowStepDef(
        id="NOVELTY_CHECK",
        agent_id="code_only",
        output_schema="NoveltyAssessment",
        next_step="INTEGRITY_AUDIT",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=6000, est_output_tokens=2000),
    ),
    WorkflowStepDef(
        id="INTEGRITY_AUDIT",
        agent_id="code_only",
        output_schema="dict",
        next_step="CONTRADICTION_CHECK",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="CONTRADICTION_CHECK",
        agent_id="ambiguity_engine",
        output_schema="ContradictionAnalysis",
        next_step="METHODOLOGY_REVIEW",
        estimated_cost=_estimate_step_cost("sonnet", est_input_tokens=4000, est_output_tokens=1500),
    ),
    WorkflowStepDef(
        id="METHODOLOGY_REVIEW",
        agent_id="methodology_reviewer",
        output_schema="MethodologyAssessment",
        next_step="EVIDENCE_GRADE",
        estimated_cost=_estimate_step_cost("opus", est_input_tokens=10000, est_output_tokens=3000),
    ),
    WorkflowStepDef(
        id="EVIDENCE_GRADE",
        agent_id="code_only",
        output_schema="dict",
        next_step="HUMAN_CHECKPOINT",
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="HUMAN_CHECKPOINT",
        agent_id="code_only",
        output_schema="dict",
        next_step="SYNTHESIZE_REVIEW",
        is_human_checkpoint=True,
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="SYNTHESIZE_REVIEW",
        agent_id="research_director",
        output_schema="PeerReviewSynthesis",
        next_step="REPORT",
        estimated_cost=_estimate_step_cost("opus", est_input_tokens=12000, est_output_tokens=4000),
    ),
    WorkflowStepDef(
        id="REPORT",
        agent_id="code_only",
        output_schema="W8PeerReviewReport",
        next_step=None,
        estimated_cost=0.0,
    ),
]

# Method routing for agent steps
_METHOD_MAP: dict[str, tuple[str, str]] = {
    "EXTRACT_CLAIMS": ("claim_extractor", "run"),
    "BACKGROUND_LIT": ("knowledge_manager", "search_literature"),
    "CONTRADICTION_CHECK": ("ambiguity_engine", "detect_contradictions"),
    "METHODOLOGY_REVIEW": ("methodology_reviewer", "run"),
    "SYNTHESIZE_REVIEW": ("research_director", "synthesize_peer_review"),
}

# Code-only steps (including hybrid steps with internal LLM calls)
_CODE_STEPS = frozenset({
    "INGEST", "PARSE_SECTIONS", "CITE_VALIDATION",
    "NOVELTY_CHECK", "INTEGRITY_AUDIT", "EVIDENCE_GRADE", "HUMAN_CHECKPOINT", "REPORT",
})


class W8PaperReviewRunner:
    """Orchestrates the W8 Paper Review pipeline.

    12-step pipeline from PDF ingestion to structured peer review report.
    Reuses existing engines (CitationValidator, RCMXTScorer, ContradictionDetector)
    and agents (KnowledgeManager, ResearchDirector, AmbiguityEngine).

    Usage:
        runner = W8PaperReviewRunner(registry=registry, llm_layer=llm)
        result = await runner.run(pdf_path="/path/to/paper.pdf", budget=3.0)
    """

    def __init__(
        self,
        registry: AgentRegistry,
        engine: WorkflowEngine | None = None,
        sse_hub: SSEHub | None = None,
        persist_fn=None,
        llm_layer=None,
        memory=None,
    ) -> None:
        self.registry = registry
        self.engine = engine or WorkflowEngine()
        self.sse_hub = sse_hub
        self._persist_fn = persist_fn
        self._llm_layer = llm_layer
        self._memory = memory
        self._step_results: dict[str, AgentOutput] = {}
        self._pdf_bytes: bytes = b""
        self._file_path: Path | None = None
        self._paper_title: str = ""
        self._parsed_paper = None  # ParsedPaper

    async def _persist(self, instance: WorkflowInstance) -> None:
        if self._persist_fn:
            await self._persist_fn(instance)

    @observe(name="workflow.w8_paper_review")
    async def run(
        self,
        pdf_path: str = "",
        instance: WorkflowInstance | None = None,
        budget: float = 3.0,
        query: str = "",
        skip_human_checkpoint: bool = False,
    ) -> dict[str, Any]:
        """Execute the full W8 pipeline.

        Args:
            pdf_path: Path to the paper PDF file.
            instance: Optional pre-created WorkflowInstance.
            budget: Maximum budget in USD.
            query: Optional query override (defaults to paper title).

        Returns:
            Dict with step_results, instance, and paused_at.
        """
        if instance is None:
            instance = WorkflowInstance(
                template="W8",
                query=query or pdf_path,
                budget_total=budget,
                budget_remaining=budget,
            )

        self.engine.start(instance, first_step="INGEST")
        await self._persist(instance)
        self._step_results = {}

        for step in W8_STEPS:
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

            step_start = time.time()

            if step.id in _CODE_STEPS:
                result = await self._run_code_step(step, pdf_path, instance)
                step_ms = int((time.time() - step_start) * 1000)
                self._step_results[step.id] = result

                # Check for code step failure
                if not result.is_success:
                    self.engine.fail(instance, result.error or f"Code step {step.id} failed")
                    await self._persist(instance)
                    break

                # Deduct cost for hybrid code steps that make LLM calls (e.g., NOVELTY_CHECK)
                if result.cost > 0:
                    self.engine.deduct_budget(instance, result.cost)

                self.engine.advance(
                    instance, step.id,
                    step_result={"type": "code_only"},
                    agent_id=result.agent_id,
                    status="completed",
                    duration_ms=step_ms,
                    cost=result.cost,
                )
                await self._persist(instance)

                # Human checkpoint
                if step.is_human_checkpoint and not skip_human_checkpoint:
                    self.engine.request_human(instance)
                    await self._persist(instance)
                    logger.info("W8 paused at %s for human review", step.id)
                    break

            elif step.id in _METHOD_MAP:
                result = await self._run_agent_step(step, instance)
                step_ms = int((time.time() - step_start) * 1000)
                self._step_results[step.id] = result

                if not result.is_success:
                    # Graceful degradation for optional agents
                    agent_id = _METHOD_MAP[step.id][0]
                    agent_obj = self.registry.get(agent_id)
                    if agent_obj and agent_obj.spec.degradation_mode == "skip":
                        logger.warning("Skipping failed %s (degradation=skip): %s", step.id, result.error)
                        self.engine.advance(
                            instance, step.id,
                            agent_id=agent_id,
                            status="skipped",
                            duration_ms=step_ms,
                        )
                        await self._persist(instance)
                        continue
                    self.engine.fail(instance, result.error or "Agent step failed")
                    await self._persist(instance)
                    break

                if result.cost > 0:
                    self.engine.deduct_budget(instance, result.cost)

                self.engine.advance(
                    instance, step.id,
                    agent_id=step.agent_id,
                    status="completed",
                    duration_ms=step_ms,
                    cost=result.cost,
                )
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

        return {
            "instance": instance,
            "step_results": {
                k: v.model_dump(mode="json") if hasattr(v, "model_dump") else v
                for k, v in self._step_results.items()
            },
            "paused_at": instance.current_step if instance.state == "WAITING_HUMAN" else None,
        }

    @observe(name="workflow.w8_paper_review.resume")
    async def resume_after_human(
        self,
        instance: WorkflowInstance,
        query: str = "",
    ) -> dict[str, Any]:
        """Resume after human review at HUMAN_CHECKPOINT.

        Continues from SYNTHESIZE_REVIEW through REPORT.
        """
        if instance.state != "RUNNING":
            self.engine.resume(instance)

        remaining_steps = [s for s in W8_STEPS if s.id in ("SYNTHESIZE_REVIEW", "REPORT")]

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

            step_start = time.time()

            if step.id == "REPORT":
                result = await self._run_code_step(step, "", instance)
                step_ms = int((time.time() - step_start) * 1000)
                self._step_results[step.id] = result
                self.engine.advance(
                    instance, step.id,
                    agent_id="code_only",
                    status="completed",
                    duration_ms=step_ms,
                )
                await self._persist(instance)
            else:
                result = await self._run_agent_step(step, instance)
                step_ms = int((time.time() - step_start) * 1000)
                self._step_results[step.id] = result

                if not result.is_success:
                    self.engine.fail(instance, result.error or "Agent step failed")
                    await self._persist(instance)
                    break

                if result.cost > 0:
                    self.engine.deduct_budget(instance, result.cost)

                self.engine.advance(
                    instance, step.id,
                    agent_id=step.agent_id,
                    status="completed",
                    duration_ms=step_ms,
                    cost=result.cost,
                )
                await self._persist(instance)

            if self.sse_hub:
                await self.sse_hub.broadcast_dict(
                    event_type="workflow.step_completed",
                    workflow_id=instance.id,
                    step_id=step.id,
                    agent_id=step.agent_id,
                )

        # Store results on instance
        self._store_results(instance)

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

    # === Agent Steps ===

    async def _run_agent_step(
        self,
        step: WorkflowStepDef,
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

        # Build context from prior steps — dict for task description building
        prior_outputs = {}
        for sid, result in self._step_results.items():
            if hasattr(result, "output") and result.output:
                prior_outputs[sid] = result.output

        # Build task description based on step
        task_desc = self._build_task_description(step.id, prior_outputs)

        # Convert to list[dict] format for ContextPackage
        prior_outputs_list = [
            {"step_id": sid, "output": output}
            for sid, output in prior_outputs.items()
        ]

        context = ContextPackage(
            task_description=task_desc,
            prior_step_outputs=prior_outputs_list,
        )

        # For SYNTHESIZE_REVIEW, add all analysis results to context
        if step.id == "SYNTHESIZE_REVIEW":
            context.metadata["paper_title"] = self._paper_title
            context.metadata["review_mode"] = "peer_review"

        try:
            # For steps using `run()`, call execute() (which wraps run with retry)
            if method_name == "run":
                return await agent.execute(context)

            # For named methods (search_literature, detect_contradictions, synthesize)
            method = getattr(agent, method_name, None)
            if method is None:
                return AgentOutput(
                    agent_id=agent_id,
                    error=f"Agent {agent_id} has no method {method_name}",
                )
            return await method(context)
        except Exception as e:
            logger.error("Agent step %s.%s raised: %s", agent_id, method_name, e)
            return AgentOutput(
                agent_id=agent_id,
                error=f"{type(e).__name__}: {e}",
            )

    def _build_task_description(self, step_id: str, prior_outputs: dict) -> str:
        """Build the task description for an agent step."""
        if step_id == "EXTRACT_CLAIMS":
            # Full paper text for claim extraction
            if self._parsed_paper:
                sections_text = []
                for s in self._parsed_paper.sections:
                    sections_text.append(f"## {s.heading}\n{s.text}")
                return "\n\n".join(sections_text)
            return ""

        elif step_id == "BACKGROUND_LIT":
            # Search query built from paper claims
            claims = prior_outputs.get("EXTRACT_CLAIMS", {}).get("claims", [])
            main_findings = [c["claim_text"] for c in claims if c.get("claim_type") == "main_finding"]
            hypothesis = prior_outputs.get("EXTRACT_CLAIMS", {}).get("stated_hypothesis", "")
            query_parts = []
            if hypothesis:
                query_parts.append(hypothesis)
            query_parts.extend(main_findings[:5])
            return f"Search literature related to: {'; '.join(query_parts)}" if query_parts else self._paper_title

        elif step_id == "CONTRADICTION_CHECK":
            # Provide paper claims + background literature for contradiction detection
            claims = prior_outputs.get("EXTRACT_CLAIMS", {}).get("claims", [])
            lit = prior_outputs.get("BACKGROUND_LIT", {})
            parts = [f"Paper: {self._paper_title}"]
            parts.append(f"Paper claims ({len(claims)}):")
            for c in claims[:15]:
                parts.append(f"- [{c.get('claim_type', '?')}] {c.get('claim_text', '')}")
            if lit.get("summary"):
                parts.append(f"\nBackground literature:\n{lit['summary'][:3000]}")
            return "\n".join(parts)

        elif step_id == "METHODOLOGY_REVIEW":
            # Methods section + full paper context
            if self._parsed_paper:
                methods_sections = [
                    s for s in self._parsed_paper.sections
                    if any(kw in s.heading.lower() for kw in ["method", "material", "experimental"])
                ]
                results_sections = [
                    s for s in self._parsed_paper.sections
                    if "result" in s.heading.lower()
                ]
                parts = [f"Paper: {self._paper_title}\n"]
                for s in methods_sections:
                    parts.append(f"## {s.heading}\n{s.text}")
                for s in results_sections:
                    parts.append(f"## {s.heading}\n{s.text}")
                return "\n\n".join(parts)
            return self._paper_title

        elif step_id == "SYNTHESIZE_REVIEW":
            # All prior results for final synthesis
            parts = [
                "INSTRUCTIONS: Write this peer review exactly as a senior academic reviewer would write "
                "for a biomedical journal. Do NOT mention automated tools, software pipelines, or analysis "
                "steps by name. Do NOT reference internal system components. Write evidence_basis fields "
                "using natural scientific reasoning — cite the manuscript's own text, reported statistics, "
                "or named prior studies, never the analysis process that found them. "
                "Your review will be submitted directly to a journal editor.\n",
                f"Paper under review: {self._paper_title}\n",
                "The following analyses have been completed. Synthesize them into a structured peer review:\n",
            ]

            # Claims
            claims = prior_outputs.get("EXTRACT_CLAIMS", {}).get("claims", [])
            parts.append(f"### Key Claims from the Manuscript ({len(claims)} identified)")
            for c in claims[:20]:
                parts.append(f"- [{c.get('claim_type', '?')}] {c.get('claim_text', '')}")

            # Citation report
            cite = prior_outputs.get("CITE_VALIDATION", {})
            if cite:
                total = cite.get("total_citations", 0)
                verified = cite.get("verified", 0)
                cite_notes = cite.get("notes", [])
                if total > 0:
                    parts.append(f"\n### Citation Review: {verified}/{total} references verified")
                elif cite_notes:
                    parts.append(f"\n### Citation Review: {cite_notes[0][:200]}")

            # Literature
            lit = prior_outputs.get("BACKGROUND_LIT", {})
            if lit.get("summary"):
                parts.append(f"\n### Related Prior Literature\n{lit['summary'][:2000]}")

            # Novelty
            novelty = prior_outputs.get("NOVELTY_CHECK", {})
            if novelty and not novelty.get("skipped"):
                established = novelty.get("already_established", [])
                unique = novelty.get("unique_contributions", [])
                missing = novelty.get("landmark_papers_missing", [])
                parts.append(f"\n### Novelty Analysis")
                if established:
                    parts.append("Findings already established in prior literature:")
                    for item in established:
                        parts.append(f"  - {item}")
                if unique:
                    parts.append("Genuinely novel contributions:")
                    for item in unique:
                        parts.append(f"  - {item}")
                if missing:
                    parts.append("Key landmark papers the manuscript should compare against:")
                    for item in missing:
                        parts.append(f"  - {item}")

            # Integrity
            integrity = prior_outputs.get("INTEGRITY_AUDIT", {})
            if integrity.get("summary"):
                parts.append(f"\n### Data Integrity Findings\n{integrity.get('summary', '')}")

            # Contradictions
            contra = prior_outputs.get("CONTRADICTION_CHECK", {})
            if contra.get("summary"):
                parts.append(f"\n### Internal Inconsistencies\n{contra.get('summary', '')}")

            # Methodology
            method = prior_outputs.get("METHODOLOGY_REVIEW", {})
            if method.get("study_design_critique"):
                parts.append(f"\n### Methodological Assessment")
                parts.append(f"Study design: {method.get('study_design_critique', '')}")
                parts.append(f"Statistical approach: {method.get('statistical_methods', '')}")
                parts.append(f"Controls: {method.get('controls_adequacy', '')}")
                parts.append(f"Sample size: {method.get('sample_size_assessment', '')}")
                biases = method.get("potential_biases", [])
                if biases:
                    parts.append("Potential biases: " + "; ".join(biases[:5]))

            # RCMXT
            rcmxt = prior_outputs.get("EVIDENCE_GRADE", {})
            if rcmxt.get("scores"):
                parts.append(f"\n### Evidence Quality ({rcmxt.get('total_scored', 0)} claims evaluated)")
                for s in rcmxt.get("scores", [])[:5]:
                    parts.append(f"  - {s.get('claim', '')[:80]}: composite {s.get('composite', 'N/A')}")

            return "\n".join(parts)

        return self._paper_title

    # === Code-only Steps ===

    async def _run_code_step(
        self,
        step: WorkflowStepDef,
        pdf_path: str,
        instance: WorkflowInstance,
    ) -> AgentOutput:
        """Run a code-only step."""
        if step.id == "INGEST":
            return self._step_ingest(pdf_path)
        elif step.id == "PARSE_SECTIONS":
            return self._step_parse()
        elif step.id == "CITE_VALIDATION":
            return self._step_cite_validation()
        elif step.id == "NOVELTY_CHECK":
            return await self._step_novelty_check()
        elif step.id == "INTEGRITY_AUDIT":
            return await self._step_integrity_audit()
        elif step.id == "EVIDENCE_GRADE":
            return await self._step_evidence_grade()
        elif step.id == "HUMAN_CHECKPOINT":
            return AgentOutput(
                agent_id="code_only",
                output={"step": "HUMAN_CHECKPOINT", "status": "awaiting_reviewer"},
                summary="Pausing for human reviewer input",
            )
        elif step.id == "REPORT":
            return self._step_report(instance)
        return AgentOutput(agent_id="code_only", error=f"Unknown code step: {step.id}")

    def _step_ingest(self, pdf_path: str) -> AgentOutput:
        """INGEST: Read and validate paper file (PDF or DOCX)."""
        if not pdf_path:
            return AgentOutput(
                agent_id="code_only",
                error="No PDF path provided",
            )

        path = Path(pdf_path)
        if not path.exists():
            return AgentOutput(
                agent_id="code_only",
                error=f"PDF file not found: {pdf_path}",
            )

        suffix = path.suffix.lower()
        if suffix not in (".pdf", ".docx", ".doc"):
            return AgentOutput(
                agent_id="code_only",
                error=f"Not a PDF or DOCX file: {pdf_path}",
            )

        self._pdf_bytes = path.read_bytes()
        self._file_path = path  # Store for DOCX parsing
        size_kb = len(self._pdf_bytes) / 1024

        return AgentOutput(
            agent_id="code_only",
            output={
                "step": "INGEST",
                "pdf_path": str(path),
                "file_type": suffix,
                "size_kb": round(size_kb, 1),
            },
            summary=f"Ingested {suffix.upper()}: {path.name} ({size_kb:.1f} KB)",
        )

    def _step_parse(self) -> AgentOutput:
        """PARSE_SECTIONS: Extract text and split into sections."""
        if not self._pdf_bytes:
            return AgentOutput(
                agent_id="code_only",
                error="No PDF bytes to parse (INGEST step may have failed)",
            )

        try:
            from app.engines.pdf.parser import PaperParser

            parser = PaperParser()

            # Use file path for DOCX, bytes for PDF
            file_path = getattr(self, "_file_path", None)
            if file_path and file_path.suffix.lower() in (".docx", ".doc"):
                self._parsed_paper = parser.parse_docx(file_path)
            else:
                self._parsed_paper = parser.parse(self._pdf_bytes)

            self._paper_title = self._parsed_paper.title

            return AgentOutput(
                agent_id="code_only",
                output={
                    "step": "PARSE_SECTIONS",
                    "title": self._parsed_paper.title,
                    "page_count": self._parsed_paper.page_count,
                    "sections": [
                        {"heading": s.heading, "length": len(s.text), "figures": len(s.figures)}
                        for s in self._parsed_paper.sections
                    ],
                    "has_references": bool(self._parsed_paper.references_raw),
                },
                summary=f"Parsed: '{self._parsed_paper.title}' — {self._parsed_paper.page_count or '?'} pages, {len(self._parsed_paper.sections)} sections",
            )
        except ImportError as e:
            return AgentOutput(
                agent_id="code_only",
                error=f"Required library not installed: {e}",
            )
        except Exception as e:
            return AgentOutput(
                agent_id="code_only",
                error=f"Paper parsing failed: {e}",
            )

    def _step_cite_validation(self) -> AgentOutput:
        """CITE_VALIDATION: Validate citations extracted from claims.

        For PDFs: parses reference list and validates DOIs via Crossref.
        For DOCX without embedded DOIs: extracts numbered reference titles and
        attempts PubMed title-based lookup via KnowledgeManager to resolve DOI/PMID.
        """
        from app.engines.citation_validator import CitationValidator

        validator = CitationValidator()

        # Register references from claim supporting_refs (may contain raw DOI/PMID strings)
        claims_output = self._step_results.get("EXTRACT_CLAIMS")
        refs_as_sources = []
        if claims_output and hasattr(claims_output, "output") and isinstance(claims_output.output, dict):
            for claim in claims_output.output.get("claims", []):
                for ref in claim.get("supporting_refs", []):
                    doi_match = re.search(r"(10\.\d{4,9}/[^\s,;\]]+)", ref)
                    pmid_match = re.search(r"(\d{7,9})", ref)
                    source = {}
                    if doi_match:
                        source["doi"] = doi_match.group(1)
                    if pmid_match:
                        source["pmid"] = pmid_match.group(1)
                    if source:
                        refs_as_sources.append(source)

        if refs_as_sources:
            validator.register_sources(refs_as_sources)

        # Try parsed reference section first
        refs_text = self._parsed_paper.references_raw if self._parsed_paper else ""

        # Scan full text for any embedded DOIs
        doi_pattern = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Z0-9]+)\b", re.IGNORECASE)
        full_text = self._parsed_paper.full_text if self._parsed_paper else ""
        embedded_dois = list(set(doi_pattern.findall(full_text))) if not refs_text else []

        report = validator.validate(refs_text)

        # Estimate reference count from full text if validator found nothing
        numbered_refs: list[str] = []
        if report.total_citations == 0 and full_text:
            numbered_refs = re.findall(r"^\s*\[?\d{1,3}\]?\s+\w", full_text, re.MULTILINE)

        # --- Title-based reference resolution via PubMed (KnowledgeManager) ---
        # Attempt to resolve references that lack DOI/PMID by extracting titles
        # from the numbered reference list and querying PubMed via KnowledgeManager.
        resolved_citations: list[dict] = []
        if report.total_citations == 0 and not embedded_dois and full_text:
            resolved_citations = self._resolve_refs_by_title(full_text)
            if resolved_citations:
                # Register resolved refs with validator for completeness
                validator.register_sources([
                    {k: v for k, v in r.items() if k in ("doi", "pmid")}
                    for r in resolved_citations if r.get("doi") or r.get("pmid")
                ])

        report_dict = {
            "step": "CITE_VALIDATION",
            "total_citations": report.total_citations,
            "verified": report.verified,
            "verification_rate": report.verification_rate,
            "is_clean": report.is_clean,
            "embedded_dois_found": len(embedded_dois),
            "resolved_citations": resolved_citations,
            "notes": [],
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

        if report.total_citations > 0:
            summary = f"Citations: {report.verified}/{report.total_citations} verified ({report.verification_rate:.0%})"
        elif resolved_citations:
            summary = f"References resolved via title lookup: {len(resolved_citations)}"
        elif embedded_dois:
            summary = f"DOIs found in text: {len(embedded_dois)} (no structured reference list)"
        else:
            summary = "Citation verification limited: no machine-readable identifiers in reference list"

        return AgentOutput(
            agent_id="code_only",
            output=report_dict,
            output_type="CitationReport",
            summary=summary,
        )

    def _resolve_refs_by_title(self, full_text: str, max_refs: int = 15) -> list[dict]:
        """Extract numbered reference titles from text and look up DOI/PMID via KnowledgeManager.

        Uses regex to identify numbered reference list entries, extracts likely titles,
        and queries PubMed synchronously via the integration client.
        Only called when no DOIs/PMIDs are found in the reference list.
        """
        import asyncio

        from app.integrations.pubmed import PubMedClient

        # Extract candidate reference entries: "[N] Author. Title. Journal. Year."
        # Heuristic: lines starting with optional bracket, number, and content
        ref_block_match = re.search(
            r"(?:references|bibliography|works cited)[:\n]+(.{200,}?)(?:\n\n\n|\Z)",
            full_text,
            re.IGNORECASE | re.DOTALL,
        )
        block = ref_block_match.group(1) if ref_block_match else full_text[-8000:]

        # Match numbered entries like "[1] ...", "1. ...", "1) ..."
        entries = re.findall(
            r"(?:^\s*\[?\d{1,3}\]?[\.\)]\s*)(.+?)(?=^\s*\[?\d{1,3}\]?[\.\)]|\Z)",
            block,
            re.MULTILINE | re.DOTALL,
        )
        entries = [e.strip().replace("\n", " ") for e in entries[:max_refs] if len(e.strip()) > 20]

        if not entries:
            return []

        client = PubMedClient()
        resolved: list[dict] = []

        async def _lookup_all() -> None:
            for entry in entries:
                # Extract likely title: everything before a period followed by journal
                # Heuristic: grab first 120 chars, stop before journal abbreviation
                raw_title = entry[:120].split(". ")[0].strip(" .")
                if len(raw_title) < 15:
                    continue
                try:
                    results = await client.search(raw_title, max_results=1)
                    if results:
                        hit = results[0]
                        resolved.append({
                            "query_title": raw_title,
                            "matched_title": hit.get("title", ""),
                            "pmid": hit.get("pmid", ""),
                            "doi": hit.get("doi", ""),
                            "year": hit.get("year", ""),
                            "authors": hit.get("authors", []),
                        })
                except Exception as e:
                    logger.debug("Title lookup failed for %r: %s", raw_title[:60], e)

        try:
            # Run async lookups in a new event loop if needed
            try:
                loop = asyncio.get_running_loop()
                # Already in async context — schedule as task and gather
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, _lookup_all())
                    future.result(timeout=30)
            except RuntimeError:
                asyncio.run(_lookup_all())
        except Exception as e:
            logger.warning("Reference title resolution failed: %s", e)

        logger.info("CITE_VALIDATION resolved %d/%d references via title lookup", len(resolved), len(entries))
        return resolved

    async def _step_integrity_audit(self) -> AgentOutput:
        """INTEGRITY_AUDIT: Run deterministic integrity checks on paper text."""
        agent = self.registry.get("data_integrity_auditor")
        if agent is None:
            return AgentOutput(
                agent_id="code_only",
                output={"step": "INTEGRITY_AUDIT", "skipped": True, "reason": "agent_unavailable"},
                summary="Integrity audit skipped: agent not available",
            )

        # Gather text from parsed paper
        text = self._parsed_paper.full_text if self._parsed_paper else ""
        if not text:
            return AgentOutput(
                agent_id="code_only",
                output={"step": "INTEGRITY_AUDIT", "skipped": True, "reason": "no_text"},
                summary="Integrity audit skipped: no text available",
            )

        # Extract DOIs for retraction checking
        doi_pattern = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
        dois = list(set(doi_pattern.findall(text)))

        try:
            output = await agent.quick_check(text, dois=dois or None)
            return AgentOutput(
                agent_id="data_integrity_auditor",
                output={"step": "INTEGRITY_AUDIT", **(output.output or {})},
                output_type="IntegrityQuickCheck",
                summary=output.summary or "Integrity audit completed",
            )
        except Exception as e:
            logger.warning("INTEGRITY_AUDIT failed: %s", e)
            return AgentOutput(
                agent_id="code_only",
                output={"step": "INTEGRITY_AUDIT", "skipped": True, "error": str(e)},
                summary=f"Integrity audit skipped: {e}",
            )

    async def _step_novelty_check(self) -> AgentOutput:
        """NOVELTY_CHECK: Assess how novel the paper's findings are vs. recent landmark literature.

        Searches for high-impact recent papers in the same subfield, then uses LLM
        to compare the paper's key claims against established findings. Specifically
        checks against landmark spaceflight/domain studies (NASA Twins Study, SOMA, etc.).
        """
        from app.models.messages import ContextPackage
        from app.models.peer_review import NoveltyAssessment

        if not self._llm_layer:
            return AgentOutput(
                agent_id="code_only",
                output={"step": "NOVELTY_CHECK", "skipped": True, "reason": "no_llm_layer"},
                summary="Novelty check skipped: LLM layer not available",
            )

        # 1. Gather paper claims
        claims_output = self._step_results.get("EXTRACT_CLAIMS")
        claims = []
        if claims_output and hasattr(claims_output, "output") and isinstance(claims_output.output, dict):
            claims = claims_output.output.get("claims", [])
        main_findings = [c["claim_text"] for c in claims if c.get("claim_type") == "main_finding"][:12]
        hypothesis = claims_output.output.get("stated_hypothesis", "") if claims_output and claims_output.output else ""

        # 2. Background lit papers from previous step
        lit_output = self._step_results.get("BACKGROUND_LIT")
        background_papers: list[dict] = []
        if lit_output and hasattr(lit_output, "output") and isinstance(lit_output.output, dict):
            background_papers = lit_output.output.get("papers", [])

        # 3. Additional landmark-focused search via KnowledgeManager
        landmark_papers: list[dict] = []
        km = self.registry.get("knowledge_manager") if self.registry else None
        if km and self._paper_title:
            # Build a targeted query for recent landmark papers
            topic_words = " ".join(self._paper_title.split()[:6])
            novelty_query = (
                f"landmark major studies {topic_words} 2019 2020 2021 2022 2023 2024 "
                f"NASA spaceflight omics immune transcriptomics"
            )
            try:
                km_context = ContextPackage(task_description=novelty_query)
                km_result = await km.search_literature(km_context)
                if km_result and hasattr(km_result, "output") and isinstance(km_result.output, dict):
                    landmark_papers = km_result.output.get("papers", [])
            except Exception as e:
                logger.warning("NOVELTY_CHECK landmark search failed: %s", e)

        # Deduplicate all papers by PMID/DOI
        seen: set[str] = set()
        all_papers: list[dict] = []
        for p in background_papers + landmark_papers:
            key = p.get("pmid") or p.get("doi") or p.get("title", "")[:50]
            if key and key not in seen:
                seen.add(key)
                all_papers.append(p)

        # 4. Build LLM prompt for novelty assessment
        paper_list_text = ""
        for p in all_papers[:15]:
            authors = p.get("authors", [])
            author_str = f"{authors[0]} et al." if authors else "Unknown"
            year = p.get("year", "")
            title = p.get("title", "Unknown")
            pmid = p.get("pmid", "")
            abstract = p.get("abstract", "")[:300]
            paper_list_text += f"\n- **{title}** ({author_str}, {year}, PMID:{pmid})\n  {abstract}\n"

        findings_text = "\n".join(f"- {f}" for f in main_findings) if main_findings else "(none extracted)"

        system_prompt = (
            "You are an expert scientific peer reviewer specializing in novelty assessment. "
            "Your task is to determine whether a paper's key findings have already been established "
            "in prior landmark studies, or whether they represent genuine contributions. "
            "Be specific: cite actual paper titles/authors when noting overlap. "
            "Be fair: acknowledge that replication has value, but distinguish confirmatory from novel work. "
            "Pay special attention to recent high-impact studies that may have pre-established the same findings."
        )

        user_prompt = f"""Assess the novelty of the following paper's key findings relative to existing literature.

PAPER TITLE: {self._paper_title}

STATED HYPOTHESIS: {hypothesis or "(not stated)"}

KEY CLAIMS FROM THIS PAPER:
{findings_text}

RELATED PAPERS FOUND IN LITERATURE:
{paper_list_text if paper_list_text else "(no related papers retrieved)"}

IMPORTANT CONTEXT — Check specifically whether these findings have already been reported in:
- NASA Twins Study (Scott/Mark Kelly, Science 2019) — comprehensive spaceflight omics, T cell changes
- Inspiration4/SOMA package (Nature 2024) — largest civilian spaceflight omics, 64 astronauts, immune profiling
- Any prior ISS crew investigations or ground-based microgravity immune studies

Rate novelty from 0.0 (completely replicates prior work) to 1.0 (entirely novel findings).
For each established finding, name the specific prior paper.
For each unique contribution, explain what makes it genuinely new.
Provide 2-3 actionable recommendations for how the authors can reframe or strengthen the novelty argument."""

        try:
            novelty_result, meta = await self._llm_layer.complete_structured(
                messages=[{"role": "user", "content": user_prompt}],
                model_tier="sonnet",
                response_model=NoveltyAssessment,
                system=system_prompt,
                max_tokens=2500,
            )

            return AgentOutput(
                agent_id="knowledge_manager",
                output={"step": "NOVELTY_CHECK", **novelty_result.model_dump(mode="json")},
                output_type="NoveltyAssessment",
                model_tier="sonnet",
                model_version=meta.model_version,
                input_tokens=meta.input_tokens,
                output_tokens=meta.output_tokens,
                cost=meta.cost,
                summary=(
                    f"Novelty score: {novelty_result.novelty_score:.2f} — "
                    f"{len(novelty_result.already_established)} established, "
                    f"{len(novelty_result.unique_contributions)} novel, "
                    f"{len(novelty_result.landmark_papers_missing)} missing landmark refs"
                ),
            )
        except Exception as e:
            logger.warning("NOVELTY_CHECK LLM call failed: %s", e)
            return AgentOutput(
                agent_id="code_only",
                output={"step": "NOVELTY_CHECK", "skipped": True, "error": str(e)},
                summary=f"Novelty check skipped: {e}",
            )

    async def _step_evidence_grade(self) -> AgentOutput:
        """EVIDENCE_GRADE: RCMXT scoring of extracted claims."""
        from app.engines.rcmxt_scorer import RCMXTScorer

        scorer = RCMXTScorer(mode="heuristic", llm_layer=self._llm_layer)

        # Build evidence data from claims
        claims_output = self._step_results.get("EXTRACT_CLAIMS")
        lit_output = self._step_results.get("BACKGROUND_LIT")

        search_data = None
        if lit_output and hasattr(lit_output, "output") and isinstance(lit_output.output, dict):
            search_data = lit_output.output

        # Use extracted claims as synthesis for RCMXT scoring
        extract_data = None
        if claims_output and hasattr(claims_output, "output") and isinstance(claims_output.output, dict):
            extract_data = claims_output.output

        scorer.load_step_data(search_data, extract_data, None)
        scores = scorer.score_all()
        scores_dicts = [s.model_dump(mode="json") for s in scores]

        return AgentOutput(
            agent_id="code_only",
            output={
                "step": "EVIDENCE_GRADE",
                "scores": scores_dicts,
                "total_scored": len(scores),
            },
            output_type="RCMXTScores",
            summary=f"RCMXT scored {len(scores)} claims",
        )

    def _step_report(self, instance: WorkflowInstance) -> AgentOutput:
        """REPORT: Assemble final peer review report."""
        from app.engines.w8_report_builder import generate_w8_report

        return generate_w8_report(instance, self._step_results, self._paper_title)

    def _store_results(self, instance: WorkflowInstance) -> None:
        """Store key results on the workflow instance."""
        # Citation report
        cite_result = self._step_results.get("CITE_VALIDATION")
        if cite_result and hasattr(cite_result, "output") and isinstance(cite_result.output, dict):
            instance.citation_report = cite_result.output

        # RCMXT scores
        rcmxt_result = self._step_results.get("EVIDENCE_GRADE")
        if rcmxt_result and hasattr(rcmxt_result, "output") and isinstance(rcmxt_result.output, dict):
            instance.rcmxt_scores = rcmxt_result.output.get("scores", [])

        # Session manifest
        from app.engines.w8_report_builder import build_w8_session_manifest
        manifest = build_w8_session_manifest(instance, self._step_results)
        existing = dict(instance.session_manifest) if instance.session_manifest else {}
        existing.update(manifest)
        instance.session_manifest = existing
