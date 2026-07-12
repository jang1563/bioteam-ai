#!/usr/bin/env python3
"""RCMXT Calibration Script — Phase B: LLM Calibration.

Scores all 150 benchmark claims using the LLM-based RCMXT scorer
and computes calibration metrics against expert-annotated expected scores.

Requires ANTHROPIC_API_KEY in environment. Costs ~$6 per full run (5 repetitions).

Usage:
    python -m scripts.run_rcmxt_calibration
    python -m scripts.run_rcmxt_calibration --runs 1 --output results/calibration.json
    python -m scripts.run_rcmxt_calibration --mode hybrid

Targets (plan_v4.md Phase B):
    - ICC(2,1) >= 0.7 per axis (LLM vs expert consensus)
    - Intra-run std < 0.15 per axis
    - MAE < 0.15 vs expert consensus
    - No systematic bias > 0.1 (Bland-Altman)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.engines.rcmxt_scorer import RCMXTScorer
from app.llm.layer import LLMLayer

BENCHMARKS_DIR = Path(__file__).parent.parent / "app" / "cold_start" / "benchmarks"


def load_benchmark() -> dict:
    """Load the 150-claim benchmark file."""
    path = BENCHMARKS_DIR / "rcmxt_150_claims.json"
    if not path.exists():
        print(f"ERROR: Benchmark file not found: {path}")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def compute_mae(predicted: list[float], expected: list[float]) -> float:
    """Mean absolute error."""
    assert len(predicted) == len(expected)
    return sum(abs(p - e) for p, e in zip(predicted, expected)) / len(predicted)


def compute_pearson(x: list[float], y: list[float]) -> float:
    """Pearson correlation coefficient."""
    n = len(x)
    if n < 3:
        return 0.0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    std_x = (sum((xi - mean_x) ** 2 for xi in x)) ** 0.5
    std_y = (sum((yi - mean_y) ** 2 for yi in y)) ** 0.5
    if std_x == 0 or std_y == 0:
        return 0.0
    return cov / (std_x * std_y)


def compute_intra_run_std(all_runs: list[list[float]]) -> float:
    """Mean standard deviation across runs for each claim."""
    n_claims = len(all_runs[0])
    stds = []
    for i in range(n_claims):
        claim_scores = [run[i] for run in all_runs]
        if len(claim_scores) > 1:
            stds.append(statistics.stdev(claim_scores))
    return statistics.mean(stds) if stds else 0.0


async def run_calibration(
    benchmark: dict,
    n_runs: int = 5,
    mode: str = "llm",
) -> dict:
    """Run the full calibration protocol.

    Args:
        benchmark: Loaded 150-claim benchmark data.
        n_runs: Number of repetitions per claim.
        mode: Scoring mode ("llm" or "hybrid").

    Returns:
        Calibration results dict with per-axis metrics.
    """
    llm = LLMLayer()
    claims = benchmark["claims"]
    n_claims = len(claims)

    axes = ["R", "C", "M", "T"]
    # Track per-axis scores across runs
    all_runs: dict[str, list[list[float]]] = {a: [] for a in axes}
    x_runs: list[list[float | None]] = []

    print(f"\nRunning {n_runs} calibration runs on {n_claims} claims (mode={mode})...")
    total_cost = 0.0

    for run_idx in range(n_runs):
        print(f"\n--- Run {run_idx + 1}/{n_runs} ---")
        scorer = RCMXTScorer(mode=mode, llm_layer=llm)
        run_scores: dict[str, list[float]] = {a: [] for a in axes}
        run_x: list[float | None] = []

        for i, claim in enumerate(claims):
            if (i + 1) % 25 == 0:
                print(f"  Scored {i + 1}/{n_claims}...")

            score, llm_resp = await scorer.score_benchmark_claim(
                claim["claim"], claim["domain"]
            )
            total_cost += 0.008  # Approximate per-claim cost

            for axis in axes:
                run_scores[axis].append(getattr(score, axis))
            run_x.append(score.X)

        for axis in axes:
            all_runs[axis].append(run_scores[axis])
        x_runs.append(run_x)

    # Compute metrics
    print("\n--- Computing calibration metrics ---")
    results: dict = {
        "metadata": {
            "n_claims": n_claims,
            "n_runs": n_runs,
            "mode": mode,
            "total_cost_estimate": round(total_cost, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "axes": {},
    }

    for axis in axes:
        expected = [c[f"expected_{axis}"] for c in claims]
        # Use first run for primary metrics
        predicted = all_runs[axis][0]

        mae = compute_mae(predicted, expected)
        pearson = compute_pearson(predicted, expected)
        intra_std = compute_intra_run_std(all_runs[axis]) if n_runs > 1 else 0.0
        bias = statistics.mean(predicted) - statistics.mean(expected)

        results["axes"][axis] = {
            "mae": round(mae, 4),
            "pearson": round(pearson, 4),
            "intra_run_std": round(intra_std, 4),
            "bias": round(bias, 4),
            "mean_predicted": round(statistics.mean(predicted), 4),
            "mean_expected": round(statistics.mean(expected), 4),
            "pass_mae": mae < 0.15,
            "pass_intra_std": intra_std < 0.15,
            "pass_bias": abs(bias) < 0.10,
        }

    # X-axis (only for claims where expected_X is not None)
    x_claims_idx = [i for i, c in enumerate(claims) if c["expected_X"] is not None]
    if x_claims_idx:
        x_expected = [claims[i]["expected_X"] for i in x_claims_idx]
        x_predicted = [x_runs[0][i] for i in x_claims_idx if x_runs[0][i] is not None]
        if len(x_predicted) == len(x_expected):
            x_mae = compute_mae(x_predicted, x_expected)
            x_pearson = compute_pearson(x_predicted, x_expected)
            results["axes"]["X"] = {
                "mae": round(x_mae, 4),
                "pearson": round(x_pearson, 4),
                "n_claims_with_x": len(x_claims_idx),
                "pass_mae": x_mae < 0.15,
            }

    # Per-domain breakdown
    results["domains"] = {}
    for domain in ("spaceflight_biology", "cancer_genomics", "neuroscience"):
        domain_idx = [i for i, c in enumerate(claims) if c["domain"] == domain]
        domain_results: dict = {}
        for axis in axes:
            expected = [claims[i][f"expected_{axis}"] for i in domain_idx]
            predicted = [all_runs[axis][0][i] for i in domain_idx]
            domain_results[axis] = {
                "mae": round(compute_mae(predicted, expected), 4),
                "pearson": round(compute_pearson(predicted, expected), 4),
            }
        results["domains"][domain] = domain_results

    return results


def print_report(results: dict) -> None:
    """Print a formatted calibration report."""
    print("\n" + "=" * 60)
    print("RCMXT CALIBRATION REPORT")
    print("=" * 60)
    meta = results["metadata"]
    print(f"Claims: {meta['n_claims']} | Runs: {meta['n_runs']} | Mode: {meta['mode']}")
    print(f"Estimated cost: ${meta['total_cost_estimate']:.2f}")
    print(f"Timestamp: {meta['timestamp']}")

    print("\n--- Per-Axis Results ---")
    print(f"{'Axis':<6} {'MAE':<8} {'Pearson':<10} {'IntraStd':<10} {'Bias':<8} {'Pass?'}")
    print("-" * 50)

    for axis in ("R", "C", "M", "T", "X"):
        if axis not in results["axes"]:
            continue
        r = results["axes"][axis]
        pass_all = r.get("pass_mae", False) and r.get("pass_intra_std", True) and r.get("pass_bias", True)
        print(
            f"{axis:<6} {r['mae']:<8.4f} {r['pearson']:<10.4f} "
            f"{r.get('intra_run_std', 'N/A'):<10} {r.get('bias', 'N/A'):<8} "
            f"{'PASS' if pass_all else 'FAIL'}"
        )

    print("\n--- Per-Domain MAE ---")
    for domain, dr in results.get("domains", {}).items():
        print(f"\n  {domain}:")
        for axis, vals in dr.items():
            print(f"    {axis}: MAE={vals['mae']:.4f}, r={vals['pearson']:.4f}")

    overall_pass = all(
        results["axes"][a].get("pass_mae", False)
        for a in ("R", "C", "M", "T")
    )
    print(f"\n{'=' * 60}")
    print(f"OVERALL: {'PASS' if overall_pass else 'FAIL'} (target: MAE < 0.15 per axis)")
    print(f"{'=' * 60}")


async def main():
    parser = argparse.ArgumentParser(description="RCMXT Calibration Script")
    parser.add_argument("--runs", type=int, default=5, help="Number of repetitions per claim")
    parser.add_argument("--mode", default="llm", choices=["llm", "hybrid"], help="Scoring mode")
    parser.add_argument("--output", type=str, default=None, help="Output JSON file path")
    args = parser.parse_args()

    benchmark = load_benchmark()
    results = await run_calibration(benchmark, n_runs=args.runs, mode=args.mode)
    print_report(results)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
