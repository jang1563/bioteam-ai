#!/usr/bin/env python3
"""Download and manage benchmark data for W9 evaluation.

Dataset tiers:
  Tier 0 (query-only): No download needed — cancer_pathway, gtex_tissue_markers
  Tier 1 (fixture): No download needed — fixture_degs, fixture_vcf (use test fixtures)
  Tier 2 (small download): ~50MB — GenoTEX metadata (git sparse-checkout)
  Tier 3 (large/restricted): >1GB — MAQC, ClinVar (manual only)

Usage:
  python -m scripts.download_benchmark_data check     # Show status of all datasets
  python -m scripts.download_benchmark_data download   # Download Tier 2 datasets
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.benchmarks.datasets import BENCHMARK_DATASETS, BENCHMARK_SUITES


def _check_status() -> None:
    """Print status of all benchmark datasets."""
    print("=== Benchmark Dataset Status ===\n")

    for did, ds in BENCHMARK_DATASETS.items():
        if ds.is_query_only:
            status = "READY (query-only)"
        elif ds.data_manifest_path and Path(ds.data_manifest_path).exists():
            status = "READY (data present)"
        elif ds.data_manifest_path:
            status = f"MISSING ({ds.data_manifest_path})"
        else:
            status = "READY (no data needed)"
        print(f"  {did:25s}  {status}")

    print("\n=== Suites ===\n")
    for sid, dids in BENCHMARK_SUITES.items():
        ready = sum(
            1 for d in dids
            if d in BENCHMARK_DATASETS and (
                BENCHMARK_DATASETS[d].is_query_only
                or (BENCHMARK_DATASETS[d].data_manifest_path
                    and Path(BENCHMARK_DATASETS[d].data_manifest_path).exists())
                or not BENCHMARK_DATASETS[d].data_manifest_path
            )
        )
        print(f"  {sid:20s}  {ready}/{len(dids)} ready")

    # External adapters
    print("\n=== External Adapters ===\n")
    try:
        from app.benchmarks.adapters.bioagent_bench import BioAgentBenchAdapter
        adapter = BioAgentBenchAdapter()
        print(f"  bioagent_bench       READY ({len(adapter.list_tasks())} tasks, pre-defined)")
    except Exception as e:
        print(f"  bioagent_bench       ERROR: {e}")

    try:
        from app.benchmarks.adapters.genotex import GenoTEXAdapter
        adapter = GenoTEXAdapter()
        if adapter.is_available():
            tasks = adapter.list_tasks()
            print(f"  genotex              READY ({len(tasks)} tasks)")
        else:
            print("  genotex              NOT DOWNLOADED")
            print("    To download: git clone --depth 1 --filter=blob:none --sparse \\")
            print("      https://github.com/Liu-Hy/GenoTEX backend/data/benchmarks/external/genotex")
            print("    cd backend/data/benchmarks/external/genotex && git sparse-checkout set metadata output/regress")
    except Exception as e:
        print(f"  genotex              ERROR: {e}")


def _download() -> None:
    """Download Tier 2 benchmark data."""
    print("=== Downloading Tier 2 Benchmark Data ===\n")

    # GenoTEX
    print("[GenoTEX] Checking...")
    try:
        from app.benchmarks.adapters.genotex import GenoTEXAdapter
        adapter = GenoTEXAdapter()
        if adapter.is_available():
            print("[GenoTEX] Already present. Skipping.")
        else:
            print("[GenoTEX] Not found. Manual download required:")
            print("  git clone --depth 1 --filter=blob:none --sparse \\")
            print("    https://github.com/Liu-Hy/GenoTEX backend/data/benchmarks/external/genotex")
            print("  cd backend/data/benchmarks/external/genotex")
            print("  git sparse-checkout set metadata output/regress")
    except Exception as e:
        print(f"[GenoTEX] Error: {e}")

    # BioAgent Bench
    print("\n[BioAgent Bench] Pre-defined data (no download needed).")

    # Tier 3 instructions
    print("\n=== Tier 3 (Manual Download) ===\n")
    print("[MAQC] Download from GEO: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE5350")
    print("  Place in: backend/data/benchmarks/maqc_a_vs_b/")
    print("[ClinVar] Download from NCBI: https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/")
    print("  Place in: backend/data/benchmarks/clinvar_brca/")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage W9 benchmark data")
    parser.add_argument("command", choices=["check", "download", "status"],
                        help="check: show status, download: fetch Tier 2 data, status: alias for check")
    args = parser.parse_args()

    if args.command in ("check", "status"):
        _check_status()
    elif args.command == "download":
        _download()


if __name__ == "__main__":
    main()
