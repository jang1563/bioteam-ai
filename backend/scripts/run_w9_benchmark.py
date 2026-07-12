"""W9 Bioinformatics Benchmark CLI.

Runs the W9 evaluation pipeline:
  1. Load benchmark datasets (MAQC, ClinVar, GTEx, TCGA)
  2. Execute W9 on each dataset (quick/standard/deep mode)
  3. Score results against ground truth
  4. Save JSONL results for regression tracking

Usage:
    # Query-only datasets (no data needed, uses LLM knowledge)
    uv run python backend/scripts/run_w9_benchmark.py --query-only --mode quick

    # Single dataset
    uv run python backend/scripts/run_w9_benchmark.py --dataset cancer_pathway --mode quick

    # Full benchmark suite
    uv run python backend/scripts/run_w9_benchmark.py --suite core_bioinfo --mode quick

    # External benchmark (BioAgent Bench)
    uv run python backend/scripts/run_w9_benchmark.py --external bioagent_bench --mode quick

    # Compare two runs
    uv run python backend/scripts/run_w9_benchmark.py --compare run_a.json run_b.json

    # Show latest results
    uv run python backend/scripts/run_w9_benchmark.py --report-only --latest

    # Dry run (show what would execute without running)
    uv run python backend/scripts/run_w9_benchmark.py --suite ci_quick --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("w9_benchmark")

RUNS_DIR = Path(__file__).parent.parent / "data" / "w9_benchmark" / "runs"


def _ensure_dirs() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def _save_result(result_dict: dict) -> Path:
    """Save a benchmark result as JSONL."""
    _ensure_dirs()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    filename = f"{result_dict.get('dataset_id', 'unknown')}_{ts}.json"
    path = RUNS_DIR / filename
    path.write_text(json.dumps(result_dict, indent=2, default=str))
    logger.info("Saved result: %s", path)
    return path


def _load_latest_results(n: int = 10) -> list[dict]:
    """Load the most recent N result files."""
    _ensure_dirs()
    files = sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    results = []
    for f in files[:n]:
        try:
            results.append(json.loads(f.read_text()))
        except json.JSONDecodeError:
            logger.warning("Skipping invalid JSON: %s", f)
    return results


def _print_result(result: dict) -> None:
    """Pretty-print a benchmark result."""
    print(f"\n{'='*60}")
    print(f"Dataset:   {result.get('dataset_id', '?')}")
    print(f"Template:  {result.get('template', '?')}")
    print(f"Cost Mode: {result.get('cost_mode', '?')}")
    print(f"Run ID:    {result.get('run_id', '?')}")
    print(f"{'='*60}")
    print(f"  Gene Recall:       {result.get('gene_recall', 0):.3f}")
    print(f"  Gene Precision:    {result.get('gene_precision', 0):.3f}")
    print(f"  Gene F1:           {result.get('gene_f1', 0):.3f}")
    print(f"  Gene Jaccard:      {result.get('gene_jaccard', 0):.3f}")
    print(f"  Pathway Overlap:   {result.get('pathway_overlap', 0):.3f}")
    print(f"  Direction Accuracy:{result.get('direction_accuracy', 0):.3f}")
    print(f"  FC Correlation:    {result.get('fc_correlation', 0):.3f}")
    print(f"  Biology Score:     {result.get('biology_score', 0):.3f}{'  (fallback)' if result.get('is_biology_fallback') else ''}")
    print("  ---")
    print(f"  BioAgent Score:    {result.get('bioagent_score', 0):.3f}")
    print(f"  Cost:              ${result.get('total_cost_usd', 0):.2f}")
    print(f"  Runtime:           {result.get('runtime_seconds', 0):.1f}s")
    if result.get("fair_mode"):
        print("  Fair Mode:         YES (no hints, equal P/R)")

    # Grade
    score = result.get("bioagent_score", 0)
    if score >= 0.70:
        grade = "GOLD"
    elif score >= 0.50:
        grade = "SILVER"
    elif score >= 0.30:
        grade = "BRONZE"
    else:
        grade = "BELOW THRESHOLD"
    print(f"  Grade:             {grade}")

    # Published baseline comparison
    dataset_id = result.get("dataset_id", "")
    external = result.get("external_benchmark", "")
    lookup_id = external if external else dataset_id
    try:
        from app.benchmarks.baselines import format_baseline_comparison
        comparison = format_baseline_comparison(lookup_id, result)
        if comparison:
            print(comparison)
    except Exception:
        pass
    print()


def _print_comparison(comparison_dict: dict) -> None:
    """Pretty-print a comparison result."""
    print(f"\n{'='*60}")
    print(f"Comparison: {comparison_dict.get('run_a_id', '?')} → {comparison_dict.get('run_b_id', '?')}")
    print(f"Dataset:    {comparison_dict.get('dataset_id', '?')}")
    print(f"{'='*60}")

    deltas = comparison_dict.get("metric_deltas", {})
    for metric, delta in sorted(deltas.items()):
        arrow = "↑" if delta > 0 else "↓" if delta < 0 else "="
        print(f"  {metric:25s} {arrow} {delta:+.4f}")

    if comparison_dict.get("regression_detected"):
        print(f"\n  *** REGRESSION DETECTED in: {', '.join(comparison_dict.get('regression_metrics', []))}")
    else:
        print("\n  No regression detected.")

    improvements = comparison_dict.get("improvement_metrics", [])
    if improvements:
        print(f"  Improvements in: {', '.join(improvements)}")
    print()


async def cmd_run_dataset(args: argparse.Namespace) -> None:
    """Run benchmark on a single dataset."""
    from app.benchmarks.datasets import get_dataset
    from app.benchmarks.engine import BenchmarkEngine

    dataset = get_dataset(args.dataset)
    if not dataset:
        logger.error("Unknown dataset: %s", args.dataset)
        sys.exit(1)

    if getattr(args, "dry_run", False):
        print(f"[DRY RUN] Would run: {dataset.id} (template={args.template}, mode={args.mode})")
        print(f"  Query-only: {dataset.is_query_only}")
        print(f"  Expected genes: {len(dataset.expected_genes)}, pathways: {len(dataset.expected_pathways)}")
        return

    fair = getattr(args, "fair", False)
    engine = BenchmarkEngine()
    result = await engine.run_dataset(dataset, template=args.template, cost_mode=args.mode, fair=fair)

    result_dict = result.model_dump()
    _save_result(result_dict)
    _print_result(result_dict)


async def cmd_run_suite(args: argparse.Namespace) -> None:
    """Run benchmark on an entire suite."""
    from app.benchmarks.datasets import get_suite
    from app.benchmarks.engine import BenchmarkEngine

    datasets = get_suite(args.suite)
    if not datasets:
        logger.error("Unknown suite: %s", args.suite)
        sys.exit(1)

    if getattr(args, "dry_run", False):
        print(f"[DRY RUN] Suite '{args.suite}': {len(datasets)} datasets")
        for ds in datasets:
            qo = " (query-only)" if ds.is_query_only else ""
            print(f"  - {ds.id}{qo}: {len(ds.expected_genes)} genes, {len(ds.expected_pathways)} pathways")
        return

    fair = getattr(args, "fair", False)
    engine = BenchmarkEngine()
    results = await engine.run_suite(datasets, template=args.template, cost_mode=args.mode, fair=fair)

    for result in results:
        result_dict = result.model_dump()
        _save_result(result_dict)
        _print_result(result_dict)

    if results:
        avg_score = sum(r.bioagent_score for r in results) / len(results)
        total_cost = sum(r.total_cost_usd for r in results)
        mode_label = " (FAIR)" if fair else ""
        print(f"\nSuite Summary{mode_label}: avg BioAgent={avg_score:.3f}, total cost=${total_cost:.2f}")


async def cmd_query_only(args: argparse.Namespace) -> None:
    """Run all query-only datasets."""
    from app.benchmarks.engine import BenchmarkEngine

    if getattr(args, "dry_run", False):
        from app.benchmarks.datasets import BENCHMARK_DATASETS
        qo = [d for d in BENCHMARK_DATASETS.values() if d.is_query_only]
        print(f"[DRY RUN] Query-only: {len(qo)} datasets")
        for ds in qo:
            print(f"  - {ds.id}: {len(ds.expected_genes)} genes, {len(ds.expected_pathways)} pathways")
        return

    fair = getattr(args, "fair", False)
    engine = BenchmarkEngine()
    results = await engine.run_query_only(cost_mode=args.mode, fair=fair)

    for result in results:
        result_dict = result.model_dump()
        _save_result(result_dict)
        _print_result(result_dict)

    if results:
        avg_score = sum(r.bioagent_score for r in results) / len(results)
        mode_label = " (FAIR)" if fair else ""
        print(f"\nQuery-Only Summary{mode_label}: avg BioAgent={avg_score:.3f}")


async def cmd_external(args: argparse.Namespace) -> None:
    """Run external benchmark via adapter."""
    from app.benchmarks.engine import BenchmarkEngine

    adapters = {
        "bioagent_bench": "app.benchmarks.adapters.bioagent_bench.BioAgentBenchAdapter",
        "genotex": "app.benchmarks.adapters.genotex.GenoTEXAdapter",
    }

    adapter_path = adapters.get(args.external)
    if not adapter_path:
        logger.error("Unknown external benchmark: %s. Available: %s", args.external, list(adapters.keys()))
        sys.exit(1)

    # Dynamic import
    module_path, class_name = adapter_path.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    adapter = getattr(mod, class_name)()

    if getattr(args, "dry_run", False):
        tasks = adapter.list_tasks()
        print(f"[DRY RUN] External '{args.external}': {len(tasks)} tasks")
        for tid in tasks:
            ds = adapter.load_task(tid)
            print(f"  - {tid}: {len(ds.expected_genes)} genes, {len(ds.expected_pathways)} pathways")
        return

    if not adapter.is_available():
        logger.error("External benchmark '%s' data not available. Run download first.", args.external)
        sys.exit(1)

    fair = getattr(args, "fair", False)
    engine = BenchmarkEngine()
    results = await engine.run_external(adapter, cost_mode=args.mode, fair=fair)

    for result in results:
        result_dict = result.model_dump()
        _save_result(result_dict)
        _print_result(result_dict)
        if result.native_scores:
            print(f"  Native Scores: {result.native_scores}")


def cmd_compare(args: argparse.Namespace) -> None:
    """Compare two run result files."""
    from app.benchmarks.engine import BenchmarkEngine
    from app.benchmarks.models import BenchmarkResult

    try:
        run_a_data = json.loads(Path(args.compare[0]).read_text())
        run_b_data = json.loads(Path(args.compare[1]).read_text())
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error("Cannot load run files: %s", e)
        sys.exit(1)

    run_a = BenchmarkResult(**run_a_data)
    run_b = BenchmarkResult(**run_b_data)

    comparison = BenchmarkEngine.compare_runs(run_a, run_b)
    _print_comparison(comparison.model_dump())


def cmd_report(args: argparse.Namespace) -> None:
    """Show latest benchmark results."""
    results = _load_latest_results(args.latest_n or 10)
    if not results:
        print("No benchmark results found.")
        return

    for result in results:
        _print_result(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="W9 Bioinformatics Benchmark CLI")
    subparsers = parser.add_subparsers(dest="command")

    # Run single dataset
    run_parser = subparsers.add_parser("run", help="Run benchmark on a dataset")
    run_parser.add_argument("--dataset", required=True, help="Dataset ID (e.g. cancer_pathway)")
    run_parser.add_argument("--mode", default="quick", choices=["quick", "standard", "deep"])
    run_parser.add_argument("--template", default="multi_omics")
    run_parser.add_argument("--dry-run", action="store_true", help="Show what would run without executing")
    run_parser.add_argument("--fair", action="store_true", help="Fair mode: no domain hints, equal P/R weights")

    # Run suite
    suite_parser = subparsers.add_parser("suite", help="Run benchmark suite")
    suite_parser.add_argument("--suite", required=True, help="Suite ID (e.g. ci_quick, query_only)")
    suite_parser.add_argument("--mode", default="quick", choices=["quick", "standard", "deep"])
    suite_parser.add_argument("--template", default="multi_omics")
    suite_parser.add_argument("--dry-run", action="store_true")
    suite_parser.add_argument("--fair", action="store_true", help="Fair mode: no domain hints, equal P/R weights")

    # Query-only
    qo_parser = subparsers.add_parser("query-only", help="Run all query-only datasets")
    qo_parser.add_argument("--mode", default="quick", choices=["quick", "standard", "deep"])
    qo_parser.add_argument("--dry-run", action="store_true")
    qo_parser.add_argument("--fair", action="store_true", help="Fair mode: no domain hints, equal P/R weights")

    # External benchmark
    ext_parser = subparsers.add_parser("external", help="Run external benchmark")
    ext_parser.add_argument("--benchmark", dest="external", required=True,
                            choices=["bioagent_bench", "genotex"], help="External benchmark name")
    ext_parser.add_argument("--mode", default="quick", choices=["quick", "standard", "deep"])
    ext_parser.add_argument("--dry-run", action="store_true")
    ext_parser.add_argument("--fair", action="store_true", help="Fair mode: no domain hints, equal P/R weights")

    # Compare
    compare_parser = subparsers.add_parser("compare", help="Compare two runs")
    compare_parser.add_argument("files", nargs=2, metavar="FILE", help="Two JSON result files")

    # Report
    report_parser = subparsers.add_parser("report", help="Show latest results")
    report_parser.add_argument("-n", "--latest-n", type=int, default=10, help="Number of results")

    # Legacy flat argument support
    parser.add_argument("--dataset", help="Dataset ID")
    parser.add_argument("--mode", default="quick", choices=["quick", "standard", "deep"])
    parser.add_argument("--template", default="multi_omics")
    parser.add_argument("--suite", help="Suite ID")
    parser.add_argument("--query-only", action="store_true", dest="query_only")
    parser.add_argument("--external", help="External benchmark name")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    parser.add_argument("--fair", action="store_true", dest="fair", help="Fair mode: no domain hints, equal P/R weights")
    parser.add_argument("--compare", nargs=2, metavar="FILE", help="Compare two result files")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--latest", action="store_true")

    args = parser.parse_args()

    # Handle subcommands and legacy flat arguments
    if args.command:
        if args.command == "run":
            asyncio.run(cmd_run_dataset(args))
        elif args.command == "suite":
            asyncio.run(cmd_run_suite(args))
        elif args.command == "query-only":
            asyncio.run(cmd_query_only(args))
        elif args.command == "external":
            asyncio.run(cmd_external(args))
        elif args.command == "compare":
            args.compare = args.files
            cmd_compare(args)
        elif args.command == "report":
            cmd_report(args)
    elif args.report_only or args.latest:
        args.latest_n = 10
        cmd_report(args)
    elif args.compare:
        cmd_compare(args)
    elif getattr(args, "query_only", False):
        asyncio.run(cmd_query_only(args))
    elif getattr(args, "external", None):
        asyncio.run(cmd_external(args))
    elif args.suite:
        asyncio.run(cmd_run_suite(args))
    elif args.dataset:
        asyncio.run(cmd_run_dataset(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
