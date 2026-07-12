#!/usr/bin/env python3
"""Recompute corpus evaluation metrics from saved predictions and updated gold labels.

Use this when corpus labels change and you want updated metrics without re-calling APIs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_common import compute_metrics as _compute_metrics_base  # noqa: E402
from eval_common import load_jsonl


def parse_args() -> argparse.Namespace:
    base = Path(__file__).resolve().parent / "output" / "v3"
    parser = argparse.ArgumentParser(description="Recompute metrics from cached predictions.")
    parser.add_argument(
        "--predictions",
        type=Path,
        default=base / "eval" / "eval_results.jsonl",
        help="Prediction JSONL with pred_* fields.",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=base / "corpus_final_v4.jsonl",
        help="Gold corpus JSONL.",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=base / "eval" / "eval_report_recomputed.json",
        help="Recomputed report JSON path.",
    )
    parser.add_argument(
        "--misclassified-out",
        type=Path,
        default=base / "eval" / "misclassified_recomputed.jsonl",
        help="Recomputed misclassified JSONL path.",
    )
    parser.add_argument(
        "--fail-on-coverage-gap",
        action="store_true",
        help="Exit non-zero if predictions do not cover the entire gold corpus.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    preds = load_jsonl(args.predictions)
    corpus = {row["id"]: row for row in load_jsonl(args.corpus)}

    # Merge predictions with gold labels
    merged: list[dict] = []
    missing_gold = 0
    duplicate_prediction_ids = 0
    seen_prediction_ids: set[str] = set()
    covered_gold_ids: set[str] = set()
    for row in preds:
        rid = row.get("id")
        if rid in seen_prediction_ids:
            duplicate_prediction_ids += 1
        seen_prediction_ids.add(rid)
        gold = corpus.get(rid)
        if not gold:
            missing_gold += 1
            continue
        covered_gold_ids.add(rid)
        m = dict(row)
        m["gold_type"] = gold.get("contradiction_type")
        m["gold_genuine"] = bool(gold.get("is_genuine_contradiction", False))
        merged.append(m)

    unscored_gold_ids = sorted(set(corpus.keys()) - covered_gold_ids)
    gold_total = len(corpus)
    gold_covered = len(covered_gold_ids)

    # Compute metrics using shared function
    report = _compute_metrics_base(merged)

    # Add recompute-specific fields
    report["total_predictions"] = len(preds)
    report["matched_with_gold"] = len(merged)
    report["missing_gold_rows"] = missing_gold
    report["gold_total_rows"] = gold_total
    report["gold_covered_rows"] = gold_covered
    report["gold_coverage_rate"] = round(gold_covered / gold_total, 3) if gold_total else 0.0
    report["unscored_gold_rows"] = len(unscored_gold_ids)
    report["unscored_gold_ids_sample"] = unscored_gold_ids[:50]
    report["duplicate_prediction_ids"] = duplicate_prediction_ids
    report["scope_note"] = (
        "matched_subset_only" if unscored_gold_ids else "full_gold_coverage"
    )

    # Error analysis with TYPE_MISMATCH support
    valid = [r for r in merged if not r.get("parse_failed", False)]
    misclassified = []
    for r in valid:
        if r.get("pred_genuine") != r["gold_genuine"] or r.get("pred_type") != r["gold_type"]:
            item = dict(r)
            if r.get("pred_genuine") and not r["gold_genuine"]:
                item["error_type"] = "FP"
            elif (not r.get("pred_genuine")) and r["gold_genuine"]:
                item["error_type"] = "FN"
            else:
                item["error_type"] = "TYPE_MISMATCH"
            misclassified.append(item)

    # Write outputs
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.misclassified_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with args.misclassified_out.open("w", encoding="utf-8") as fp:
        for row in misclassified:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("Recompute complete")
    print(f"  predictions={len(preds)} matched_gold={len(merged)} missing_gold={missing_gold}")
    print(f"  gold_coverage={gold_covered}/{gold_total} ({report['gold_coverage_rate']:.1%})")
    print(f"  binary_f1={report['binary']['f1']} P={report['binary']['precision']} R={report['binary']['recall']}")
    print(f"  report={args.report_out}  misclassified={args.misclassified_out} ({len(misclassified)})")

    if args.fail_on_coverage_gap and unscored_gold_ids:
        raise SystemExit(f"Coverage gap: {len(unscored_gold_ids)} unscored gold rows")


if __name__ == "__main__":
    main()
