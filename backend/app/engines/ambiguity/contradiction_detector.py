"""Contradiction Detector — deterministic pre-screening for contradiction pairs.

Uses ChromaDB cosine distance to find semantically similar but potentially
contradictory claim pairs. No LLM calls — pure algorithmic pre-screening
to reduce expensive LLM classification calls.

Only queries 'literature' and 'lab_kb' collections (never 'synthesis')
to prevent circular reasoning.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.memory.semantic import SemanticMemory

logger = logging.getLogger(__name__)

# Allowed collections for contradiction detection (no synthesis)
_ALLOWED_COLLECTIONS = ["literature", "lab_kb"]


class ContradictionDetector:
    """Deterministic pre-screening for potential contradiction pairs.

    Uses ChromaDB cosine distance + linguistic contradiction markers
    to identify claim pairs worthy of LLM classification.
    """

    SIMILARITY_THRESHOLD: float = 0.35  # Max cosine distance to be "related"
    DIVERGENCE_FLOOR: float = 0.05      # Min distance to filter near-duplicates
    MIN_CLAIM_LENGTH: int = 20

    CONTRADICTION_MARKERS: list[tuple[str, str]] = [
        ("increase", "decrease"),
        ("upregulate", "downregulate"),
        ("promote", "inhibit"),
        ("activate", "suppress"),
        ("enhance", "reduce"),
        ("positive", "negative"),
        ("significant", "not significant"),
        ("required", "dispensable"),
        ("causal", "correlational"),
        ("elevated", "reduced"),
    ]

    def find_candidate_pairs(
        self,
        claims: list[str],
        memory: SemanticMemory,
        collections: list[str] | None = None,
        n_per_claim: int = 5,
    ) -> list[tuple[str, str, float]]:
        """Find semantically related claim pairs that may contradict.

        For each claim, searches ChromaDB for similar documents.
        Pairs with cosine distance between DIVERGENCE_FLOOR and
        SIMILARITY_THRESHOLD are candidates.

        Args:
            claims: List of claim strings to check.
            memory: SemanticMemory instance.
            collections: Collections to search (default: literature + lab_kb).
            n_per_claim: Number of results per claim per collection.

        Returns:
            List of (claim_a, claim_b, similarity_score) tuples,
            sorted by similarity (highest first).
            similarity_score = 1.0 - cosine_distance.
        """
        if len(claims) < 2:
            return []

        target_collections = collections or _ALLOWED_COLLECTIONS
        # Enforce safety: never query synthesis
        target_collections = [c for c in target_collections if c in _ALLOWED_COLLECTIONS]

        raw_pairs: list[tuple[str, str, float]] = []

        # Strategy 1: Cross-match claims against ChromaDB
        for claim in claims:
            if len(claim) < self.MIN_CLAIM_LENGTH:
                continue
            for coll in target_collections:
                try:
                    results = memory.search(coll, claim, n_results=n_per_claim)
                except Exception:
                    continue
                for result in results:
                    text = result.get("text", "")
                    distance = result.get("distance", 1.0)
                    if len(text) < self.MIN_CLAIM_LENGTH:
                        continue
                    if self.DIVERGENCE_FLOOR < distance < self.SIMILARITY_THRESHOLD:
                        similarity = 1.0 - distance
                        raw_pairs.append((claim, text, similarity))

        # Strategy 2: All-pairs from input claims list
        for i in range(len(claims)):
            if len(claims[i]) < self.MIN_CLAIM_LENGTH:
                continue
            for j in range(i + 1, len(claims)):
                if len(claims[j]) < self.MIN_CLAIM_LENGTH:
                    continue
                # Use contradiction markers as signal for direct claim pairs
                if self._has_contradiction_markers(claims[i], claims[j]):
                    raw_pairs.append((claims[i], claims[j], 0.7))

        deduped = self._deduplicate_pairs(raw_pairs)
        return self.filter_by_quality(deduped)

    def _has_contradiction_markers(self, claim_a: str, claim_b: str) -> bool:
        """Check if two claims contain opposite-meaning terms.

        Case-insensitive. Returns True if any marker pair is found
        where one term is in claim_a and the other in claim_b.
        """
        a_lower = claim_a.lower()
        b_lower = claim_b.lower()
        for term_a, term_b in self.CONTRADICTION_MARKERS:
            if (term_a in a_lower and term_b in b_lower) or \
               (term_b in a_lower and term_a in b_lower):
                return True
        return False

    def _deduplicate_pairs(
        self,
        pairs: list[tuple[str, str, float]],
    ) -> list[tuple[str, str, float]]:
        """Remove duplicate pairs where (a,b) == (b,a).

        Keeps the entry with the highest similarity score.
        """
        seen: dict[tuple[str, str], float] = {}
        for a, b, score in pairs:
            key = (min(a, b), max(a, b))
            if key not in seen or score > seen[key]:
                seen[key] = score
        return [(k[0], k[1], v) for k, v in seen.items()]

    def filter_by_quality(
        self,
        pairs: list[tuple[str, str, float]],
        max_pairs: int = 20,
    ) -> list[tuple[str, str, float]]:
        """Apply quality filters and cap.

        Prioritizes pairs with contradiction markers, then by similarity.
        """
        # Separate marker-matched and non-marker pairs
        with_markers = []
        without_markers = []
        for a, b, score in pairs:
            if len(a) < self.MIN_CLAIM_LENGTH or len(b) < self.MIN_CLAIM_LENGTH:
                continue
            if self._has_contradiction_markers(a, b):
                with_markers.append((a, b, score))
            else:
                without_markers.append((a, b, score))

        # Sort each group by similarity (highest first)
        with_markers.sort(key=lambda x: x[2], reverse=True)
        without_markers.sort(key=lambda x: x[2], reverse=True)

        # Prioritize marker-matched pairs
        result = with_markers + without_markers
        return result[:max_pairs]
