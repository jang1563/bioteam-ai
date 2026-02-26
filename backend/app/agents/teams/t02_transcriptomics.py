"""Transcriptomics Agent (Team 2) — RNA-seq, scRNA-seq, cfRNA analysis.

Responsibilities:
1. Gene expression analysis (default run)
2. Paper screening for W1 Literature Review (SCREEN step)
3. Data extraction from papers for W1 Literature Review (EXTRACT step)
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field

# === Output Models ===


class GeneExpressionResult(BaseModel):
    """Result of a gene expression analysis query."""

    query: str
    genes_analyzed: list[str] = Field(default_factory=list)
    differentially_expressed: list[dict] = Field(default_factory=list)
    methodology: str = ""
    datasets_used: list[str] = Field(default_factory=list)
    summary: str = ""
    confidence: float = 0.0
    caveats: list[str] = Field(default_factory=list)


class ScreeningDecision(BaseModel):
    """Screening decision for a single paper."""

    paper_id: str
    title: str = ""
    decision: str = "exclude"  # "include" | "exclude"
    relevance_score: float = 0.0
    reasoning: str = ""
    flags: list[str] = Field(default_factory=list)


class ScreeningResult(BaseModel):
    """Result of screening papers for a literature review."""

    total_screened: int = 0
    included: int = 0
    excluded: int = 0
    decisions: list[ScreeningDecision] = Field(default_factory=list)


class ExtractedPaperData(BaseModel):
    """Data extracted from a single paper."""

    paper_id: str
    title: str = ""
    genes: list[str] = Field(default_factory=list)
    organism: str = ""
    tissue: str = ""
    technology: str = ""
    sample_size: int = 0
    key_findings: list[str] = Field(default_factory=list)
    data_accession: str | None = None
    quality_flags: list[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Result of extracting data from included papers."""

    total_extracted: int = 0
    papers: list[ExtractedPaperData] = Field(default_factory=list)
    common_genes: list[str] = Field(default_factory=list)
    methodology_summary: str = ""


# === Agent Implementation ===


class TranscriptomicsAgent(BaseAgent):
    """Specialist agent for transcriptomics and single-cell analysis.

    Supports 3 execution modes:
    - run(): Default gene expression query answering
    - screen_papers(): W1 SCREEN step — paper relevance screening
    - extract_data(): W1 EXTRACT step — structured data extraction
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Answer a gene expression analysis query."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Analyze this gene expression query:\n\n"
                    f"{context.task_description}\n\n"
                    f"Provide a structured analysis including genes involved, "
                    f"datasets to consult, methodology, and confidence level."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=GeneExpressionResult,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="GeneExpressionResult",
            summary=result.summary[:200] if result.summary else f"Analyzed: {context.task_description[:100]}",
            llm_response=meta,
        )

    @staticmethod
    def _format_prior_papers(prior_outputs: list) -> str:
        """Format prior step outputs into readable paper list for LLM.

        Extracts papers from SEARCH or SCREEN output dicts and formats
        them as a numbered list with title, PMID, and truncated abstract.
        Falls back to string representation if no structured papers found.
        """
        if not prior_outputs:
            return "No papers provided."
        papers: list[dict] = []
        for output in prior_outputs:
            if not isinstance(output, dict):
                continue
            for p in output.get("papers", []):
                if isinstance(p, dict):
                    papers.append(p)
            for d in output.get("decisions", []):
                if isinstance(d, dict) and d.get("decision") == "include":
                    papers.append(d)
        if not papers:
            # Fallback: stringify as before (covers non-standard output shapes)
            return "\n".join(f"- {p}" for p in prior_outputs)
        lines = []
        for i, p in enumerate(papers, 1):
            title = p.get("title", "Unknown")
            pmid = p.get("pmid", p.get("paper_id", ""))
            abstract = (p.get("abstract", "") or "")[:300]
            ref_id = f"PMID:{pmid}" if pmid else ""
            entry = f"[{i}] {title}"
            if ref_id:
                entry += f" ({ref_id})"
            if abstract:
                entry += f"\n    {abstract}"
            lines.append(entry)
        return "\n\n".join(lines)

    async def screen_papers(self, context: ContextPackage) -> AgentOutput:
        """Screen papers for relevance to a literature review query.

        Used in W1 SCREEN step. Papers are passed via context.prior_step_outputs.
        """
        papers_text = self._format_prior_papers(context.prior_step_outputs)

        messages = [
            {
                "role": "user",
                "content": (
                    f"Screen these papers for relevance to: {context.task_description}\n\n"
                    f"Papers to screen:\n{papers_text}\n\n"
                    f"For each paper, decide include/exclude with reasoning and relevance score."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=ScreeningResult,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="ScreeningResult",
            summary=f"Screened {result.total_screened} papers: {result.included} included, {result.excluded} excluded",
            llm_response=meta,
        )

    async def extract_data(self, context: ContextPackage) -> AgentOutput:
        """Extract structured data from included papers.

        Used in W1 EXTRACT step. Included papers from SCREEN step are in context.prior_step_outputs.
        """
        papers_text = self._format_prior_papers(context.prior_step_outputs)

        messages = [
            {
                "role": "user",
                "content": (
                    f"Extract structured data from these papers related to: {context.task_description}\n\n"
                    f"Papers:\n{papers_text}\n\n"
                    f"Extract: gene lists, organism, tissue, technology, sample size, "
                    f"key findings, and data accessions."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=ExtractionResult,
            system=self.system_prompt_cached,
            max_tokens=16384,  # Extraction of many papers produces large structured output
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="ExtractionResult",
            summary=f"Extracted data from {result.total_extracted} papers, {len(result.common_genes)} common genes",
            llm_response=meta,
        )
