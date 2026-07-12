#!/usr/bin/env python3
"""Apply deterministic label-consistency fixes to contradiction corpus.

Rule enforced:
- If `is_genuine_contradiction == false`, `contradiction_type` must be `contextual`.

The script does not overwrite source by default. It writes a new corpus file and
an explicit change log for auditability.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    base = Path(__file__).resolve().parent / "output" / "v3"
    parser = argparse.ArgumentParser(description="Fix corpus label consistency.")
    parser.add_argument(
        "--input",
        type=Path,
        default=base / "corpus_final_v4.jsonl",
        help="Input corpus JSONL.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=base / "corpus_final_v5_consistent.jsonl",
        help="Output corpus JSONL.",
    )
    parser.add_argument(
        "--changelog",
        type=Path,
        default=base / "corpus_final_v5_consistent_changes.jsonl",
        help="Per-row change log JSONL.",
    )
    parser.add_argument(
        "--stats",
        type=Path,
        default=base / "corpus_final_v5_consistent_stats.json",
        help="Summary stats JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]

    out_rows: list[dict] = []
    changes: list[dict] = []

    for row in rows:
        new_row = dict(row)
        rid = row.get("id", "")
        old_type = row.get("contradiction_type")
        genuine = bool(row.get("is_genuine_contradiction", False))

        if (not genuine) and old_type != "contextual":
            new_row["contradiction_type"] = "contextual"
            changes.append(
                {
                    "id": rid,
                    "change": "set_non_genuine_to_contextual",
                    "old_contradiction_type": old_type,
                    "new_contradiction_type": "contextual",
                    "is_genuine_contradiction": genuine,
                }
            )
        out_rows.append(new_row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fp:
        for row in out_rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    with args.changelog.open("w", encoding="utf-8") as fp:
        for row in changes:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    stats = {
        "input": str(args.input),
        "output": str(args.output),
        "total_entries": len(rows),
        "changed_entries": len(changes),
        "change_type_counts": {"set_non_genuine_to_contextual": len(changes)},
    }
    args.stats.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("Corpus consistency fix complete")
    print(f"  total_entries={len(rows)} changed_entries={len(changes)}")
    print(f"  output={args.output}")
    print(f"  changelog={args.changelog}")
    print(f"  stats={args.stats}")


if __name__ == "__main__":
    main()
