#!/usr/bin/env python3
"""Build an all-type queue for magnitude recheck from v5 candidate files."""

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
    r"\bodds ratio\b",
    r"\bhazard ratio\b",
    r"\brelative risk\b",
    r"\bheterogeneity\b",
    r"\binconsistent\b",
    r"\bdiscrepancy\b",
    r"\bmodest\b",
    r"\bweak\b",
    r"\bsmall\b",
    r"\blarge\b",
    r"\bfold\b",
    r"%",
]
TRUNCATED_PATTERNS = [
    re.compile(r"\bp\s*[<=>]\s*0\.$", flags=re.IGNORECASE),
    re.compile(r"=\s*\.$"),
]


def parse_args() -> argparse.Namespace:
    base = Path(__file__).resolve().parent / "output" / "v3"
    parser = argparse.ArgumentParser(description="Build all-type magnitude recheck queue.")
    parser.add_argument("--candidates-dir", type=Path, default=base)
    parser.add_argument("--corpus", type=Path, default=base / "corpus_final_v7_magnitude_relabel.jsonl")
    parser.add_argument("--out-queue", type=Path, default=base / "qa_v7" / "magnitude_recheck_queue_alltypes.jsonl")
    parser.add_argument("--out-summary", type=Path, default=base / "qa_v7" / "magnitude_recheck_queue_alltypes_summary.json")
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _cue_hits(text: str) -> list[str]:
    hits = []
    for pat in MAG_CUE_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            hits.append(pat)
    return hits


def main() -> None:
    args = parse_args()
    candidate_files = sorted(args.candidates_dir.glob("candidates_*_v5.jsonl"))
    corpus_by_id = {row["id"]: row for row in _load_jsonl(args.corpus)}

    by_id: dict[str, dict] = {}
    for file_path in candidate_files:
        for row in _load_jsonl(file_path):
            pair_id = row.get("pair_id")
            label = row.get("label")
            if not pair_id or not isinstance(label, dict):
                continue

            pred_type = str(label.get("contradiction_type", ""))
            pred_genuine = bool(label.get("is_genuine_contradiction", False))
            conf = float(label.get("confidence", 0.0))
            if not pred_genuine or conf < 0.8:
                continue
            if conf > 1.0:
                continue
            if pred_type not in {"direct", "methodological", "temporal"}:
                continue

            claim_a = str(row.get("claim_a", {}).get("text", ""))
            claim_b = str(row.get("claim_b", {}).get("text", ""))
            if any(p.search(claim_a) or p.search(claim_b) for p in TRUNCATED_PATTERNS):
                continue
            hits = _cue_hits(f"{claim_a} {claim_b}")
            if not hits:
                continue

            in_corpus = pair_id in corpus_by_id
            current_type = corpus_by_id[pair_id]["contradiction_type"] if in_corpus else None
            if current_type == "magnitude":
                continue

            score = 0
            score += 20 + min(len(hits), 5) * 8
            if row.get("intended_type") == "magnitude":
                score += 30
            if conf >= 0.95:
                score += 8
            elif conf >= 0.9:
                score += 5

            item = {
                "id": pair_id,
                "source_file": file_path.name,
                "domain": row.get("domain", ""),
                "intended_type": row.get("intended_type", ""),
                "pred_type": pred_type,
                "pred_genuine": pred_genuine,
                "pred_confidence": conf,
                "in_current_corpus": in_corpus,
                "current_corpus_type": current_type,
                "current_corpus_genuine": (
                    corpus_by_id[pair_id]["is_genuine_contradiction"] if in_corpus else None
                ),
                "cue_count": len(hits),
                "cue_patterns": hits,
                "priority_score": score,
                "claim_a": claim_a,
                "claim_b": claim_b,
                "recommended_action": "Recheck for possible magnitude relabel",
            }

            prev = by_id.get(pair_id)
            if prev is None or item["priority_score"] > prev["priority_score"]:
                by_id[pair_id] = item

    queue = sorted(by_id.values(), key=lambda x: (-x["priority_score"], x["id"]))
    args.out_queue.parent.mkdir(parents=True, exist_ok=True)
    with args.out_queue.open("w", encoding="utf-8") as fp:
        for row in queue:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "queue_size": len(queue),
        "in_current_corpus": sum(1 for row in queue if row["in_current_corpus"]),
        "not_in_current_corpus": sum(1 for row in queue if not row["in_current_corpus"]),
        "pred_type_distribution": dict(Counter(row["pred_type"] for row in queue)),
        "intended_type_distribution": dict(Counter(row["intended_type"] for row in queue)),
        "top_20_ids": [row["id"] for row in queue[:20]],
    }
    args.out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("All-type recheck queue built")
    print(f"  queue={args.out_queue} (n={len(queue)})")
    print(f"  summary={args.out_summary}")


if __name__ == "__main__":
    main()
