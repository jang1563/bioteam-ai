#!/usr/bin/env python3
"""Export manual adjudication pack to close remaining magnitude support gap."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    base = Path(__file__).resolve().parent / "output" / "v3"
    parser = argparse.ArgumentParser(description="Export magnitude adjudication CSV pack.")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=base / "corpus_final_v7_magnitude_relabel.jsonl",
        help="Current corpus JSONL.",
    )
    parser.add_argument(
        "--queue",
        type=Path,
        default=base / "qa_v7" / "magnitude_recheck_queue_alltypes.jsonl",
        help="All-type recheck queue JSONL.",
    )
    parser.add_argument(
        "--target-additional",
        type=int,
        default=13,
        help="How many additional magnitude entries are needed.",
    )
    parser.add_argument(
        "--buffer",
        type=int,
        default=12,
        help="Extra rows to include above target for reviewer choice.",
    )
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=base / "qa_v7" / "magnitude_adjudication_pack.csv",
        help="Output CSV for manual adjudication.",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=base / "qa_v7" / "magnitude_adjudication_pack.json",
        help="Output metadata JSON.",
    )
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    args = parse_args()
    corpus = {row["id"]: row for row in _load_jsonl(args.corpus)}
    queue = _load_jsonl(args.queue)
    target_rows = args.target_additional + args.buffer

    rows = []
    for item in queue:
        rid = item["id"]
        current = corpus.get(rid, {})
        rows.append(
            {
                "id": rid,
                "priority_score": item.get("priority_score", 0),
                "source_file": item.get("source_file", ""),
                "domain": item.get("domain", ""),
                "intended_type": item.get("intended_type", ""),
                "pred_type": item.get("pred_type", ""),
                "pred_confidence": item.get("pred_confidence", ""),
                "cue_count": item.get("cue_count", 0),
                "cue_patterns": " | ".join(item.get("cue_patterns", [])),
                "in_current_corpus": item.get("in_current_corpus", False),
                "current_type": current.get("contradiction_type", ""),
                "current_is_genuine": current.get("is_genuine_contradiction", ""),
                "claim_a": item.get("claim_a", ""),
                "claim_b": item.get("claim_b", ""),
                # columns for manual annotation
                "adjudicated_type": "",
                "adjudicated_is_genuine": "",
                "adjudication_confidence": "",
                "adjudication_notes": "",
            }
        )

    rows.sort(key=lambda x: (-x["priority_score"], x["id"]))
    selected = rows[:target_rows]

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(selected[0].keys()) if selected else [])
        if selected:
            writer.writeheader()
            writer.writerows(selected)

    meta = {
        "corpus": str(args.corpus),
        "queue": str(args.queue),
        "target_additional_magnitude": args.target_additional,
        "buffer": args.buffer,
        "rows_exported": len(selected),
        "out_csv": str(args.out_csv),
    }
    args.out_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("Magnitude adjudication pack exported")
    print(f"  rows_exported={len(selected)} target_additional={args.target_additional}")
    print(f"  csv={args.out_csv}")
    print(f"  meta={args.out_json}")


if __name__ == "__main__":
    main()
