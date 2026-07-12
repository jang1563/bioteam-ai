#!/usr/bin/env python3
"""Build candidate queue to expand magnitude support via re-adjudication.

This script does not modify corpus labels. It identifies likely magnitude
candidates from existing v5 candidate files and emits a prioritized queue.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

MAG_CUE_PATTERNS = [
    r"\beffect size\b",
    r"\bnon-?significant\b",
    r"\bsignificant\b",
    r"\bp\s*[<=>]",
    r"\bconfidence interval\b",
    r"\bheterogeneity\b",
    r"\binconsistent\b",
    r"\bdiscrepancy\b",
    r"\bmodest\b",
    r"\bsmall\b",
    r"\blarge\b",
    r"\bfold\b",
    r"%",
]


def parse_args() -> argparse.Namespace:
    base = Path(__file__).resolve().parent / "output" / "v3"
    parser = argparse.ArgumentParser(description="Build magnitude expansion candidate queue.")
    parser.add_argument(
        "--candidates-dir",
        type=Path,
        default=base,
        help="Directory containing candidates_*_v5.jsonl files.",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=base / "corpus_final_v6_curated.jsonl",
        help="Current working corpus JSONL.",
    )
    parser.add_argument(
        "--out-queue",
        type=Path,
        default=base / "qa_v6" / "magnitude_expansion_queue.jsonl",
        help="Output prioritized queue JSONL.",
    )
    parser.add_argument(
        "--out-summary",
        type=Path,
        default=base / "qa_v6" / "magnitude_expansion_summary.json",
        help="Output summary JSON.",
    )
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _cue_hits(text: str) -> list[str]:
    hits = []
    for pat in MAG_CUE_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            hits.append(pat)
    return hits


def _score_candidate(
    *,
    intended_type: str,
    pred_type: str,
    pred_genuine: bool,
    conf: float,
    in_corpus: bool,
    current_corpus_type: str | None,
    cue_count: int,
) -> int:
    score = 0
    if intended_type == "magnitude":
        score += 60
    if pred_genuine:
        score += 20
    if pred_type in {"direct", "methodological", "temporal"}:
        score += 12
    if conf >= 0.9:
        score += 8
    elif conf >= 0.8:
        score += 5
    score += min(cue_count, 5) * 4
    if in_corpus and current_corpus_type == "magnitude":
        score -= 1000  # already magnitude, exclude later
    return score


def main() -> None:
    args = parse_args()
    candidate_files = sorted(args.candidates_dir.glob("candidates_*_v5.jsonl"))
    corpus_rows = _load_jsonl(args.corpus)
    corpus_by_id = {row["id"]: row for row in corpus_rows}

    by_id: dict[str, dict] = {}
    for file_path in candidate_files:
        for row in _load_jsonl(file_path):
            pair_id = row.get("pair_id")
            if not pair_id:
                continue
            label = row.get("label")
            if not isinstance(label, dict):
                continue

            pred_type = str(label.get("contradiction_type", ""))
            pred_genuine = bool(label.get("is_genuine_contradiction", False))
            conf = float(label.get("confidence", 0.0))
            intended_type = str(row.get("intended_type", ""))
            claim_a = str(row.get("claim_a", {}).get("text", ""))
            claim_b = str(row.get("claim_b", {}).get("text", ""))
            text = f"{claim_a} {claim_b}"
            hits = _cue_hits(text)
            in_corpus = pair_id in corpus_by_id
            current_type = corpus_by_id[pair_id]["contradiction_type"] if in_corpus else None
            current_genuine = corpus_by_id[pair_id]["is_genuine_contradiction"] if in_corpus else None

            score = _score_candidate(
                intended_type=intended_type,
                pred_type=pred_type,
                pred_genuine=pred_genuine,
                conf=conf,
                in_corpus=in_corpus,
                current_corpus_type=current_type,
                cue_count=len(hits),
            )

            item = {
                "id": pair_id,
                "source_file": file_path.name,
                "domain": row.get("domain", ""),
                "intended_type": intended_type,
                "pred_type": pred_type,
                "pred_genuine": pred_genuine,
                "pred_confidence": conf,
                "in_current_corpus": in_corpus,
                "current_corpus_type": current_type,
                "current_corpus_genuine": current_genuine,
                "cue_count": len(hits),
                "cue_patterns": hits,
                "priority_score": score,
                "claim_a": claim_a,
                "claim_b": claim_b,
                "recommended_action": (
                    "Re-adjudicate for magnitude relabel"
                    if in_corpus
                    else "Evaluate for possible corpus inclusion as magnitude"
                ),
            }

            # Keep highest score per id
            prev = by_id.get(pair_id)
            if prev is None or item["priority_score"] > prev["priority_score"]:
                by_id[pair_id] = item

    queue = []
    for item in by_id.values():
        if item["pred_type"] == "magnitude":
            continue
        if item["pred_confidence"] < 0.8:
            continue

        intended_magnitude = item["intended_type"] == "magnitude"
        strong_magnitude_signal = (
            item["pred_genuine"]
            and item["pred_type"] in {"direct", "methodological", "temporal"}
            and item["cue_count"] >= 3
        )
        if not (intended_magnitude or strong_magnitude_signal):
            continue
        queue.append(item)
    queue.sort(key=lambda x: (-x["priority_score"], x["id"]))

    args.out_queue.parent.mkdir(parents=True, exist_ok=True)
    with args.out_queue.open("w", encoding="utf-8") as fp:
        for row in queue:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    in_corpus_queue = [row for row in queue if row["in_current_corpus"]]
    new_rows_queue = [row for row in queue if not row["in_current_corpus"]]
    summary = {
        "current_corpus": str(args.corpus),
        "candidate_files": [p.name for p in candidate_files],
        "queue_size": len(queue),
        "queue_in_current_corpus": len(in_corpus_queue),
        "queue_not_in_current_corpus": len(new_rows_queue),
        "top_20_potential_ids": [row["id"] for row in queue[:20]],
        "pred_type_distribution": dict(Counter(row["pred_type"] for row in queue)),
        "intended_type_distribution": dict(Counter(row["intended_type"] for row in queue)),
    }
    args.out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("Magnitude expansion queue built")
    print(f"  queue={args.out_queue} (n={len(queue)})")
    print(f"  in_current_corpus={len(in_corpus_queue)} not_in_corpus={len(new_rows_queue)}")
    print(f"  summary={args.out_summary}")


if __name__ == "__main__":
    main()
