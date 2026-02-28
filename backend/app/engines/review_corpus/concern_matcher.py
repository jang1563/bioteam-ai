"""Semantic matcher: compares W8 output concerns vs human reviewer concerns.

Uses ChromaDB semantic search (existing lab_kb collection) to compute:
- Recall: what fraction of human concerns did W8 also raise?
- Precision: what fraction of W8 concerns were real issues (validated by humans)?

Falls back to simple keyword overlap if ChromaDB unavailable.
"""

from __future__ import annotations

import logging
import re
from typing import Callable

from app.models.review_corpus import ReviewerConcern, W8BenchmarkResult

logger = logging.getLogger(__name__)

# Minimum semantic similarity to count as a "match"
_SIMILARITY_THRESHOLD = 0.65


class ConcernMatcher:
    """Match W8-raised concerns against ground-truth human reviewer concerns.

    Supports semantic similarity (via embedding function) or fallback keyword overlap.
    """

    def __init__(self, embed_fn: Callable[[str], list[float]] | None = None) -> None:
        """
        Args:
            embed_fn: Optional function that returns embeddings for a string.
                      If None, falls back to keyword overlap matching.
        """
        self._embed_fn = embed_fn

    def compute_metrics(
        self,
        article_id: str,
        source: str,
        human_concerns: list[ReviewerConcern],
        w8_review_text: str,
        w8_workflow_id: str | None = None,
        w8_comment_count: int | None = None,
        exclude_figure_concerns: bool = True,
    ) -> W8BenchmarkResult:
        """Compute recall/precision metrics for one article.

        Args:
            article_id: Source article ID.
            source: Data source ("elife", "plos", etc.).
            human_concerns: Structured concerns from open peer review corpus.
            w8_review_text: Full text output from W8 synthesize step.
            w8_workflow_id: Optional W8 workflow run ID.

        Returns:
            W8BenchmarkResult with recall, precision, and detailed overlap data.
        """
        if not human_concerns:
            return W8BenchmarkResult(
                article_id=article_id,
                source=source,
                w8_workflow_id=w8_workflow_id,
            )

        w8_sentences = self._split_into_sentences(w8_review_text)

        # Optionally exclude figure-only concerns (W8 cannot read figures)
        if exclude_figure_concerns:
            all_concerns = [c for c in human_concerns if not getattr(c, "is_figure_concern", False)]
        else:
            all_concerns = human_concerns
        major_concerns = [c for c in all_concerns if c.severity == "major"]

        matched_all: list[str] = []
        missed_all: list[str] = []
        matched_major: list[str] = []
        missed_major: list[str] = []

        for concern in all_concerns:
            is_match = self._concern_is_covered(concern.concern_text, w8_sentences)
            if is_match:
                matched_all.append(concern.concern_id)
                if concern.severity == "major":
                    matched_major.append(concern.concern_id)
            else:
                missed_all.append(concern.concern_id)
                if concern.severity == "major":
                    missed_major.append(concern.concern_id)

        major_recall = len(matched_major) / len(major_concerns) if major_concerns else None
        overall_recall = len(matched_all) / len(all_concerns) if all_concerns else None

        # Precision: what fraction of W8 "concerns" map back to human concerns
        w8_concerns_raised = list({c for c in matched_all})
        if w8_comment_count and w8_comment_count > 0:
            # Use explicit W8 structured comment count as denominator
            precision = len(w8_concerns_raised) / w8_comment_count if w8_concerns_raised else 0.0
        elif w8_review_text:
            # Better fallback: count structured comments in the W8 review text
            # (numbered items like **1.**, bullet points, or section headers)
            estimated_comments = self._count_w8_comments(w8_review_text)
            if estimated_comments > 0:
                precision = len(w8_concerns_raised) / estimated_comments
            else:
                precision = None
        else:
            precision = None

        return W8BenchmarkResult(
            article_id=article_id,
            source=source,
            w8_workflow_id=w8_workflow_id,
            major_concern_recall=major_recall,
            overall_concern_recall=overall_recall,
            concern_precision=precision,
            w8_concerns_raised=w8_concerns_raised,
            human_concerns_matched=matched_all,
            human_concerns_missed=missed_all,
        )

    def _concern_is_covered(self, concern_text: str, w8_sentences: list[str]) -> bool:
        """Check if a human concern is covered by any W8 sentence."""
        if self._embed_fn is not None:
            return self._semantic_match(concern_text, w8_sentences)
        return self._keyword_match(concern_text, w8_sentences)

    def _semantic_match(self, concern_text: str, w8_sentences: list[str]) -> bool:
        """Use cosine similarity of embeddings to check coverage."""
        try:
            concern_emb = self._embed_fn(concern_text)  # type: ignore[misc]
            for sentence in w8_sentences:
                sent_emb = self._embed_fn(sentence)  # type: ignore[misc]
                sim = self._cosine_similarity(concern_emb, sent_emb)
                if sim >= _SIMILARITY_THRESHOLD:
                    return True
        except Exception as e:
            logger.debug("Semantic match failed, falling back to keyword: %s", e)
            return self._keyword_match(concern_text, w8_sentences)
        return False

    def _keyword_match(self, concern_text: str, w8_sentences: list[str]) -> bool:
        """Simple keyword overlap: ≥3 keywords from concern appear in any W8 sentence."""
        keywords = self._extract_keywords(concern_text)
        if not keywords:
            return False
        min_matches = max(2, len(keywords) // 3)
        for sentence in w8_sentences:
            sentence_lower = sentence.lower()
            hits = sum(1 for kw in keywords if kw in sentence_lower)
            if hits >= min_matches:
                return True
        return False

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract meaningful keywords from concern text (lowercase, >4 chars, not stopwords)."""
        stopwords = {
            "the", "that", "this", "with", "from", "they", "their", "have",
            "been", "would", "could", "should", "which", "were", "also", "more",
            "than", "when", "what", "does", "into", "such", "these", "those",
        }
        words = re.findall(r"\b[a-z][a-z\-]{3,}\b", text.lower())
        return [w for w in words if w not in stopwords]

    @staticmethod
    def _count_w8_comments(review_text: str) -> int:
        """Count structured concern/comment items in a W8 review text.

        Counts (in order of reliability):
        1. Numbered bold markers like **1.** or **1)** (W8 report format)
        2. Bullet-point lines starting with "- " or "* "
        Falls back to zero if no structured items found.
        """
        # Priority 1: numbered comments e.g. **1.** or **1)**
        numbered = re.findall(r"\*\*\d+[\.\)]", review_text)
        if numbered:
            return len(numbered)

        # Priority 2: bullet points (each line starting with "- " or "* ")
        bullet_lines = [
            line for line in review_text.split("\n")
            if re.match(r"^\s*[-*]\s+\S", line)
        ]
        if bullet_lines:
            return len(bullet_lines)

        return 0

    @staticmethod
    def _split_into_sentences(text: str) -> list[str]:
        """Split review text into sentences for matching."""
        if not text:
            return []
        # Split on sentence-ending punctuation
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if len(s.strip()) > 20]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two embedding vectors."""
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
