#!/usr/bin/env python3
"""Recheck likely magnitude candidates with a focused direct-vs-magnitude prompt.

Input queue comes from `build_magnitude_expansion_queue.py`.
This script:
1) Filters queue to intended magnitude + predicted genuine + non-magnitude type
2) Runs Gemini re-adjudication (direct vs magnitude only)
3) Optionally applies relabels to corpus and writes v7 candidate corpus
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from pathlib import Path

import httpx

SYSTEM_PROMPT = """\
You are adjudicating contradiction subtype for biomedical claims.
Choose ONLY one:
- direct: opposite direction/effect under same context
- magnitude: same direction/context but incompatible effect size, strength, or significance consistency
- contextual: apparent difference explained by different context or non-contradictory uncertainty framing

Important:
- Statements like "association exists" vs "effect is weak/modest/inconsistent/not significant" are often MAGNITUDE.
- Use DIRECT only when direction itself is opposite (increase vs decrease, promotes vs inhibits, present vs absent).
- If claims are not genuinely incompatible, choose CONTEXTUAL.
Return JSON only.
"""

USER_TEMPLATE = """\
Claim A: {claim_a}

Claim B: {claim_b}

Output ONLY:
{{"recheck_type":"direct|magnitude|contextual","confidence":0.90,"is_genuine_contradiction":true,"rationale":"1-2 sentences"}}
"""


def parse_args() -> argparse.Namespace:
    base = Path(__file__).resolve().parent / "output" / "v3"
    parser = argparse.ArgumentParser(description="Recheck magnitude relabel candidates.")
    parser.add_argument(
        "--queue",
        type=Path,
        default=base / "qa_v6" / "magnitude_expansion_queue.jsonl",
        help="Input magnitude expansion queue JSONL.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=base / "qa_v6" / "magnitude_recheck_checkpoint.jsonl",
        help="Recheck checkpoint JSONL.",
    )
    parser.add_argument(
        "--decisions-out",
        type=Path,
        default=base / "qa_v6" / "magnitude_recheck_decisions.jsonl",
        help="Decision output JSONL.",
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=base / "qa_v6" / "magnitude_recheck_summary.json",
        help="Summary JSON output.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="Max candidates to process in this run.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=4.5,
        help="Seconds between requests.",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.85,
        help="Minimum recheck confidence to accept relabel.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset checkpoint before run.",
    )
    parser.add_argument(
        "--include-contextual",
        action="store_true",
        help="Also include intended-magnitude rows currently predicted as contextual.",
    )
    parser.add_argument(
        "--any-intended",
        action="store_true",
        help="Do not restrict to intended_type=magnitude.",
    )
    parser.add_argument(
        "--apply-to-corpus",
        action="store_true",
        help="Apply accepted magnitude relabels to corpus.",
    )
    parser.add_argument(
        "--corpus-in",
        type=Path,
        default=base / "corpus_final_v6_curated.jsonl",
        help="Corpus input when --apply-to-corpus is used.",
    )
    parser.add_argument(
        "--corpus-out",
        type=Path,
        default=base / "corpus_final_v7_magnitude_relabel.jsonl",
        help="Corpus output when --apply-to-corpus is used.",
    )
    parser.add_argument(
        "--corpus-changes-out",
        type=Path,
        default=base / "corpus_final_v7_magnitude_relabel_changes.jsonl",
        help="Change log when --apply-to-corpus is used.",
    )
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
        t = str(data.get("recheck_type", ""))
        if t not in {"direct", "magnitude", "contextual"}:
            return None
        return {
            "recheck_type": t,
            "confidence": float(data.get("confidence", 0.0)),
            "is_genuine_contradiction": bool(data.get("is_genuine_contradiction", t != "contextual")),
            "rationale": str(data.get("rationale", "")),
        }
    except Exception:
        return None


async def _recheck_one(client: httpx.AsyncClient, api_key: str, row: dict) -> dict | None:
    payload = {
        "contents": [{"role": "user", "parts": [{"text": USER_TEMPLATE.format(
            claim_a=row.get("claim_a", "")[:380],
            claim_b=row.get("claim_b", "")[:380],
        )}]}],
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


async def run_recheck(args: argparse.Namespace, candidates: list[dict], api_key: str) -> list[dict]:
    done: dict[str, dict] = {}
    if args.checkpoint.exists():
        for line in args.checkpoint.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            done[row["id"]] = row

    remaining = [row for row in candidates if row["id"] not in done][: args.limit]
    if not remaining:
        return list(done.values())

    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with args.checkpoint.open("a", encoding="utf-8") as fp:
        async with httpx.AsyncClient(timeout=60.0) as client:
            for idx, row in enumerate(remaining, start=1):
                out = await _recheck_one(client, api_key, row)
                merged = dict(row)
                merged["recheck"] = out
                merged["parse_failed"] = out is None
                done[row["id"]] = merged
                fp.write(json.dumps(merged, ensure_ascii=False) + "\n")
                fp.flush()
                if idx % 10 == 0 or idx == len(remaining):
                    ok = sum(1 for r in done.values() if isinstance(r.get("recheck"), dict))
                    print(f"  {idx}/{len(remaining)} rechecked (ok={ok}, total={len(done)})")
                await asyncio.sleep(args.sleep)
    return list(done.values())


def apply_relabels(args: argparse.Namespace, accepted: dict[str, dict]) -> dict:
    corpus = _load_jsonl(args.corpus_in)
    out = []
    changes = []
    for row in corpus:
        rid = row["id"]
        if rid in accepted:
            old_type = row.get("contradiction_type")
            if old_type != "magnitude":
                new_row = dict(row)
                new_row["contradiction_type"] = "magnitude"
                new_row["is_genuine_contradiction"] = True
                out.append(new_row)
                changes.append(
                    {
                        "id": rid,
                        "old_type": old_type,
                        "old_is_genuine": row.get("is_genuine_contradiction"),
                        "new_type": "magnitude",
                        "new_is_genuine": True,
                        "reason": "magnitude_recheck",
                        "confidence": accepted[rid]["recheck"]["confidence"],
                    }
                )
                continue
        out.append(row)

    args.corpus_out.parent.mkdir(parents=True, exist_ok=True)
    with args.corpus_out.open("w", encoding="utf-8") as fp:
        for row in out:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
    with args.corpus_changes_out.open("w", encoding="utf-8") as fp:
        for row in changes:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {
        "corpus_in": str(args.corpus_in),
        "corpus_out": str(args.corpus_out),
        "changed_rows": len(changes),
    }


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY.")

    if args.reset and args.checkpoint.exists():
        args.checkpoint.unlink()

    queue = _load_jsonl(args.queue)
    allowed_pred_types = {"direct", "methodological", "temporal"}
    if args.include_contextual:
        allowed_pred_types.add("contextual")

    candidates = []
    for row in queue:
        if (not args.any_intended) and row.get("intended_type") != "magnitude":
            continue
        if row.get("pred_type") not in allowed_pred_types:
            continue
        if row.get("pred_type") == "contextual":
            # contextual rows were previously non-genuine; include only when explicitly requested
            if not args.include_contextual:
                continue
        else:
            if row.get("pred_genuine") is not True:
                continue
        candidates.append(row)
    candidates.sort(key=lambda x: (-x.get("priority_score", 0), x["id"]))

    results = asyncio.run(run_recheck(args, candidates, api_key))
    with args.decisions_out.open("w", encoding="utf-8") as fp:
        for row in results:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    accepted = {
        row["id"]: row
        for row in results
        if isinstance(row.get("recheck"), dict)
        and row["recheck"]["recheck_type"] == "magnitude"
        and row["recheck"]["is_genuine_contradiction"] is True
        and float(row["recheck"]["confidence"]) >= args.min_confidence
    }

    apply_summary = None
    if args.apply_to_corpus:
        apply_summary = apply_relabels(args, accepted)

    summary = {
        "queue": str(args.queue),
        "candidate_count": len(candidates),
        "processed_count": len(results),
        "accepted_relabels": len(accepted),
        "min_confidence": args.min_confidence,
        "accepted_ids": sorted(accepted.keys()),
        "apply_summary": apply_summary,
    }
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("Magnitude recheck complete")
    print(f"  candidates={len(candidates)} processed={len(results)} accepted={len(accepted)}")
    if apply_summary:
        print(f"  corpus_changed={apply_summary['changed_rows']}")
    print(f"  summary={args.summary_out}")


if __name__ == "__main__":
    main()
