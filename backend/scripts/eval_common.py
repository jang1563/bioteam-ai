#!/usr/bin/env python3
"""Shared evaluation utilities for contradiction corpus scripts.

Extracts duplicated code from evaluate_corpus_gemini.py, evaluate_corpus_claude.py,
benchmark_w6.py, evaluate_w6_gemini_live.py, and recompute_corpus_metrics.py.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from pathlib import Path

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

VALID_TYPES = frozenset({"direct", "magnitude", "methodological", "temporal", "contextual"})
GENUINE_TYPES = frozenset({"direct", "magnitude", "methodological", "temporal"})
GENUINE_TYPES_ORDERED = ("direct", "temporal", "magnitude", "methodological")


# ── Response parsing ──────────────────────────────────────────────────────────

def parse_gemini_response(text: str) -> dict | None:
    """Parse Gemini JSON response with regex fallback.

    Returns dict with keys: contradiction_type, confidence,
    is_genuine_contradiction, rationale.  Returns None on parse failure.
    """
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    try:
        data = json.loads(text)
        ct = (data.get("contradiction_type") or "").strip().lower()
        genuine = bool(data.get("is_genuine_contradiction", False))
        if not genuine and (not ct or ct not in VALID_TYPES):
            ct = "contextual"
        if ct not in VALID_TYPES:
            return None
        return {
            "contradiction_type": ct,
            "confidence": float(data.get("confidence", 0.0)),
            "is_genuine_contradiction": genuine,
            "rationale": str(data.get("rationale", "")),
        }
    except (json.JSONDecodeError, ValueError):
        pass

    # Regex fallback for partial JSON
    ct_m = re.search(r'"contradiction_type"\s*:\s*"(\w+)"', text)
    conf_m = re.search(r'"confidence"\s*:\s*([\d.]+)', text)
    genuine_m = re.search(r'"is_genuine_contradiction"\s*:\s*(true|false)', text)
    rationale_m = re.search(r'"rationale"\s*:\s*"([^"]{5,})"', text)

    if ct_m and conf_m and genuine_m:
        ct = ct_m.group(1)
        if ct not in VALID_TYPES:
            return None
        return {
            "contradiction_type": ct,
            "confidence": float(conf_m.group(1)),
            "is_genuine_contradiction": genuine_m.group(1) == "true",
            "rationale": rationale_m.group(1) if rationale_m else "[truncated]",
        }
    return None


# ── Checkpoint ────────────────────────────────────────────────────────────────

def load_checkpoint(
    path: Path,
    valid_ids: set[str] | None = None,
    id_field: str = "id",
) -> dict[str, dict]:
    """Load checkpoint JSONL with dedup and optional stale-row filtering."""
    if not path.exists():
        return {}

    done: dict[str, dict] = {}
    with open(path) as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                done[r[id_field]] = r

    if valid_ids is not None:
        stale = [rid for rid in done if rid not in valid_ids]
        if stale:
            for rid in stale:
                del done[rid]
            log.info("Dropped %d stale checkpoint rows", len(stale))

    log.info("Checkpoint loaded: %d rows", len(done))
    return done


# ── Result construction ───────────────────────────────────────────────────────

def build_eval_result(entry: dict, pred: dict | None) -> dict:
    """Build standardized evaluation result row from gold entry + prediction."""
    return {
        "id": entry["id"],
        "gold_type": entry["contradiction_type"],
        "gold_genuine": entry["is_genuine_contradiction"],
        "domain": entry.get("domain", ""),
        "pred_type": pred["contradiction_type"] if pred else None,
        "pred_genuine": pred["is_genuine_contradiction"] if pred else None,
        "pred_confidence": pred["confidence"] if pred else None,
        "pred_rationale": pred["rationale"] if pred else None,
        "parse_failed": pred is None,
    }


# ── Metrics computation ──────────────────────────────────────────────────────

def compute_metrics(results: list[dict]) -> dict:
    """Compute binary, per-type, domain, and calibration metrics."""
    valid = [r for r in results if not r.get("parse_failed", False)]
    failed = [r for r in results if r.get("parse_failed", False)]

    tp = sum(1 for r in valid if r.get("pred_genuine") and r["gold_genuine"])
    fp = sum(1 for r in valid if r.get("pred_genuine") and not r["gold_genuine"])
    fn = sum(1 for r in valid if not r.get("pred_genuine") and r["gold_genuine"])
    tn = sum(1 for r in valid if not r.get("pred_genuine") and not r["gold_genuine"])

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    binary_match = sum(1 for r in valid if r.get("pred_genuine") == r["gold_genuine"])
    type_exact_all = sum(1 for r in valid if r.get("pred_type") == r["gold_type"])
    genuine_valid = [r for r in valid if r["gold_genuine"]]
    type_exact_genuine = sum(1 for r in genuine_valid if r.get("pred_type") == r["gold_type"])

    # Per-type recall (gold genuine only)
    type_stats: dict[str, dict] = {}
    type_confusion: dict[str, Counter] = defaultdict(Counter)

    for gold_type in GENUINE_TYPES_ORDERED:
        gold_entries = [
            r for r in valid
            if r["gold_genuine"] and r["gold_type"] == gold_type
        ]
        if not gold_entries:
            continue

        correct_type = sum(
            1 for r in gold_entries
            if r.get("pred_genuine") and r.get("pred_type") == gold_type
        )
        wrong_type = sum(
            1 for r in gold_entries
            if r.get("pred_genuine") and r.get("pred_type") != gold_type
        )
        missed = sum(1 for r in gold_entries if not r.get("pred_genuine"))

        type_stats[gold_type] = {
            "support": len(gold_entries),
            "correct_type": correct_type,
            "wrong_type_but_genuine": wrong_type,
            "missed_as_contextual": missed,
            "detection_recall": round((correct_type + wrong_type) / len(gold_entries), 3),
            "type_recall": round(correct_type / len(gold_entries), 3),
        }

        for r in gold_entries:
            type_confusion[gold_type][r.get("pred_type") or "none"] += 1

    # Contextual false positive rate
    contextual_entries = [r for r in valid if not r["gold_genuine"]]
    fp_rate = round(fp / len(contextual_entries), 3) if contextual_entries else 0.0

    # Domain-level binary accuracy
    domain_stats: dict[str, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
    for r in valid:
        d = r.get("domain", "unknown") or "unknown"
        domain_stats[d]["total"] += 1
        if r.get("pred_genuine") == r["gold_genuine"]:
            domain_stats[d]["correct"] += 1
    domain_acc = {
        d: {"accuracy": round(v["correct"] / v["total"], 3), "support": v["total"]}
        for d, v in domain_stats.items()
    }

    # Confidence calibration
    bins = [(0.0, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
    calibration = []
    for lo, hi in bins:
        bin_entries = [
            r for r in valid
            if r.get("pred_confidence") is not None and lo <= r["pred_confidence"] < hi
        ]
        if bin_entries:
            acc = sum(1 for r in bin_entries if r.get("pred_genuine") == r["gold_genuine"])
            calibration.append({
                "range": f"{lo:.1f}-{hi:.1f}",
                "count": len(bin_entries),
                "binary_accuracy": round(acc / len(bin_entries), 3),
            })

    return {
        "total": len(results),
        "valid": len(valid),
        "parse_failed": len(failed),
        "agreement": {
            "binary_match_rate": round(binary_match / len(valid), 3) if valid else 0.0,
            "binary_mismatch_rate": round(1 - (binary_match / len(valid)), 3) if valid else 0.0,
            "type_exact_match_rate_all": round(type_exact_all / len(valid), 3) if valid else 0.0,
            "type_exact_match_rate_genuine_only": (
                round(type_exact_genuine / len(genuine_valid), 3)
                if genuine_valid else 0.0
            ),
            "genuine_support": len(genuine_valid),
        },
        "binary": {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
        },
        "contextual_fp_rate": fp_rate,
        "type_stats": type_stats,
        "type_confusion": {k: dict(v) for k, v in type_confusion.items()},
        "domain_accuracy": domain_acc,
        "calibration": calibration,
    }


# ── Report printing ──────────────────────────────────────────────────────────

def print_report(metrics: dict, corpus_name: str = "", note: str = ""):
    """Print formatted evaluation report to stdout."""
    SEP = "=" * 65

    print(f"\n{SEP}")
    title = "EVALUATION REPORT"
    if corpus_name:
        title += f"  ({corpus_name}, {metrics['total']} entries)"
    if note:
        print(f"NOTE: {note}")
    print(title)
    print(SEP)

    b = metrics["binary"]
    print("\n[Binary Classification]  genuine vs contextual")
    print(f"  Precision             : {b['precision']:.3f}")
    print(f"  Recall                : {b['recall']:.3f}")
    print(f"  F1                    : {b['f1']:.3f}")
    print(f"  Confusion             : TP={b['tp']} FP={b['fp']} FN={b['fn']} TN={b['tn']}")
    print(f"  Contextual FP rate    : {metrics['contextual_fp_rate']:.1%}  "
          f"(contextual incorrectly predicted genuine)")

    a = metrics["agreement"]
    print("\n[Agreement Summary]  (parsed entries only)")
    print(f"  Binary match rate     : {a['binary_match_rate']:.1%}")
    print(f"  Binary mismatch rate  : {a['binary_mismatch_rate']:.1%}")
    print(f"  Type exact match (all): {a['type_exact_match_rate_all']:.1%}")
    print(f"  Type exact match (genuine-only, n={a['genuine_support']}): "
          f"{a['type_exact_match_rate_genuine_only']:.1%}")

    print("\n[Per-type Analysis]  (gold genuine entries only)")
    print(f"  {'Type':20s}  {'N':>4}  {'Detected':>9}  {'Correct Type':>12}  {'Missed':>7}")
    print(f"  {'-'*20}  {'-'*4}  {'-'*9}  {'-'*12}  {'-'*7}")
    for t in GENUINE_TYPES_ORDERED:
        ts = metrics["type_stats"].get(t)
        if not ts:
            continue
        print(
            f"  {t:20s}  {ts['support']:>4}  "
            f"{ts['detection_recall']:>8.1%}  "
            f"{ts['type_recall']:>11.1%}  "
            f"{ts['missed_as_contextual']:>7}"
        )

    if metrics.get("type_confusion"):
        print("\n[Type Confusion]  gold_type -> predicted_type")
        for gold_type, pred_counts in metrics["type_confusion"].items():
            items = sorted(pred_counts.items(), key=lambda x: -x[1])
            breakdown = "  ".join(f"{pt}:{cnt}" for pt, cnt in items)
            print(f"  gold={gold_type:<16} {breakdown}")

    if metrics.get("domain_accuracy"):
        print("\n[Domain Accuracy]")
        for domain, stats in sorted(metrics["domain_accuracy"].items(),
                                    key=lambda x: -x[1]["support"]):
            bar = "#" * int(stats["accuracy"] * 20)
            print(f"  {domain:<30}  acc={stats['accuracy']:.1%}  n={stats['support']:>4}  {bar}")

    if metrics.get("calibration"):
        print("\n[Confidence Calibration]")
        for cb in metrics["calibration"]:
            bar = "#" * int(cb["binary_accuracy"] * 20)
            print(f"  conf {cb['range']}:  n={cb['count']:>4}  acc={cb['binary_accuracy']:.1%}  {bar}")

    print("\n[Summary]")
    print(f"  Total entries   : {metrics['total']}")
    print(f"  Valid (parsed)  : {metrics['valid']}")
    print(f"  Parse failures  : {metrics['parse_failed']}")
    print(SEP)


# ── Error analysis ────────────────────────────────────────────────────────────

def save_error_analysis(
    results: list[dict],
    corpus_path: Path,
    output_path: Path,
):
    """Save misclassified entries with claim text for error analysis."""
    corpus = {}
    with open(corpus_path) as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                corpus[entry["id"]] = entry

    misclassified = [r for r in results
                     if not r.get("parse_failed", False)
                     and r.get("pred_genuine") != r["gold_genuine"]]

    enriched = []
    for r in misclassified:
        entry = corpus.get(r["id"], {})
        enriched.append({
            **r,
            "claim_a": entry.get("claim_a", "")[:200],
            "claim_b": entry.get("claim_b", "")[:200],
            "error_type": (
                "FP" if r.get("pred_genuine") and not r["gold_genuine"]
                else "FN"
            ),
        })

    enriched.sort(key=lambda x: (0 if x["error_type"] == "FN" else 1, x["gold_type"]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for r in enriched:
            f.write(json.dumps(r) + "\n")

    fn_count = sum(1 for r in enriched if r["error_type"] == "FN")
    fp_count = sum(1 for r in enriched if r["error_type"] == "FP")
    log.info(
        "Error analysis saved: %d misclassified (FN=%d FP=%d) -> %s",
        len(enriched), fn_count, fp_count, output_path.name,
    )


# ── JSONL I/O ─────────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    """Load JSONL file, skipping blank lines."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(rows: list[dict], path: Path):
    """Write rows to JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def load_eval_results(eval_dir: Path) -> list[dict]:
    """Load eval_results.jsonl or fall back to checkpoint.jsonl.

    Used by compute_panel_agreement.py to load results from any eval directory.
    """
    results_path = eval_dir / "eval_results.jsonl"
    if results_path.exists():
        return load_jsonl(results_path)
    ckpt_path = eval_dir / "checkpoint.jsonl"
    if ckpt_path.exists():
        return list(load_checkpoint(ckpt_path).values())
    raise FileNotFoundError(f"No results found in {eval_dir}")
