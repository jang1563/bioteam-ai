#!/usr/bin/env python3
"""Evaluate W6 ambiguity runner on contradiction corpus (Gemini live path).

Purpose:
- Validate real runtime behavior of W6 CLASSIFY step under Gemini free-tier path
- Produce binary + per-type metrics comparable to corpus evaluation reports

Usage:
  cd backend
  ../.venv/bin/python -m scripts.evaluate_w6_gemini_live --limit 20
  ../.venv/bin/python -m scripts.evaluate_w6_gemini_live --resume
  ../.venv/bin/python -m scripts.evaluate_w6_gemini_live --reset
  ../.venv/bin/python -m scripts.evaluate_w6_gemini_live --prompt-variant temporal_a
  ../.venv/bin/python -m scripts.evaluate_w6_gemini_live --mode full_w6 --limit 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.agents.ambiguity_engine import AmbiguityEngineAgent
from app.agents.base import BaseAgent
from app.agents.knowledge_manager import KnowledgeManagerAgent
from app.agents.registry import AgentRegistry
from app.config import settings
from app.workflows.runners.w6_ambiguity import W6AmbiguityRunner
from eval_common import GENUINE_TYPES  # noqa: E402
from eval_common import compute_metrics as _compute_metrics_base

ROOT = Path(__file__).resolve().parent
DEFAULT_CORPUS = ROOT / "output" / "v3" / "corpus_final_v14_gate_curated.jsonl"
LEGACY_CORPUS = ROOT / "output" / "v3" / "corpus_final_v4.jsonl"
DEFAULT_OUT_ROOT = ROOT / "output" / "v3"

PROMPT_VARIANT_TO_FILE = {
    "baseline": "ambiguity_engine.md",
    "temporal_a": "ambiguity_engine_temporal_a.md",
    "temporal_b": "ambiguity_engine_temporal_b.md",
}


class DummyLLM:
    """Minimal stub for BaseAgent init. Gemini path handles real completions."""

    def build_cached_system(self, text: str):
        return text

    def estimate_cost(self, *args, **kwargs):
        return 0.0


def _build_runner(prompt_variant: str) -> W6AmbiguityRunner:
    settings.refinement_enabled = False
    settings.ambiguity_llm_provider = "gemini"
    settings.knowledge_manager_llm_provider = "gemini"

    llm = DummyLLM()
    registry = AgentRegistry()

    km_spec = BaseAgent.load_spec("knowledge_manager")
    ae_spec = BaseAgent.load_spec("ambiguity_engine")
    ae_spec.system_prompt_file = PROMPT_VARIANT_TO_FILE[prompt_variant]

    registry.register(KnowledgeManagerAgent(spec=km_spec, llm=llm))
    registry.register(AmbiguityEngineAgent(spec=ae_spec, llm=llm))
    return W6AmbiguityRunner(registry=registry)


def _build_ambiguity_agent(prompt_variant: str) -> AmbiguityEngineAgent:
    settings.refinement_enabled = False
    settings.ambiguity_llm_provider = "gemini"

    ae_spec = BaseAgent.load_spec("ambiguity_engine")
    ae_spec.system_prompt_file = PROMPT_VARIANT_TO_FILE[prompt_variant]
    return AmbiguityEngineAgent(spec=ae_spec, llm=DummyLLM(), memory=None)


def _load_entries(corpus_path: Path, limit: int | None) -> list[dict]:
    entries = [json.loads(line) for line in corpus_path.read_text().splitlines() if line.strip()]
    if limit is not None:
        return entries[:limit]
    return entries


def _load_done(checkpoint_path: Path, entry_ids: set[str]) -> dict[str, dict]:
    if not checkpoint_path.exists():
        return {}
    done: dict[str, dict] = {}
    for line in checkpoint_path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        row_id = row.get("id")
        if row_id in entry_ids:
            done[row_id] = row
    return done


def _pick_pred_type(classify_output: dict, pred_genuine: bool) -> str | None:
    if not pred_genuine:
        return "contextual"

    entries = classify_output.get("entries", [])
    votes: list[str] = []
    for entry in entries:
        for t in entry.get("types", []):
            if t in GENUINE_TYPES:
                votes.append(t)
    if not votes:
        return None
    return Counter(votes).most_common(1)[0][0]


async def run_eval(
    *,
    limit: int | None,
    rpm_sleep: float,
    resume: bool,
    mode: str,
    prompt_variant: str,
    corpus_path: Path,
    checkpoint_path: Path,
) -> list[dict]:
    entries = _load_entries(corpus_path=corpus_path, limit=limit)
    entry_ids = {e["id"] for e in entries}
    done = _load_done(checkpoint_path, entry_ids) if resume else {}
    remaining = [e for e in entries if e["id"] not in done]

    print(
        f"Mode={mode} Variant={prompt_variant} corpus={corpus_path.name} "
        f"Total={len(entries)} Done={len(done)} Remaining={len(remaining)} sleep={rpm_sleep}s"
    )
    if not remaining:
        return list(done.values())

    runner = _build_runner(prompt_variant=prompt_variant) if mode == "full_w6" else None
    ambiguity_agent = (
        _build_ambiguity_agent(prompt_variant=prompt_variant)
        if mode == "classify_only"
        else None
    )

    with checkpoint_path.open("a", encoding="utf-8") as fp:
        for idx, entry in enumerate(remaining, start=1):
            query = f"Claim A: {entry['claim_a']}\nClaim B: {entry['claim_b']}"
            parse_failed = False
            pred_type = None
            pred_genuine = None
            model_version = ""
            total_cost = 0.0
            error = None
            try:
                if mode == "full_w6":
                    assert runner is not None
                    result = await runner.run(query=query)
                    step_results = result.get("step_results", {})
                    classify = step_results.get("CLASSIFY", {})
                    classify_output = classify.get("output", {}) if isinstance(classify, dict) else {}
                    contradictions_found = int(classify_output.get("contradictions_found", 0))
                    pred_genuine = contradictions_found > 0
                    pred_type = _pick_pred_type(classify_output, pred_genuine)
                    model_version = str(classify.get("model_version", ""))
                    total_cost = float(classify.get("cost", 0.0))
                else:
                    assert ambiguity_agent is not None
                    classification = None
                    meta = None
                    for cls_attempt in range(3):
                        try:
                            classification, meta = await ambiguity_agent._classify_pair_llm(
                                claim_a=entry["claim_a"],
                                claim_b=entry["claim_b"],
                                similarity=0.5,
                            )
                            break
                        except Exception:  # pragma: no cover
                            if cls_attempt == 2:
                                raise
                            # Retry transient/parse failures once or twice before hard fail.
                            await asyncio.sleep(0.8)

                    assert classification is not None and meta is not None

                    pred_genuine = bool(classification.is_genuine_contradiction)
                    if pred_genuine:
                        genuine_types = [t for t in classification.types if t in GENUINE_TYPES]
                        pred_type = genuine_types[0] if genuine_types else None
                    else:
                        pred_type = "contextual"
                    model_version = str(getattr(meta, "model_version", "") or "")
                    total_cost = float(getattr(meta, "cost", 0.0) or 0.0)

                if pred_genuine and pred_type not in GENUINE_TYPES:
                    parse_failed = True
                    error = "genuine_without_valid_type"
            except Exception as e:  # pragma: no cover
                parse_failed = True
                error = f"{type(e).__name__}: {e}"

            row = {
                "id": entry["id"],
                "gold_type": entry["contradiction_type"],
                "gold_genuine": entry["is_genuine_contradiction"],
                "domain": entry.get("domain", ""),
                "pred_type": pred_type,
                "pred_genuine": pred_genuine,
                "parse_failed": parse_failed,
                "model_version": model_version,
                "cost": total_cost,
                "error": error,
            }
            done[row["id"]] = row
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
            fp.flush()

            if idx % 5 == 0 or idx == len(remaining):
                ok = sum(1 for r in done.values() if not r["parse_failed"])
                print(f"  {idx}/{len(remaining)} processed | valid={ok}/{len(done)}")
            if rpm_sleep > 0:
                await asyncio.sleep(rpm_sleep)

    return list(done.values())


def compute_metrics(results: list[dict]) -> dict:
    """Compute metrics using shared base, then add runtime-specific fields."""
    metrics = _compute_metrics_base(results)
    valid = [r for r in results if not r.get("parse_failed", False)]
    model_counts = Counter(r.get("model_version", "") for r in valid)
    total_cost = round(sum(float(r.get("cost", 0.0) or 0.0) for r in valid), 6)
    metrics["runtime"] = {
        "model_versions": dict(model_counts),
        "total_cost": total_cost,
    }
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["classify_only", "full_w6"],
        default="classify_only",
        help="classify_only: evaluate ambiguity CLASSIFY behavior only (fast). full_w6: run full W6 pipeline.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum rows to evaluate. If lower than corpus size, report is partial by design.",
    )
    parser.add_argument("--sleep", type=float, default=4.5, help="Seconds between entries.")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument(
        "--prompt-variant",
        choices=sorted(PROMPT_VARIANT_TO_FILE.keys()),
        default="baseline",
        help="Ambiguity prompt variant to evaluate.",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS if DEFAULT_CORPUS.exists() else LEGACY_CORPUS,
        help="Corpus JSONL path. Defaults to v14 gate-curated if present.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory. Default: output/v3/w6_eval[_<variant>].",
    )
    args = parser.parse_args()

    out_dir = args.out_dir
    if out_dir is None:
        suffix = "" if args.prompt_variant == "baseline" else f"_{args.prompt_variant}"
        out_dir = DEFAULT_OUT_ROOT / f"w6_eval{suffix}"

    checkpoint = out_dir / "checkpoint.jsonl"
    results = out_dir / "eval_results.jsonl"
    report = out_dir / "eval_report.json"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.corpus.exists():
        raise FileNotFoundError(f"Corpus not found: {args.corpus}")

    if args.reset:
        for p in (checkpoint, results, report):
            if p.exists():
                p.unlink()

    rows = asyncio.run(
        run_eval(
            limit=args.limit,
            rpm_sleep=args.sleep,
            resume=args.resume,
            mode=args.mode,
            prompt_variant=args.prompt_variant,
            corpus_path=args.corpus,
            checkpoint_path=checkpoint,
        )
    )
    metrics = compute_metrics(rows)
    corpus_total_rows = len(
        [line for line in args.corpus.read_text(encoding="utf-8").splitlines() if line.strip()]
    )
    is_partial_eval = len(rows) < corpus_total_rows
    metrics["eval_config"] = {
        "mode": args.mode,
        "prompt_variant": args.prompt_variant,
        "prompt_file": PROMPT_VARIANT_TO_FILE[args.prompt_variant],
        "corpus_path": str(args.corpus),
        "corpus_total_rows": corpus_total_rows,
        "evaluated_rows": len(rows),
        "is_partial_eval": is_partial_eval,
        "out_dir": str(out_dir),
        "limit": args.limit,
        "sleep": args.sleep,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    with results.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
    report.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")

    b = metrics["binary"]
    print("\nW6 Gemini Live Eval")
    print(
        f"  mode={args.mode} variant={args.prompt_variant} "
        f"prompt={PROMPT_VARIANT_TO_FILE[args.prompt_variant]} "
        f"corpus={args.corpus.name}"
    )
    print(f"  valid={metrics['valid']}/{metrics['total']} parse_failed={metrics['parse_failed']}")
    print(f"  P={b['precision']:.3f} R={b['recall']:.3f} F1={b['f1']:.3f}")
    print(f"  TP={b['tp']} FP={b['fp']} FN={b['fn']} TN={b['tn']}")
    print(f"  model_versions={metrics['runtime']['model_versions']}")
    print(f"  total_cost={metrics['runtime']['total_cost']}")
    if is_partial_eval:
        print(
            f"  WARNING=partial_eval evaluated={len(rows)} "
            f"corpus_total={corpus_total_rows}"
        )
    print(f"  report={report}")


if __name__ == "__main__":
    main()
