#!/usr/bin/env python3
"""Corpus QA for contradiction dataset v3/v4 and stratified split generation.

This script performs three jobs:
1) Data integrity and label consistency checks
2) Type-support analysis for corpus improvement planning
3) Deterministic stratified split generation for fair re-evaluation

Usage:
  cd backend
  ../.venv/bin/python -m scripts.qa_corpus_v3
  ../.venv/bin/python -m scripts.qa_corpus_v3 --min-genuine-support 40 --seed 7
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

try:
    from scripts.corpus_quality_utils import claim_quality_issues
except ImportError:  # pragma: no cover - direct script execution path
    from corpus_quality_utils import claim_quality_issues

VALID_TYPES = {"direct", "contextual", "methodological", "temporal", "magnitude"}
GENUINE_TYPES = ("direct", "temporal", "magnitude", "methodological")
SEED_OFFSET = {
    "contextual": 11,
    "direct": 23,
    "temporal": 37,
    "magnitude": 53,
    "methodological": 71,
}
REQUIRED_FIELDS = (
    "id",
    "claim_a",
    "claim_b",
    "contradiction_type",
    "is_genuine_contradiction",
    "confidence",
)

# Lightweight lexical cues used for manual-review prioritization.
TIME_CUES = re.compile(
    r"\b(time|hour|day|week|month|year|stage|early|late|baseline|follow-?up|acute|chronic|post|pre)\b",
    flags=re.IGNORECASE,
)
METHOD_CUES = re.compile(
    r"\b(assay|western blot|mass spectrometry|rna-?seq|chip-?seq|pcr|qpcr|immuno|microscopy|flow cytometry|pipeline|algorithm|antibody)\b",
    flags=re.IGNORECASE,
)
MAGNITUDE_CUES = re.compile(
    r"(%|fold|odds ratio|hazard ratio|relative risk|effect size|significant|non-?significant|p\s*[<=>]|confidence interval|ci\b|increase[sd]?\s+by|decrease[sd]?\s+by|reduction)",
    flags=re.IGNORECASE,
)
TRUNCATED_PVALUE = re.compile(r"\bp\s*[<=>]\s*0\.$", flags=re.IGNORECASE)
FLAG_PRIORITY = {
    "invalid_type": 100,
    "nongenuine_noncontextual": 100,
    "genuine_marked_contextual": 100,
    "missing_required_fields": 95,
    "confidence_not_numeric": 90,
    "confidence_out_of_range": 90,
    "empty_claim": 85,
    "truncated_pvalue_pattern": 80,
    "claim_a_unmatched_closing_paren": 82,
    "claim_b_unmatched_closing_paren": 82,
    "claim_a_suspicious_fragment_prefix": 82,
    "claim_b_suspicious_fragment_prefix": 82,
    "duplicate_exact_pair": 80,
    "duplicate_or_swapped_pair": 65,
    "temporal_without_time_cue": 45,
    "methodological_without_method_cue": 40,
    "magnitude_without_magnitude_cue": 40,
}
HARD_REMOVE_PREFIXES = (
    "invalid_type",
    "nongenuine_noncontextual",
    "genuine_marked_contextual",
    "missing_required_fields",
    "confidence_not_numeric",
    "confidence_out_of_range",
    "empty_claim",
    "truncated_pvalue_pattern",
    "claim_a_unmatched_closing_paren",
    "claim_b_unmatched_closing_paren",
    "claim_a_suspicious_fragment_prefix",
    "claim_b_suspicious_fragment_prefix",
    "duplicate_exact_pair",
)


def _flag_priority(flag: str) -> int:
    for prefix, score in FLAG_PRIORITY.items():
        if flag.startswith(prefix):
            return score
    return 20


def _flag_matches_prefix(flag: str, prefix: str) -> bool:
    return flag == prefix or flag.startswith(f"{prefix}:")


def _is_hard_flag(flag: str) -> bool:
    return any(_flag_matches_prefix(flag, prefix) for prefix in HARD_REMOVE_PREFIXES)


def _recommended_action(flags: list[str]) -> str:
    if any(f.startswith("nongenuine_noncontextual") for f in flags):
        return "Set contradiction_type=contextual or re-adjudicate genuine label."
    if any(f.startswith("genuine_marked_contextual") for f in flags):
        return "Set contradiction_type to one genuine type or set is_genuine_contradiction=false."
    if any(f.startswith("truncated_pvalue_pattern") for f in flags):
        return "Re-open source abstract and repair truncated claim text."
    if any(f.startswith("methodological_without_method_cue") for f in flags):
        return "Confirm methodological signal exists; else relabel as direct/contextual."
    if any(f.startswith("temporal_without_time_cue") for f in flags):
        return "Confirm explicit time/stage contrast; else relabel."
    if any(f.startswith("magnitude_without_magnitude_cue") for f in flags):
        return "Confirm effect-size/significance contrast; else relabel."
    return "Manual review required."


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="QA corpus and generate stratified splits.")
    parser.add_argument(
        "--input",
        type=Path,
        default=root / "output" / "v3" / "corpus_final_v4.jsonl",
        help="Input corpus JSONL.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=root / "output" / "v3" / "qa",
        help="Output directory for QA reports and split files.",
    )
    parser.add_argument(
        "--min-genuine-support",
        type=int,
        default=30,
        help="Target minimum support per genuine type for stable analysis.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic sampling.",
    )
    return parser.parse_args()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _has_any_cue(entry: dict, pattern: re.Pattern[str]) -> bool:
    text = f"{entry.get('claim_a', '')} {entry.get('claim_b', '')}"
    return bool(pattern.search(text))


def _sample(rows: list[dict], n: int, seed: int) -> list[dict]:
    if n >= len(rows):
        return sorted(rows, key=lambda r: r["id"])
    rng = random.Random(seed)
    picked = rng.sample(rows, n)
    return sorted(picked, key=lambda r: r["id"])


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    flags_by_id: dict[str, list[str]] = defaultdict(list)
    global_issues: list[str] = []

    by_type = Counter()
    genuine_by_type = Counter()
    by_domain = Counter()
    contextual_count = 0

    seen_pair: dict[tuple[str, str], list[str]] = defaultdict(list)
    seen_unordered_pair: dict[tuple[str, str], list[str]] = defaultdict(list)

    for row in rows:
        rid = row.get("id", "<missing-id>")
        by_type[row.get("contradiction_type", "")] += 1
        by_domain[row.get("domain", "")] += 1
        if row.get("is_genuine_contradiction"):
            genuine_by_type[row.get("contradiction_type", "")] += 1
        else:
            contextual_count += 1

        missing = [field for field in REQUIRED_FIELDS if field not in row]
        if missing:
            flags_by_id[rid].append(f"missing_required_fields:{','.join(missing)}")

        ctype = row.get("contradiction_type")
        genuine = bool(row.get("is_genuine_contradiction", False))
        conf = row.get("confidence")

        if ctype not in VALID_TYPES:
            flags_by_id[rid].append("invalid_type")

        if genuine and ctype == "contextual":
            flags_by_id[rid].append("genuine_marked_contextual")
        if (not genuine) and ctype != "contextual":
            flags_by_id[rid].append("nongenuine_noncontextual")

        if not isinstance(conf, (int, float)):
            flags_by_id[rid].append("confidence_not_numeric")
        elif conf < 0.0 or conf > 1.0:
            flags_by_id[rid].append("confidence_out_of_range")

        claim_a = str(row.get("claim_a", "")).strip()
        claim_b = str(row.get("claim_b", "")).strip()
        if not claim_a or not claim_b:
            flags_by_id[rid].append("empty_claim")
        if TRUNCATED_PVALUE.search(claim_a) or TRUNCATED_PVALUE.search(claim_b):
            flags_by_id[rid].append("truncated_pvalue_pattern")
        for issue in claim_quality_issues(claim_a):
            if issue in {"unmatched_closing_paren", "suspicious_fragment_prefix"}:
                flags_by_id[rid].append(f"claim_a_{issue}")
        for issue in claim_quality_issues(claim_b):
            if issue in {"unmatched_closing_paren", "suspicious_fragment_prefix"}:
                flags_by_id[rid].append(f"claim_b_{issue}")

        pair = (_norm(claim_a), _norm(claim_b))
        seen_pair[pair].append(rid)
        seen_unordered_pair[tuple(sorted(pair))].append(rid)

        # Heuristic review flags for hard types: prioritize manual curation.
        if genuine and ctype == "temporal" and not _has_any_cue(row, TIME_CUES):
            flags_by_id[rid].append("temporal_without_time_cue")
        if genuine and ctype == "methodological" and not _has_any_cue(row, METHOD_CUES):
            flags_by_id[rid].append("methodological_without_method_cue")
        if genuine and ctype == "magnitude" and not _has_any_cue(row, MAGNITUDE_CUES):
            flags_by_id[rid].append("magnitude_without_magnitude_cue")

    exact_dup_groups = [ids for ids in seen_pair.values() if len(ids) > 1]
    reversed_dup_groups = [ids for ids in seen_unordered_pair.values() if len(ids) > 1]
    for ids in exact_dup_groups:
        for rid in ids:
            flags_by_id[rid].append("duplicate_exact_pair")
    for ids in reversed_dup_groups:
        if len(ids) == 2:
            # Keep this softer than exact duplicate because A/B can legitimately be swapped in some pipelines.
            for rid in ids:
                flags_by_id[rid].append("duplicate_or_swapped_pair")

    unknown_types = sorted(t for t in by_type.keys() if t and t not in VALID_TYPES)
    if unknown_types:
        global_issues.append(f"unknown_types={unknown_types}")

    support_gap = {
        t: max(0, args.min_genuine_support - genuine_by_type.get(t, 0))
        for t in GENUINE_TYPES
    }
    min_genuine_class = min(genuine_by_type.get(t, 0) for t in GENUINE_TYPES)
    multiclass_5way_min = min(by_type.get(t, 0) for t in ("contextual",) + GENUINE_TYPES)

    # Generate deterministic splits for apples-to-apples re-evaluation.
    by_type_rows: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_type_rows[row["contradiction_type"]].append(row)

    split_5way = []
    for ctype in ("contextual",) + GENUINE_TYPES:
        sampled = _sample(
            by_type_rows.get(ctype, []),
            multiclass_5way_min,
            args.seed + SEED_OFFSET[ctype],
        )
        split_5way.extend(sampled)
    split_5way = sorted(split_5way, key=lambda r: (r["contradiction_type"], r["id"]))

    split_4way = []
    for ctype in GENUINE_TYPES:
        sampled = _sample(
            by_type_rows.get(ctype, []),
            min_genuine_class,
            args.seed + SEED_OFFSET[ctype],
        )
        split_4way.extend(sampled)
    split_4way = sorted(split_4way, key=lambda r: (r["contradiction_type"], r["id"]))

    positives = [r for r in rows if r.get("is_genuine_contradiction")]
    negatives = [r for r in rows if not r.get("is_genuine_contradiction")]
    binary_n = min(len(positives), len(negatives))
    split_binary = _sample(positives, binary_n, args.seed + 101) + _sample(negatives, binary_n, args.seed + 202)
    split_binary = sorted(split_binary, key=lambda r: (int(not r["is_genuine_contradiction"]), r["id"]))

    flags_rows = []
    flag_counter = Counter()
    for row in rows:
        rid = row.get("id", "<missing-id>")
        item_flags = sorted(set(flags_by_id.get(rid, [])))
        if not item_flags:
            continue
        for flag in item_flags:
            flag_counter[flag] += 1
        flags_rows.append(
            {
                "id": rid,
                "contradiction_type": row.get("contradiction_type"),
                "is_genuine_contradiction": row.get("is_genuine_contradiction"),
                "domain": row.get("domain", ""),
                "flags": item_flags,
            }
        )
    flags_rows = sorted(flags_rows, key=lambda x: x["id"])

    report = {
        "input_file": str(args.input),
        "total_entries": len(rows),
        "valid_types": sorted(VALID_TYPES),
        "counts": {
            "by_type_all": dict(by_type),
            "by_type_genuine_only": dict(genuine_by_type),
            "contextual_total": contextual_count,
            "by_domain": dict(by_domain),
        },
        "support_target": {
            "min_genuine_support_per_type": args.min_genuine_support,
            "gap_by_genuine_type": support_gap,
            "all_targets_met": all(v == 0 for v in support_gap.values()),
        },
        "split_recommendation": {
            "multiclass_5way_per_class": multiclass_5way_min,
            "multiclass_5way_total": multiclass_5way_min * 5,
            "genuine_4way_per_class": min_genuine_class,
            "genuine_4way_total": min_genuine_class * 4,
            "binary_balanced_per_class": binary_n,
            "binary_balanced_total": binary_n * 2,
        },
        "quality_flags": {
            "total_rows_flagged": len(flags_rows),
            "flag_counts": dict(flag_counter),
        },
        "duplicates": {
            "exact_duplicate_groups": len(exact_dup_groups),
            "exact_duplicate_rows": sum(len(ids) for ids in exact_dup_groups),
            "duplicate_or_swapped_groups": len(reversed_dup_groups),
            "duplicate_or_swapped_rows": sum(len(ids) for ids in reversed_dup_groups),
        },
        "global_issues": global_issues,
        "artifacts": {
            "flags_jsonl": "corpus_qa_flags.jsonl",
            "curation_queue_jsonl": "corpus_curation_queue.jsonl",
            "split_multiclass_5way_jsonl": "stratified_multiclass_5way.jsonl",
            "split_genuine_4way_jsonl": "stratified_genuine_4way.jsonl",
            "split_binary_balanced_jsonl": "stratified_binary_balanced.jsonl",
        },
    }

    report_path = args.out_dir / "corpus_qa_report.json"
    flags_path = args.out_dir / "corpus_qa_flags.jsonl"
    curation_queue_path = args.out_dir / "corpus_curation_queue.jsonl"
    curation_queue_hard_path = args.out_dir / "corpus_curation_queue_hard.jsonl"
    curation_queue_soft_path = args.out_dir / "corpus_curation_queue_soft.jsonl"
    split_5way_path = args.out_dir / "stratified_multiclass_5way.jsonl"
    split_4way_path = args.out_dir / "stratified_genuine_4way.jsonl"
    split_binary_path = args.out_dir / "stratified_binary_balanced.jsonl"

    curation_queue = []
    curation_queue_hard = []
    curation_queue_soft = []
    for row in rows:
        rid = row.get("id", "<missing-id>")
        item_flags = sorted(set(flags_by_id.get(rid, [])))
        if not item_flags:
            continue
        primary = sorted(item_flags, key=lambda f: (-_flag_priority(f), f))[0]
        score = max(_flag_priority(f) for f in item_flags)
        hard_flags = [flag for flag in item_flags if _is_hard_flag(flag)]
        soft_flags = [flag for flag in item_flags if not _is_hard_flag(flag)]
        queue_row = {
            "id": rid,
            "priority": score,
            "primary_flag": primary,
            "flags": item_flags,
            "hard_flags": hard_flags,
            "soft_flags": soft_flags,
            "gate": "hard_remove" if hard_flags else "soft_review",
            "contradiction_type": row.get("contradiction_type"),
            "is_genuine_contradiction": row.get("is_genuine_contradiction"),
            "domain": row.get("domain", ""),
            "recommended_action": _recommended_action(item_flags),
            "claim_a": row.get("claim_a", ""),
            "claim_b": row.get("claim_b", ""),
        }
        curation_queue.append(queue_row)
        if hard_flags:
            curation_queue_hard.append(queue_row)
        else:
            curation_queue_soft.append(queue_row)
    curation_queue = sorted(curation_queue, key=lambda x: (-x["priority"], x["id"]))
    curation_queue_hard = sorted(curation_queue_hard, key=lambda x: (-x["priority"], x["id"]))
    curation_queue_soft = sorted(curation_queue_soft, key=lambda x: (-x["priority"], x["id"]))

    hard_flag_rows = sum(1 for row in flags_rows if any(_is_hard_flag(flag) for flag in row["flags"]))
    soft_flag_rows = sum(1 for row in flags_rows if any(not _is_hard_flag(flag) for flag in row["flags"]))
    report["quality_flags"].update(
        {
            "hard_flag_rows": hard_flag_rows,
            "soft_flag_rows": soft_flag_rows,
            "hard_remove_prefixes": list(HARD_REMOVE_PREFIXES),
        }
    )
    report["curation_gate"] = {
        "hard_remove_rows": len(curation_queue_hard),
        "soft_review_rows": len(curation_queue_soft),
    }
    report["artifacts"].update(
        {
            "curation_queue_hard_jsonl": "corpus_curation_queue_hard.jsonl",
            "curation_queue_soft_jsonl": "corpus_curation_queue_soft.jsonl",
        }
    )

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_jsonl(flags_path, flags_rows)
    _write_jsonl(curation_queue_path, curation_queue)
    _write_jsonl(curation_queue_hard_path, curation_queue_hard)
    _write_jsonl(curation_queue_soft_path, curation_queue_soft)
    _write_jsonl(split_5way_path, split_5way)
    _write_jsonl(split_4way_path, split_4way)
    _write_jsonl(split_binary_path, split_binary)

    print("Corpus QA complete")
    print(f"  entries={len(rows)} | flagged={len(flags_rows)}")
    print(f"  report={report_path}")
    print(f"  flags={flags_path}")
    print(f"  curation_queue={curation_queue_path} (n={len(curation_queue)})")
    print(f"  curation_queue_hard={curation_queue_hard_path} (n={len(curation_queue_hard)})")
    print(f"  curation_queue_soft={curation_queue_soft_path} (n={len(curation_queue_soft)})")
    print(f"  split_5way={split_5way_path} (n={len(split_5way)})")
    print(f"  split_4way={split_4way_path} (n={len(split_4way)})")
    print(f"  split_binary={split_binary_path} (n={len(split_binary)})")


if __name__ == "__main__":
    main()
