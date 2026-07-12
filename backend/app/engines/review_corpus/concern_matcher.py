"""Semantic matcher: compares W8 output concerns vs human reviewer concerns.

Uses ChromaDB semantic search (existing lab_kb collection) to compute:
- Recall: what fraction of human concerns did W8 also raise?
- Precision: what fraction of W8 concerns were real issues (validated by humans)?

Falls back to simple keyword overlap if ChromaDB unavailable.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Callable, Literal

from app.models.review_corpus import ReviewerConcern, W8BenchmarkResult

logger = logging.getLogger(__name__)

# Minimum semantic similarity to count as a "match"
_SIMILARITY_THRESHOLD = 0.65
_TOKEN_COSINE_THRESHOLD = 0.05


class ConcernMatcher:
    """Match W8-raised concerns against ground-truth human reviewer concerns.

    Supports semantic similarity (via embedding function) or fallback keyword overlap.
    """

    def __init__(
        self,
        embed_fn: Callable[[str], list[float]] | None = None,
        match_mode: Literal["keyword", "embedding", "token_cosine"] | None = None,
        similarity_threshold: float | None = None,
    ) -> None:
        """
        Args:
            embed_fn: Optional function that returns embeddings for a string.
                      If None, falls back to keyword overlap matching.
            match_mode: Matching strategy for concern coverage.
                        If None, reads from config (w8_match_mode) or defaults to "keyword".
            similarity_threshold: Optional override for semantic/token cosine threshold.
                                  If None, reads from config or falls back to module constants.
        """
        self._embed_fn = embed_fn

        # Resolve match_mode from config if not explicitly provided
        try:
            from app.config import settings as _settings
            effective_mode = match_mode or _settings.w8_match_mode
        except Exception:
            effective_mode = match_mode or "keyword"
        self._match_mode = effective_mode

        # Resolve threshold from config if not explicitly provided
        if similarity_threshold is not None:
            self._similarity_threshold = similarity_threshold
        else:
            try:
                from app.config import settings as _cfg
                if self._match_mode == "token_cosine":
                    self._similarity_threshold = _cfg.w8_token_cosine_threshold
                else:
                    self._similarity_threshold = _cfg.w8_similarity_threshold
            except Exception:
                self._similarity_threshold = (
                    _SIMILARITY_THRESHOLD if self._match_mode == "embedding" else _TOKEN_COSINE_THRESHOLD
                )

    def compute_metrics(
        self,
        article_id: str,
        source: str,
        human_concerns: list[ReviewerConcern],
        w8_review_text: str,
        w8_workflow_id: str | None = None,
        w8_comment_count: int | None = None,
        w8_concern_texts: list[str] | None = None,
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

        # Precision: what fraction of surfaced W8 concerns map back to human concerns
        w8_concerns_raised = list({c for c in matched_all})
        matched_w8_texts: list[str] = []
        unmatched_w8_texts: list[str] = []
        if w8_concern_texts:
            for text in w8_concern_texts:
                if self._w8_concern_is_validated(text, all_concerns):
                    matched_w8_texts.append(text)
                else:
                    unmatched_w8_texts.append(text)
            precision = len(matched_w8_texts) / len(w8_concern_texts) if w8_concern_texts else None
        elif w8_comment_count and w8_comment_count > 0:
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
            w8_concerns_matched=matched_w8_texts,
            w8_concerns_unmatched=unmatched_w8_texts,
            human_concerns_matched=matched_all,
            human_concerns_missed=missed_all,
        )

    def _concern_is_covered(self, concern_text: str, w8_sentences: list[str]) -> bool:
        """Check if a human concern is covered by any W8 sentence."""
        if self._match_mode == "embedding" and self._embed_fn is not None:
            return self._semantic_match(concern_text, w8_sentences)
        if self._match_mode == "token_cosine":
            return self._token_cosine_match(concern_text, w8_sentences)
        return self._keyword_match(concern_text, w8_sentences)

    def _w8_concern_is_validated(
        self,
        w8_concern_text: str,
        human_concerns: list[ReviewerConcern],
    ) -> bool:
        """Check whether a surfaced W8 concern aligns with any human concern."""
        human_texts = [c.concern_text for c in human_concerns]
        return self._concern_is_covered(w8_concern_text, human_texts)

    def score_text_pair(self, left_text: str, right_text: str) -> float:
        """Score similarity between two concern texts under the configured match mode."""
        if self._match_mode == "embedding" and self._embed_fn is not None:
            try:
                left_emb = self._embed_fn(left_text)  # type: ignore[misc]
                right_emb = self._embed_fn(right_text)  # type: ignore[misc]
                return self._cosine_similarity(left_emb, right_emb)
            except Exception as e:
                logger.debug("Embedding score failed, falling back to token cosine: %s", e)
        if self._match_mode == "token_cosine":
            return self._sparse_cosine_similarity(
                self._token_vector(left_text),
                self._token_vector(right_text),
            )

        left_keywords = set(self._extract_keywords(left_text))
        right_keywords = set(self._extract_keywords(right_text))
        if not left_keywords or not right_keywords:
            return 0.0
        overlap = len(left_keywords & right_keywords)
        denom = max(len(left_keywords), len(right_keywords))
        return overlap / denom

    def _semantic_match(self, concern_text: str, w8_sentences: list[str]) -> bool:
        """Use cosine similarity of embeddings to check coverage."""
        try:
            concern_emb = self._embed_fn(concern_text)  # type: ignore[misc]
            for sentence in w8_sentences:
                sent_emb = self._embed_fn(sentence)  # type: ignore[misc]
                sim = self._cosine_similarity(concern_emb, sent_emb)
                if sim >= self._similarity_threshold:
                    return True
        except Exception as e:
            logger.debug("Semantic match failed, falling back to keyword: %s", e)
            return self._keyword_match(concern_text, w8_sentences)
        return False

    def _token_cosine_match(self, concern_text: str, w8_sentences: list[str]) -> bool:
        """Deterministic token/bigram cosine matcher for local benchmark use."""
        concern_vec = self._token_vector(concern_text)
        concern_tokens = self._extract_keywords(concern_text)
        if not concern_vec:
            return False
        for sentence in w8_sentences:
            sentence_vec = self._token_vector(sentence)
            sim = self._sparse_cosine_similarity(concern_vec, sentence_vec)
            if sim >= self._similarity_threshold and self._has_meaningful_token_overlap(
                concern_tokens,
                self._extract_keywords(sentence),
            ):
                return True
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
        return [ConcernMatcher._normalize_token(w) for w in words if w not in stopwords]

    @classmethod
    def _token_vector(cls, text: str) -> dict[str, float]:
        """Build a deterministic sparse vector from normalized tokens and bigrams."""
        tokens = cls._extract_keywords(text)
        if not tokens:
            return {}
        vec: dict[str, float] = {}
        for token in tokens:
            vec[token] = vec.get(token, 0.0) + 1.0
        for i in range(len(tokens) - 1):
            bigram = f"{tokens[i]}::{tokens[i + 1]}"
            vec[bigram] = vec.get(bigram, 0.0) + 1.5
        return vec

    @staticmethod
    def _has_meaningful_token_overlap(left_tokens: list[str], right_tokens: list[str]) -> bool:
        """Require more than a single incidental token match for token-cosine mode."""
        left = set(left_tokens)
        right = set(right_tokens)
        if not left or not right:
            return False

        overlap = left & right
        if len(overlap) >= 2:
            return True

        left_bigrams = {f"{left_tokens[i]}::{left_tokens[i + 1]}" for i in range(len(left_tokens) - 1)}
        right_bigrams = {f"{right_tokens[i]}::{right_tokens[i + 1]}" for i in range(len(right_tokens) - 1)}
        return bool(left_bigrams & right_bigrams)

    @staticmethod
    def _normalize_token(token: str) -> str:
        """Very light stemming to improve lexical robustness without extra deps."""
        # Greek/Latin -sis/-ses plurals: analyses→analysis, syntheses→synthesis
        if token.endswith("ses") and len(token) > 5:
            candidate = token[:-2] + "is"
            # Only apply when char before -sis is a vowel (Greek pattern)
            sis_pos = len(candidate) - 3
            if sis_pos > 0 and candidate[sis_pos - 1] in "aeiouy":
                return candidate

        for suffix in ("ization", "ations", "ation", "ments", "ment", "ingly", "edly", "ness"):
            if token.endswith(suffix) and len(token) > len(suffix) + 3:
                return token[: -len(suffix)]
        for suffix in ("ings", "ers", "ies", "ing", "ed", "es", "s"):
            if token.endswith(suffix) and len(token) > len(suffix) + 3:
                stem = token[: -len(suffix)]
                if suffix == "ies":
                    stem += "y"
                # Guard: don't strip "ed" from -ve roots (improved→improve not improv)
                if suffix == "ed" and stem.endswith("v"):
                    return stem + "e"
                # Guard: don't strip "s" from -sis, -ous, -us, -is endings
                if suffix == "s" and stem[-1] in ("i", "u", "s"):
                    continue
                # Guard: don't strip "es" leaving stem ending in "s" (processes→process ok via "s")
                if suffix == "es" and stem.endswith("s"):
                    continue
                return stem
        return token

    @staticmethod
    def _sparse_cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
        """Cosine similarity for sparse token dictionaries."""
        if not a or not b:
            return 0.0
        common = set(a) & set(b)
        dot = sum(a[k] * b[k] for k in common)
        norm_a = math.sqrt(sum(v * v for v in a.values()))
        norm_b = math.sqrt(sum(v * v for v in b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

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
