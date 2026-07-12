#!/usr/bin/env python3
"""Shared quality guards for corpus expansion scripts."""

from __future__ import annotations

import re

# Historical manual exclusions from Phase A audit.
# These IDs should not be reintroduced unless explicitly overridden.
LEGACY_EXCLUDED_IDS = {
    "V3-DIR-0037",
    "V3-DIR-0052",
    "V3-MET-0077",
    "V3-MAG-0007",
    "V3-MAG-0040",
    "V3-MAG-0049",
    "V3-TEM-0092",
    "V3-TEM-0075",
    "V3-MET-0083",
}

_TRUNC_PATTERNS = [
    re.compile(r"\bp\s*[<=>]\s*0\.$", flags=re.IGNORECASE),
    re.compile(r"=\s*\.$"),
]

_SHORT_START_WHITELIST = {
    "a",
    "an",
    "as",
    "at",
    "by",
    "for",
    "if",
    "in",
    "is",
    "it",
    "no",
    "of",
    "on",
    "or",
    "to",
    "vs",
    "we",
}

_FRAGMENT_FOLLOWERS = {"with", "the", "of", "and", "or", "to"}


def claim_quality_issues(text: str) -> list[str]:
    """Return quality issue codes for a single claim text."""
    issues: list[str] = []
    claim = text.strip()

    if len(claim) < 25:
        issues.append("too_short")

    words = re.findall(r"[A-Za-z]+", claim)
    if len(words) < 5:
        issues.append("too_few_tokens")

    if any(pattern.search(claim) for pattern in _TRUNC_PATTERNS):
        issues.append("truncated_pvalue_pattern")

    if claim.count(")") > claim.count("("):
        issues.append("unmatched_closing_paren")

    if len(words) >= 2:
        first = words[0].lower()
        second = words[1].lower()
        if len(first) <= 2 and first not in _SHORT_START_WHITELIST:
            issues.append("suspicious_short_start_token")
        if len(first) <= 3 and first not in _SHORT_START_WHITELIST and second in _FRAGMENT_FOLLOWERS:
            issues.append("suspicious_fragment_prefix")

    return sorted(set(issues))


def pair_quality_issues(claim_a: str, claim_b: str) -> list[str]:
    """Return prefixed issue codes for a pair of claims."""
    issues: list[str] = []
    issues.extend(f"claim_a:{issue}" for issue in claim_quality_issues(claim_a))
    issues.extend(f"claim_b:{issue}" for issue in claim_quality_issues(claim_b))
    return sorted(set(issues))
