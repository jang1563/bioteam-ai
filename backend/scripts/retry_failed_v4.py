#!/usr/bin/env python3
"""
Retry failed v3 pairs with regex fallback for partial JSON parsing.

Root cause of failures: Gemini responseSchema bug where STRING fields
are truncated — model outputs opening quote of "rationale" but produces
no content, leaving JSON unterminated.

Fix: Try json.loads() first; if that fails, extract structured fields
(contradiction_type, confidence, is_genuine_contradiction) via regex.
Rationale is set to "[truncated]" for partial parses.

Reads _classified_v2.jsonl files, finds pairs where label is None,
re-classifies with improved settings, merges back.
"""
import asyncio
import json
import logging
import os
import re
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
log = logging.getLogger(__name__)

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"
CONCURRENCY = 2
MIN_SLEEP = 6.0  # Seconds between requests (rate limit: 15 req/min)

OUT_DIR = Path(__file__).parent / "output" / "v3"

# Minimal schema — only enum fields + boolean (no STRING to avoid truncation bug)
# We ask for rationale in plain text via a workaround
_SCHEMA_NO_RATIONALE = {
    "type": "OBJECT",
    "properties": {
        "contradiction_type": {
            "type": "STRING",
            "enum": ["direct", "magnitude", "methodological", "temporal", "contextual"],
        },
        "confidence": {"type": "NUMBER"},
        "is_genuine_contradiction": {"type": "BOOLEAN"},
    },
    "required": ["contradiction_type", "confidence", "is_genuine_contradiction"],
}

_SYSTEM = """\
You are a biomedical literature expert classifying scientific contradictions.
Both claims come from the SAME abstract. Assign the MOST SPECIFIC type.

TYPES (apply in order 1→5, stop at first match):
1. DIRECT: Same gene/protein/phenomenon, same biological context, OPPOSITE direction
2. MAGNITUDE: Same direction, same context, INCOMPATIBLE effect sizes
3. METHODOLOGICAL: Same question, same context, DIFFERENT methods yield opposite results
4. TEMPORAL: Same context, results differ specifically due to TIMEPOINT (acute vs chronic, early vs late)
5. CONTEXTUAL [LAST RESORT]: Results differ SOLELY due to different biological contexts

Set is_genuine_contradiction=true for types 1-4, false for type 5.
"""

_USER = """\
Claim A (from same abstract as B):
{claim_a}

Claim B:
{claim_b}

Type hint: This pair was retrieved as a potential {type_hint} contradiction.
Classify following types 1→5 in order."""


def _parse_partial(content: str) -> dict | None:
    """Try json.loads first; fall back to regex for truncated JSON."""
    try:
        return json.loads(content)
    except (json.JSONDecodeError, ValueError):
        # Regex fallback — extract structured fields even from truncated output
        ct_m = re.search(r'"contradiction_type"\s*:\s*"(\w+)"', content)
        conf_m = re.search(r'"confidence"\s*:\s*([\d.]+)', content)
        genuine_m = re.search(r'"is_genuine_contradiction"\s*:\s*(true|false)', content)
        rationale_m = re.search(r'"rationale"\s*:\s*"([^"]{5,})"', content)

        if ct_m and conf_m and genuine_m:
            ct = ct_m.group(1)
            # Validate enum value
            if ct not in ("direct", "magnitude", "methodological", "temporal", "contextual"):
                return None
            return {
                "contradiction_type": ct,
                "confidence": float(conf_m.group(1)),
                "is_genuine_contradiction": genuine_m.group(1) == "true",
                "rationale": rationale_m.group(1) if rationale_m else "[truncated]",
                "_partial_parse": True,
            }
        return None


async def _classify_one(client: httpx.AsyncClient, pair: dict) -> dict | None:
    """Classify one pair. Returns classification dict or None on failure."""
    payload = {
        "contents": [{"role": "user", "parts": [{"text": _USER.format(
            claim_a=pair["claim_a"]["text"][:300],
            claim_b=pair["claim_b"]["text"][:300],
            type_hint=pair.get("intended_type", "unknown"),
        )}]}],
        "systemInstruction": {"parts": [{"text": _SYSTEM}]},
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 256,  # Minimal — only enum + bool + number needed
            "responseMimeType": "application/json",
            "responseSchema": _SCHEMA_NO_RATIONALE,
        },
    }
    try:
        resp = await client.post(API_URL, json=payload, timeout=45.0)
        resp.raise_for_status()
        content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        result = _parse_partial(content)
        if result:
            return result
        log.warning("Unparseable response for %s: %r", pair.get("pair_id", "?"), content[:120])
        return None
    except Exception as e:
        log.warning("Failed %s: %s", pair.get("pair_id", "?"), e)
        return None


async def _classify_one_with_sem(client, pair, sem):
    async with sem:
        return await _classify_one(client, pair)


async def retry_type(ctype: str, sem: asyncio.Semaphore, source: str = "v2"):
    """Retry failed pairs for a given type.

    source: 'v2' reads _classified_v2.jsonl (original classification)
            'retry' reads _retry.jsonl (previous retry attempt)
    """
    if source == "v2":
        in_file = OUT_DIR / f"candidates_{ctype}_classified_v2.jsonl"
    else:
        in_file = OUT_DIR / f"candidates_{ctype}_retry.jsonl"

    out_file = OUT_DIR / f"candidates_{ctype}_v4.jsonl"

    if not in_file.exists():
        log.warning("[%s] Input file not found: %s", ctype, in_file)
        return

    # Load all pairs from source file
    pairs = []
    with open(in_file, "rb") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            pairs.append(d)

    # Find failed pairs (label is not a dict)
    failed = [p for p in pairs if not isinstance(p.get("label"), dict)]
    log.info("[%s] %d failed pairs to retry (of %d total) from %s",
             ctype, len(failed), len(pairs), in_file.name)

    if not failed:
        log.info("[%s] Nothing to retry — copying source as v4", ctype)
        with open(out_file, "w") as f:
            for p in pairs:
                f.write(json.dumps(p) + "\n")
        return

    # Classify failed pairs
    results = {}
    partial_count = 0
    async with httpx.AsyncClient(timeout=60) as client:
        tasks = []
        for pair in failed:
            tasks.append((
                pair["pair_id"],
                asyncio.create_task(_classify_one_with_sem(client, pair, sem)),
            ))

        ok = 0
        for i, (pid, task) in enumerate(tasks):
            lbl = await task
            results[pid] = lbl
            if lbl:
                ok += 1
                if lbl.get("_partial_parse"):
                    partial_count += 1
            if (i + 1) % 10 == 0:
                log.info("  [%s] %d/%d ok=%d (partial=%d)", ctype, i + 1, len(failed), ok, partial_count)
            # Rate limiting
            await asyncio.sleep(MIN_SLEEP)

    log.info("[%s] Classification done: ok=%d partial=%d failed=%d",
             ctype, ok, partial_count, len(failed) - ok)

    # Merge: update pairs with retry results
    updated = 0
    merged = []
    for p in pairs:
        pid = p["pair_id"]
        if pid in results and results[pid] is not None:
            p = dict(p)
            p["label"] = results[pid]
            updated += 1
        merged.append(p)

    # Write merged file
    with open(out_file, "w") as f:
        for p in merged:
            f.write(json.dumps(p) + "\n")

    log.info("[%s] v4 done: %d updated, %d total → %s", ctype, updated, len(merged), out_file.name)


def print_summary(ctype: str, filepath: Path):
    if not filepath.exists():
        print(f"[{ctype}] File not found: {filepath}")
        return
    types_count: dict = {}
    genuine_count: dict = {}
    partial_count = 0
    none_count = 0
    with open(filepath) as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            lbl = d.get("label")
            if isinstance(lbl, dict):
                ct = lbl.get("contradiction_type")
                g = lbl.get("is_genuine_contradiction")
                types_count[ct] = types_count.get(ct, 0) + 1
                if g:
                    genuine_count[ct] = genuine_count.get(ct, 0) + 1
                if lbl.get("_partial_parse"):
                    partial_count += 1
            else:
                none_count += 1
    target = genuine_count.get(ctype, 0)
    total = sum(types_count.values()) + none_count
    print(f"[{ctype:15s}] total={total} dist={types_count}")
    print(f"  genuine_{ctype}={target}  partial_rescue={partial_count}  still_none={none_count}")


async def main():
    if not API_KEY:
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY.")

    sem = asyncio.Semaphore(CONCURRENCY)

    print("\n" + "=" * 60)
    print("RETRY FAILED v3 PAIRS (v4: regex fallback + no STRING schema)")
    print("=" * 60)

    # Use retry.jsonl if it exists (from previous retry_failed_v3.py run),
    # otherwise fall back to v2.
    for ctype in ["direct", "methodological", "temporal", "magnitude"]:
        retry_file = OUT_DIR / f"candidates_{ctype}_retry.jsonl"
        source = "retry" if retry_file.exists() else "v2"
        log.info("[%s] Using source: %s", ctype, source)
        await retry_type(ctype, sem, source=source)

    # Summary
    print("\n=== v4 SUMMARY ===")
    for ctype in ["direct", "methodological", "temporal", "magnitude"]:
        v4_file = OUT_DIR / f"candidates_{ctype}_v4.jsonl"
        print_summary(ctype, v4_file)


if __name__ == "__main__":
    asyncio.run(main())
