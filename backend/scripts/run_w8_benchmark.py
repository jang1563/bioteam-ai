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
W8_BENCHMARK_DIR = Path(__file__).parent.parent / "data" / "w8_benchmark"
RUNS_DIR = W8_BENCHMARK_DIR / "runs"
CALIBRATION_DIR = W8_BENCHMARK_DIR / "calibration"
DEFAULT_CALIBRATION_FIXTURE = Path(__file__).parent.parent / "tests" / "fixtures" / "w8_match_calibration_fixture.json"
DEFAULT_TOKEN_COSINE_THRESHOLD = 0.05

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
    """Flatten surfaced W8 review output into one review text for ConcernMatcher."""
    parts: list[str] = []
    steps = w8_result.get("step_results", {})

    # Benchmark only the final surfaced review, not internal intermediate analyses.
    synth = steps.get("SYNTHESIZE_REVIEW", {}).get("output") or {}
    if synth.get("summary_assessment"):
        parts.append(synth["summary_assessment"])
    if synth.get("decision_reasoning"):
        parts.append(synth["decision_reasoning"])
    for comment in synth.get("comments", []) or []:
        text = comment.get("comment", "")
        if text:
            parts.append(f"[{comment.get('category', '').upper()}] {text}")

    return "\n\n".join(parts)


def extract_w8_concern_texts(w8_result: dict) -> list[str]:
    """Extract surfaced W8 concern texts from the final review synthesis."""
    synth = w8_result.get("step_results", {}).get("SYNTHESIZE_REVIEW", {}).get("output", {})
    comments = synth.get("comments") or []
    texts: list[str] = []
    for comment in comments:
        text = str(comment.get("comment", "")).strip()
        if text:
            texts.append(text)
    return texts


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
    w8_concern_texts: list[str],
    w8_decision: str | None,
    gt_decision: str | None,
    w8_comment_count: int | None = None,
    match_mode: str = "keyword",
    similarity_threshold: float | None = None,
) -> dict:
    """Compute recall, precision, and decision accuracy for one article."""
    from app.engines.review_corpus.concern_matcher import ConcernMatcher
    from app.models.review_corpus import ReviewerConcern

    # Use top-10 concerns only (Phase 0 finding: W8 over-generates)
    major_concerns = [
        ReviewerConcern(**c) for c in human_concerns if c.get("severity") == "major"
    ][:10]
    all_concerns = [ReviewerConcern(**c) for c in human_concerns][:20]

    matcher = ConcernMatcher(
        embed_fn=None,
        match_mode=match_mode,
        similarity_threshold=_resolve_similarity_threshold(match_mode, similarity_threshold),
    )
    result = matcher.compute_metrics(
        article_id=article_id,
        source=source,
        human_concerns=all_concerns,
        w8_review_text=w8_text,
        w8_comment_count=w8_comment_count,
        w8_concern_texts=w8_concern_texts,
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
        "w8_concerns_matched": result.w8_concerns_matched,
        "w8_concerns_unmatched": result.w8_concerns_unmatched,
        "human_matched": result.human_concerns_matched,
        "human_missed": result.human_concerns_missed,
        "match_mode": match_mode,
        "similarity_threshold": _resolve_similarity_threshold(match_mode, similarity_threshold),
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


def _resolve_similarity_threshold(match_mode: str, similarity_threshold: float | None) -> float | None:
    """Resolve the effective threshold for a benchmark run."""
    if similarity_threshold is not None:
        return similarity_threshold
    if match_mode == "token_cosine":
        return DEFAULT_TOKEN_COSINE_THRESHOLD
    return None


def run_threshold_calibration(
    fixture_path: Path,
    match_mode: str,
    threshold_start: float,
    threshold_stop: float,
    threshold_step: float,
) -> dict:
    """Run a simple threshold sweep over manually curated match cases."""
    from app.engines.review_corpus.concern_matcher import ConcernMatcher

    if match_mode not in {"token_cosine", "keyword"}:
        raise ValueError("Calibration currently supports only keyword/token_cosine modes")

    with open(fixture_path) as f:
        payload = json.load(f)

    cases = payload.get("cases", [])
    if not cases:
        print("No calibration cases found.")
        return {}

    thresholds: list[float] = []
    current = threshold_start
    while current <= threshold_stop + 1e-9:
        thresholds.append(round(current, 4))
        current += threshold_step

    rows: list[dict] = []
    for threshold in thresholds:
        matcher = ConcernMatcher(match_mode=match_mode, similarity_threshold=threshold)
        tp = fp = fn = tn = 0
        for case in cases:
            score = matcher.score_text_pair(case["left_text"], case["right_text"])
            pred = score >= threshold
            gold = bool(case["is_match"])
            if pred and gold:
                tp += 1
            elif pred and not gold:
                fp += 1
            elif not pred and gold:
                fn += 1
            else:
                tn += 1
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        accuracy = (tp + tn) / len(cases) if cases else 0.0
        rows.append(
            {
                "threshold": threshold,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "accuracy": accuracy,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "tn": tn,
            }
        )

    best = max(rows, key=lambda row: (row["f1"], row["accuracy"], row["precision"]))
    print(f"\nCalibration fixture: {fixture_path}")
    print(f"Match mode: {match_mode}")
    print(f"Cases: {len(cases)}")
    print(f"\n{'Threshold':>10} {'Prec':>8} {'Recall':>8} {'F1':>8} {'Acc':>8}")
    print("-" * 48)
    for row in rows:
        print(
            f"{row['threshold']:>10.2f} {row['precision']:>8.2%} "
            f"{row['recall']:>8.2%} {row['f1']:>8.2%} {row['accuracy']:>8.2%}"
        )
    print("\nBest threshold:")
    print(
        f"  threshold={best['threshold']:.2f} "
        f"precision={best['precision']:.2%} recall={best['recall']:.2%} "
        f"f1={best['f1']:.2%} accuracy={best['accuracy']:.2%}"
    )
    return {
        "fixture_path": str(fixture_path),
        "match_mode": match_mode,
        "case_count": len(cases),
        "threshold_start": threshold_start,
        "threshold_stop": threshold_stop,
        "threshold_step": threshold_step,
        "recommended_threshold": best["threshold"],
        "best": best,
        "rows": rows,
    }


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
    match_mode: str,
    similarity_threshold: float | None,
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
        w8_concern_texts = extract_w8_concern_texts(w8_result)
        w8_decision = extract_w8_decision(w8_result)
        w8_comment_count = extract_w8_comment_count(w8_result)

        # Compute metrics
        metrics = compute_metrics(
            article_id=article_id,
            source=source,
            human_concerns=concerns,
            w8_text=w8_text,
            w8_concern_texts=w8_concern_texts,
            w8_decision=w8_decision,
            gt_decision=gt_decision,
            w8_comment_count=w8_comment_count,
            match_mode=match_mode,
            similarity_threshold=similarity_threshold,
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

def _build_aggregate_summary(all_metrics: list[dict]) -> dict:
    """Build normalized aggregate summary for artifact output and reporting."""
    valid_recall = [m["overall_concern_recall"] for m in all_metrics if m["overall_concern_recall"] is not None]
    valid_major = [m["major_concern_recall"] for m in all_metrics if m["major_concern_recall"] is not None]
    valid_prec = [m["concern_precision"] for m in all_metrics if m["concern_precision"] is not None]
    decisions = [m for m in all_metrics if m["decision_match"] is not None]

    decision_accuracy = None
    if decisions:
        decision_accuracy = sum(1 for d in decisions if d["decision_match"]) / len(decisions)

    return {
        "article_count": len(all_metrics),
        "overall_concern_recall_avg": (sum(valid_recall) / len(valid_recall)) if valid_recall else None,
        "major_concern_recall_avg": (sum(valid_major) / len(valid_major)) if valid_major else None,
        "concern_precision_avg": (sum(valid_prec) / len(valid_prec)) if valid_prec else None,
        "decision_accuracy": decision_accuracy,
        "articles_with_decision": len(decisions),
        "articles_with_precision": len(valid_prec),
        "articles_with_recall": len(valid_recall),
    }


def print_aggregate_report(all_metrics: list[dict]) -> None:
    """Print aggregate benchmark report."""
    if not all_metrics:
        print("\nNo metrics computed.")
        return

    summary = _build_aggregate_summary(all_metrics)

    print(f"\n{'='*65}")
    print(f"W8 BENCHMARK RESULTS — {len(all_metrics)} articles")
    print(f"{'='*65}")
    print(f"\n{'Metric':<35} {'Value':>10}")
    print(f"{'-'*45}")
    if summary["overall_concern_recall_avg"] is not None:
        print(f"{'Overall concern recall (avg)':<35} {summary['overall_concern_recall_avg']:>10.2%}")
    if summary["major_concern_recall_avg"] is not None:
        print(f"{'Major concern recall (avg)':<35} {summary['major_concern_recall_avg']:>10.2%}")
    if summary["concern_precision_avg"] is not None:
        print(f"{'Concern precision (avg)':<35} {summary['concern_precision_avg']:>10.2%}")
    if summary["decision_accuracy"] is not None:
        print(f"{'Decision accuracy (coarse)':<35} {summary['decision_accuracy']:>10.2%}")

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


def save_results(
    all_metrics: list[dict],
    label: str,
    source: str,
    config: dict | None = None,
) -> Path:
    """Save benchmark results in a canonical artifact schema."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone

    from app.models.review_corpus import (
        W8BenchmarkAggregate,
        W8BenchmarkArticleMetrics,
        W8BenchmarkRun,
    )

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = RUNS_DIR / f"w8_benchmark_run_{label}_{ts}.json"
    artifact = W8BenchmarkRun(
        label=label,
        source=source,  # type: ignore[arg-type]
        config=config or {},
        aggregate=W8BenchmarkAggregate(**_build_aggregate_summary(all_metrics)),
        articles=[W8BenchmarkArticleMetrics(**m) for m in all_metrics],
    )
    with open(out_path, "w") as f:
        json.dump(artifact.model_dump(mode="json"), f, indent=2)
    logger.info("Results saved to %s", out_path)
    return out_path


def save_calibration_results(result: dict, label: str) -> Path:
    """Save calibration sweep results to JSON."""
    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = CALIBRATION_DIR / f"w8_benchmark_calibration_{label}_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    logger.info("Calibration results saved to %s", out_path)
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
    parser.add_argument(
        "--article-ids",
        type=str,
        default="",
        help="Comma-separated explicit article IDs to benchmark (overrides --max)",
    )
    parser.add_argument("--run-w8", action="store_true",
                        help="Run W8 pipeline on articles (requires PDFs)")
    parser.add_argument("--budget", type=float, default=3.0,
                        help="Budget per article in USD (only with --run-w8)")
    parser.add_argument("--use-llm", action="store_true",
                        help="Use LLM (Haiku) to extract concerns from DL (default: heuristic)")
    parser.add_argument(
        "--match-mode",
        choices=["keyword", "token_cosine"],
        default="keyword",
        help="Concern matching strategy for benchmark scoring",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=None,
        help="Override similarity threshold for the selected match mode (default token_cosine=0.05)",
    )
    parser.add_argument(
        "--calibration-fixture",
        type=str,
        default="",
        help="Run threshold calibration using a fixture JSON instead of a benchmark run",
    )
    parser.add_argument("--threshold-start", type=float, default=0.30)
    parser.add_argument("--threshold-stop", type=float, default=0.85)
    parser.add_argument("--threshold-step", type=float, default=0.05)
    parser.add_argument("--report-only", action="store_true",
                        help="Print saved results without running")
    args = parser.parse_args()

    if args.calibration_fixture:
        fixture_path = Path(args.calibration_fixture)
    else:
        fixture_path = DEFAULT_CALIBRATION_FIXTURE

    if args.calibration_fixture or fixture_path.exists():
        if args.calibration_fixture:
            result = run_threshold_calibration(
                fixture_path=fixture_path,
                match_mode=args.match_mode,
                threshold_start=args.threshold_start,
                threshold_stop=args.threshold_stop,
                threshold_step=args.threshold_step,
            )
            if result:
                save_calibration_results(result, args.match_mode)
            return

    if args.report_only:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        results = sorted(RUNS_DIR.glob("w8_benchmark_run_*.json"))
        if not results:
            print("No saved benchmark results found.")
            return
        latest = results[-1]
        with open(latest) as f:
            data = json.load(f)
        metrics = data.get("articles") or data.get("metrics") or []
        print_aggregate_report(metrics)
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

    explicit_ids = [item.strip() for item in args.article_ids.split(",") if item.strip()]
    if explicit_ids:
        known = set(available)
        missing = [aid for aid in explicit_ids if aid not in known]
        if missing:
            print(f"Unknown article IDs for source={args.source}: {', '.join(missing)}")
            return
        article_ids = explicit_ids
    else:
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
        match_mode=args.match_mode,
        similarity_threshold=args.similarity_threshold,
    )

    print_aggregate_report(all_metrics)
    if all_metrics:
        save_results(
            all_metrics,
            label=args.source,
            source=args.source,
            config={
                "source": args.source,
                "max_articles": args.max_articles,
                "article_ids": article_ids,
                "run_w8": args.run_w8,
                "budget": args.budget,
                "use_llm": args.use_llm,
                "match_mode": args.match_mode,
                "similarity_threshold": _resolve_similarity_threshold(
                    args.match_mode,
                    args.similarity_threshold,
                ),
            },
        )


if __name__ == "__main__":
    asyncio.run(main())
