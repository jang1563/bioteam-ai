#!/usr/bin/env python3
"""
Retry failed v3 pairs with maxOutputTokens=2048 and simplified schema.
Reads _classified_v2.jsonl files, finds pairs where label is None,
re-classifies with improved settings, merges back.
"""
import asyncio
import json
import logging
import os
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
log = logging.getLogger(__name__)

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"
CONCURRENCY = 2  # Conservative for reliability
MIN_SLEEP = 6.0  # Seconds between requests (rate limit: 15 req/min)

OUT_DIR = Path(__file__).parent / "output" / "v3"

# Simplified schema — NO suggested_resolution
_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "contradiction_type": {
            "type": "STRING",
            "enum": ["direct", "magnitude", "methodological", "temporal", "contextual"]
        },
        "confidence": {"type": "NUMBER"},
        "is_genuine_contradiction": {"type": "BOOLEAN"},
        "rationale": {"type": "STRING"},
    },
    "required": ["contradiction_type", "confidence", "is_genuine_contradiction", "rationale"]
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
Keep rationale concise (2-3 sentences max).
"""

_USER = """\
Claim A (from same abstract as B):
{claim_a}

Claim B:
{claim_b}

Type hint: This pair was retrieved as a potential {type_hint} contradiction.
Classify following types 1→5 in order."""


async def _classify_one(client: httpx.AsyncClient, pair: dict) -> dict | None:
    """Classify one pair. Returns the Gemini classification dict, or None on failure."""
    payload = {
        "contents": [{"role": "user", "parts": [{"text": _USER.format(
            claim_a=pair["claim_a"]["text"][:300],
            claim_b=pair["claim_b"]["text"][:300],
            type_hint=pair.get("intended_type", "unknown"),
        )}]}],
        "systemInstruction": {"parts": [{"text": _SYSTEM}]},
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 2048,  # Increased from 1024
            "responseMimeType": "application/json",
            "responseSchema": _SCHEMA,
        },
    }
    try:
        resp = await client.post(API_URL, json=payload, timeout=45.0)
        resp.raise_for_status()
        log.info("HTTP Request: POST %s %s", API_URL[:80], resp.status_code)
        content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(content)
    except Exception as e:
        log.warning("Failed %s: %s", pair.get("pair_id", "?"), e)
        return None


async def retry_type(ctype: str, sem: asyncio.Semaphore):
    """Retry failed pairs for a given type."""
    v2_file = OUT_DIR / f"candidates_{ctype}_classified_v2.jsonl"
    out_file = OUT_DIR / f"candidates_{ctype}_retry.jsonl"

    # Load all pairs from v2 file
    pairs = []
    with open(v2_file, "rb") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            pairs.append(d)

    # Find failed pairs (label is not a dict)
    failed = [p for p in pairs if not isinstance(p.get("label"), dict)]
    log.info("[%s] %d failed pairs to retry (of %d total)", ctype, len(failed), len(pairs))

    if not failed:
        log.info("[%s] Nothing to retry!", ctype)
        return {}

    # Classify failed pairs
    results = {}
    async with httpx.AsyncClient(timeout=60) as client:
        tasks = []
        for pair in failed:
            tasks.append((pair["pair_id"], pair, asyncio.create_task(_classify_one_with_sem(client, pair, sem))))

        ok = 0
        for i, (pid, pair, task) in enumerate(tasks):
            lbl = await task
            results[pid] = lbl
            if lbl:
                ok += 1
            if (i + 1) % 10 == 0:
                log.info("  [%s] %d/%d ok=%d", ctype, i+1, len(failed), ok)
            # Rate limiting
            await asyncio.sleep(MIN_SLEEP)

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

    log.info("[%s] Retry complete: %d updated, %d total", ctype, updated, len(merged))
    return results


async def _classify_one_with_sem(client, pair, sem):
    async with sem:
        return await _classify_one(client, pair)


async def main():
    if not API_KEY:
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY.")

    sem = asyncio.Semaphore(CONCURRENCY)
    types_to_retry = ["direct", "methodological", "temporal", "magnitude"]

    print("\n" + "="*60)
    print("RETRY FAILED v3 PAIRS (maxOutputTokens=2048)")
    print("="*60)

    for ctype in types_to_retry:
        await retry_type(ctype, sem)

    # Print summary
    print("\n=== RETRY SUMMARY ===")
    for ctype in types_to_retry:
        retry_file = OUT_DIR / f"candidates_{ctype}_retry.jsonl"
        if not retry_file.exists():
            print(f"[{ctype}] No retry file!")
            continue
        types_count = {}
        genuine_count = {}
        with open(retry_file) as f:
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
                else:
                    types_count[None] = types_count.get(None, 0) + 1
        target = genuine_count.get(ctype, 0)
        print(f"[{ctype:15s}] dist={types_count}  genuine_target={target}")


if __name__ == "__main__":
    asyncio.run(main())
