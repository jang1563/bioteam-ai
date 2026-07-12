#!/usr/bin/env python3
"""
evaluate_corpus_claude.py — Claude Haiku Cross-Evaluation of Contradiction Corpus

Evaluates corpus_final.jsonl using Claude Haiku (claude-haiku-4-5-20251001).
Provides independent cross-model evaluation to remove circular bias
from the Gemini-classified + Gemini-evaluated pipeline.

Uses Anthropic SDK tool_use for structured output.

Usage:
  python evaluate_corpus_claude.py --prompt baseline
  python evaluate_corpus_claude.py --prompt contrastive --dry-run
"""
import argparse
import json
import logging
import os
import time
from pathlib import Path

import anthropic
from eval_common import (
    VALID_TYPES,
    build_eval_result,
    compute_metrics,
    load_checkpoint,
    print_report,
    save_error_analysis,
    write_jsonl,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
MODEL = "claude-haiku-4-5-20251001"
DEFAULT_SLEEP = 0.5
DEFAULT_CORPUS = Path(__file__).parent / "output" / "v3" / "corpus_final.jsonl"
DEFAULT_EVAL_DIR = Path(__file__).parent / "output" / "v3" / "eval_claude_baseline"

TOOL_SCHEMA = {
    "name": "classify_contradiction",
    "description": "Classify the contradiction between two biomedical claims",
    "input_schema": {
        "type": "object",
        "properties": {
            "contradiction_type": {
                "type": "string",
                "enum": ["direct", "magnitude", "methodological", "temporal", "contextual"],
            },
            "confidence": {"type": "number", "description": "Confidence score 0.0-1.0"},
            "is_genuine_contradiction": {"type": "boolean"},
            "rationale": {"type": "string", "description": "2-3 sentence explanation"},
        },
        "required": ["contradiction_type", "confidence", "is_genuine_contradiction", "rationale"],
    },
}

# ── Prompts (reuse Gemini prompts, replace output instruction) ────────────────
from evaluate_corpus_gemini import PROMPTS as _GEMINI_PROMPTS  # noqa: E402

PROMPTS: dict[str, tuple[str, str]] = {}
for _key, (_sys, _usr) in _GEMINI_PROMPTS.items():
    # Remove last 2 lines ("Output ONLY a JSON..." + JSON example) and add tool instruction
    _usr_claude = _usr.rsplit("\n", 2)[0].rstrip() + "\n\nUse the classify_contradiction tool to report your classification."
    PROMPTS[_key] = (_sys, _usr_claude)


# ── Classification ────────────────────────────────────────────────────────────
def classify_one(
    client: anthropic.Anthropic,
    entry: dict,
    system_prompt: str,
    user_template: str,
) -> dict | None:
    """Classify one corpus entry using Claude Haiku tool_use."""
    user_msg = user_template.format(
        claim_a=entry["claim_a"][:400],
        claim_b=entry["claim_b"][:400],
    )
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
            tools=[TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "classify_contradiction"},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "classify_contradiction":
                inp = block.input
                ct = inp.get("contradiction_type", "")
                if ct not in VALID_TYPES:
                    log.warning("Invalid type '%s' for %s", ct, entry["id"])
                    return None
                return {
                    "contradiction_type": ct,
                    "confidence": float(inp.get("confidence", 0.0)),
                    "is_genuine_contradiction": bool(inp.get("is_genuine_contradiction", False)),
                    "rationale": str(inp.get("rationale", "")),
                }
        log.warning("No tool_use block for %s", entry["id"])
        return None
    except Exception as e:
        log.warning("API error for %s: %s", entry["id"], e)
        return None


# ── Evaluation loop ───────────────────────────────────────────────────────────
def run_evaluation(
    client: anthropic.Anthropic,
    system_prompt: str,
    user_template: str,
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
        log.info("DRY RUN: evaluating first 5 entries only")

    entry_ids = {e["id"] for e in entries}
    done = load_checkpoint(checkpoint_file, valid_ids=entry_ids)

    remaining = [e for e in entries if e["id"] not in done]
    log.info("Corpus: %d | Done: %d | Remaining: %d", len(entries), len(done), len(remaining))

    if not remaining:
        return list(done.values())

    checkpoint_f = open(checkpoint_file, "a")
    ok = parse_fail = 0

    for i, entry in enumerate(remaining):
        pred = classify_one(client, entry, system_prompt, user_template)
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

        time.sleep(sleep_time)

    checkpoint_f.close()
    log.info("Evaluation complete: ok=%d parse_fail=%d", ok, parse_fail)
    return list(done.values())


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Claude Haiku cross-evaluation")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR)
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP)
    parser.add_argument("--prompt", choices=list(PROMPTS.keys()), default="baseline")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("Set ANTHROPIC_API_KEY environment variable.")

    client = anthropic.Anthropic(api_key=api_key)
    corpus_path = args.corpus
    eval_dir = args.eval_dir
    results_file = eval_dir / "eval_results.jsonl"
    report_file = eval_dir / "eval_report.json"
    misclassified_file = eval_dir / "misclassified.jsonl"

    system_prompt, user_template = PROMPTS[args.prompt]

    checkpoint_file = eval_dir / "checkpoint.jsonl"
    if args.reset and checkpoint_file.exists():
        checkpoint_file.unlink()
        log.info("Checkpoint cleared.")

    n_entries = len([l for l in open(corpus_path) if l.strip()])
    print(f"\nCross-Evaluation — Claude Haiku [{args.prompt}]")
    print(f"{corpus_path.name} | {n_entries} entries | ~{n_entries * args.sleep / 60:.1f} min")

    results = run_evaluation(
        client=client,
        system_prompt=system_prompt,
        user_template=user_template,
        corpus_path=corpus_path,
        eval_dir=eval_dir,
        sleep_time=args.sleep,
        dry_run=args.dry_run,
    )

    if not args.dry_run:
        metrics = compute_metrics(results)
        print_report(metrics, corpus_name=corpus_path.name,
                     note="Independent cross-model evaluation (corpus classified by Gemini)")
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
    main()
