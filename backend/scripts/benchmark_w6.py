#!/usr/bin/env python3
"""
benchmark_w6.py — W6 AmbiguityEngine Benchmark on Contradiction Corpus

Evaluates the production AmbiguityEngineAgent against corpus_final.jsonl
by calling agent.classify_pair() directly for each entry.

This tests the CLASSIFY step of W6 in isolation, bypassing the
ContradictionDetector pre-screening. Measures how well the agent's
LLM classification matches the held reference labels.

Supports provider switching via AMBIGUITY_LLM_PROVIDER env var:
  - "gemini" (default, free tier)
  - "anthropic" (Sonnet, paid)

Uses the agent's actual system prompt (ambiguity_engine_temporal_a.md)
and ContradictionClassification Pydantic model, matching production behavior.

Usage:
  export GEMINI_API_KEY=<your-key>
  python benchmark_w6.py --corpus output/v3/corpus_final.jsonl
  python benchmark_w6.py --dry-run
  python benchmark_w6.py --reset --provider gemini
  python benchmark_w6.py --provider anthropic  # uses Sonnet (paid)

Output:
  output/v3/benchmark_w6/checkpoint.jsonl
  output/v3/benchmark_w6/eval_results.jsonl
  output/v3/benchmark_w6/eval_report.json
  output/v3/benchmark_w6/misclassified.jsonl
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Add backend to path for app imports
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from app.agents.ambiguity_engine import AmbiguityEngineAgent  # noqa: E402
from app.agents.base import BaseAgent  # noqa: E402
from app.llm.layer import LLMLayer  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from eval_common import (  # noqa: E402
    build_eval_result,
    compute_metrics,
    load_checkpoint,
    print_report,
    save_error_analysis,
    write_jsonl,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
log = logging.getLogger(__name__)
# Quiet noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("app.llm").setLevel(logging.WARNING)
logging.getLogger("app.agents").setLevel(logging.WARNING)

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_CORPUS = Path(__file__).parent / "output" / "v3" / "corpus_final.jsonl"
DEFAULT_EVAL_DIR = Path(__file__).parent / "output" / "v3" / "benchmark_w6"

# Sleep between calls (Gemini free tier: 15 RPM → 4.0s min)
SLEEP_GEMINI = 4.5
SLEEP_ANTHROPIC = 0.5


async def benchmark_one(
    agent: AmbiguityEngineAgent,
    entry: dict,
) -> dict | None:
    """Classify one corpus entry using the W6 agent's classify_pair()."""
    try:
        result = await agent.classify_pair(
            claim_a=entry["claim_a"][:500],
            claim_b=entry["claim_b"][:500],
        )
        # Map ContradictionClassification → eval schema
        pred_type = result.types[0] if result.types else "contextual"
        return {
            "contradiction_type": pred_type,
            "confidence": result.confidence,
            "is_genuine_contradiction": result.is_genuine_contradiction,
            "rationale": "; ".join(
                f"{k}: {v}" for k, v in result.type_reasoning.items()
            ) if result.type_reasoning else "",
            "types_all": result.types,
        }
    except Exception as e:
        log.warning("classify_pair failed for %s: %s", entry.get("id", "?"), e)
        return None


async def run_benchmark(
    agent: AmbiguityEngineAgent,
    corpus_path: Path,
    eval_dir: Path,
    sleep_time: float,
    dry_run: bool = False,
) -> list[dict]:
    eval_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_file = eval_dir / "checkpoint.jsonl"

    entries = [json.loads(l) for l in open(corpus_path) if l.strip()]
    if dry_run:
        entries = entries[:5]
        log.info("DRY RUN: benchmarking first 5 entries only")

    entry_ids = {e["id"] for e in entries}
    done = load_checkpoint(checkpoint_file, valid_ids=entry_ids)

    remaining = [e for e in entries if e["id"] not in done]
    log.info("Corpus: %d | Done: %d | Remaining: %d", len(entries), len(done), len(remaining))

    if not remaining:
        return list(done.values())

    log.info("Estimated time: %.0f min (%.1f sec/entry)", len(remaining) * sleep_time / 60, sleep_time)

    checkpoint_f = open(checkpoint_file, "a")
    ok = parse_fail = 0

    for i, entry in enumerate(remaining):
        pred = await benchmark_one(agent, entry)
        result = build_eval_result(entry, pred)

        done[entry["id"]] = result
        checkpoint_f.write(json.dumps(result) + "\n")
        checkpoint_f.flush()

        if pred:
            ok += 1
        else:
            parse_fail += 1

        if (i + 1) % 20 == 0 or (i + 1) == len(remaining):
            evaluable = [r for r in done.values() if not r["parse_failed"]]
            binary_correct = sum(1 for r in evaluable if r["pred_genuine"] == r["gold_genuine"])
            acc = 100 * binary_correct / max(1, len(evaluable))
            log.info("  %d/%d | ok=%d fail=%d | acc=%.1f%%", i + 1, len(remaining), ok, parse_fail, acc)

        await asyncio.sleep(sleep_time)

    checkpoint_f.close()
    log.info("Benchmark complete: ok=%d parse_fail=%d", ok, parse_fail)
    return list(done.values())


async def main():
    parser = argparse.ArgumentParser(description="W6 AmbiguityEngine benchmark")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR)
    parser.add_argument("--provider", choices=["gemini", "anthropic"], default="gemini")
    args = parser.parse_args()

    os.environ["AMBIGUITY_LLM_PROVIDER"] = args.provider
    sleep_time = SLEEP_GEMINI if args.provider == "gemini" else SLEEP_ANTHROPIC

    llm = LLMLayer()
    spec = BaseAgent.load_spec("ambiguity_engine")
    agent = AmbiguityEngineAgent(spec=spec, llm=llm, memory=None)

    eval_dir = args.eval_dir
    corpus_path = args.corpus
    results_file = eval_dir / "eval_results.jsonl"
    report_file = eval_dir / "eval_report.json"
    misclassified_file = eval_dir / "misclassified.jsonl"

    checkpoint_file = eval_dir / "checkpoint.jsonl"
    if args.reset and checkpoint_file.exists():
        checkpoint_file.unlink()
        log.info("Checkpoint cleared.")

    provider_label = f"{args.provider} ({'free' if args.provider == 'gemini' else 'paid'})"
    n_entries = len([l for l in open(corpus_path) if l.strip()])
    print(f"\nW6 Benchmark — {provider_label} | prompt: {spec.system_prompt_file}")
    print(f"{corpus_path.name} | {n_entries} entries | ~{n_entries * sleep_time / 60:.0f} min")

    results = await run_benchmark(
        agent=agent, corpus_path=corpus_path, eval_dir=eval_dir,
        sleep_time=sleep_time, dry_run=args.dry_run,
    )

    if not args.dry_run:
        metrics = compute_metrics(results)
        print_report(metrics, corpus_name=corpus_path.name)
        save_error_analysis(results, corpus_path, misclassified_file)
        write_jsonl(results, results_file)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, "w") as f:
            json.dump(metrics, f, indent=2)
        log.info("Results -> %s  Report -> %s", results_file, report_file)
    else:
        print("\nDRY RUN complete. Sample predictions:")
        for r in results[:5]:
            match = "Y" if r["pred_genuine"] == r["gold_genuine"] else "N"
            print(f"  {r['id']}  gold={r['gold_type']}  pred={r['pred_type']}  match={match}")


if __name__ == "__main__":
    asyncio.run(main())
