#!/usr/bin/env python3
"""
compute_panel_agreement.py — Multi-model panel agreement analysis

Loads evaluation results from multiple models and computes inter-rater
reliability metrics to assess corpus quality without manual scoring.

Metrics computed:
  - Pairwise Cohen's kappa (binary + 5-way type)
  - Fleiss' kappa (multi-rater, binary)
  - Krippendorff's alpha (handles missing data from parse failures)
  - Majority-vote consensus labels
  - Disagreement identification for selective manual review

Based on the Panel of LLM Evaluators (PoLL) approach
(Verga et al. 2024, arXiv:2404.18796).

Usage:
  python compute_panel_agreement.py \\
    --eval-dirs output/v3/eval \\
                output/v3/eval_gpt4nano_baseline \\
                output/v3/eval_deepseek_baseline \\
                output/v3/eval_llama4scout_baseline \\
    --labels "Gemini" "GPT-4.1 nano" "DeepSeek V3.2" "Llama 4 Scout" \\
    --out-dir output/v3/panel_agreement

  python compute_panel_agreement.py \\
    --eval-dirs output/v3/eval output/v3/eval_gpt4nano_baseline \\
    --labels "Gemini" "GPT-4.1 nano" \\
    --out-dir output/v3/panel_2model
"""
from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np
from eval_common import (
    load_eval_results,
    load_jsonl,
    write_jsonl,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
log = logging.getLogger(__name__)


# ── Data loading ─────────────────────────────────────────────────────────────

def load_panel_data(
    eval_dirs: list[Path],
    labels: list[str],
) -> tuple[dict[str, dict], set[str]]:
    """Load results from each model, align by entry ID.

    Returns:
        panel: {entry_id: {label: result_row, ...}, ...}
        all_ids: set of all entry IDs across all models
    """
    panel: dict[str, dict] = {}
    all_ids: set[str] = set()

    for eval_dir, label in zip(eval_dirs, labels):
        results = load_eval_results(eval_dir)
        log.info("Loaded %d results from %s (%s)", len(results), eval_dir.name, label)

        for r in results:
            eid = r["id"]
            all_ids.add(eid)
            if eid not in panel:
                panel[eid] = {}
            panel[eid][label] = r

    return panel, all_ids


# ── Pairwise Cohen's kappa ──────────────────────────────────────────────────

def _cohen_kappa(y1: list, y2: list) -> float:
    """Compute Cohen's kappa manually (avoids hard sklearn dependency for this)."""
    assert len(y1) == len(y2)
    n = len(y1)
    if n == 0:
        return 0.0

    categories = sorted(set(y1) | set(y2))
    cat_idx = {c: i for i, c in enumerate(categories)}
    k = len(categories)

    # Confusion matrix
    conf = [[0] * k for _ in range(k)]
    for a, b in zip(y1, y2):
        conf[cat_idx[a]][cat_idx[b]] += 1

    po = sum(conf[i][i] for i in range(k)) / n  # observed agreement

    row_sums = [sum(conf[i]) for i in range(k)]
    col_sums = [sum(conf[j][i] for j in range(k)) for i in range(k)]
    pe = sum(row_sums[i] * col_sums[i] for i in range(k)) / (n * n)  # expected

    if pe == 1.0:
        return 1.0
    return (po - pe) / (1.0 - pe)


def compute_pairwise_kappa(
    panel: dict[str, dict],
    labels: list[str],
    task: str = "binary",
) -> dict[str, float]:
    """Compute Cohen's kappa for every pair of models.

    task="binary": genuine (True/False)
    task="type": 5-way classification
    """
    kappas = {}
    for l1, l2 in combinations(labels, 2):
        y1, y2 = [], []
        for eid, model_results in panel.items():
            r1 = model_results.get(l1)
            r2 = model_results.get(l2)
            if not r1 or not r2:
                continue
            if r1.get("parse_failed") or r2.get("parse_failed"):
                continue

            if task == "binary":
                y1.append(r1.get("pred_genuine", False))
                y2.append(r2.get("pred_genuine", False))
            elif task == "type":
                y1.append(r1.get("pred_type", "contextual"))
                y2.append(r2.get("pred_type", "contextual"))

        pair_key = f"{l1} vs {l2}"
        if len(y1) >= 2:
            kappas[pair_key] = round(_cohen_kappa(y1, y2), 3)
        else:
            kappas[pair_key] = None
            log.warning("Insufficient data for %s", pair_key)

    return kappas


# ── Fleiss' kappa ────────────────────────────────────────────────────────────

def compute_fleiss_kappa(
    panel: dict[str, dict],
    labels: list[str],
) -> float | None:
    """Compute Fleiss' kappa for binary classification across all models.

    Only includes entries where ALL models have valid (non-failed) predictions.
    """
    n_raters = len(labels)
    categories = [True, False]  # genuine, contextual

    # Build rating matrix: rows=items, columns=categories, values=count of raters
    matrix = []
    for eid, model_results in panel.items():
        votes = []
        all_valid = True
        for label in labels:
            r = model_results.get(label)
            if not r or r.get("parse_failed"):
                all_valid = False
                break
            votes.append(r.get("pred_genuine", False))

        if not all_valid:
            continue

        row = [votes.count(True), votes.count(False)]
        matrix.append(row)

    if not matrix:
        return None

    N = len(matrix)  # number of items
    n = n_raters
    k = len(categories)

    # Compute P_i for each item
    p_i_sum = 0.0
    for row in matrix:
        p_i_sum += sum(r * r for r in row)
    p_bar = (1.0 / (N * n * (n - 1))) * (p_i_sum - N * n)

    # Compute P_j for each category
    col_sums = [sum(row[j] for row in matrix) for j in range(k)]
    p_e = sum((s / (N * n)) ** 2 for s in col_sums)

    if p_e == 1.0:
        return 1.0
    return round((p_bar - p_e) / (1.0 - p_e), 3)


# ── Krippendorff's alpha ────────────────────────────────────────────────────

def compute_krippendorff_alpha(
    panel: dict[str, dict],
    labels: list[str],
    task: str = "binary",
) -> float | None:
    """Compute Krippendorff's alpha. Handles missing data (parse failures).

    Falls back to manual computation if krippendorff package not available.
    """
    # Build reliability matrix: rows=models, columns=entries
    entry_ids = sorted(panel.keys())
    n_models = len(labels)
    n_items = len(entry_ids)

    reliability_data = np.full((n_models, n_items), np.nan)

    for j, eid in enumerate(entry_ids):
        for i, label in enumerate(labels):
            r = panel[eid].get(label)
            if not r or r.get("parse_failed"):
                continue
            if task == "binary":
                reliability_data[i, j] = 1.0 if r.get("pred_genuine") else 0.0
            elif task == "type":
                type_map = {"direct": 0, "temporal": 1, "magnitude": 2, "methodological": 3, "contextual": 4}
                pred_type = r.get("pred_type", "contextual")
                reliability_data[i, j] = type_map.get(pred_type, 4)

    try:
        import krippendorff
        level = "nominal"
        alpha = krippendorff.alpha(reliability_data=reliability_data, level_of_measurement=level)
        return round(alpha, 3)
    except ImportError:
        log.warning("krippendorff package not installed — computing alpha manually")
        return _krippendorff_alpha_manual(reliability_data)


def _krippendorff_alpha_manual(data: np.ndarray) -> float | None:
    """Manual Krippendorff's alpha for nominal data.

    data: shape (n_coders, n_items), NaN for missing.
    """
    n_coders, n_items = data.shape

    # Collect all paired values per item
    D_o = 0.0  # observed disagreement
    total_pairs = 0
    value_counts: Counter = Counter()

    for j in range(n_items):
        col = data[:, j]
        valid = col[~np.isnan(col)]
        m = len(valid)
        if m < 2:
            continue

        n_pairs = m * (m - 1)
        total_pairs += n_pairs

        # Count disagreements within this item
        for a in range(len(valid)):
            for b in range(a + 1, len(valid)):
                if valid[a] != valid[b]:
                    D_o += 2  # each pair counted once, multiplied by 2

        for v in valid:
            value_counts[v] += 1

    if total_pairs == 0:
        return None

    D_o /= total_pairs

    # Expected disagreement
    total_values = sum(value_counts.values())
    D_e = 1.0 - sum(n * (n - 1) for n in value_counts.values()) / (total_values * (total_values - 1))

    if D_e == 0:
        return 1.0
    return round(1.0 - D_o / D_e, 3)


# ── Majority vote consensus ─────────────────────────────────────────────────

def compute_consensus(
    panel: dict[str, dict],
    labels: list[str],
    corpus_path: Path | None = None,
) -> list[dict]:
    """Compute majority-vote consensus for binary and type classification.

    Returns list of dicts with consensus labels + agreement metadata.
    """
    corpus_lookup = {}
    if corpus_path and corpus_path.exists():
        corpus_lookup = {e["id"]: e for e in load_jsonl(corpus_path)}

    results = []
    for eid in sorted(panel.keys()):
        model_results = panel[eid]

        # Collect valid votes
        genuine_votes = []
        type_votes = []
        model_preds = {}

        for label in labels:
            r = model_results.get(label)
            if not r or r.get("parse_failed"):
                model_preds[label] = {"genuine": None, "type": None}
                continue
            g = r.get("pred_genuine", False)
            t = r.get("pred_type", "contextual")
            genuine_votes.append(g)
            type_votes.append(t)
            model_preds[label] = {"genuine": g, "type": t}

        n_valid = len(genuine_votes)
        if n_valid == 0:
            continue

        # Binary consensus
        n_genuine = sum(1 for v in genuine_votes if v)
        n_contextual = n_valid - n_genuine

        consensus_genuine = n_genuine > n_contextual
        if n_genuine == n_contextual:
            # Tie — default to contextual (conservative); avoids gold-label bias
            consensus_genuine = False

        # Agreement level
        majority_size = max(n_genuine, n_contextual)
        if majority_size == n_valid:
            agreement = "unanimous"
        elif n_genuine == n_contextual:
            agreement = "split"
        elif n_valid >= 4 and majority_size >= n_valid * 0.75:
            agreement = "strong_majority"
        else:
            agreement = "majority"

        # Type consensus (among genuine-voting models only)
        genuine_type_votes = [t for g, t in zip(genuine_votes, type_votes) if g]
        if genuine_type_votes:
            type_counter = Counter(genuine_type_votes)
            consensus_type = type_counter.most_common(1)[0][0]
        else:
            consensus_type = "contextual"

        gold_genuine = None
        gold_type = None
        for label in labels:
            r = model_results.get(label, {})
            if r.get("gold_genuine") is not None:
                gold_genuine = r.get("gold_genuine")
                gold_type = r.get("gold_type")
                break

        row = {
            "id": eid,
            "gold_genuine": gold_genuine,
            "gold_type": gold_type,
            "consensus_genuine": consensus_genuine,
            "consensus_type": consensus_type,
            "vote_genuine_count": n_genuine,
            "vote_contextual_count": n_contextual,
            "n_valid_models": n_valid,
            "agreement_level": agreement,
            "differs_from_gold": (
                consensus_genuine != gold_genuine if gold_genuine is not None else None
            ),
            "model_predictions": model_preds,
        }

        # Add claim text if available
        corpus_entry = corpus_lookup.get(eid, {})
        if corpus_entry:
            row["claim_a"] = corpus_entry.get("claim_a", "")[:200]
            row["claim_b"] = corpus_entry.get("claim_b", "")[:200]
            row["domain"] = corpus_entry.get("domain", "")

        results.append(row)

    return results


# ── Disagreement identification ──────────────────────────────────────────────

def identify_disagreements(consensus: list[dict]) -> list[dict]:
    """Find entries needing manual review:
    1. Split votes (2:2 or similar)
    2. Consensus differs from gold label
    """
    disagreements = []
    for row in consensus:
        needs_review = False
        reasons = []

        if row["agreement_level"] == "split":
            needs_review = True
            reasons.append("split_vote")

        if row.get("differs_from_gold"):
            needs_review = True
            reasons.append("consensus_vs_gold_mismatch")

        if needs_review:
            disagreements.append({**row, "review_reasons": reasons})

    disagreements.sort(key=lambda x: (
        0 if "split_vote" in x["review_reasons"] else 1,
        x.get("gold_type", ""),
    ))
    return disagreements


# ── Report generation ────────────────────────────────────────────────────────

def generate_report(
    panel: dict[str, dict],
    labels: list[str],
    consensus: list[dict],
    disagreements: list[dict],
) -> dict:
    """Generate comprehensive panel agreement report."""
    # Binary metrics
    binary_pairwise = compute_pairwise_kappa(panel, labels, task="binary")
    binary_fleiss = compute_fleiss_kappa(panel, labels)
    binary_alpha = compute_krippendorff_alpha(panel, labels, task="binary")

    # Type metrics
    type_pairwise = compute_pairwise_kappa(panel, labels, task="type")
    type_alpha = compute_krippendorff_alpha(panel, labels, task="type")

    # Agreement counts
    agreement_counts = Counter(c["agreement_level"] for c in consensus)
    consensus_vs_gold = sum(1 for c in consensus if c.get("differs_from_gold") is False)
    gold_differs = sum(1 for c in consensus if c.get("differs_from_gold") is True)

    # Per-model parse failure rate
    model_stats = {}
    for label in labels:
        total = 0
        failed = 0
        for eid, mr in panel.items():
            r = mr.get(label)
            if r:
                total += 1
                if r.get("parse_failed"):
                    failed += 1
        model_stats[label] = {
            "total": total,
            "parse_failed": failed,
            "parse_failure_rate": round(failed / max(1, total), 3),
        }

    # Per-model binary P/R/F1 (vs gold)
    for label in labels:
        tp = fp = fn = tn = 0
        for eid, mr in panel.items():
            r = mr.get(label)
            if not r or r.get("parse_failed"):
                continue
            pg = r.get("pred_genuine", False)
            gg = r.get("gold_genuine", False)
            if pg and gg:
                tp += 1
            elif pg and not gg:
                fp += 1
            elif not pg and gg:
                fn += 1
            else:
                tn += 1
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rc = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * p * rc / (p + rc) if (p + rc) > 0 else 0.0
        model_stats[label].update({
            "precision": round(p, 3),
            "recall": round(rc, 3),
            "f1": round(f1, 3),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        })

    # Quality assessment
    alpha_met = binary_alpha is not None and binary_alpha >= 0.80
    manual_needed = not alpha_met or agreement_counts.get("split", 0) > len(consensus) * 0.10

    report = {
        "panel_size": len(labels),
        "models": labels,
        "corpus_entries": len(panel),
        "entries_with_all_models_valid": sum(
            1 for c in consensus if c["n_valid_models"] == len(labels)
        ),

        "binary_agreement": {
            "fleiss_kappa": binary_fleiss,
            "krippendorff_alpha": binary_alpha,
            "pairwise_kappa": binary_pairwise,
        },

        "type_agreement": {
            "krippendorff_alpha": type_alpha,
            "pairwise_kappa": type_pairwise,
        },

        "agreement_distribution": dict(agreement_counts),

        "consensus_vs_gold": {
            "match_count": consensus_vs_gold,
            "mismatch_count": gold_differs,
            "match_rate": round(consensus_vs_gold / max(1, consensus_vs_gold + gold_differs), 3),
        },

        "model_stats": model_stats,

        "quality_assessment": {
            "binary_alpha": binary_alpha,
            "alpha_threshold_met": alpha_met,
            "manual_review_needed": manual_needed,
            "manual_review_count": len(disagreements),
            "interpretation": (
                "Gold-standard quality — no manual review needed"
                if alpha_met
                else "Review recommended for disagreement entries"
                if binary_alpha and binary_alpha >= 0.667
                else "Corpus quality uncertain — broader review recommended"
            ),
        },
    }

    return report


def print_summary(report: dict):
    """Print human-readable summary to stdout."""
    SEP = "=" * 70

    print(f"\n{SEP}")
    print(f"PANEL AGREEMENT REPORT — {report['panel_size']} models, {report['corpus_entries']} entries")
    print(SEP)

    print("\n[Models]")
    for label, stats in report["model_stats"].items():
        print(
            f"  {label:<25}  P={stats['precision']:.3f}  R={stats['recall']:.3f}  "
            f"F1={stats['f1']:.3f}  fail={stats['parse_failure_rate']:.1%}"
        )

    ba = report["binary_agreement"]
    print("\n[Binary Agreement]  genuine vs contextual")
    print(f"  Fleiss' kappa          : {ba['fleiss_kappa']}")
    print(f"  Krippendorff's alpha   : {ba['krippendorff_alpha']}")
    print("  Pairwise Cohen's kappa :")
    for pair, k in ba["pairwise_kappa"].items():
        bar = "#" * int((k or 0) * 20)
        print(f"    {pair:<40}  {k}  {bar}")

    ta = report["type_agreement"]
    print("\n[Type Agreement]  5-way classification")
    print(f"  Krippendorff's alpha   : {ta['krippendorff_alpha']}")
    print("  Pairwise Cohen's kappa :")
    for pair, k in ta["pairwise_kappa"].items():
        bar = "#" * int((k or 0) * 20)
        print(f"    {pair:<40}  {k}  {bar}")

    ad = report["agreement_distribution"]
    print("\n[Agreement Distribution]")
    for level in ["unanimous", "strong_majority", "majority", "split"]:
        count = ad.get(level, 0)
        total_with_consensus = sum(report["agreement_distribution"].get(lv, 0) for lv in ["unanimous", "strong_majority", "majority", "split"])
        pct = count / max(1, total_with_consensus) * 100
        print(f"  {level:<20}  {count:>4}  ({pct:.1f}%)")

    cvg = report["consensus_vs_gold"]
    print("\n[Consensus vs Gold Labels]")
    print(f"  Match rate             : {cvg['match_rate']:.1%}  ({cvg['match_count']}/{cvg['match_count'] + cvg['mismatch_count']})")
    print(f"  Gold entries to review : {cvg['mismatch_count']}")

    qa = report["quality_assessment"]
    print("\n[Quality Assessment]")
    print(f"  Binary alpha           : {qa['binary_alpha']}")
    print(f"  Threshold met (>=0.80) : {'YES' if qa['alpha_threshold_met'] else 'NO'}")
    print(f"  Manual review needed   : {'YES' if qa['manual_review_needed'] else 'NO'}")
    print(f"  Entries for review     : {qa['manual_review_count']}")
    print(f"  Interpretation         : {qa['interpretation']}")
    print(SEP)


# ── Comparison table ─────────────────────────────────────────────────────────

def write_comparison_table(report: dict, out_path: Path):
    """Write human-readable comparison table."""
    lines = []
    lines.append("=" * 90)
    lines.append("MULTI-MODEL COMPARISON TABLE")
    lines.append("=" * 90)
    lines.append("")
    lines.append(f"{'Model':<25}  {'P':>6}  {'R':>6}  {'F1':>6}  {'TP':>4}  {'FP':>4}  {'FN':>4}  {'TN':>4}  {'Fail%':>6}")
    lines.append(f"{'-'*25}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*4}  {'-'*4}  {'-'*4}  {'-'*4}  {'-'*6}")

    for label, stats in report["model_stats"].items():
        lines.append(
            f"{label:<25}  {stats['precision']:>6.3f}  {stats['recall']:>6.3f}  "
            f"{stats['f1']:>6.3f}  {stats['tp']:>4}  {stats['fp']:>4}  "
            f"{stats['fn']:>4}  {stats['tn']:>4}  {stats['parse_failure_rate']:>5.1%}"
        )

    lines.append("")
    lines.append(f"Binary Fleiss' kappa     : {report['binary_agreement']['fleiss_kappa']}")
    lines.append(f"Binary Krippendorff's α  : {report['binary_agreement']['krippendorff_alpha']}")
    lines.append(f"Type Krippendorff's α    : {report['type_agreement']['krippendorff_alpha']}")
    lines.append("")
    lines.append(f"Quality: {report['quality_assessment']['interpretation']}")
    lines.append("=" * 90)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Multi-model panel agreement analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--eval-dirs", nargs="+", type=Path, required=True,
        help="Evaluation result directories (one per model)",
    )
    parser.add_argument(
        "--labels", nargs="+", required=True,
        help="Model labels (same order as --eval-dirs)",
    )
    parser.add_argument(
        "--corpus", type=Path, default=None,
        help="Corpus JSONL for claim text enrichment in disagreement report",
    )
    parser.add_argument(
        "--out-dir", type=Path,
        default=Path(__file__).parent / "output" / "v3" / "panel_agreement",
    )
    args = parser.parse_args()

    if len(args.eval_dirs) != len(args.labels):
        raise ValueError("Number of --eval-dirs must match --labels")
    if len(args.eval_dirs) < 2:
        raise ValueError("Need at least 2 models for agreement analysis")

    # Resolve corpus path
    corpus_path = args.corpus
    if not corpus_path:
        # Try to find corpus_final.jsonl in default location
        default = Path(__file__).parent / "output" / "v3" / "corpus_final.jsonl"
        if default.exists():
            corpus_path = default

    # Load panel data
    panel, all_ids = load_panel_data(args.eval_dirs, args.labels)
    log.info("Panel: %d models, %d unique entries", len(args.labels), len(all_ids))

    # Compute consensus
    consensus = compute_consensus(panel, args.labels, corpus_path)
    log.info("Consensus computed for %d entries", len(consensus))

    # Identify disagreements
    disagreements = identify_disagreements(consensus)
    log.info("Disagreements: %d entries need review", len(disagreements))

    # Generate report
    report = generate_report(panel, args.labels, consensus, disagreements)

    # Print summary
    print_summary(report)

    # Save outputs
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "panel_agreement_report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)

    write_jsonl(consensus, out_dir / "consensus_labels.jsonl")
    write_jsonl(disagreements, out_dir / "disagreement_entries.jsonl")
    write_comparison_table(report, out_dir / "comparison_table.txt")

    log.info("Report    -> %s", out_dir / "panel_agreement_report.json")
    log.info("Consensus -> %s", out_dir / "consensus_labels.jsonl")
    log.info("Disagree  -> %s", out_dir / "disagreement_entries.jsonl")
    log.info("Table     -> %s", out_dir / "comparison_table.txt")


if __name__ == "__main__":
    main()
