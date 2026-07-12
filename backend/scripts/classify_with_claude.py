#!/usr/bin/env python3
"""
Phase B: Classify 68 None pairs using Claude Haiku via Anthropic SDK.

Gemini safety filters permanently blocked these 68 pairs.
Claude Haiku is used as fallback classifier — same schema, same taxonomy.

Reads *_v4.jsonl files, finds pairs where label is None,
classifies with Haiku, merges back → *_v5.jsonl files.
Then updates corpus_final_v2.jsonl with newly classified genuine pairs.

Expected cost: ~68 × 400 tokens input × 200 tokens output × Haiku pricing
              ≈ 68 × ($0.80 + $4.00) / 1M = ~$0.33 total (very conservative)
"""
import json
import logging
import os
from collections import Counter
from pathlib import Path

import anthropic
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
log = logging.getLogger(__name__)

OUT_DIR = Path(__file__).parent / "output" / "v3"
CORPUS_V2 = OUT_DIR / "corpus_final_v2.jsonl"
CORPUS_V3 = OUT_DIR / "corpus_final_v3.jsonl"

CONF_THRESHOLD = 0.80
CONF_THRESHOLD_TEMPORAL = 0.75

# Use haiku for cost efficiency
MODEL = "claude-haiku-4-5-20251001"

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


class ContradictionLabel(BaseModel):
    contradiction_type: str = Field(
        description="One of: direct, magnitude, methodological, temporal, contextual"
    )
    confidence: float = Field(ge=0.0, le=1.0)
    is_genuine_contradiction: bool = Field(
        description="True for direct/magnitude/methodological/temporal; False for contextual"
    )
    rationale: str = Field(description="2-3 sentence explanation")


_SYSTEM = """\
You are a biomedical literature expert classifying scientific contradictions.
Both claims come from the SAME abstract. Assign the MOST SPECIFIC type.

TYPES (apply in order 1→5, stop at first match):
1. DIRECT: Same gene/protein/phenomenon, same biological context, OPPOSITE direction
   e.g. overexpression → increased X; knockdown → decreased X
2. MAGNITUDE: Same direction, same context, INCOMPATIBLE effect sizes
   e.g. "significant benefit" vs "inconsistent results" or "modest effect at best"
3. METHODOLOGICAL: Same question, same context, DIFFERENT methods yield opposite results
   e.g. fold-change values correlated but p-values did not
4. TEMPORAL: Same context, results differ specifically due to TIMEPOINT
   e.g. acute vs chronic, early vs late stage, short-term vs long-term
5. CONTEXTUAL [LAST RESORT]: Results differ SOLELY due to different biological contexts
   e.g. different cell types, species, or patient populations

Set is_genuine_contradiction=true for types 1-4 (genuine scientific tension).
Set is_genuine_contradiction=false for type 5 (context explains the difference).
Set confidence < 0.80 if uncertain — these will be filtered out.

IMPORTANT: Only classify as genuine (types 1-4) if both claims clearly assert
incompatible findings. Limitation statements, uncertainty phrases ("may", "remains unclear"),
or knowledge gaps do NOT constitute genuine contradictions.
"""

_USER = """\
Claim A (from same abstract as Claim B):
{claim_a}

Claim B:
{claim_b}

Type hint: This pair was extracted as a potential {type_hint} contradiction.
Classify following types 1→5 in order. Be strict — prefer contextual (5) over genuine if uncertain."""


def classify_one(pair: dict) -> dict | None:
    """Classify one pair synchronously. Returns label dict or None on failure."""
    claim_a = pair.get("claim_a", {}).get("text", "")[:400]
    claim_b = pair.get("claim_b", {}).get("text", "")[:400]
    type_hint = pair.get("intended_type", "unknown")

    if not claim_a or not claim_b:
        log.warning("Empty claims for %s", pair.get("pair_id", "?"))
        return None

    try:
        # Use Anthropic SDK with structured output via tool_use
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=_SYSTEM,
            messages=[{"role": "user", "content": _USER.format(
                claim_a=claim_a,
                claim_b=claim_b,
                type_hint=type_hint,
            )}],
            tools=[{
                "name": "classify_contradiction",
                "description": "Classify the contradiction between two biomedical claims",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "contradiction_type": {
                            "type": "string",
                            "enum": ["direct", "magnitude", "methodological", "temporal", "contextual"],
                        },
                        "confidence": {"type": "number"},
                        "is_genuine_contradiction": {"type": "boolean"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["contradiction_type", "confidence", "is_genuine_contradiction", "rationale"],
                },
            }],
            tool_choice={"type": "tool", "name": "classify_contradiction"},
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "classify_contradiction":
                inp = block.input
                # Validate
                ct = inp.get("contradiction_type", "")
                if ct not in ("direct", "magnitude", "methodological", "temporal", "contextual"):
                    log.warning("Invalid contradiction_type '%s' for %s", ct, pair.get("pair_id"))
                    return None
                return {
                    "contradiction_type": ct,
                    "confidence": float(inp.get("confidence", 0.0)),
                    "is_genuine_contradiction": bool(inp.get("is_genuine_contradiction", False)),
                    "rationale": str(inp.get("rationale", "")),
                    "_partial_parse": False,
                    "_classifier": "claude_haiku",
                }
        log.warning("No tool_use block for %s", pair.get("pair_id", "?"))
        return None

    except Exception as e:
        log.warning("Failed %s: %s", pair.get("pair_id", "?"), e)
        return None


def process_type(ctype: str) -> list[dict]:
    """Process None pairs for one contradiction type. Returns newly classified genuine entries."""
    v4_file = OUT_DIR / f"candidates_{ctype}_v4.jsonl"
    v5_file = OUT_DIR / f"candidates_{ctype}_v5.jsonl"

    if not v4_file.exists():
        log.warning("[%s] v4 file not found", ctype)
        return []

    pairs = [json.loads(l) for l in open(v4_file) if l.strip()]
    failed = [p for p in pairs if not isinstance(p.get("label"), dict)]

    log.info("[%s] %d None pairs to classify (of %d total)", ctype, len(failed), len(pairs))

    if not failed:
        log.info("[%s] Nothing to classify — copying to v5", ctype)
        with open(v5_file, "w") as f:
            for p in pairs:
                f.write(json.dumps(p) + "\n")
        return []

    results = {}
    ok = 0
    for i, pair in enumerate(failed):
        pid = pair["pair_id"]
        lbl = classify_one(pair)
        results[pid] = lbl
        if lbl:
            ok += 1
        if (i + 1) % 5 == 0 or (i + 1) == len(failed):
            log.info("  [%s] %d/%d classified (ok=%d)", ctype, i + 1, len(failed), ok)

    log.info("[%s] Done: ok=%d / %d attempted", ctype, ok, len(failed))

    # Merge
    merged = []
    for p in pairs:
        pid = p["pair_id"]
        if pid in results and results[pid] is not None:
            p = dict(p)
            p["label"] = results[pid]
        merged.append(p)

    with open(v5_file, "w") as f:
        for p in merged:
            f.write(json.dumps(p) + "\n")

    log.info("[%s] Saved %d entries → %s", ctype, len(merged), v5_file.name)
    return []  # Corpus update done separately


def build_new_entries() -> list[dict]:
    """Collect newly classified genuine entries from v5 files that were None in v4."""
    # Load existing corpus_final_v2 IDs to avoid duplication
    existing_ids = set()
    if CORPUS_V2.exists():
        for l in open(CORPUS_V2):
            if l.strip():
                existing_ids.add(json.loads(l)["id"])

    new_entries = []
    for ctype in ["direct", "methodological", "temporal", "magnitude"]:
        v4_file = OUT_DIR / f"candidates_{ctype}_v4.jsonl"
        v5_file = OUT_DIR / f"candidates_{ctype}_v5.jsonl"
        if not v4_file.exists() or not v5_file.exists():
            continue

        v4_none_ids = {
            json.loads(l)["pair_id"]
            for l in open(v4_file) if l.strip()
            and not isinstance(json.loads(l).get("label"), dict)
        }

        for l in open(v5_file):
            if not l.strip():
                continue
            entry = json.loads(l)
            if entry["pair_id"] not in v4_none_ids:
                continue  # Was already classified in v4
            lbl = entry.get("label")
            if not isinstance(lbl, dict):
                continue  # Still None after Haiku classification

            # Apply quality filter
            conf = lbl.get("confidence", 0.0)
            ct = lbl.get("contradiction_type", "")
            threshold = CONF_THRESHOLD_TEMPORAL if ct == "temporal" else CONF_THRESHOLD
            if conf < threshold or conf > 1.0:
                continue
            if not lbl.get("is_genuine_contradiction", False):
                continue  # Only add genuine; contextual doesn't need rescue

            # Build corpus entry (same schema as build_final_corpus.py)
            claim_a = entry.get("claim_a", {})
            claim_b = entry.get("claim_b", {})
            corpus_entry = {
                "id": entry["pair_id"],
                "source_pmid": claim_a.get("source_pmid", ""),
                "source_doi": claim_a.get("source_doi", ""),
                "paper_title": claim_a.get("paper_title", ""),
                "domain": entry.get("domain", ""),
                "extraction_pattern": str(entry.get("extraction_pattern", "")),
                "claim_a": claim_a.get("text", ""),
                "claim_b": claim_b.get("text", ""),
                "contradiction_type": ct,
                "is_genuine_contradiction": True,
                "confidence": conf,
                "rationale": lbl.get("rationale", ""),
                "intended_type": entry.get("intended_type", ""),
                "_partial_parse": False,
                "_classifier": "claude_haiku",
            }

            if corpus_entry["id"] not in existing_ids:
                new_entries.append(corpus_entry)
                log.info("  NEW genuine: %s  type=%s  conf=%.2f", corpus_entry["id"], ct, conf)

    return new_entries


def update_corpus(new_entries: list[dict]) -> None:
    """Append new entries to corpus_final_v2 → write corpus_final_v3."""
    existing = []
    if CORPUS_V2.exists():
        existing = [json.loads(l) for l in open(CORPUS_V2) if l.strip()]

    combined = existing + new_entries
    # Sort: genuine first, then by type, then conf desc
    combined.sort(key=lambda e: (
        0 if e["is_genuine_contradiction"] else 1,
        e["contradiction_type"],
        -e["confidence"],
    ))

    with open(CORPUS_V3, "w") as f:
        for e in combined:
            f.write(json.dumps(e) + "\n")

    genuine = Counter(e["contradiction_type"] for e in combined if e["is_genuine_contradiction"])
    contextual = sum(1 for e in combined if not e["is_genuine_contradiction"])

    print("\n=== corpus_final_v3.jsonl ===")
    print(f"Base (v2)     : {len(existing)} entries")
    print(f"New (Haiku)   : {len(new_entries)} entries")
    print(f"Total output  : {len(combined)} entries")
    print(f"\nGenuine non-contextual: {sum(genuine.values())}")
    for ct in ["direct", "temporal", "magnitude", "methodological"]:
        print(f"  {ct:20s}: {genuine.get(ct, 0)}")
    print(f"Contextual    : {contextual}")
    print(f"Output file   : {CORPUS_V3}")


def main():
    print("\n" + "=" * 60)
    print("PHASE B: Claude Haiku classification of 68 None pairs")
    print("=" * 60)

    for ctype in ["direct", "methodological", "temporal", "magnitude"]:
        process_type(ctype)

    print("\n=== Collecting newly classified genuine entries ===")
    new_entries = build_new_entries()
    print(f"New genuine entries from Haiku: {len(new_entries)}")

    update_corpus(new_entries)


if __name__ == "__main__":
    main()
