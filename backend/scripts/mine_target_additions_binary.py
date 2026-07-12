#!/usr/bin/env python3
"""Mine extra temporal/magnitude additions from non-corpus candidates with binary checks."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from collections import Counter
from pathlib import Path

import httpx

try:
    from scripts.corpus_quality_utils import LEGACY_EXCLUDED_IDS, pair_quality_issues
except ImportError:  # pragma: no cover - direct script execution path
    from corpus_quality_utils import LEGACY_EXCLUDED_IDS, pair_quality_issues

SYSTEM_BY_TARGET = {
    "temporal": """\
You are judging whether a claim pair is a genuine TEMPORAL contradiction.

TEMPORAL contradiction criteria:
- same biological phenomenon/context
- discrepancy specifically due to timepoint/stage/phase (early vs late, acute vs chronic, baseline vs follow-up)
- both claims can be incompatible in timing profile, not merely different populations

If not temporal contradiction, return contextual.
Return JSON only.
""",
    "magnitude": """\
You are judging whether a claim pair is a genuine MAGNITUDE contradiction.

MAGNITUDE contradiction criteria:
- same direction/context generally
- discrepancy in effect strength, size, or significance consistency (strong vs weak, significant vs non-significant, high vs low estimate)
- not opposite directional effect

If not magnitude contradiction, return contextual.
Return JSON only.
""",
}

USER_BY_TARGET = {
    "temporal": """\
Claim A: {claim_a}

Claim B: {claim_b}

Output ONLY JSON:
{{"is_target":true,"target_type":"temporal","confidence":0.90,"rationale":"1-2 sentences"}}
If not target, set is_target=false and target_type="contextual".
""",
    "magnitude": """\
Claim A: {claim_a}

Claim B: {claim_b}

Output ONLY JSON:
{{"is_target":true,"target_type":"magnitude","confidence":0.90,"rationale":"1-2 sentences"}}
If not target, set is_target=false and target_type="contextual".
""",
}


def parse_args() -> argparse.Namespace:
    base = Path(__file__).resolve().parent / "output" / "v3"
    parser = argparse.ArgumentParser(description="Mine additional target-type entries.")
    parser.add_argument("--candidates-dir", type=Path, default=base)
    parser.add_argument("--corpus-in", type=Path, default=base / "corpus_final_v10_plus17.jsonl")
    parser.add_argument("--checkpoint", type=Path, default=base / "qa_v7" / "binary_target_checkpoint.jsonl")
    parser.add_argument("--decisions-out", type=Path, default=base / "qa_v7" / "binary_target_decisions.jsonl")
    parser.add_argument("--selected-out", type=Path, default=base / "qa_v7" / "binary_target_selected.jsonl")
    parser.add_argument("--summary-out", type=Path, default=base / "qa_v7" / "binary_target_summary.json")
    parser.add_argument("--corpus-out", type=Path, default=base / "corpus_final_v11_plus17.jsonl")
    parser.add_argument("--corpus-changes-out", type=Path, default=base / "corpus_final_v11_plus17_changes.jsonl")
    parser.add_argument("--needed-additions", type=int, default=12, help="Additional rows needed beyond current corpus.")
    parser.add_argument("--min-confidence", type=float, default=0.85)
    parser.add_argument("--sleep", type=float, default=4.5)
    parser.add_argument("--reset", action="store_true")
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _quality_issues(pair_id: str, claim_a: str, claim_b: str) -> list[str]:
    issues = pair_quality_issues(claim_a, claim_b)
    if pair_id in LEGACY_EXCLUDED_IDS:
        issues.append("legacy_excluded_id")
    return sorted(set(issues))


def _collect_candidates(args: argparse.Namespace, target: str) -> list[dict]:
    corpus_ids = {row["id"] for row in _load_jsonl(args.corpus_in)}
    rows = []
    skipped_quality = 0
    for path in sorted(args.candidates_dir.glob("candidates_*_v5.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            label = item.get("label")
            if not isinstance(label, dict):
                continue
            pid = item.get("pair_id")
            if not pid or pid in corpus_ids:
                continue
            intended = item.get("intended_type", "")
            if intended != target:
                continue
            conf = float(label.get("confidence", 0.0))
            if conf > 1.0:
                continue
            claim_a = str(item.get("claim_a", {}).get("text", ""))
            claim_b = str(item.get("claim_b", {}).get("text", ""))
            if _quality_issues(pid, claim_a, claim_b):
                skipped_quality += 1
                continue
            rows.append(
                {
                    "id": pid,
                    "target": target,
                    "source_file": path.name,
                    "domain": item.get("domain", ""),
                    "query_source": item.get("query_source", ""),
                    "intended_type": intended,
                    "pred_type": label.get("contradiction_type"),
                    "pred_confidence": conf,
                    "pred_genuine": bool(label.get("is_genuine_contradiction", False)),
                    "claim_a": claim_a,
                    "claim_b": claim_b,
                    "claim_a_meta": item.get("claim_a", {}),
                    "claim_b_meta": item.get("claim_b", {}),
                }
            )
    # prioritize contextual or uncertain predictions first
    rows.sort(
        key=lambda x: (
            0 if x["pred_type"] == "contextual" else 1,
            -x["pred_confidence"],
            x["id"],
        )
    )
    print(f"[{target}] candidates={len(rows)} skipped_quality={skipped_quality}")
    return rows


def _parse_binary_response(text: str, target: str) -> dict | None:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    try:
        data = json.loads(text)
        is_target = bool(data.get("is_target", False))
        t = str(data.get("target_type", ""))
        conf = float(data.get("confidence", 0.0))
        rationale = str(data.get("rationale", ""))
        if is_target and t != target:
            return None
        if (not is_target) and t not in {"contextual", target}:
            return None
        return {
            "is_target": is_target,
            "target_type": target if is_target else "contextual",
            "confidence": conf,
            "rationale": rationale,
        }
    except Exception:
        return None


async def _check_one(client: httpx.AsyncClient, api_key: str, row: dict) -> dict | None:
    target = row["target"]
    payload = {
        "contents": [{"role": "user", "parts": [{"text": USER_BY_TARGET[target].format(
            claim_a=row["claim_a"][:400],
            claim_b=row["claim_b"][:400],
        )}]}],
        "systemInstruction": {"parts": [{"text": SYSTEM_BY_TARGET[target]}]},
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 512, "thinkingConfig": {"thinkingBudget": 0}},
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
        return _parse_binary_response(parts[0].get("text", ""), target)
    except Exception:
        return None


async def _run_checks(args: argparse.Namespace, rows: list[dict], api_key: str) -> list[dict]:
    done: dict[str, dict] = {}
    if args.checkpoint.exists():
        for line in args.checkpoint.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[f"{row['target']}::{row['id']}"] = row

    remaining = [row for row in rows if f"{row['target']}::{row['id']}" not in done]
    if not remaining:
        return list(done.values())

    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with args.checkpoint.open("a", encoding="utf-8") as fp:
        async with httpx.AsyncClient(timeout=60.0) as client:
            for idx, row in enumerate(remaining, start=1):
                out = await _check_one(client, api_key, row)
                merged = dict(row)
                merged["binary_check"] = out
                merged["parse_failed"] = out is None
                done[f"{row['target']}::{row['id']}"] = merged
                fp.write(json.dumps(merged, ensure_ascii=False) + "\n")
                fp.flush()
                if idx % 10 == 0 or idx == len(remaining):
                    ok = sum(1 for x in done.values() if isinstance(x.get("binary_check"), dict))
                    print(f"  {idx}/{len(remaining)} checked (ok={ok}, total={len(done)})")
                await asyncio.sleep(args.sleep)
    return list(done.values())


def _to_corpus(row: dict) -> dict:
    check = row["binary_check"]
    target = row["target"]
    return {
        "id": row["id"],
        "source_pmid": row.get("claim_a_meta", {}).get("source_pmid", ""),
        "source_doi": row.get("claim_a_meta", {}).get("source_doi", ""),
        "paper_title": row.get("claim_a_meta", {}).get("paper_title", ""),
        "domain": row.get("domain", ""),
        "extraction_pattern": "",
        "claim_a": row.get("claim_a", ""),
        "claim_b": row.get("claim_b", ""),
        "contradiction_type": target,
        "is_genuine_contradiction": True,
        "confidence": float(check["confidence"]),
        "rationale": check.get("rationale", ""),
        "intended_type": row.get("intended_type", ""),
        "_partial_parse": False,
    }


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY.")
    if args.reset and args.checkpoint.exists():
        args.checkpoint.unlink()

    corpus_rows = _load_jsonl(args.corpus_in)
    rows = _collect_candidates(args, "temporal") + _collect_candidates(args, "magnitude")
    results = asyncio.run(_run_checks(args, rows, api_key))

    args.decisions_out.parent.mkdir(parents=True, exist_ok=True)
    with args.decisions_out.open("w", encoding="utf-8") as fp:
        for row in results:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    accepted = [
        row
        for row in results
        if isinstance(row.get("binary_check"), dict)
        and row["binary_check"]["is_target"] is True
        and float(row["binary_check"]["confidence"]) >= args.min_confidence
    ]
    accepted.sort(
        key=lambda x: (
            0 if x["target"] == "magnitude" else 1,
            -float(x["binary_check"]["confidence"]),
            x["id"],
        )
    )

    existing_ids = {row["id"] for row in corpus_rows}
    selected = []
    for row in accepted:
        if row["id"] in existing_ids:
            continue
        selected.append(row)
        if len(selected) >= args.needed_additions:
            break

    with args.selected_out.open("w", encoding="utf-8") as fp:
        for row in selected:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    additions = [_to_corpus(row) for row in selected]
    merged = corpus_rows + additions
    with args.corpus_out.open("w", encoding="utf-8") as fp:
        for row in merged:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
    with args.corpus_changes_out.open("w", encoding="utf-8") as fp:
        for row in additions:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "corpus_in": str(args.corpus_in),
        "corpus_out": str(args.corpus_out),
        "candidate_pool": len(rows),
        "processed": len(results),
        "accepted_total": len(accepted),
        "selected_additions": len(selected),
        "needed_additions": args.needed_additions,
        "min_confidence": args.min_confidence,
        "added_by_type": dict(Counter(row["target"] for row in selected)),
        "selected_ids": [row["id"] for row in selected],
    }
    args.summary_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("Binary target mining complete")
    print(f"  candidate_pool={len(rows)} processed={len(results)}")
    print(f"  accepted={len(accepted)} selected_additions={len(selected)}")
    print(f"  summary={args.summary_out}")


if __name__ == "__main__":
    main()
