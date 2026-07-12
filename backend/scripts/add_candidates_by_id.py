#!/usr/bin/env python3
"""Append specific candidate IDs from v5 files into corpus."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

try:
    from scripts.corpus_quality_utils import LEGACY_EXCLUDED_IDS, pair_quality_issues
except ImportError:  # pragma: no cover - direct script execution path
    from corpus_quality_utils import LEGACY_EXCLUDED_IDS, pair_quality_issues

VALID_TYPES = {"direct", "contextual", "methodological", "temporal", "magnitude"}

def parse_args() -> argparse.Namespace:
    base = Path(__file__).resolve().parent / "output" / "v3"
    parser = argparse.ArgumentParser(description="Add selected candidate IDs to corpus.")
    parser.add_argument("--candidates-dir", type=Path, default=base)
    parser.add_argument("--corpus-in", type=Path, required=True)
    parser.add_argument("--corpus-out", type=Path, required=True)
    parser.add_argument("--changes-out", type=Path, required=True)
    parser.add_argument("--rejected-out", type=Path, help="Optional JSONL path for rejected IDs.")
    parser.add_argument("--ids", nargs="+", required=True, help="Candidate pair IDs to add.")
    parser.add_argument("--min-confidence", type=float, default=0.85)
    parser.add_argument("--allow-blocklisted", action="store_true")
    parser.add_argument("--allow-quality-issues", action="store_true")
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    args = parse_args()
    requested_ids = list(dict.fromkeys(args.ids))
    ids = set(requested_ids)

    corpus = _load_jsonl(args.corpus_in)
    existing = {row["id"] for row in corpus}

    # index candidates by id
    cand_by_id: dict[str, dict] = {}
    for p in sorted(args.candidates_dir.glob("candidates_*_v5.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            pid = item.get("pair_id")
            if pid in ids:
                cand_by_id[pid] = item

    additions = []
    missing = []
    rejected = []
    rejected_reasons: Counter[str] = Counter()
    for pid in requested_ids:
        if pid in existing:
            continue
        item = cand_by_id.get(pid)
        if not item or not isinstance(item.get("label"), dict):
            missing.append(pid)
            continue
        lbl = item["label"]
        claim_a = str(item.get("claim_a", {}).get("text", ""))
        claim_b = str(item.get("claim_b", {}).get("text", ""))

        reasons = []
        if (not args.allow_blocklisted) and pid in LEGACY_EXCLUDED_IDS:
            reasons.append("legacy_excluded_id")
        if not args.allow_quality_issues:
            reasons.extend(pair_quality_issues(claim_a, claim_b))

        ct = str(lbl.get("contradiction_type", ""))
        if ct not in VALID_TYPES:
            reasons.append("invalid_contradiction_type")

        try:
            conf = float(lbl.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = -1.0
            reasons.append("invalid_confidence")

        if conf < 0.0 or conf > 1.0:
            reasons.append("confidence_out_of_range")
        elif conf < args.min_confidence:
            reasons.append("confidence_below_min")

        if reasons:
            uniq_reasons = sorted(set(reasons))
            rejected.append({"id": pid, "reasons": uniq_reasons})
            rejected_reasons.update(uniq_reasons)
            continue

        additions.append(
            {
                "id": pid,
                "source_pmid": item.get("claim_a", {}).get("source_pmid", ""),
                "source_doi": item.get("claim_a", {}).get("source_doi", ""),
                "paper_title": item.get("claim_a", {}).get("paper_title", ""),
                "domain": item.get("domain", ""),
                "extraction_pattern": "",
                "claim_a": claim_a,
                "claim_b": claim_b,
                "contradiction_type": ct,
                "is_genuine_contradiction": bool(lbl.get("is_genuine_contradiction", False)),
                "confidence": conf,
                "rationale": lbl.get("rationale", ""),
                "intended_type": item.get("intended_type", ""),
                "_partial_parse": False,
            }
        )

    merged = corpus + additions
    with args.corpus_out.open("w", encoding="utf-8") as fp:
        for row in merged:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
    with args.changes_out.open("w", encoding="utf-8") as fp:
        for row in additions:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
    if args.rejected_out:
        args.rejected_out.parent.mkdir(parents=True, exist_ok=True)
        with args.rejected_out.open("w", encoding="utf-8") as fp:
            for row in rejected:
                fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("Candidate additions complete")
    print(f"  corpus_in={len(corpus)} added={len(additions)} corpus_out={len(merged)}")
    print(f"  rejected={len(rejected)} min_confidence={args.min_confidence}")
    if missing:
        print(f"  missing_ids={missing}")
    if rejected_reasons:
        print(f"  rejected_reasons={dict(rejected_reasons)}")
    print(f"  corpus_out={args.corpus_out}")
    print(f"  changes_out={args.changes_out}")
    if args.rejected_out:
        print(f"  rejected_out={args.rejected_out}")


if __name__ == "__main__":
    main()
