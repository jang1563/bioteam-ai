#!/usr/bin/env python3
"""
Phase B: Classify 68 None pairs using Gemini plain-text mode (free tier).

Root cause of original failures: Gemini safety filters blocked calls that used
responseMimeType="application/json" + responseSchema. Plain text mode bypasses
this (status 200, no safety block). We parse JSON from the text response.

Reads *_v4.jsonl files, finds pairs where label is None,
classifies with Gemini plain text, merges back → *_v5.jsonl files.
Then updates corpus_final_v2.jsonl → corpus_final_v3.jsonl.
"""
import asyncio
import json
import logging
import os
import re
from collections import Counter
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
log = logging.getLogger(__name__)

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"
CONCURRENCY = 3
MIN_SLEEP = 4.0  # seconds between requests (15 rpm free tier)

OUT_DIR = Path(__file__).parent / "output" / "v3"
CORPUS_V2 = OUT_DIR / "corpus_final_v2.jsonl"
CORPUS_V3 = OUT_DIR / "corpus_final_v3.jsonl"

CONF_THRESHOLD = 0.80
CONF_THRESHOLD_TEMPORAL = 0.75

_SYSTEM = """\
You are a biomedical literature expert classifying scientific contradictions.
Both claims come from the SAME abstract. Assign the MOST SPECIFIC type.

TYPES (apply in order 1→5, stop at first match):
1. DIRECT: Same gene/protein/phenomenon, same biological context, OPPOSITE direction
2. MAGNITUDE: Same direction, same context, INCOMPATIBLE effect sizes
3. METHODOLOGICAL: Same question, same context, DIFFERENT methods yield opposite results
4. TEMPORAL: Same context, results differ specifically due to TIMEPOINT
5. CONTEXTUAL [LAST RESORT]: Results differ SOLELY due to different biological contexts

Set is_genuine_contradiction=true for types 1-4, false for type 5.

IMPORTANT: Only classify as genuine (1-4) if claims clearly assert incompatible findings.
Limitation statements, truncated claims, or uncertainty phrases are NOT genuine contradictions.
"""

_USER = """\
Claim A (from same abstract as Claim B):
{claim_a}

Claim B:
{claim_b}

Type hint: This pair was extracted as a potential {type_hint} contradiction.
Classify using types 1→5 in order (stop at first match).

Output ONLY a JSON object (no markdown, no extra text). Use these exact string values:
- "direct" for type 1
- "magnitude" for type 2
- "methodological" for type 3
- "temporal" for type 4
- "contextual" for type 5

{{"contradiction_type": "direct or magnitude or methodological or temporal or contextual", "confidence": 0.95, "is_genuine_contradiction": true, "rationale": "2-3 sentences"}}"""

VALID_TYPES = {"direct", "magnitude", "methodological", "temporal", "contextual"}


def _parse_response(text: str) -> dict | None:
    """Parse JSON from Gemini plain text response. Handles markdown fences."""
    # Strip markdown fences if present
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ```
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```\s*$', '', text, flags=re.MULTILINE)
    text = text.strip()

    # Try direct parse
    try:
        data = json.loads(text)
        ct = data.get("contradiction_type", "")
        if ct not in VALID_TYPES:
            return None
        return {
            "contradiction_type": ct,
            "confidence": float(data.get("confidence", 0.0)),
            "is_genuine_contradiction": bool(data.get("is_genuine_contradiction", False)),
            "rationale": str(data.get("rationale", "")),
            "_partial_parse": False,
            "_classifier": "gemini_plain",
        }
    except (json.JSONDecodeError, ValueError, KeyError):
        pass

    # Regex fallback for truncated/partial JSON
    ct_m = re.search(r'"contradiction_type"\s*:\s*"(\w+)"', text)
    conf_m = re.search(r'"confidence"\s*:\s*([\d.]+)', text)
    genuine_m = re.search(r'"is_genuine_contradiction"\s*:\s*(true|false)', text)
    rationale_m = re.search(r'"rationale"\s*:\s*"([^"]{5,})"', text)

    if ct_m and conf_m and genuine_m:
        ct = ct_m.group(1)
        if ct not in VALID_TYPES:
            return None
        return {
            "contradiction_type": ct,
            "confidence": float(conf_m.group(1)),
            "is_genuine_contradiction": genuine_m.group(1) == "true",
            "rationale": rationale_m.group(1) if rationale_m else "[truncated]",
            "_partial_parse": True,
            "_classifier": "gemini_plain",
        }
    return None


async def _classify_one(client: httpx.AsyncClient, pair: dict) -> dict | None:
    """Classify one pair. Returns label dict or None on failure."""
    claim_a = pair.get("claim_a", {}).get("text", "")[:350]
    claim_b = pair.get("claim_b", {}).get("text", "")[:350]
    type_hint = pair.get("intended_type", "unknown")

    if not claim_a or not claim_b:
        log.warning("Empty claims for %s", pair.get("pair_id", "?"))
        return None

    payload = {
        "contents": [{"role": "user", "parts": [{"text": _USER.format(
            claim_a=claim_a,
            claim_b=claim_b,
            type_hint=type_hint,
        )}]}],
        "systemInstruction": {"parts": [{"text": _SYSTEM}]},
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 1024,  # Plain JSON ~200 tokens; no thinking needed
            "thinkingConfig": {"thinkingBudget": 0},  # Disable thinking to prevent token truncation
        },
    }

    try:
        resp = await client.post(API_URL, json=payload, timeout=45.0)
        resp.raise_for_status()
        data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            log.warning("No candidates for %s: %s", pair.get("pair_id"), data.get("promptFeedback", ""))
            return None

        cand = candidates[0]
        finish_reason = cand.get("finishReason", "")
        content = cand.get("content", {})
        parts = content.get("parts", [])

        if not parts:
            log.warning("No parts for %s (finishReason=%s)", pair.get("pair_id"), finish_reason)
            return None

        text = parts[0].get("text", "")
        if not text:
            return None

        result = _parse_response(text)
        if result:
            if finish_reason == "MAX_TOKENS":
                result["_partial_parse"] = True
            return result

        log.warning("Unparseable for %s: %r", pair.get("pair_id", "?"), text[:120])
        return None

    except Exception as e:
        log.warning("Failed %s: %s", pair.get("pair_id", "?"), e)
        return None


async def _classify_with_sem(client, pair, sem):
    async with sem:
        return await _classify_one(client, pair)


async def process_type(ctype: str, sem: asyncio.Semaphore) -> None:
    """Process None pairs for one contradiction type. Writes *_v5.jsonl."""
    v4_file = OUT_DIR / f"candidates_{ctype}_v4.jsonl"
    v5_file = OUT_DIR / f"candidates_{ctype}_v5.jsonl"

    if not v4_file.exists():
        log.warning("[%s] v4 file not found", ctype)
        return

    pairs = [json.loads(l) for l in open(v4_file) if l.strip()]
    failed = [p for p in pairs if not isinstance(p.get("label"), dict)]

    log.info("[%s] %d None pairs to classify (of %d total)", ctype, len(failed), len(pairs))

    if not failed:
        log.info("[%s] Nothing to classify — copying to v5", ctype)
        with open(v5_file, "w") as f:
            for p in pairs:
                f.write(json.dumps(p) + "\n")
        return

    results = {}
    async with httpx.AsyncClient(timeout=60) as client:
        tasks = [(p["pair_id"], asyncio.create_task(_classify_with_sem(client, p, sem))) for p in failed]

        ok = partial = 0
        for i, (pid, task) in enumerate(tasks):
            lbl = await task
            results[pid] = lbl
            if lbl:
                ok += 1
                if lbl.get("_partial_parse"):
                    partial += 1
            if (i + 1) % 5 == 0 or (i + 1) == len(failed):
                log.info("  [%s] %d/%d ok=%d (partial=%d)", ctype, i + 1, len(failed), ok, partial)
            await asyncio.sleep(MIN_SLEEP)

    log.info("[%s] Done: ok=%d partial=%d failed=%d", ctype, ok, partial, len(failed) - ok)

    # Merge
    merged = []
    updated = 0
    for p in pairs:
        pid = p["pair_id"]
        if pid in results and results[pid] is not None:
            p = dict(p)
            p["label"] = results[pid]
            updated += 1
        merged.append(p)

    with open(v5_file, "w") as f:
        for p in merged:
            f.write(json.dumps(p) + "\n")

    log.info("[%s] Saved %d entries (%d updated) → %s", ctype, len(merged), updated, v5_file.name)


def build_new_corpus_entries() -> list[dict]:
    """Collect newly classified genuine entries from v5 files (were None in v4)."""
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

        # IDs that were None in v4
        v4_none_ids = set()
        for l in open(v4_file):
            if not l.strip():
                continue
            p = json.loads(l)
            if not isinstance(p.get("label"), dict):
                v4_none_ids.add(p["pair_id"])

        for l in open(v5_file):
            if not l.strip():
                continue
            entry = json.loads(l)
            if entry["pair_id"] not in v4_none_ids:
                continue  # Already classified in v4 — already in corpus_v2

            lbl = entry.get("label")
            if not isinstance(lbl, dict):
                continue  # Still None

            # Quality filters
            conf = lbl.get("confidence", 0.0)
            ct = lbl.get("contradiction_type", "")
            threshold = CONF_THRESHOLD_TEMPORAL if ct == "temporal" else CONF_THRESHOLD
            if conf < threshold or conf > 1.0:
                continue
            if not lbl.get("is_genuine_contradiction", False):
                continue  # Only recover genuine non-contextual

            corpus_entry = {
                "id": entry["pair_id"],
                "source_pmid": entry.get("claim_a", {}).get("source_pmid", ""),
                "source_doi": entry.get("claim_a", {}).get("source_doi", ""),
                "paper_title": entry.get("claim_a", {}).get("paper_title", ""),
                "domain": entry.get("domain", ""),
                "extraction_pattern": str(entry.get("extraction_pattern", "")),
                "claim_a": entry.get("claim_a", {}).get("text", ""),
                "claim_b": entry.get("claim_b", {}).get("text", ""),
                "contradiction_type": ct,
                "is_genuine_contradiction": True,
                "confidence": conf,
                "rationale": lbl.get("rationale", ""),
                "intended_type": entry.get("intended_type", ""),
                "_partial_parse": lbl.get("_partial_parse", False),
                "_classifier": "gemini_plain",
            }

            if corpus_entry["id"] not in existing_ids:
                new_entries.append(corpus_entry)
                log.info("  NEW genuine: %s  type=%s  conf=%.2f", corpus_entry["id"], ct, conf)

    return new_entries


def write_corpus_v3(new_entries: list[dict]) -> None:
    """Merge new entries with corpus_final_v2 → write corpus_final_v3."""
    existing = [json.loads(l) for l in open(CORPUS_V2) if l.strip()] if CORPUS_V2.exists() else []
    combined = existing + new_entries

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
    print(f"Base (v2)    : {len(existing)} entries")
    print(f"New (Phase B): {len(new_entries)} entries")
    print(f"Total        : {len(combined)} entries")
    print(f"\nGenuine non-contextual: {sum(genuine.values())}")
    for ct in ["direct", "temporal", "magnitude", "methodological"]:
        print(f"  {ct:20s}: {genuine.get(ct, 0)}")
    print(f"Contextual   : {contextual}")
    print(f"\nOutput: {CORPUS_V3}")


async def main():
    if not API_KEY:
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY.")

    print("\n" + "=" * 60)
    print("PHASE B: Gemini plain-text classification of 68 None pairs")
    print("=" * 60)

    sem = asyncio.Semaphore(CONCURRENCY)
    for ctype in ["direct", "methodological", "temporal", "magnitude"]:
        await process_type(ctype, sem)

    print("\n=== Collecting new genuine entries ===")
    new_entries = build_new_corpus_entries()
    print(f"New genuine entries rescued: {len(new_entries)}")

    write_corpus_v3(new_entries)

    # Print v5 summary
    print("\n=== v5 summary per type ===")
    for ctype in ["direct", "methodological", "temporal", "magnitude"]:
        v5 = OUT_DIR / f"candidates_{ctype}_v5.jsonl"
        if not v5.exists():
            continue
        entries = [json.loads(l) for l in open(v5) if l.strip()]
        none_count = sum(1 for e in entries if not isinstance(e.get("label"), dict))
        genuine = sum(1 for e in entries
                      if isinstance(e.get("label"), dict)
                      and e["label"].get("is_genuine_contradiction")
                      and e["label"].get("contradiction_type") == ctype)
        print(f"  [{ctype:15s}] total={len(entries)} none_remaining={none_count} genuine_{ctype}={genuine}")


if __name__ == "__main__":
    asyncio.run(main())
