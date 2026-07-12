"""Contradiction taxonomy helpers for W6 ambiguity workflows.

Canonical taxonomy (v3 corpus / evaluation):
- direct
- contextual
- methodological
- temporal
- magnitude

This module also normalizes legacy v0.1 labels that still may appear in
historical prompts/checkpoints.
"""

from __future__ import annotations

CANONICAL_TYPES: tuple[str, ...] = (
    "direct",
    "contextual",
    "methodological",
    "temporal",
    "magnitude",
)

GENUINE_TYPES: tuple[str, ...] = (
    "direct",
    "methodological",
    "temporal",
    "magnitude",
)

LEGACY_TO_CANONICAL: dict[str, str] = {
    # v0.1 ambiguity taxonomy
    "conditional_truth": "contextual",
    "technical_artifact": "methodological",
    "interpretive_framing": "methodological",
    "statistical_noise": "magnitude",
    "temporal_dynamics": "temporal",
}

VALID_TYPE_SET = set(CANONICAL_TYPES)


def normalize_type_label(label: str) -> str | None:
    """Map one raw label to canonical taxonomy; return None if unknown."""
    if not label:
        return None
    key = str(label).strip().lower()
    if not key:
        return None
    mapped = LEGACY_TO_CANONICAL.get(key, key)
    if mapped in VALID_TYPE_SET:
        return mapped
    return None


def normalize_type_list(labels: list[str] | None) -> list[str]:
    """Normalize, filter unknowns, and deduplicate while preserving order."""
    if not labels:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for raw in labels:
        normalized = normalize_type_label(raw)
        if not normalized or normalized in seen:
            continue
        out.append(normalized)
        seen.add(normalized)
    return out

