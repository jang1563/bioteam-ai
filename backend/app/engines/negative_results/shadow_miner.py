"""Shadow Miner — automated PubMed negative-result classifier.

Searches PubMed for papers matching a topic query (augmented with negative-result
vocabulary), classifies each abstract with an LLM (Haiku), and stores confirmed
negative results in the Lab KB via LabKBEngine.

Usage:
    miner = ShadowMiner(llm_layer=layer, session=session)
    result = await miner.run("CRISPR off-target effects", max_papers=10)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.engines.negative_results.lab_kb import LabKBEngine
from app.integrations.pubmed import PubMedClient, PubMedPaper
from pydantic import BaseModel, Field
from sqlmodel import Session

if TYPE_CHECKING:
    from app.llm.layer import LLMLayer

logger = logging.getLogger(__name__)


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class NegativeResultClassification(BaseModel):
    """LLM output for a single abstract classification."""

    is_negative: bool = Field(
        description="True if the abstract reports a null/negative/failed result as a primary finding"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence that this is a genuine negative result (0–1)"
    )
    claim: str = Field(
        default="",
        description="The specific hypothesis or intervention that was tested",
    )
    outcome: str = Field(
        default="",
        description="The negative outcome observed (e.g., 'no significant effect on survival')",
    )
    organism: str = Field(default="", description="Model organism or cell line used (empty if unknown)")
    failure_category: str = Field(
        default="",
        description=(
            "Category of failure: 'statistical' (p>0.05), 'mechanistic' (pathway absent), "
            "'reproducibility' (failed replication), 'dose_response' (no dose-response), "
            "'off_target' (specificity failure), or 'other'"
        ),
    )
    reasoning: str = Field(default="", description="Brief reasoning for the classification (1-2 sentences)")


class MineRunResult(BaseModel):
    """Summary of a shadow mining run."""

    query: str
    augmented_query: str
    papers_fetched: int
    papers_classified: int
    negatives_found: int
    entries_created: int
    pmids_processed: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# ── Core engine ───────────────────────────────────────────────────────────────

_NEGATIVE_VOCAB = (
    '"no significant" OR "null result" OR "failed to" OR "no effect" '
    'OR "did not" OR "negative result" OR "not statistically significant" '
    'OR "no association" OR "no difference"'
)

_CLASSIFY_PROMPT = """\
You are a biomedical evidence classifier. Determine whether the abstract below reports a NEGATIVE or NULL result as one of its PRIMARY findings.

A negative result means:
- The main hypothesis was NOT supported (p > 0.05 with adequate power, or Bayesian equivalence)
- The intervention / drug / gene manipulation had NO significant effect on the measured outcome
- A previously reported finding FAILED to replicate
- There was NO dose-response relationship despite expectations

Do NOT mark as negative:
- Papers where a negative finding is a secondary or minor observation
- Papers primarily reporting a positive result with a small negative aside
- Reviews or meta-analyses (unless they specifically conclude null)

Abstract:
{abstract}

Title: {title}
"""


class ShadowMiner:
    """Automated pipeline: PubMed search → LLM classify → Lab KB storage."""

    def __init__(self, llm_layer: "LLMLayer", session: Session) -> None:
        self.llm = llm_layer
        self.lab_kb = LabKBEngine(session)
        self.pubmed = PubMedClient()

    def _augment_query(self, topic: str) -> str:
        """Augment topic query with negative-result vocabulary."""
        return f"({topic}) AND ({_NEGATIVE_VOCAB})"

    async def classify_abstract(self, paper: PubMedPaper) -> NegativeResultClassification | None:
        """Use LLM (Haiku) to classify a single abstract."""
        if not paper.abstract:
            return None
        prompt = _CLASSIFY_PROMPT.format(abstract=paper.abstract, title=paper.title)
        try:
            result: NegativeResultClassification = await self.llm.complete_structured(
                prompt=prompt,
                schema=NegativeResultClassification,
                model="haiku",
                max_tokens=512,
            )
            return result
        except Exception as exc:
            logger.warning("Shadow Miner classify failed for PMID %s: %s", paper.pmid, exc)
            return None

    async def run(
        self,
        topic: str,
        max_papers: int = 10,
        min_confidence: float = 0.6,
    ) -> MineRunResult:
        """Run the full shadow mining pipeline for a topic.

        Args:
            topic: Research topic to mine (e.g., "CRISPR off-target").
            max_papers: Maximum PubMed papers to fetch.
            min_confidence: Minimum LLM confidence to store a result.

        Returns:
            MineRunResult with run statistics.
        """
        aug_query = self._augment_query(topic)
        errors: list[str] = []
        pmids_processed: list[str] = []
        negatives_found = 0
        entries_created = 0

        # Fetch papers from PubMed
        try:
            papers = self.pubmed.search(aug_query, max_results=max_papers)
        except Exception as exc:
            logger.error("Shadow Miner PubMed search failed: %s", exc)
            return MineRunResult(
                query=topic,
                augmented_query=aug_query,
                papers_fetched=0,
                papers_classified=0,
                negatives_found=0,
                entries_created=0,
                errors=[f"PubMed search error: {exc}"],
            )

        papers_classified = 0
        for paper in papers:
            pmids_processed.append(paper.pmid)
            try:
                classification = await self.classify_abstract(paper)
            except Exception as exc:
                errors.append(f"PMID {paper.pmid}: classify error — {exc}")
                continue

            if classification is None:
                continue

            papers_classified += 1

            if not classification.is_negative or classification.confidence < min_confidence:
                continue

            negatives_found += 1

            # Build source string: pubmed:{pmid} (doi if available)
            source = f"pubmed:{paper.pmid}"
            if paper.doi:
                source = f"doi:{paper.doi}"

            try:
                self.lab_kb.create(
                    claim=classification.claim or paper.title,
                    outcome=classification.outcome,
                    source=source,
                    organism=classification.organism or None,
                    confidence=round(classification.confidence, 3),
                    failure_category=classification.failure_category,
                    implications=[],
                    conditions={
                        "journal": paper.journal,
                        "year": paper.year,
                        "pmid": paper.pmid,
                        "mined_query": topic,
                        "reasoning": classification.reasoning,
                    },
                    created_by="shadow_miner",
                )
                entries_created += 1
            except Exception as exc:
                errors.append(f"PMID {paper.pmid}: DB store error — {exc}")

        return MineRunResult(
            query=topic,
            augmented_query=aug_query,
            papers_fetched=len(papers),
            papers_classified=papers_classified,
            negatives_found=negatives_found,
            entries_created=entries_created,
            pmids_processed=pmids_processed,
            errors=errors,
        )
