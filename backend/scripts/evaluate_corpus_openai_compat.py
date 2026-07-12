#!/usr/bin/env python3
"""
evaluate_corpus_openai_compat.py — Multi-provider cross-evaluation (OpenAI-compatible APIs)

Evaluates contradiction corpus using OpenAI-compatible APIs for independent
cross-model validation. Part of the Panel of LLM Evaluators (PoLL) approach
(Verga et al. 2024, arXiv:2404.18796).

Supported providers:
  - gpt4nano:     GPT-4.1 nano via OpenAI API
  - deepseek:     DeepSeek V3.2 via DeepSeek API (OpenAI-compatible)
  - llama4scout:  Llama 4 Scout via Groq API (OpenAI-compatible)

Uses function_calling (tool_use) for structured output — same schema as
evaluate_corpus_claude.py and evaluate_corpus_gemini.py.

Usage:
  python evaluate_corpus_openai_compat.py --provider gpt4nano --prompt baseline
  python evaluate_corpus_openai_compat.py --provider deepseek --prompt baseline
  python evaluate_corpus_openai_compat.py --provider llama4scout --prompt baseline --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path

from eval_common import (
    VALID_TYPES,
    build_eval_result,
    compute_metrics,
    load_checkpoint,
    parse_gemini_response,
    print_report,
    save_error_analysis,
    write_jsonl,
)
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
log = logging.getLogger(__name__)

# ── Provider configurations ──────────────────────────────────────────────────
PROVIDERS = {
    "gpt4nano": {
        "env_key": "OPENAI_API_KEY",
        "base_url": None,
        "model": "gpt-4.1-nano",
        "sleep": 0.3,
        "display_name": "GPT-4.1 nano",
        "input_cost_per_mtok": 0.20,
        "output_cost_per_mtok": 0.80,
    },
    "deepseek": {
        "env_key": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "sleep": 0.3,
        "display_name": "DeepSeek V3.2",
        "input_cost_per_mtok": 0.28,
        "output_cost_per_mtok": 0.42,
    },
    "llama4scout": {
        "env_key": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "sleep": 0.5,
        "display_name": "Llama 4 Scout (Groq)",
        "input_cost_per_mtok": 0.11,
        "output_cost_per_mtok": 0.34,
    },
}

DEFAULT_CORPUS = Path(__file__).parent / "output" / "v3" / "corpus_final.jsonl"

# ── Tool schema (OpenAI function_calling format) ─────────────────────────────
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "classify_contradiction",
        "description": "Classify the contradiction between two biomedical claims",
        "parameters": {
            "type": "object",
            "properties": {
                "contradiction_type": {
                    "type": "string",
                    "enum": ["direct", "magnitude", "methodological", "temporal", "contextual"],
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score 0.0-1.0",
                },
                "is_genuine_contradiction": {"type": "boolean"},
                "rationale": {
                    "type": "string",
                    "description": "2-3 sentence explanation",
                },
            },
            "required": ["contradiction_type", "confidence", "is_genuine_contradiction", "rationale"],
        },
    },
}

# ── Prompts (reuse Gemini prompts, adapt for function_calling) ───────────────
from evaluate_corpus_gemini import PROMPTS as _GEMINI_PROMPTS  # noqa: E402

PROMPTS: dict[str, tuple[str, str]] = {}
for _key, (_sys, _usr) in _GEMINI_PROMPTS.items():
    # Remove last 2 lines (JSON output instruction) and add function_calling instruction
    _usr_adapted = (
        _usr.rsplit("\n", 2)[0].rstrip()
        + "\n\nUse the classify_contradiction function to report your classification."
    )
    PROMPTS[_key] = (_sys, _usr_adapted)


# ── Classification ───────────────────────────────────────────────────────────
def classify_one(
    client: OpenAI,
    model: str,
    entry: dict,
    system_prompt: str,
    user_template: str,
) -> tuple[dict | None, dict]:
    """Classify one corpus entry via OpenAI-compatible function_calling.

    Returns (prediction_dict, usage_dict). prediction_dict is None on failure.
    """
    user_msg = user_template.format(
        claim_a=entry["claim_a"][:400],
        claim_b=entry["claim_b"][:400],
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            tools=[TOOL_SCHEMA],
            tool_choice={"type": "function", "function": {"name": "classify_contradiction"}},
            max_tokens=512,
            temperature=0.0,
        )

        # Extract usage
        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens or 0,
                "output_tokens": response.usage.completion_tokens or 0,
            }

        # Extract tool call
        message = response.choices[0].message
        if not message.tool_calls:
            log.warning("No tool_calls for %s", entry["id"])
            return None, usage

        tool_call = message.tool_calls[0]
        if tool_call.function.name != "classify_contradiction":
            log.warning("Wrong function name '%s' for %s", tool_call.function.name, entry["id"])
            return None, usage

        args = json.loads(tool_call.function.arguments)
        ct = (args.get("contradiction_type") or "").strip().lower()
        if ct not in VALID_TYPES:
            log.warning("Invalid type '%s' for %s", ct, entry["id"])
            return None, usage

        pred = {
            "contradiction_type": ct,
            "confidence": float(args.get("confidence", 0.0)),
            "is_genuine_contradiction": bool(args.get("is_genuine_contradiction", False)),
            "rationale": str(args.get("rationale", "")),
        }
        return pred, usage

    except json.JSONDecodeError as e:
        log.warning("JSON parse error for %s: %s", entry["id"], e)
        return None, {}
    except Exception as e:
        # Handle Groq/Llama tool_use_failed: extract JSON from failed_generation
        err_str = str(e)
        if "tool_use_failed" in err_str and "failed_generation" in err_str:
            pred = _parse_failed_generation(err_str, entry["id"])
            if pred:
                return pred, {}
        log.warning("API error for %s: %s", entry["id"], e)
        return None, {}


def _parse_failed_generation(err_str: str, entry_id: str) -> dict | None:
    """Extract classification from Groq's failed_generation error.

    When Llama generates reasoning before calling the function,
    Groq returns the full text in 'failed_generation'. We extract
    the JSON parameters from it.
    """
    import re

    # Try to find the parameters JSON block within the error
    # Pattern: "parameters": { ... }
    m = re.search(r'"parameters"\s*:\s*(\{(?:[^{}]|\{[^{}]*\})*\})', err_str)
    if not m:
        # Also try direct field extraction
        return parse_gemini_response(err_str)

    params_str = m.group(1)
    try:
        args = json.loads(params_str)
    except json.JSONDecodeError:
        # Fallback: regex extraction from the full error string
        return parse_gemini_response(err_str)

    ct = (args.get("contradiction_type") or "").strip().lower()
    if ct not in VALID_TYPES:
        return None

    genuine = args.get("is_genuine_contradiction")
    if genuine is None:
        # Try to infer from partial data
        return None

    log.info("Recovered from failed_generation for %s: type=%s genuine=%s", entry_id, ct, genuine)
    return {
        "contradiction_type": ct,
        "confidence": float(args.get("confidence", 0.0)),
        "is_genuine_contradiction": bool(genuine),
        "rationale": str(args.get("rationale", "[recovered from failed_generation]")),
    }


# ── Evaluation loop ──────────────────────────────────────────────────────────
def run_evaluation(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_template: str,
    corpus_path: Path,
    eval_dir: Path,
    sleep_time: float,
    dry_run: bool = False,
) -> tuple[list[dict], dict]:
    """Run evaluation loop with checkpoint resume. Returns (results, total_usage)."""
    eval_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_file = eval_dir / "checkpoint.jsonl"

    entries = [json.loads(l) for l in corpus_path.read_text().splitlines() if l.strip()]
    if dry_run:
        entries = entries[:5]
        log.info("DRY RUN: evaluating first 5 entries only")

    entry_ids = {e["id"] for e in entries}
    done = load_checkpoint(checkpoint_file, valid_ids=entry_ids)

    remaining = [e for e in entries if e["id"] not in done]
    log.info("Corpus: %d | Done: %d | Remaining: %d", len(entries), len(done), len(remaining))

    if not remaining:
        return list(done.values()), {"input_tokens": 0, "output_tokens": 0}

    ok = parse_fail = 0
    total_usage = {"input_tokens": 0, "output_tokens": 0}

    with open(checkpoint_file, "a") as checkpoint_f:
        for i, entry in enumerate(remaining):
            pred, usage = classify_one(client, model, entry, system_prompt, user_template)
            result = build_eval_result(entry, pred)

            total_usage["input_tokens"] += usage.get("input_tokens", 0)
            total_usage["output_tokens"] += usage.get("output_tokens", 0)

            if pred:
                ok += 1
                # Only checkpoint successful evaluations; failed entries will be retried on resume
                done[entry["id"]] = result
                checkpoint_f.write(json.dumps(result) + "\n")
                checkpoint_f.flush()
            else:
                parse_fail += 1

            if (i + 1) % 20 == 0 or (i + 1) == len(remaining):
                evaluable = [r for r in done.values() if not r["parse_failed"]]
                binary_correct = sum(1 for r in evaluable if r["pred_genuine"] == r["gold_genuine"])
                acc = 100 * binary_correct / max(1, len(evaluable))
                log.info("  %d/%d | ok=%d fail=%d | acc=%.1f%%", i + 1, len(remaining), ok, parse_fail, acc)

            time.sleep(sleep_time)
    log.info("Evaluation complete: ok=%d parse_fail=%d", ok, parse_fail)
    return list(done.values()), total_usage


# ── Entry point ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Multi-provider cross-evaluation (OpenAI-compatible APIs)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python evaluate_corpus_openai_compat.py --provider gpt4nano --prompt baseline
  python evaluate_corpus_openai_compat.py --provider deepseek --prompt baseline --dry-run
  python evaluate_corpus_openai_compat.py --provider llama4scout --prompt baseline""",
    )
    parser.add_argument(
        "--provider", required=True, choices=list(PROVIDERS.keys()),
        help="Provider to use for evaluation",
    )
    parser.add_argument("--prompt", choices=list(PROMPTS.keys()), default="baseline")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--eval-dir", type=Path, default=None, help="Override output directory")
    parser.add_argument("--sleep", type=float, default=None, help="Override sleep between requests")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    prov = PROVIDERS[args.provider]

    # Resolve API key
    api_key = os.environ.get(prov["env_key"], "")
    if not api_key:
        raise RuntimeError(f"Set {prov['env_key']} environment variable.")

    # Build client
    client_kwargs = {"api_key": api_key}
    if prov["base_url"]:
        client_kwargs["base_url"] = prov["base_url"]
    client = OpenAI(**client_kwargs)

    model = prov["model"]
    sleep_time = args.sleep if args.sleep is not None else prov["sleep"]

    # Resolve eval directory
    if args.eval_dir:
        eval_dir = args.eval_dir
    else:
        eval_dir = Path(__file__).parent / "output" / "v3" / f"eval_{args.provider}_{args.prompt}"

    corpus_path = args.corpus
    results_file = eval_dir / "eval_results.jsonl"
    report_file = eval_dir / "eval_report.json"
    misclassified_file = eval_dir / "misclassified.jsonl"
    cost_file = eval_dir / "cost_summary.json"

    system_prompt, user_template = PROMPTS[args.prompt]

    checkpoint_file = eval_dir / "checkpoint.jsonl"
    if args.reset and checkpoint_file.exists():
        checkpoint_file.unlink()
        log.info("Checkpoint cleared.")

    with open(corpus_path) as f:
        n_entries = sum(1 for l in f if l.strip())
    est_time = n_entries * sleep_time / 60
    print(f"\nCross-Evaluation — {prov['display_name']} [{args.prompt}]")
    print(f"{corpus_path.name} | {n_entries} entries | ~{est_time:.1f} min")
    print(f"Model: {model} | Sleep: {sleep_time}s")

    results, total_usage = run_evaluation(
        client=client,
        model=model,
        system_prompt=system_prompt,
        user_template=user_template,
        corpus_path=corpus_path,
        eval_dir=eval_dir,
        sleep_time=sleep_time,
        dry_run=args.dry_run,
    )

    # Cost summary
    input_cost = total_usage["input_tokens"] * prov["input_cost_per_mtok"] / 1_000_000
    output_cost = total_usage["output_tokens"] * prov["output_cost_per_mtok"] / 1_000_000
    total_cost = input_cost + output_cost
    n_evaluated = sum(1 for r in results if not r.get("parse_failed", True))

    cost_summary = {
        "provider": args.provider,
        "model": model,
        "display_name": prov["display_name"],
        "prompt_variant": args.prompt,
        "total_input_tokens": total_usage["input_tokens"],
        "total_output_tokens": total_usage["output_tokens"],
        "input_cost_usd": round(input_cost, 4),
        "output_cost_usd": round(output_cost, 4),
        "total_cost_usd": round(total_cost, 4),
        "entries_evaluated": len(results),
        "avg_input_tokens_per_entry": (
            round(total_usage["input_tokens"] / max(1, n_evaluated))
            if total_usage["input_tokens"] > 0 else 0
        ),
        "avg_output_tokens_per_entry": (
            round(total_usage["output_tokens"] / max(1, n_evaluated))
            if total_usage["output_tokens"] > 0 else 0
        ),
    }

    if not args.dry_run:
        metrics = compute_metrics(results)
        print_report(
            metrics,
            corpus_name=corpus_path.name,
            note=f"Cross-model evaluation — {prov['display_name']} (corpus classified by Gemini)",
        )
        save_error_analysis(results, corpus_path, misclassified_file)
        write_jsonl(results, results_file)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, "w") as f:
            json.dump(metrics, f, indent=2)
        with open(cost_file, "w") as f:
            json.dump(cost_summary, f, indent=2)
        log.info("Results -> %s", results_file)
        log.info("Report  -> %s", report_file)
        log.info("Cost    -> %s  ($%.4f)", cost_file, total_cost)
    else:
        print("\nDRY RUN complete. Sample predictions:")
        for r in results[:5]:
            match = "Y" if r["pred_genuine"] == r["gold_genuine"] else "N"
            print(f"  {r['id']}  gold={r['gold_type']}  pred={r['pred_type']}  match={match}")
        if total_usage["input_tokens"] > 0:
            print(f"\nToken usage: input={total_usage['input_tokens']} output={total_usage['output_tokens']}")
            print(f"Estimated full-run cost: ${total_cost * n_entries / max(1, len(results)):.4f}")


if __name__ == "__main__":
    main()
