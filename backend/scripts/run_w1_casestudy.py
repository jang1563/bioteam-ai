#!/usr/bin/env python3
"""W1 Spaceflight Anemia Case Study — Real Data Execution.

Runs the full W1 Literature Review pipeline with REAL API calls:
  - Anthropic Claude (Opus + Sonnet) for LLM steps
  - PubMed + Semantic Scholar for literature search
  - Crossref for retraction checking

Usage:
    cd backend
    uv run python -m scripts.run_w1_casestudy
    uv run python -m scripts.run_w1_casestudy --query "CRISPR gene therapy mechanisms"
    uv run python -m scripts.run_w1_casestudy --budget 2.0

Requires: ANTHROPIC_API_KEY env var. Recommended: NCBI_EMAIL.
Estimated cost: $0.20-0.50 per run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend is importable and .env is found
BACKEND_DIR = Path(__file__).parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

# pydantic-settings reads .env relative to CWD; ensure it finds root .env
if (PROJECT_ROOT / ".env").exists() and not Path(".env").exists():
    os.chdir(PROJECT_ROOT)

# Initialize DB tables BEFORE any model imports that trigger engine creation
from app.db.database import create_db_and_tables
create_db_and_tables()

from app.agents.registry import create_registry
from app.config import settings
from app.engines.integrity.retraction_checker import RetractionChecker
from app.integrations.crossref import CrossrefClient
from app.llm.layer import LLMLayer
from app.memory.semantic import SemanticMemory
from app.workflows.runners.w1_literature import W1LiteratureReviewRunner

# ══════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════

DEFAULT_QUERY = "spaceflight-induced anemia mechanisms"
DEFAULT_BUDGET = 5.0
RESULTS_DIR = BACKEND_DIR / "results"
CHROMA_DIR = BACKEND_DIR / "data" / "chroma_casestudy"

logger = logging.getLogger("w1_casestudy")


# ══════════════════════════════════════════════════════════════════
# Initialization
# ══════════════════════════════════════════════════════════════════


def check_env() -> list[str]:
    """Check required environment variables. Returns list of warnings."""
    warnings = []
    if not settings.anthropic_api_key:
        print("  ERROR: ANTHROPIC_API_KEY is not set. Add it to .env file.")
        sys.exit(1)
    if not settings.ncbi_email and not os.environ.get("NCBI_EMAIL"):
        warnings.append("NCBI_EMAIL not set — PubMed search will be DISABLED (add to .env)")
    if not settings.s2_api_key and not os.environ.get("S2_API_KEY"):
        warnings.append("S2_API_KEY not set — Semantic Scholar uses unauthenticated mode (lower rate limit)")
    return warnings


def init_services():
    """Initialize real services for W1 pipeline."""
    llm = LLMLayer()
    memory = SemanticMemory(persist_dir=str(CHROMA_DIR))
    registry = create_registry(llm, memory)

    # Inject PubMed + S2 clients into KnowledgeManager
    # (KM only uses PubMed if self._pubmed or NCBI_EMAIL is set,
    #  and only uses S2 if self._s2 is not None)
    km = registry.get("knowledge_manager")
    if km:
        from app.integrations.pubmed import PubMedClient
        from app.integrations.semantic_scholar import SemanticScholarClient

        # PubMed: needs NCBI_EMAIL (set via settings.ncbi_email → os.environ)
        if settings.ncbi_email:
            os.environ.setdefault("NCBI_EMAIL", settings.ncbi_email)
        if os.environ.get("NCBI_EMAIL"):
            km._pubmed = PubMedClient()
            logger.info("Injected PubMedClient into KnowledgeManager")
        else:
            logger.warning("NCBI_EMAIL not set — PubMed search disabled")

        # Semantic Scholar: works without API key (lower rate limit)
        km._s2 = SemanticScholarClient()
        logger.info("Injected SemanticScholarClient into KnowledgeManager")

    # Inject real CrossrefClient into DIA agent for retraction checking (A2 fix)
    dia = registry.get("data_integrity_auditor")
    if dia:
        dia._retraction_checker = RetractionChecker(
            crossref_client=CrossrefClient(
                email=os.environ.get("CROSSREF_EMAIL", settings.crossref_email or ""),
            ),
        )
        logger.info("Injected CrossrefClient into DataIntegrityAuditor")

    runner = W1LiteratureReviewRunner(
        registry=registry, llm_layer=llm, rcmxt_mode="hybrid",
    )
    return llm, memory, registry, runner


# ══════════════════════════════════════════════════════════════════
# Execution
# ══════════════════════════════════════════════════════════════════


async def run_pipeline(runner: W1LiteratureReviewRunner, query: str, budget: float) -> dict:
    """Run full W1 pipeline (Phase 1 + auto-resume at checkpoint)."""

    print(f"\n  Phase 1: SCOPE → SYNTHESIZE (6 steps)")
    print(f"  Query: {query}")
    print(f"  Budget: ${budget:.2f}")
    print()

    t0 = time.time()
    phase1 = await runner.run(query=query, budget=budget)
    t1 = time.time()

    inst = phase1["instance"]
    step_count_1 = len(phase1["step_results"])
    print(f"  Phase 1 complete: {step_count_1} steps, state={inst.state}, "
          f"budget=${inst.budget_remaining:.4f} remaining, {t1 - t0:.1f}s")

    if inst.state != "WAITING_HUMAN":
        print(f"\n  WARNING: Expected WAITING_HUMAN, got {inst.state}")
        if inst.state == "FAILED":
            # Find the failure
            for h in inst.step_history:
                if h.get("status") == "failed":
                    print(f"  Failed at: {h['step_id']} — {h.get('error', 'unknown')}")
        return {"phase1": phase1, "phase2": None, "error": f"Unexpected state: {inst.state}"}

    print(f"\n  Phase 2: CONTRADICTION_CHECK → REPORT (6 steps)")
    print()

    t2 = time.time()
    phase2 = await runner.resume_after_human(inst, query=query)
    t3 = time.time()

    step_count_2 = len(phase2["step_results"])
    print(f"  Phase 2 complete: {step_count_2} steps, state={phase2['instance'].state}, "
          f"budget=${phase2['instance'].budget_remaining:.4f} remaining, {t3 - t2:.1f}s")

    return {
        "phase1": phase1,
        "phase2": phase2,
        "total_duration_s": (t1 - t0) + (t3 - t2),
    }


# ══════════════════════════════════════════════════════════════════
# Reporting
# ══════════════════════════════════════════════════════════════════


def print_cost_report(result: dict) -> None:
    """Print per-step cost breakdown table."""
    phase2 = result.get("phase2")
    if not phase2:
        return

    inst = phase2["instance"]
    step_results = {
        **result["phase1"]["step_results"],
        **phase2["step_results"],
    }

    print("\n" + "=" * 70)
    print("  COST REPORT")
    print("=" * 70)
    print(f"  {'Step':<22} {'Status':<8} {'Tokens In':<11} {'Tokens Out':<12} {'Cost':>8}")
    print("  " + "-" * 66)

    total_in = 0
    total_out = 0
    total_cost = 0.0

    for step_id, sr in step_results.items():
        if isinstance(sr, dict):
            in_tok = sr.get("input_tokens", 0)
            out_tok = sr.get("output_tokens", 0)
            cost = sr.get("cost", 0.0)
            status = "ok" if not sr.get("error") else "FAIL"
        else:
            in_tok = getattr(sr, "input_tokens", 0)
            out_tok = getattr(sr, "output_tokens", 0)
            cost = getattr(sr, "cost", 0.0)
            status = "ok" if getattr(sr, "is_success", True) else "FAIL"

        total_in += in_tok
        total_out += out_tok
        total_cost += cost
        print(f"  {step_id:<22} {status:<8} {in_tok:>9,}  {out_tok:>10,}  ${cost:>7.4f}")

    print("  " + "-" * 66)
    print(f"  {'TOTAL':<22} {'':8} {total_in:>9,}  {total_out:>10,}  ${total_cost:>7.4f}")
    print(f"\n  Budget: ${inst.budget_total:.2f} → ${inst.budget_remaining:.4f} remaining")
    print(f"  Duration: {result.get('total_duration_s', 0):.1f}s")


def print_quality_report(result: dict) -> None:
    """Print quality metrics: PRISMA, RCMXT, integrity, novelty."""
    phase2 = result.get("phase2")
    if not phase2:
        return

    inst = phase2["instance"]
    manifest = inst.session_manifest or {}

    print("\n" + "=" * 70)
    print("  QUALITY REPORT")
    print("=" * 70)

    # PRISMA flow
    prisma = manifest.get("prisma", {})
    if prisma:
        print(f"\n  PRISMA Flow:")
        print(f"    Identified:       {prisma.get('records_identified', '?')}")
        print(f"    Screened:         {prisma.get('records_screened', '?')}")
        print(f"    Excluded:         {prisma.get('records_excluded_screening', '?')}")
        print(f"    Full-text:        {prisma.get('full_text_assessed', '?')}")
        print(f"    Included:         {prisma.get('studies_included', '?')}")
        print(f"    Negative results: {prisma.get('negative_results_found', '?')}")

    # RCMXT scores
    scores = inst.rcmxt_scores or []
    if scores:
        composites = [s.get("composite", 0) for s in scores if s.get("composite")]
        print(f"\n  RCMXT Scores: {len(scores)} claims scored")
        if composites:
            print(f"    Composite avg: {sum(composites)/len(composites):.3f}")
            print(f"    Composite min: {min(composites):.3f}")
            print(f"    Composite max: {max(composites):.3f}")
        for s in scores[:3]:  # Show top 3
            print(f"    - {s.get('claim', '?')[:60]}  → {s.get('composite', '?')}")

    # Citation report
    citation = inst.citation_report or {}
    if citation:
        print(f"\n  Citation Check:")
        print(f"    Total citations:    {citation.get('total_citations', '?')}")
        print(f"    Verified:           {citation.get('verified', '?')}")
        print(f"    Verification rate:  {citation.get('verification_rate', '?')}")

    # Integrity findings
    ic = manifest.get("integrity_quick_check", {})
    if ic:
        findings = ic.get("findings", [])
        by_sev = {}
        for f in findings:
            sev = f.get("severity", "info")
            by_sev[sev] = by_sev.get(sev, 0) + 1
        print(f"\n  Integrity Check: {len(findings)} findings")
        print(f"    Overall level: {ic.get('overall_level', '?')}")
        for sev, count in sorted(by_sev.items()):
            print(f"    {sev}: {count}")
        for f in findings[:5]:
            print(f"    - [{f.get('severity')}] {f.get('category')}: {f.get('title', '')[:50]}")

    # Novelty
    step_results = phase2["step_results"]
    novelty = step_results.get("NOVELTY_CHECK", {})
    if isinstance(novelty, dict):
        nov_out = novelty.get("output", novelty)
        if isinstance(nov_out, dict):
            print(f"\n  Novelty Assessment:")
            print(f"    Finding: {nov_out.get('finding', '?')[:80]}")
            print(f"    Is novel: {nov_out.get('is_novel', '?')}")
            print(f"    Score:    {nov_out.get('novelty_score', '?')}")

    # Model versions
    versions = manifest.get("model_versions", [])
    if versions:
        print(f"\n  Models used: {', '.join(versions)}")

    # LLM calls summary
    llm_calls = manifest.get("llm_calls", [])
    if llm_calls:
        print(f"  LLM calls: {len(llm_calls)}")


def save_results(result: dict, suffix: str) -> str:
    """Save results to JSON file. Returns file path."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"w1_spaceflight_{ts}_{suffix}.json"
    filepath = RESULTS_DIR / filename

    # Serialize: extract instance and step results
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": DEFAULT_QUERY,
        "total_duration_s": result.get("total_duration_s", 0),
    }

    if result.get("error"):
        output["error"] = result["error"]

    for phase_key in ("phase1", "phase2"):
        phase = result.get(phase_key)
        if phase is None:
            continue
        inst = phase["instance"]
        output[phase_key] = {
            "state": inst.state,
            "budget_total": inst.budget_total,
            "budget_remaining": inst.budget_remaining,
            "step_history": inst.step_history,
            "session_manifest": inst.session_manifest,
            "citation_report": inst.citation_report,
            "rcmxt_scores": inst.rcmxt_scores,
            "step_results": phase["step_results"],
        }

    with open(filepath, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n  Results saved: {filepath}")
    return str(filepath)


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════


async def main(query: str, budget: float) -> None:
    """Entry point: init → run → report → save."""
    print()
    print("=" * 70)
    print("  W1 LITERATURE REVIEW — REAL DATA EXECUTION")
    print("=" * 70)

    # Check env
    warnings = check_env()
    for w in warnings:
        print(f"  WARNING: {w}")

    # Init
    print("\n  Initializing services...")
    llm, memory, registry, runner = init_services()
    print(f"  Registry: {len(registry._agents)} agents registered")
    print(f"  ChromaDB: {CHROMA_DIR}")

    # Run pipeline
    try:
        result = await run_pipeline(runner, query, budget)
    except Exception as e:
        print(f"\n  PIPELINE CRASHED: {type(e).__name__}: {e}")
        logger.exception("Pipeline crashed")
        return

    # Report & save
    print_cost_report(result)
    print_quality_report(result)
    save_results(result, "full" if result.get("phase2") else "partial")

    # Final status
    phase2 = result.get("phase2")
    if phase2 and phase2["instance"].state == "COMPLETED":
        print("\n  STATUS: PIPELINE COMPLETED SUCCESSFULLY")
    else:
        print(f"\n  STATUS: PIPELINE DID NOT COMPLETE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="W1 Literature Review — Real Data Execution")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Research query")
    parser.add_argument("--budget", type=float, default=DEFAULT_BUDGET, help="Budget in USD")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)-30s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)

    asyncio.run(main(args.query, args.budget))
