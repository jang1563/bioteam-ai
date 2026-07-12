#!/usr/bin/env python3
"""Re-adjudicate top-K soft-review rows and apply high-confidence label updates."""

from __future__ import annotations

import argparse
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
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

VALID_TYPES = {"direct", "contextual", "methodological", "temporal", "magnitude"}
GENUINE_TYPES = {"direct", "methodological", "temporal", "magnitude"}

SYSTEM_PROMPT = """\
You are adjudicating contradiction labels for biomedical claim pairs.

Pick one contradiction_type:
- direct
- contextual
- methodological
- temporal
- magnitude

Rules:
1) contextual => not a genuine contradiction.
2) direct => opposite direction under same context.
3) temporal => discrepancy explained by time/stage contrast.
4) magnitude => same direction but incompatible strength/significance.
5) methodological => discrepancy from method/assay/analysis differences.
6) If uncertain or non-contradictory, prefer contextual.

Return JSON only.
"""

USER_TEMPLATE = """\
Claim A: {claim_a}

Claim B: {claim_b}

Current label:
- contradiction_type: {old_type}
- is_genuine_contradiction: {old_genuine}

Output only JSON:
{{"contradiction_type":"direct|contextual|methodological|temporal|magnitude","is_genuine_contradiction":true,"confidence":0.90,"rationale":"1-2 sentences"}}
"""


def parse_args() -> argparse.Namespace:
    base = Path(__file__).resolve().parent / "output" / "v3"
    parser = argparse.ArgumentParser(description="Review top-K soft queue rows and apply updates.")
    parser.add_argument(
        "--queue-soft",
        type=Path,
        default=base / "qa_v12_gate_v2" / "corpus_curation_queue_soft.jsonl",
    )
    parser.add_argument(
        "--corpus-in",
        type=Path,
        default=base / "corpus_final_v14_gate_curated.jsonl",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Number of highest-priority soft rows to review.",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.90,
        help="Minimum confidence required to apply a label change.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=4.5,
        help="Seconds between Gemini requests.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=base / "qa_v12_gate_v2" / "soft_topk_review_checkpoint.jsonl",
    )
    parser.add_argument(
        "--decisions-out",
        type=Path,
        default=base / "qa_v12_gate_v2" / "soft_topk_review_decisions.jsonl",
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=base / "qa_v12_gate_v2" / "soft_topk_review_summary.json",
    )
    parser.add_argument(
        "--corpus-out",
        type=Path,
        default=base / "corpus_final_v15_soft20_reviewed.jsonl",
    )
    parser.add_argument(
        "--changes-out",
        type=Path,
        default=base / "corpus_final_v15_soft20_reviewed_changes.jsonl",
    )
    parser.add_argument("--reset", action="store_true")
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _parse_response(text: str) -> dict | None:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    try:
        data = json.loads(text)
    except Exception:
        return None

    ctype = str(data.get("contradiction_type", ""))
    if ctype not in VALID_TYPES:
        return None

    try:
        conf = float(data.get("confidence", 0.0))
    except Exception:
        return None

    pred_genuine = bool(data.get("is_genuine_contradiction", ctype in GENUINE_TYPES))
    if ctype == "contextual":
        pred_genuine = False
    else:
        pred_genuine = True

    return {
        "contradiction_type": ctype,
        "is_genuine_contradiction": pred_genuine,
        "confidence": conf,
        "rationale": str(data.get("rationale", "")),
    }


async def _review_one(client: httpx.AsyncClient, api_key: str, row: dict) -> dict | None:
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": USER_TEMPLATE.format(
                            claim_a=row.get("claim_a", "")[:380],
                            claim_b=row.get("claim_b", "")[:380],
                            old_type=row.get("contradiction_type", ""),
                            old_genuine=row.get("is_genuine_contradiction", False),
                        )
                    }
                ],
            }
        ],
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 512,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    try:
        resp = await client.post(url, json=payload, timeout=45.0)
        resp.raise_for_status()
        body = resp.json()
        candidates = body.get("candidates", [])
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return None
        return _parse_response(parts[0].get("text", ""))
    except Exception:
        return None


def _select_topk(queue_rows: list[dict], corpus_by_id: dict[str, dict], top_k: int) -> list[dict]:
    rows = sorted(queue_rows, key=lambda r: (-int(r.get("priority", 0)), r.get("id", "")))
    selected: list[dict] = []
    for q in rows:
        rid = q.get("id", "")
        corpus_row = corpus_by_id.get(rid)
        if not rid or not corpus_row:
            continue
        merged = dict(corpus_row)
        merged["_queue_priority"] = q.get("priority", 0)
        merged["_queue_primary_flag"] = q.get("primary_flag", "")
        merged["_queue_flags"] = q.get("flags", [])
        selected.append(merged)
        if len(selected) >= top_k:
            break
    return selected


async def _run_reviews(args: argparse.Namespace, targets: list[dict], api_key: str) -> list[dict]:
    done: dict[str, dict] = {}
    if args.checkpoint.exists():
        for line in args.checkpoint.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["id"]] = row

    remaining = [row for row in targets if row["id"] not in done]
    if not remaining:
        return [done[row["id"]] for row in targets if row["id"] in done]

    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with args.checkpoint.open("a", encoding="utf-8") as fp:
        async with httpx.AsyncClient(timeout=60.0) as client:
            for idx, row in enumerate(remaining, start=1):
                reviewed = await _review_one(client, api_key, row)
                out = dict(row)
                out["review"] = reviewed
                out["parse_failed"] = reviewed is None
                done[row["id"]] = out
                fp.write(json.dumps(out, ensure_ascii=False) + "\n")
                fp.flush()
                if idx % 5 == 0 or idx == len(remaining):
                    ok = sum(1 for r in done.values() if isinstance(r.get("review"), dict))
                    log.info("  %d/%d reviewed (ok=%d total=%d)", idx, len(remaining), ok, len(done))
                await asyncio.sleep(args.sleep)

    return [done[row["id"]] for row in targets if row["id"] in done]


def _apply_updates(args: argparse.Namespace, corpus_rows: list[dict], reviewed_rows: list[dict]) -> dict:
    by_id = {row["id"]: row for row in reviewed_rows}
    out_rows = []
    changes = []

    for row in corpus_rows:
        rid = row["id"]
        reviewed = by_id.get(rid)
        if not reviewed or not isinstance(reviewed.get("review"), dict):
            out_rows.append(row)
            continue

        pred = reviewed["review"]
        conf = float(pred.get("confidence", 0.0))
        if conf < args.min_confidence:
            out_rows.append(row)
            continue

        new_type = pred["contradiction_type"]
        new_genuine = bool(pred["is_genuine_contradiction"])
        old_type = row.get("contradiction_type")
        old_genuine = bool(row.get("is_genuine_contradiction", False))
        if new_type == old_type and new_genuine == old_genuine:
            out_rows.append(row)
            continue

        updated = dict(row)
        updated["contradiction_type"] = new_type
        updated["is_genuine_contradiction"] = new_genuine
        updated["confidence"] = conf
        if pred.get("rationale"):
            updated["rationale"] = pred["rationale"]
        out_rows.append(updated)

        changes.append(
            {
                "id": rid,
                "old_type": old_type,
                "old_is_genuine": old_genuine,
                "new_type": new_type,
                "new_is_genuine": new_genuine,
                "confidence": conf,
                "queue_priority": reviewed.get("_queue_priority", 0),
                "queue_primary_flag": reviewed.get("_queue_primary_flag", ""),
                "queue_flags": reviewed.get("_queue_flags", []),
                "reason": "soft_topk_recheck",
            }
        )

    args.corpus_out.parent.mkdir(parents=True, exist_ok=True)
    with args.corpus_out.open("w", encoding="utf-8") as fp:
        for row in out_rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    with args.changes_out.open("w", encoding="utf-8") as fp:
        for row in changes:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {
        "output_rows": len(out_rows),
        "changed_rows": len(changes),
        "changed_to_contextual": sum(1 for c in changes if c["new_type"] == "contextual"),
        "changed_to_direct": sum(1 for c in changes if c["new_type"] == "direct"),
        "changed_to_temporal": sum(1 for c in changes if c["new_type"] == "temporal"),
        "changed_to_magnitude": sum(1 for c in changes if c["new_type"] == "magnitude"),
        "changed_to_methodological": sum(1 for c in changes if c["new_type"] == "methodological"),
    }


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY.")
    if args.reset and args.checkpoint.exists():
        args.checkpoint.unlink()

    corpus_rows = _load_jsonl(args.corpus_in)
    corpus_by_id = {row["id"]: row for row in corpus_rows}
    queue_rows = _load_jsonl(args.queue_soft)
    targets = _select_topk(queue_rows, corpus_by_id, args.top_k)
    reviewed_rows = asyncio.run(_run_reviews(args, targets, api_key))

    args.decisions_out.parent.mkdir(parents=True, exist_ok=True)
    with args.decisions_out.open("w", encoding="utf-8") as fp:
        for row in reviewed_rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    apply_summary = _apply_updates(args, corpus_rows, reviewed_rows)
    parse_failed = sum(1 for row in reviewed_rows if row.get("parse_failed"))
    parsed = len(reviewed_rows) - parse_failed
    confidence_bins = Counter()
    for row in reviewed_rows:
        review = row.get("review")
        if not isinstance(review, dict):
            continue
        c = float(review.get("confidence", 0.0))
        if c >= 0.95:
            confidence_bins[">=0.95"] += 1
        elif c >= 0.90:
            confidence_bins["0.90-0.94"] += 1
        elif c >= 0.80:
            confidence_bins["0.80-0.89"] += 1
        else:
            confidence_bins["<0.80"] += 1

    summary = {
        "queue_soft": str(args.queue_soft),
        "corpus_in": str(args.corpus_in),
        "corpus_out": str(args.corpus_out),
        "top_k": args.top_k,
        "target_ids": [row["id"] for row in targets],
        "reviewed_rows": len(reviewed_rows),
        "parsed_rows": parsed,
        "parse_failed_rows": parse_failed,
        "min_confidence_to_apply": args.min_confidence,
        "confidence_bins": dict(confidence_bins),
        "apply_summary": apply_summary,
        "changes_out": str(args.changes_out),
        "decisions_out": str(args.decisions_out),
    }
    args.summary_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("Soft queue top-K review complete")
    print(f"  reviewed={len(reviewed_rows)} parsed={parsed} parse_failed={parse_failed}")
    print(f"  changed_rows={apply_summary['changed_rows']} corpus_out={args.corpus_out}")
    print(f"  summary={args.summary_out}")


if __name__ == "__main__":
    main()
