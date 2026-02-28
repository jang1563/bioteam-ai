"""Phase 3: W8 Peer Review Benchmark Harness.

Runs the full evaluation pipeline:
  1. Load ground truth (eLife decision letters) from phase0_pilot/ or elife_corpus/
  2. Extract structured ReviewerConcerns from decision letters via ConcernParser (Haiku)
  3. Load existing W8 results (JSON) for each article
  4. Compute recall/precision via ConcernMatcher (keyword or semantic)
  5. Print per-article and aggregate metrics

Usage:
    # Evaluate phase 0 pilot (5 papers, uses existing W8 results)
    uv run python backend/scripts/run_w8_benchmark.py --source pilot

    # Evaluate corpus (requires collect_elife_corpus.py to have run first)
    uv run python backend/scripts/run_w8_benchmark.py --source corpus --max 50

    # Run W8 on new articles AND benchmark in one pass
    uv run python backend/scripts/run_w8_benchmark.py --source corpus --run-w8 --budget 3.0

    # Show saved benchmark results only
    uv run python backend/scripts/run_w8_benchmark.py --report-only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("w8_benchmark")

PILOT_DIR = Path(__file__).parent.parent / "data" / "phase0_pilot"
CORPUS_DIR = Path(__file__).parent.parent / "data" / "elife_corpus"
RESULTS_DIR = Path(__file__).parent.parent / "data" / "benchmark_results"

# Phase 0 papers with known W8 results
PILOT_PAPERS = {
    "00969": "BRAF inhibitors JNK apoptosis (cancer)",
    "83069": "GAS6 macrophage efferocytosis OA (immunology)",
    "11058": "TSC2-Rheb arginine mTORC1 (cell-biology)",
    "85560": "CMV US10 HLA-I regulation (microbiology)",
    "107189": "Pseudomonas aeruginosa evolution (evolutionary)",
}


# ---------------------------------------------------------------------------
# Concern extraction from ground truth
# ---------------------------------------------------------------------------

async def extract_ground_truth_concerns(
    article_id: str,
    decision_letter: str,
    author_response: str,
    llm_layer,
) -> list[dict]:
    """Extract structured concerns from human decision letter via ConcernParser."""
    from app.engines.review_corpus.concern_parser import ConcernParser

    parser = ConcernParser(llm_layer=llm_layer)
    batch = await parser.extract_concerns(article_id, decision_letter, author_response)

    logger.info(
        "  Extracted %d concerns from %s (reviewers: %d)",
        len(batch.concerns),
        article_id,
        batch.total_reviewers,
    )
    return [c.model_dump() for c in batch.concerns]


# ---------------------------------------------------------------------------
# W8 output extraction
# ---------------------------------------------------------------------------

def load_w8_result(article_id: str, source: str) -> dict | None:
    """Load existing W8 result JSON."""
    if source == "pilot":
        path = PILOT_DIR / f"{article_id}_w8_result.json"
    else:
        path = CORPUS_DIR / f"{article_id}_w8_result.json"

    if not path.exists():
        logger.warning("  No W8 result for %s at %s", article_id, path)
        return None

    with open(path) as f:
        return json.load(f)


def extract_w8_review_text(w8_result: dict) -> str:
    """Flatten W8 output into one review text for ConcernMatcher."""
    parts: list[str] = []
    steps = w8_result.get("step_results", {})

    # SYNTHESIZE_REVIEW — primary source
    synth = steps.get("SYNTHESIZE_REVIEW", {}).get("output") or {}
    if synth.get("summary_assessment"):
        parts.append(synth["summary_assessment"])
    for comment in synth.get("comments", []) or []:
        text = comment.get("comment", "")
        if text:
            parts.append(f"[{comment.get('category', '').upper()}] {text}")

    # METHODOLOGY_REVIEW — secondary
    method = steps.get("METHODOLOGY_REVIEW", {}).get("output") or {}
    for field in ["study_design_critique", "statistical_methods", "controls_adequacy"]:
        val = method.get(field, "")
        if val and len(val) > 30:
            parts.append(val)
    for item in method.get("potential_biases", []) or []:
        parts.append(str(item))
    for item in method.get("reproducibility_concerns", []) or []:
        parts.append(str(item))
    for item in method.get("domain_specific_issues", []) or []:
        parts.append(str(item))

    return "\n\n".join(parts)


def extract_w8_decision(w8_result: dict) -> str | None:
    """Extract W8 editorial decision."""
    synth = w8_result.get("step_results", {}).get("SYNTHESIZE_REVIEW", {}).get("output", {})
    return synth.get("decision")


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def extract_w8_comment_count(w8_result: dict) -> int | None:
    """Count W8 major + minor comments from SYNTHESIZE_REVIEW output."""
    synth = w8_result.get("step_results", {}).get("SYNTHESIZE_REVIEW", {}).get("output", {})
    major = synth.get("major_comments") or synth.get("comments") or []
    minor = synth.get("minor_comments") or []
    total = len(major) + len(minor)
    return total if total > 0 else None


def compute_metrics(
    article_id: str,
    source: str,
    human_concerns: list[dict],
    w8_text: str,
    w8_decision: str | None,
    gt_decision: str | None,
    w8_comment_count: int | None = None,
) -> dict:
    """Compute recall, precision, and decision accuracy for one article."""
    from app.engines.review_corpus.concern_matcher import ConcernMatcher
    from app.models.review_corpus import ReviewerConcern

    # Use top-10 concerns only (Phase 0 finding: W8 over-generates)
    major_concerns = [
        ReviewerConcern(**c) for c in human_concerns if c.get("severity") == "major"
    ][:10]
    all_concerns = [ReviewerConcern(**c) for c in human_concerns][:20]

    matcher = ConcernMatcher(embed_fn=None)  # keyword fallback
    result = matcher.compute_metrics(
        article_id=article_id,
        source=source,
        human_concerns=all_concerns,
        w8_review_text=w8_text,
        w8_comment_count=w8_comment_count,
        exclude_figure_concerns=True,
    )

    # Decision accuracy
    decision_match = None
    if w8_decision and gt_decision:
        # Normalize: both "major_revision" → same bucket
        decision_match = _decision_bucket(w8_decision) == _decision_bucket(gt_decision)

    return {
        "article_id": article_id,
        "source": source,
        "human_concerns_total": len(all_concerns),
        "human_major_concerns": len(major_concerns),
        "w8_decision": w8_decision,
        "gt_decision": gt_decision,
        "decision_match": decision_match,
        "major_concern_recall": result.major_concern_recall,
        "overall_concern_recall": result.overall_concern_recall,
        "concern_precision": result.concern_precision,
        "human_matched": result.human_concerns_matched,
        "human_missed": result.human_concerns_missed,
    }


def _decision_bucket(decision: str) -> str:
    """Map decision to coarse bucket for accuracy scoring."""
    mapping = {
        "accept": "accept",
        "minor_revision": "revision",
        "major_revision": "revision",
        "reject": "reject",
    }
    return mapping.get(decision.lower(), "unknown")


# ---------------------------------------------------------------------------
# Main benchmark loop
# ---------------------------------------------------------------------------

async def run_benchmark(
    source: str,
    article_ids: list[str],
    ground_truth_dir: Path,
    run_w8: bool,
    budget: float,
    llm_layer,
) -> list[dict]:
    """Run W8 benchmark for a list of article IDs."""
    all_metrics: list[dict] = []

    for article_id in article_ids:
        logger.info("=== Benchmarking %s ===", article_id)

        # Load ground truth
        gt_path = ground_truth_dir / f"{article_id}.json"
        if not gt_path.exists():
            logger.warning("  No ground truth for %s, skipping", article_id)
            continue

        with open(gt_path) as f:
            gt = json.load(f)

        decision_letter = gt.get("decision_letter", "")
        author_response = gt.get("author_response", "")
        gt_decision = gt.get("editorial_decision", None)

        if not decision_letter.strip():
            logger.warning("  Empty decision letter for %s, skipping", article_id)
            continue

        # Optionally run W8 (skip if result already exists)
        if run_w8:
            existing = load_w8_result(article_id, source)
            if existing is not None:
                logger.info("  %s: W8 result already exists — skipping W8 run", article_id)
            else:
                await _run_w8_on_article(article_id, source, ground_truth_dir, budget)

        # Load W8 result
        w8_result = load_w8_result(article_id, source)
        if w8_result is None:
            logger.warning("  No W8 result for %s, skipping", article_id)
            continue

        # Extract ground truth concerns
        concerns = await extract_ground_truth_concerns(
            article_id, decision_letter, author_response, llm_layer
        )
        if not concerns:
            logger.warning("  No concerns extracted for %s (no LLM?)", article_id)
            concerns = _heuristic_concerns(decision_letter)

        # Extract W8 review text and comment count
        w8_text = extract_w8_review_text(w8_result)
        w8_decision = extract_w8_decision(w8_result)
        w8_comment_count = extract_w8_comment_count(w8_result)

        # Compute metrics
        metrics = compute_metrics(
            article_id=article_id,
            source=source,
            human_concerns=concerns,
            w8_text=w8_text,
            w8_decision=w8_decision,
            gt_decision=gt_decision,
            w8_comment_count=w8_comment_count,
        )
        all_metrics.append(metrics)

        logger.info(
            "  recall=%.2f | major_recall=%.2f | decision=%s→%s match=%s",
            metrics["overall_concern_recall"] or 0,
            metrics["major_concern_recall"] or 0,
            w8_decision,
            gt_decision,
            metrics["decision_match"],
        )

    return all_metrics


def _heuristic_concerns(decision_letter: str) -> list[dict]:
    """Fallback: extract concerns from numbered/bulleted list in DL text."""
    import re
    concerns = []
    # Match numbered items: "1) ...", "1. ...", "Reviewer 1: ..."
    patterns = [
        r"^\s*(\d+)[.)]\s+(.+?)(?=\n\s*\d+[.)]|\Z)",
        r"(?:Reviewer\s+#?\d+[,:]?\s*)([A-Z].+?)(?=Reviewer\s+#?\d+|\Z)",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, decision_letter, re.MULTILINE | re.DOTALL):
            text = m.group(len(m.groups())).strip()[:300]
            if len(text) > 30:
                severity = "major" if any(w in text.lower() for w in ["essential", "major", "critical", "must"]) else "minor"
                concerns.append({
                    "concern_id": f"H{len(concerns)+1}",
                    "concern_text": text,
                    "category": "other",
                    "severity": severity,
                    "author_response_text": "",
                    "resolution": "unclear",
                    "was_valid": None,
                    "raised_by_multiple": False,
                })
        if concerns:
            break
    return concerns[:20]


async def _run_w8_on_article(article_id: str, source: str, data_dir: Path, budget: float):
    """Run W8 pipeline on one article.

    Prefers text-based INGEST (from corpus JSON body_text) over PDF.
    Falls back to PDF if corpus JSON lacks body_text.
    """
    from app.agents.registry import create_registry
    from app.llm.layer import LLMLayer
    from app.workflows.runners.w8_paper_review import W8PaperReviewRunner

    # Try article_data from corpus JSON (text-based, no PDF needed)
    article_data = None
    corpus_path = data_dir / f"{article_id}.json"
    if corpus_path.exists():
        with open(corpus_path) as f:
            d = json.load(f)
        if d.get("body_text") and len(d["body_text"]) > 100:
            article_data = {
                "article_id": d.get("article_id", article_id),
                "title": d.get("title", ""),
                "abstract": d.get("abstract", ""),
                "body_text": d["body_text"],
                "sections": d.get("sections", []),
                "doi": d.get("doi", ""),
            }
            logger.info("  Using XML body_text for %s (%d chars)", article_id, len(d["body_text"]))

    # Fallback: PDF file
    pdf_path = data_dir / f"{article_id}.pdf"
    if article_data is None and not pdf_path.exists():
        logger.warning("  No body_text in corpus JSON and no PDF for %s — skipping", article_id)
        return

    llm = LLMLayer()
    registry = create_registry(llm, memory=None)
    runner = W8PaperReviewRunner(registry=registry, llm_layer=llm)

    try:
        result = await runner.run(
            article_data=article_data,
            pdf_path="" if article_data else str(pdf_path),
            budget=budget,
            skip_human_checkpoint=True,
        )
        out_path = data_dir / f"{article_id}_w8_result.json"
        with open(out_path, "w") as f:
            json.dump({
                "paper_id": article_id,
                "step_results": result.get("step_results", {}),
            }, f, indent=2, default=str)
        logger.info("  W8 result saved to %s", out_path)
    except Exception as e:
        logger.error("  W8 run failed for %s: %s", article_id, e)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_aggregate_report(all_metrics: list[dict]) -> None:
    """Print aggregate benchmark report."""
    if not all_metrics:
        print("\nNo metrics computed.")
        return

    valid_recall = [m["overall_concern_recall"] for m in all_metrics if m["overall_concern_recall"] is not None]
    valid_major = [m["major_concern_recall"] for m in all_metrics if m["major_concern_recall"] is not None]
    valid_prec = [m["concern_precision"] for m in all_metrics if m["concern_precision"] is not None]
    decisions = [m for m in all_metrics if m["decision_match"] is not None]

    print(f"\n{'='*65}")
    print(f"W8 BENCHMARK RESULTS — {len(all_metrics)} articles")
    print(f"{'='*65}")
    print(f"\n{'Metric':<35} {'Value':>10}")
    print(f"{'-'*45}")
    if valid_recall:
        print(f"{'Overall concern recall (avg)':<35} {sum(valid_recall)/len(valid_recall):>10.2%}")
    if valid_major:
        print(f"{'Major concern recall (avg)':<35} {sum(valid_major)/len(valid_major):>10.2%}")
    if valid_prec:
        print(f"{'Concern precision (approx)':<35} {sum(valid_prec)/len(valid_prec):>10.2%}")
    if decisions:
        acc = sum(1 for d in decisions if d["decision_match"]) / len(decisions)
        print(f"{'Decision accuracy (coarse)':<35} {acc:>10.2%}")

    print(f"\n{'Per-article breakdown':}")
    print(f"{'ID':<10} {'Decision':>16} {'Match':>6} {'Recall':>8} {'Maj.Rec':>8} {'Prec':>8} {'#Human':>7}")
    print(f"{'-'*65}")
    for m in all_metrics:
        recall = f"{m['overall_concern_recall']:.0%}" if m["overall_concern_recall"] is not None else "—"
        maj = f"{m['major_concern_recall']:.0%}" if m["major_concern_recall"] is not None else "—"
        prec = f"{m['concern_precision']:.0%}" if m["concern_precision"] is not None else "—"
        dec = f"{m.get('w8_decision','?')}"[:15]
        match = "✓" if m.get("decision_match") else ("✗" if m.get("decision_match") is False else "?")
        n = m.get("human_concerns_total", 0)
        print(f"{m['article_id']:<10} {dec:>16} {match:>6} {recall:>8} {maj:>8} {prec:>8} {n:>7}")


def save_results(all_metrics: list[dict], label: str) -> Path:
    """Save benchmark results to JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"benchmark_{label}_{ts}.json"
    with open(out_path, "w") as f:
        json.dump({"label": label, "metrics": all_metrics}, f, indent=2)
    logger.info("Results saved to %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(description="W8 Peer Review Benchmark Harness")
    parser.add_argument("--source", choices=["pilot", "corpus"], default="pilot",
                        help="Data source: 'pilot' (phase0) or 'corpus' (elife_corpus)")
    parser.add_argument("--max", type=int, default=5, dest="max_articles",
                        help="Max articles to benchmark (default: 5)")
    parser.add_argument("--run-w8", action="store_true",
                        help="Run W8 pipeline on articles (requires PDFs)")
    parser.add_argument("--budget", type=float, default=3.0,
                        help="Budget per article in USD (only with --run-w8)")
    parser.add_argument("--use-llm", action="store_true",
                        help="Use LLM (Haiku) to extract concerns from DL (default: heuristic)")
    parser.add_argument("--report-only", action="store_true",
                        help="Print saved results without running")
    args = parser.parse_args()

    if args.report_only:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        results = sorted(RESULTS_DIR.glob("benchmark_*.json"))
        if not results:
            print("No saved benchmark results found.")
            return
        latest = results[-1]
        with open(latest) as f:
            data = json.load(f)
        print_aggregate_report(data["metrics"])
        return

    # Select data source
    if args.source == "pilot":
        data_dir = PILOT_DIR
        available = list(PILOT_PAPERS.keys())
    else:
        data_dir = CORPUS_DIR
        manifest_path = CORPUS_DIR / "manifest.json"
        if not manifest_path.exists():
            print("No corpus manifest. Run collect_elife_corpus.py first.")
            return
        with open(manifest_path) as f:
            manifest = json.load(f)
        available = [a["article_id"] for a in manifest.get("articles", [])]

    article_ids = available[:args.max_articles]
    logger.info("Benchmarking %d articles from %s", len(article_ids), args.source)

    # Setup LLM (optional)
    llm_layer = None
    if args.use_llm:
        from app.llm.layer import LLMLayer
        llm_layer = LLMLayer()
        logger.info("LLM concern extraction: enabled (Haiku)")
    else:
        logger.info("LLM concern extraction: disabled (heuristic fallback)")

    all_metrics = await run_benchmark(
        source=args.source,
        article_ids=article_ids,
        ground_truth_dir=data_dir,
        run_w8=args.run_w8,
        budget=args.budget,
        llm_layer=llm_layer,
    )

    print_aggregate_report(all_metrics)
    if all_metrics:
        save_results(all_metrics, args.source)


if __name__ == "__main__":
    asyncio.run(main())
