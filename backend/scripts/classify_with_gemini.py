"""Re-classify contradiction candidate pairs using Gemini 2.5 Flash (free tier).

Reads candidates_all.jsonl produced by build_contradiction_corpus.py (Phase 1+2).
Re-classifies ALL pairs via Gemini (bypasses Anthropic API entirely).
Outputs corpus_150_gemini.jsonl + candidates_gemini.jsonl + build_stats_gemini.json.

Usage:
    export GEMINI_API_KEY=<your-key>
    uv run python backend/scripts/classify_with_gemini.py \
        --candidates backend/scripts/output/candidates_all.jsonl \
        --output backend/scripts/output/corpus_150.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gemini_classifier")

# ── Constants ─────────────────────────────────────────────────────────────────

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
CONCURRENCY = 5   # free tier: 15 req/min → conservative
RETRY_DELAY = 4.0  # seconds between retries

ContradictionType = Literal["direct", "contextual", "methodological", "temporal", "magnitude"]

# ── Data models ───────────────────────────────────────────────────────────────

class ClaimRecord(BaseModel):
    text: str
    source_pmid: str
    source_doi: str
    paper_title: str
    year: str


class CandidatePair(BaseModel):
    pair_id: str
    domain: str
    query_source: str
    claim_a: ClaimRecord
    claim_b: ClaimRecord


class ContradictionTypeLabel(BaseModel):
    contradiction_type: ContradictionType
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    is_genuine_contradiction: bool
    suggested_resolution: str | None = None


class CorpusEntry(BaseModel):
    entry_id: str
    domain: str
    query_source: str
    claim_a: ClaimRecord
    claim_b: ClaimRecord
    contradiction_type: str
    haiku_confidence: float   # field name kept for schema compat; value is Gemini's
    haiku_rationale: str      # field name kept for schema compat
    is_genuine: bool
    suggested_resolution: str | None = None
    annotator_1_type: str | None = None
    annotator_2_type: str | None = None
    final_type: str | None = None
    curation_notes: str | None = None


# ── Gemini prompt ─────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a biomedical literature expert classifying scientific contradictions.
Assign the MOST SPECIFIC type that applies — work through types 1→5 in order and stop at the first match.

TYPES (most specific → least specific):

1. DIRECT: Same gene/protein/phenomenon, same organism/cell-type/condition, results point
   in opposite directions (up vs down, activates vs inhibits, increases vs decreases).
   Example: Paper A: "BDNF overexpression increases LTP in mouse hippocampus"
            Paper B: "BDNF overexpression decreases LTP in mouse hippocampus"
   → is_genuine_contradiction = true

2. MAGNITUDE: Same direction of effect, same biological context, but effect sizes are
   quantitatively incompatible (e.g., 10-fold vs 1.2-fold; OR=5.0 vs OR=1.1 for
   identical exposure+outcome). Both claim the same direction but disagree on how much.
   Example: Paper A: "Smoking raises lung cancer risk OR=15"
            Paper B: "Smoking raises lung cancer risk OR=1.3"
   → is_genuine_contradiction = true

3. METHODOLOGICAL: Same research question, same or equivalent biological context, but
   different measurement assays or platforms produce opposite/incompatible conclusions.
   Example: Paper A (microarray): "Gene X is upregulated 3-fold in tumor"
            Paper B (RNA-seq): "Gene X shows no significant change in tumor"
   → is_genuine_contradiction = true

4. TEMPORAL: Same phenomenon in the same biological context, results differ specifically
   because one study uses an earlier vs later timepoint, developmental stage, or disease phase.
   Example: Paper A (acute 6 h): "TNF-α activates NF-κB"
            Paper B (chronic 14 days): "TNF-α suppresses NF-κB via receptor desensitization"
   → is_genuine_contradiction = true

5. CONTEXTUAL [LAST RESORT — only if 1–4 do not apply]: Results differ SOLELY because of
   genuinely different biological contexts (different species, tissue, patient population)
   and no specific methodological, temporal, or magnitude factor is present.
   Example: Paper A: "mTOR promotes apoptosis in yeast"
            Paper B: "mTOR inhibits apoptosis in human cancer cells"
   → is_genuine_contradiction = false

DECISION PROCESS (apply in order):
① Are both claims about the SAME entity in the SAME context with OPPOSITE direction? → DIRECT
② Same direction, same context, but incompatible effect sizes? → MAGNITUDE
③ Same question, same context, but DIFFERENT methods give opposite results? → METHODOLOGICAL
④ Same context, but results differ due to TIMEPOINT or disease phase? → TEMPORAL
⑤ None of the above — only different species/tissue/population explains the difference? → CONTEXTUAL

CRITICAL: Do NOT default to contextual because papers come from different labs.
Different labs, same context, same methods, opposite results = DIRECT (not contextual).
Confidence: 0.90+ = unambiguous, 0.70–0.89 = probable, 0.50–0.69 = uncertain.
"""

_USER_TEMPLATE = """\
Domain: {domain}
{type_hint}
Claim A (PMID {pmid_a}, {year_a}, Paper: {title_a}):
{claim_a}

Claim B (PMID {pmid_b}, {year_b}, Paper: {title_b}):
{claim_b}

Classify this pair following the 5-step decision process."""


# ── Gemini API call ───────────────────────────────────────────────────────────

async def _classify_one(
    client: httpx.AsyncClient,
    pair: CandidatePair,
    api_key: str,
    sem: asyncio.Semaphore,
    type_hint: str = "",
) -> tuple[CandidatePair, ContradictionTypeLabel | None]:
    """Classify a single pair with Gemini 2.5 Flash."""
    hint_line = f"[TYPE HINT: This pair was selected as a candidate for a {type_hint} contradiction. Consider this type first.]\n" if type_hint else ""
    prompt = _USER_TEMPLATE.format(
        domain=pair.domain,
        type_hint=hint_line,
        pmid_a=pair.claim_a.source_pmid,
        year_a=pair.claim_a.year,
        title_a=pair.claim_a.paper_title[:80],
        claim_a=pair.claim_a.text,
        pmid_b=pair.claim_b.source_pmid,
        year_b=pair.claim_b.year,
        title_b=pair.claim_b.paper_title[:80],
        claim_b=pair.claim_b.text,
    )

    payload = {
        "system_instruction": {"parts": [{"text": _SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "contradiction_type": {
                        "type": "STRING",
                        "enum": ["direct", "contextual", "methodological", "temporal", "magnitude"],
                    },
                    "confidence": {"type": "NUMBER"},
                    "rationale": {"type": "STRING"},
                    "is_genuine_contradiction": {"type": "BOOLEAN"},
                    "suggested_resolution": {"type": "STRING", "nullable": True},
                },
                "required": ["contradiction_type", "confidence", "rationale", "is_genuine_contradiction"],
            },
        },
    }

    async with sem:
        for attempt in range(3):
            try:
                resp = await client.post(
                    GEMINI_URL,
                    params={"key": api_key},
                    json=payload,
                    timeout=30.0,
                )
                if resp.status_code == 429:
                    wait = RETRY_DELAY * (attempt + 1)
                    logger.warning("Rate limited on %s — waiting %.1fs", pair.pair_id, wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                # Strip markdown fences if model ignores responseMimeType
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                data = json.loads(raw)
                label = ContradictionTypeLabel(**data)
                return pair, label
            except Exception as exc:
                if attempt < 2:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    logger.warning("Gemini failed for %s: %s", pair.pair_id, exc)
                    return pair, None
    return pair, None


async def classify_all(
    pairs: list[CandidatePair],
    api_key: str,
    concurrency: int = CONCURRENCY,
    type_hint: str = "",
) -> list[tuple[CandidatePair, ContradictionTypeLabel | None]]:
    """Classify all pairs concurrently with Gemini."""
    sem = asyncio.Semaphore(concurrency)
    results: list[tuple[CandidatePair, ContradictionTypeLabel | None]] = []

    logger.info("Phase 3: Classifying %d pairs with Gemini %s (concurrency=%d, type_hint=%r)...",
                len(pairs), GEMINI_MODEL, concurrency, type_hint or "none")

    async with httpx.AsyncClient() as client:
        tasks = [_classify_one(client, pair, api_key, sem, type_hint=type_hint) for pair in pairs]
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            result = await coro
            results.append(result)
            if i % 50 == 0:
                genuine = sum(1 for _, l in results if l and l.is_genuine_contradiction)
                logger.info("  %d / %d classified — %d genuine so far", i, len(pairs), genuine)

    n_ok = sum(1 for _, l in results if l is not None)
    n_fail = sum(1 for _, l in results if l is None)
    logger.info("Phase 3 complete: %d classified, %d failed", n_ok, n_fail)
    return results


# ── Phase 4: Filter + balance ─────────────────────────────────────────────────

def filter_and_balance(
    classified: list[tuple[CandidatePair, ContradictionTypeLabel | None]],
    target_per_type: int = 30,
    min_per_type: int = 20,
    confidence_threshold: float = 0.65,
) -> tuple[list[CorpusEntry], dict]:
    all_types: list[str] = ["direct", "contextual", "methodological", "temporal", "magnitude"]

    by_type: dict[str, list[tuple[CandidatePair, ContradictionTypeLabel]]] = defaultdict(list)
    n_not_genuine = n_low_confidence = n_failed = 0

    for pair, label in classified:
        if label is None:
            n_failed += 1
            continue
        # Note: include ALL typed pairs regardless of is_genuine_contradiction.
        # "contextual" contradictions are valid corpus entries (different context = annotatable).
        # Human annotators make the final genuine/not-genuine call.
        # Track not_genuine for stats only.
        if not label.is_genuine_contradiction:
            n_not_genuine += 1
        if label.confidence < confidence_threshold:
            n_low_confidence += 1
            continue
        by_type[label.contradiction_type].append((pair, label))

    for t in all_types:
        by_type[t].sort(key=lambda x: x[1].confidence, reverse=True)

    selected: list[CorpusEntry] = []
    entry_counter = 0
    stats: dict[str, int] = {}

    for t in all_types:
        pool = by_type[t]
        take = min(target_per_type, len(pool))
        stats[t] = take
        if take < min_per_type:
            logger.warning("Type '%s': only %d entries available (min=%d)", t, take, min_per_type)
        for pair, label in pool[:take]:
            entry_counter += 1
            selected.append(CorpusEntry(
                entry_id=f"CT-{entry_counter:03d}",
                domain=pair.domain,
                query_source=pair.query_source,
                claim_a=pair.claim_a,
                claim_b=pair.claim_b,
                contradiction_type=label.contradiction_type,
                haiku_confidence=label.confidence,
                haiku_rationale=label.rationale,
                is_genuine=label.is_genuine_contradiction,
                suggested_resolution=label.suggested_resolution,
            ))

    stats_out = {
        "model": GEMINI_MODEL,
        "total_classified": len(classified),
        "failed": n_failed,
        "not_genuine": n_not_genuine,
        "low_confidence": n_low_confidence,
        "genuine_pool_size": sum(len(v) for v in by_type.values()),
        "selected": len(selected),
        "by_type": stats,
        "shortfall_types": [t for t in all_types if stats.get(t, 0) < min_per_type],
    }
    return selected, stats_out


# ── I/O ───────────────────────────────────────────────────────────────────────

def load_candidates(path: Path) -> list[CandidatePair]:
    """Load CandidatePairs from candidates_all.jsonl."""
    pairs: list[CandidatePair] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            pairs.append(CandidatePair(
                pair_id=row["pair_id"],
                domain=row["domain"],
                query_source=row["query_source"],
                claim_a=ClaimRecord(**row["claim_a"]),
                claim_b=ClaimRecord(**row["claim_b"]),
            ))
    return pairs


def export_jsonl(entries: list[CorpusEntry], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(e.model_dump_json() + "\n")
    logger.info("Exported %d corpus entries → %s", len(entries), path)


def export_candidates_jsonl(
    classified: list[tuple[CandidatePair, ContradictionTypeLabel | None]],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for pair, label in classified:
            row = {
                "pair_id": pair.pair_id,
                "domain": pair.domain,
                "query_source": pair.query_source,
                "claim_a": pair.claim_a.model_dump(),
                "claim_b": pair.claim_b.model_dump(),
                "label": label.model_dump() if label else None,
            }
            f.write(json.dumps(row) + "\n")
    logger.info("Exported %d classified pairs → %s", len(classified), path)


def print_stats(stats: dict, n_candidates: int) -> None:
    print("\n" + "=" * 60)
    print(f"GEMINI CLASSIFICATION STATS  (model: {stats['model']})")
    print("=" * 60)
    print(f"Candidate pairs input:        {n_candidates}")
    print(f"Classified:                   {stats['total_classified'] - stats['failed']}")
    print(f"  Failed (API error):         {stats['failed']}")
    print(f"  Not genuine:                {stats['not_genuine']}")
    print(f"  Low confidence (<0.65):     {stats['low_confidence']}")
    print(f"  Genuine pool:               {stats['genuine_pool_size']}")
    print(f"\nSelected for corpus:          {stats['selected']}")
    print("\nBy type:")
    for t, n in stats["by_type"].items():
        flag = " ⚠ SHORTFALL" if t in stats.get("shortfall_types", []) else ""
        print(f"  {t:<22} {n:>3}{flag}")
    if stats.get("shortfall_types"):
        print(f"\n⚠  Shortfall: {stats['shortfall_types']}")
    print("=" * 60 + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify contradiction pairs with Gemini 2.5 Flash (free tier)"
    )
    parser.add_argument(
        "--candidates",
        required=True,
        type=Path,
        help="Input candidates_all.jsonl from build_contradiction_corpus.py",
    )
    parser.add_argument(
        "--output",
        default="backend/scripts/output/corpus_150.jsonl",
        type=Path,
        help="Output corpus JSONL path",
    )
    parser.add_argument("--target-per-type", type=int, default=30)
    parser.add_argument("--min-per-type", type=int, default=20)
    parser.add_argument("--confidence-threshold", type=float, default=0.65)
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY)
    parser.add_argument(
        "--type-hint",
        default="",
        help="Optional type hint injected into every prompt (e.g. 'direct', 'methodological')",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set. Export it in the current environment.")

    # Derive sibling output paths
    out_dir = args.output.parent
    candidates_out = out_dir / "candidates_gemini.jsonl"
    stats_out = out_dir / "build_stats_gemini.json"

    # Load candidates
    pairs = load_candidates(args.candidates)
    logger.info("Loaded %d candidate pairs from %s", len(pairs), args.candidates)

    # Phase 3: Gemini classification
    t0 = time.time()
    classified = asyncio.run(classify_all(pairs, api_key, concurrency=args.concurrency, type_hint=args.type_hint))
    elapsed = time.time() - t0
    logger.info("Classification took %.1fs (%.2fs/pair)", elapsed, elapsed / max(len(pairs), 1))

    # Save classified candidates
    export_candidates_jsonl(classified, candidates_out)

    # Phase 4: Filter + balance
    selected, stats = filter_and_balance(
        classified,
        target_per_type=args.target_per_type,
        min_per_type=args.min_per_type,
        confidence_threshold=args.confidence_threshold,
    )

    # Phase 5: Export
    export_jsonl(selected, args.output)

    # Save stats
    stats_out.parent.mkdir(parents=True, exist_ok=True)
    with open(stats_out, "w") as f:
        json.dump(stats, f, indent=2)

    print_stats(stats, len(pairs))


if __name__ == "__main__":
    main()
