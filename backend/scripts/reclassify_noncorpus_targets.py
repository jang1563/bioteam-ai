#!/usr/bin/env python3
"""Reclassify non-corpus candidates to mine temporal/magnitude additions."""

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

VALID_TYPES = {"direct", "contextual", "methodological", "temporal", "magnitude"}
TARGET_TYPES = {"temporal", "magnitude"}
TEMPORAL_CUES = re.compile(
    r"\b(early|late|acute|chronic|baseline|follow-?up|stage|phase|short-?term|long-?term|initial|prolonged|during|after)\b",
    flags=re.IGNORECASE,
)
MAGNITUDE_CUES = re.compile(
    r"\b(effect size|significant|non-?significant|odds ratio|hazard ratio|relative risk|heterogeneity|inconsistent|discrepancy|fold|small|modest|weak|strong|%|p\s*[<=>])\b",
    flags=re.IGNORECASE,
)

SYSTEM_PROMPT = """\
You are adjudicating contradiction type for biomedical claim pairs.

Prioritize detecting these hard types correctly:
- temporal: same phenomenon/context, discrepancy explained by timing/stage differences
- magnitude: same direction/context, discrepancy is effect strength/significance size

Use full taxonomy:
direct / contextual / methodological / temporal / magnitude

Rules:
1) Do NOT default to contextual if claims are genuinely incompatible.
2) For temporal, require explicit timing/stage signal.
3) For magnitude, direction can be compatible while strength/significance differs.
4) If truly not contradictory, use contextual and set is_genuine_contradiction=false.

Output JSON only.
"""

USER_TEMPLATE = """\
Claim A: {claim_a}

Claim B: {claim_b}

Output ONLY JSON:
{{"recheck_type":"direct|contextual|methodological|temporal|magnitude","confidence":0.90,"is_genuine_contradiction":true,"rationale":"1-2 sentences"}}
"""


def parse_args() -> argparse.Namespace:
    base = Path(__file__).resolve().parent / "output" / "v3"
    parser = argparse.ArgumentParser(description="Reclassify non-corpus candidates for target types.")
    parser.add_argument("--candidates-dir", type=Path, default=base)
    parser.add_argument("--corpus-in", type=Path, default=base / "corpus_final_v7_magnitude_relabel.jsonl")
    parser.add_argument("--checkpoint", type=Path, default=base / "qa_v7" / "noncorpus_recheck_checkpoint.jsonl")
    parser.add_argument("--decisions-out", type=Path, default=base / "qa_v7" / "noncorpus_recheck_decisions.jsonl")
    parser.add_argument("--selected-out", type=Path, default=base / "qa_v7" / "noncorpus_selected_additions.jsonl")
    parser.add_argument("--summary-out", type=Path, default=base / "qa_v7" / "noncorpus_recheck_summary.json")
    parser.add_argument("--corpus-out", type=Path, default=base / "corpus_final_v10_plus17.jsonl")
    parser.add_argument("--corpus-changes-out", type=Path, default=base / "corpus_final_v10_plus17_changes.jsonl")
    parser.add_argument("--target-additions", type=int, default=17)
    parser.add_argument("--min-confidence", type=float, default=0.85)
    parser.add_argument("--sleep", type=float, default=4.5)
    parser.add_argument("--limit", type=int, default=120)
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
        t = str(data.get("recheck_type", ""))
        if t not in VALID_TYPES:
            return None
        return {
            "recheck_type": t,
            "confidence": float(data.get("confidence", 0.0)),
            "is_genuine_contradiction": bool(data.get("is_genuine_contradiction", t != "contextual")),
            "rationale": str(data.get("rationale", "")),
        }
    except Exception:
        return None


def _quality_issues(pair_id: str, claim_a: str, claim_b: str) -> list[str]:
    issues = pair_quality_issues(claim_a, claim_b)
    if pair_id in LEGACY_EXCLUDED_IDS:
        issues.append("legacy_excluded_id")
    return sorted(set(issues))


def _score_candidate(row: dict) -> int:
    score = 0
    intended = str(row.get("intended_type", ""))
    pred_type = str(row.get("pred_type", ""))
    conf = float(row.get("pred_confidence", 0.0))
    text = f"{row.get('claim_a','')} {row.get('claim_b','')}"
    if intended in TARGET_TYPES:
        score += 40
    if pred_type == "contextual":
        score += 20
    if conf >= 0.9:
        score += 8
    elif conf >= 0.8:
        score += 5
    if TEMPORAL_CUES.search(text):
        score += 12
    if MAGNITUDE_CUES.search(text):
        score += 12
    return score


def _collect_candidates(args: argparse.Namespace) -> list[dict]:
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
            claim_a = str(item.get("claim_a", {}).get("text", ""))
            claim_b = str(item.get("claim_b", {}).get("text", ""))
            if _quality_issues(pid, claim_a, claim_b):
                skipped_quality += 1
                continue
            conf = float(label.get("confidence", 0.0))
            if conf < 0.8 or conf > 1.0:
                continue
            row = {
                "id": pid,
                "source_file": path.name,
                "domain": item.get("domain", ""),
                "query_source": item.get("query_source", ""),
                "intended_type": item.get("intended_type", ""),
                "pred_type": label.get("contradiction_type"),
                "pred_confidence": conf,
                "pred_genuine": bool(label.get("is_genuine_contradiction", False)),
                "claim_a": claim_a,
                "claim_b": claim_b,
                "claim_a_meta": item.get("claim_a", {}),
                "claim_b_meta": item.get("claim_b", {}),
            }
            row["priority_score"] = _score_candidate(row)
            rows.append(row)
    rows.sort(key=lambda x: (-x["priority_score"], x["id"]))
    print(f"Collected candidates: {len(rows)} (skipped_quality={skipped_quality})")
    return rows


async def _recheck_one(client: httpx.AsyncClient, api_key: str, row: dict) -> dict | None:
    payload = {
        "contents": [{"role": "user", "parts": [{"text": USER_TEMPLATE.format(
            claim_a=row["claim_a"][:400],
            claim_b=row["claim_b"][:400],
        )}]}],
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
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
        return _parse_response(parts[0].get("text", ""))
    except Exception:
        return None


async def _run_recheck(args: argparse.Namespace, candidates: list[dict], api_key: str) -> list[dict]:
    done: dict[str, dict] = {}
    if args.checkpoint.exists():
        for line in args.checkpoint.read_text(encoding="utf-8").splitlines():
            if line.strip():
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


def _select_additions(args: argparse.Namespace, results: list[dict], corpus_rows: list[dict]) -> list[dict]:
    accepted = [
        row
        for row in results
        if isinstance(row.get("recheck"), dict)
        and row["recheck"]["recheck_type"] in TARGET_TYPES
        and row["recheck"]["is_genuine_contradiction"] is True
        and float(row["recheck"]["confidence"]) >= args.min_confidence
    ]
    accepted.sort(
        key=lambda x: (
            -float(x["recheck"]["confidence"]),
            0 if x["recheck"]["recheck_type"] == "magnitude" else 1,
            -x.get("priority_score", 0),
            x["id"],
        )
    )

    # Prioritize filling current gaps to 30 for magnitude and temporal.
    genuine_counts = Counter(
        row["contradiction_type"] for row in corpus_rows if row.get("is_genuine_contradiction")
    )
    mag_gap = max(0, 30 - genuine_counts.get("magnitude", 0))
    tem_gap = max(0, 30 - genuine_counts.get("temporal", 0))

    selected: list[dict] = []
    used = set()
    for t, gap in (("magnitude", mag_gap), ("temporal", tem_gap)):
        if gap <= 0:
            continue
        bucket = [row for row in accepted if row["recheck"]["recheck_type"] == t]
        for row in bucket:
            if row["id"] in used:
                continue
            selected.append(row)
            used.add(row["id"])
            if sum(1 for x in selected if x["recheck"]["recheck_type"] == t) >= gap:
                break

    # Fill remaining slots with best accepted regardless of target type balance.
    for row in accepted:
        if row["id"] in used:
            continue
        selected.append(row)
        used.add(row["id"])
        if len(selected) >= args.target_additions:
            break

    return selected[: args.target_additions]


def _to_corpus_row(row: dict) -> dict:
    recheck = row["recheck"]
    return {
        "id": row["id"],
        "source_pmid": row.get("claim_a_meta", {}).get("source_pmid", ""),
        "source_doi": row.get("claim_a_meta", {}).get("source_doi", ""),
        "paper_title": row.get("claim_a_meta", {}).get("paper_title", ""),
        "domain": row.get("domain", ""),
        "extraction_pattern": "",
        "claim_a": row.get("claim_a", ""),
        "claim_b": row.get("claim_b", ""),
        "contradiction_type": recheck["recheck_type"],
        "is_genuine_contradiction": True,
        "confidence": float(recheck["confidence"]),
        "rationale": recheck.get("rationale", ""),
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
    candidates = _collect_candidates(args)
    results = asyncio.run(_run_recheck(args, candidates, api_key))

    args.decisions_out.parent.mkdir(parents=True, exist_ok=True)
    with args.decisions_out.open("w", encoding="utf-8") as fp:
        for row in results:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    selected = _select_additions(args, results, corpus_rows)
    with args.selected_out.open("w", encoding="utf-8") as fp:
        for row in selected:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Merge corpus + selected additions
    existing_ids = {row["id"] for row in corpus_rows}
    additions = [_to_corpus_row(row) for row in selected if row["id"] not in existing_ids]
    merged = corpus_rows + additions
    with args.corpus_out.open("w", encoding="utf-8") as fp:
        for row in merged:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
    with args.corpus_changes_out.open("w", encoding="utf-8") as fp:
        for row in additions:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    by_type = Counter(a["contradiction_type"] for a in additions)
    summary = {
        "candidate_pool": len(candidates),
        "processed": len(results),
        "accepted_target_types": sum(
            1
            for row in results
            if isinstance(row.get("recheck"), dict)
            and row["recheck"]["recheck_type"] in TARGET_TYPES
            and row["recheck"]["is_genuine_contradiction"] is True
            and float(row["recheck"]["confidence"]) >= args.min_confidence
        ),
        "selected_for_addition": len(selected),
        "added_to_corpus": len(additions),
        "added_by_type": dict(by_type),
        "target_additions": args.target_additions,
        "min_confidence": args.min_confidence,
        "corpus_in": str(args.corpus_in),
        "corpus_out": str(args.corpus_out),
        "selected_ids": [row["id"] for row in selected],
    }
    args.summary_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("Non-corpus reclassification complete")
    print(f"  candidate_pool={len(candidates)} processed={len(results)}")
    print(f"  selected={len(selected)} added={len(additions)} by_type={dict(by_type)}")
    print(f"  summary={args.summary_out}")


if __name__ == "__main__":
    main()
