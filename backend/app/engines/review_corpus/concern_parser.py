"""Haiku-based reviewer concern extractor.

Uses claude-haiku-4-5-20251001 to extract structured ReviewerConcern objects
from raw decision letter and author response text.

Keeps costs minimal: ~$0.002 per article (Haiku pricing, ~1000 tokens each way).
"""

from __future__ import annotations

import logging

from app.models.review_corpus import ReviewConcernBatch, ReviewerConcern

logger = logging.getLogger(__name__)

_EXTRACTION_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = """You are a peer review analyst. Extract structured reviewer concerns
from biomedical journal decision letters and author responses.

For each distinct concern raised by reviewers:
1. Assign a concern_id (e.g. R1C1, R1C2, R2C1 — Reviewer#, Concern#)
2. Identify the category: methodology | statistics | citation | interpretation | novelty | presentation | reproducibility | other
3. Assess severity: major | minor | question
4. Find the author's response text (from the author response section)
5. Determine resolution: conceded (author agreed and changed) | rebutted (author disagreed convincingly) | partially_addressed | unclear
6. Assess was_valid: true if the author conceded AND changed the paper; false if convincingly rebutted; null if unclear
7. Note if raised_by_multiple: true if >1 reviewer raised the same concern
8. Mark is_figure_concern: true ONLY if the concern is exclusively about a figure or image
   (e.g., "Figure 3 is unclear", "The scale bar in panel B is missing") and cannot be
   evaluated without visual inspection of the figure itself

Return a JSON array of concern objects. Limit to the 20 most important concerns."""

_EXTRACTION_PROMPT_TEMPLATE = """Article ID: {article_id}

=== DECISION LETTER (first 3000 chars) ===
{decision_letter}

=== AUTHOR RESPONSE (first 2000 chars) ===
{author_response}

Extract reviewer concerns as a JSON array of objects with these fields:
concern_id, concern_text (brief), category, severity, author_response_text (brief),
resolution, was_valid (true/false/null), raised_by_multiple (true/false),
is_figure_concern (true if concern is solely about a figure/image, false otherwise).

Return ONLY valid JSON array, no markdown, no explanation."""


class ConcernParser:
    """Extract structured reviewer concerns from open peer review text.

    Uses Haiku for cost-efficiency (~$0.002/article).
    Falls back to empty list if LLM unavailable.
    """

    def __init__(self, llm_layer=None) -> None:
        self._llm = llm_layer

    async def extract_concerns(
        self,
        article_id: str,
        decision_letter: str,
        author_response: str,
    ) -> ReviewConcernBatch:
        """Extract concerns from decision letter + author response.

        Returns ReviewConcernBatch. Falls back to empty batch if LLM fails.
        """
        if not decision_letter.strip():
            return ReviewConcernBatch(article_id=article_id, concerns=[], total_reviewers=0)

        if self._llm is None:
            logger.debug("ConcernParser: no LLM layer, returning empty batch for %s", article_id)
            return ReviewConcernBatch(article_id=article_id, concerns=[], total_reviewers=0)

        prompt = _EXTRACTION_PROMPT_TEMPLATE.format(
            article_id=article_id,
            decision_letter=decision_letter[:3000],
            author_response=author_response[:2000],
        )

        try:
            raw_msg, _meta = await self._llm.complete_raw(
                messages=[{"role": "user", "content": prompt}],
                model_tier="haiku",
                system=_SYSTEM_PROMPT,
                max_tokens=2048,
            )
            # Extract text from first content block
            raw_text = ""
            for block in raw_msg.content:
                if hasattr(block, "text"):
                    raw_text = block.text
                    break
            concerns = self._parse_json_concerns(article_id, raw_text)
            total_reviewers = self._estimate_reviewer_count(concerns)
            return ReviewConcernBatch(
                article_id=article_id,
                concerns=concerns,
                total_reviewers=total_reviewers,
                extraction_model=_EXTRACTION_MODEL,
            )
        except Exception as e:
            logger.warning("ConcernParser LLM extraction failed for %s: %s", article_id, e)
            return ReviewConcernBatch(article_id=article_id, concerns=[], total_reviewers=0)

    def _parse_json_concerns(self, article_id: str, raw_text: str) -> list[ReviewerConcern]:
        """Parse raw LLM JSON output into ReviewerConcern objects."""
        import json
        import re

        # Strip markdown code blocks if present
        text = re.sub(r"```(?:json)?\n?", "", raw_text).strip().rstrip("`").strip()

        # Find JSON array
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            logger.debug("No JSON array found in concern extraction for %s", article_id)
            return []

        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as e:
            logger.warning("JSON parse error for %s: %s", article_id, e)
            return []

        concerns: list[ReviewerConcern] = []
        for item in data[:20]:
            try:
                concern = ReviewerConcern(
                    concern_id=str(item.get("concern_id", f"C{len(concerns) + 1}")),
                    concern_text=str(item.get("concern_text", ""))[:500],
                    category=item.get("category", "other"),
                    severity=item.get("severity", "minor"),
                    author_response_text=str(item.get("author_response_text", ""))[:500],
                    resolution=item.get("resolution", "unclear"),
                    was_valid=item.get("was_valid"),
                    raised_by_multiple=bool(item.get("raised_by_multiple", False)),
                    is_figure_concern=bool(item.get("is_figure_concern", False)),
                )
                concerns.append(concern)
            except Exception as e:
                logger.debug("Skipping malformed concern item: %s", e)
        return concerns

    def _estimate_reviewer_count(self, concerns: list[ReviewerConcern]) -> int:
        """Estimate number of reviewers from concern IDs (e.g. R1, R2, R3)."""
        import re
        reviewer_nums: set[str] = set()
        for c in concerns:
            match = re.match(r"R(\d+)", c.concern_id)
            if match:
                reviewer_nums.add(match.group(1))
        return len(reviewer_nums) if reviewer_nums else 0


def evaluate_extraction_against_gold(
    gold_concerns: list[ReviewerConcern],
    predicted_concerns: list[ReviewerConcern],
    count_tolerance: int = 2,
) -> dict:
    """Evaluate concern extraction fidelity separately from W8 concern matching.

    This uses exact concern_id overlap as the primary alignment because the
    extraction task is defined at the concern-unit level, not semantic
    paraphrase level. Semantic matching belongs in the downstream benchmark.
    """
    gold_by_id = {c.concern_id: c for c in gold_concerns}
    pred_by_id = {c.concern_id: c for c in predicted_concerns}

    gold_ids = set(gold_by_id)
    pred_ids = set(pred_by_id)
    matched_ids = sorted(gold_ids & pred_ids)
    missing_ids = sorted(gold_ids - pred_ids)
    extra_ids = sorted(pred_ids - gold_ids)

    count_delta = len(predicted_concerns) - len(gold_concerns)
    count_within_tolerance = abs(count_delta) <= count_tolerance

    category_matches = 0
    severity_matches = 0
    resolution_matches = 0
    for concern_id in matched_ids:
        gold = gold_by_id[concern_id]
        pred = pred_by_id[concern_id]
        if gold.category == pred.category:
            category_matches += 1
        if gold.severity == pred.severity:
            severity_matches += 1
        if gold.resolution == pred.resolution:
            resolution_matches += 1

    matched_count = len(matched_ids)
    id_precision = matched_count / len(predicted_concerns) if predicted_concerns else 0.0
    id_recall = matched_count / len(gold_concerns) if gold_concerns else 0.0
    id_f1 = (
        2 * id_precision * id_recall / (id_precision + id_recall)
        if (id_precision + id_recall)
        else 0.0
    )

    return {
        "gold_count": len(gold_concerns),
        "predicted_count": len(predicted_concerns),
        "count_delta": count_delta,
        "count_within_tolerance": count_within_tolerance,
        "matched_ids": matched_ids,
        "missing_ids": missing_ids,
        "extra_ids": extra_ids,
        "id_precision": id_precision,
        "id_recall": id_recall,
        "id_f1": id_f1,
        "category_accuracy": category_matches / matched_count if matched_count else 0.0,
        "severity_accuracy": severity_matches / matched_count if matched_count else 0.0,
        "resolution_accuracy": resolution_matches / matched_count if matched_count else 0.0,
    }
