#!/usr/bin/env python3
"""
evaluate_corpus_gemini.py — Corpus Difficulty Validation (Gemini-as-judge)

Evaluates corpus_final_v4.jsonl using Gemini 2.5 Flash (free tier).

PURPOSE:
  - LLM baseline for contradiction detection on this corpus
  - Corpus difficulty and self-consistency validation
  - Per-type hardness analysis to guide future corpus improvement

IMPORTANT LIMITATION:
  Corpus was classified BY Gemini → this partly measures self-consistency.
  High scores indicate corpus is internally consistent; does NOT confirm
  ground truth accuracy. For ground-truth evaluation, use a different model.

  Mitigation: evaluation prompt is intentionally different from
  the classification prompt (no type_hint, different framing, reasoning-first).

Usage:
  python evaluate_corpus_gemini.py
  python evaluate_corpus_gemini.py --dry-run   # test first 5 entries only
  python evaluate_corpus_gemini.py --reset      # clear checkpoint, start fresh

Output:
  output/v3/eval/checkpoint.jsonl       — progress (resume-safe)
  output/v3/eval/eval_results.jsonl     — per-entry predictions
  output/v3/eval/eval_report.json       — aggregated metrics
  output/v3/eval/misclassified.jsonl    — error analysis
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

import httpx
from eval_common import (
    build_eval_result,
    compute_metrics,
    load_checkpoint,
    parse_gemini_response,
    print_report,
    save_error_analysis,
    write_jsonl,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# ── Config ────────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"gemini-2.5-flash:generateContent?key={API_KEY}"
)
DEFAULT_SLEEP = 4.5  # seconds — stays under 15 RPM free tier limit
DEFAULT_CORPUS = Path(__file__).parent / "output" / "v3" / "corpus_final_v4.jsonl"
DEFAULT_EVAL_DIR = Path(__file__).parent / "output" / "v3" / "eval"

# ── Prompt variants ───────────────────────────────────────────────────────────
# Selected at runtime via --prompt flag

PROMPTS: dict[str, tuple[str, str]] = {}

# --- baseline: original zero-shot prompt ---
PROMPTS["baseline"] = (
"""\
You are a biomedical scientist reviewing pairs of scientific claims extracted from
research paper abstracts.

Your task: determine whether the two claims GENUINELY contradict each other, or
whether apparent differences are explained by different biological contexts,
experimental conditions, or study populations.

A GENUINE contradiction = both claims study the SAME phenomenon under the SAME
conditions but assert INCOMPATIBLE findings. If differences can be explained by
context (different cell lines, species, patient populations, conditions), it is
NOT a genuine contradiction.

Contradiction categories (assign only if genuine):
  direct:          Opposite directional effects on the same target/phenomenon
  temporal:        Results differ specifically because of time-point or disease stage
  magnitude:       Same direction of effect but incompatible effect sizes
  methodological:  Same research question, different measurement methods yield
                   opposite or incompatible conclusions
  contextual:      Different biological contexts explain the difference
                   → is_genuine_contradiction = false
""",
"""\
Claim A: {claim_a}

Claim B: {claim_b}

Evaluate step by step:
1. Are both claims about the same phenomenon in the same biological context?
2. Do they assert incompatible findings, or can context fully explain the difference?
3. If genuinely contradictory, which category fits best?

Output ONLY a JSON object (no markdown, no extra text):
{{"is_genuine_contradiction": true, "contradiction_type": "direct", "confidence": 0.90, "rationale": "1-2 sentences"}}"""
)

# --- contrastive: decision-tree + contrastive definitions + few-shot examples ---
PROMPTS["contrastive"] = (
"""\
You are a biomedical literature expert classifying contradictions between scientific claims.

DECISION PROCEDURE — follow these steps IN ORDER. Stop at the first YES.

STEP 1  METHODOLOGICAL?
  Are two DIFFERENT measurement methods, assays, imaging modalities, or analytical
  techniques being compared (e.g., MRI vs CT, RNA-seq vs microarray, ELISA vs PCR)?
  And do they yield different results for the SAME biological question?
  → YES = methodological.  Do NOT call this "direct."

STEP 2  TEMPORAL?
  Do the claims describe the SAME system but at DIFFERENT time-points, phases, or
  stages (e.g., acute vs chronic, baseline vs follow-up, early vs late, 3 days vs
  4 hours)?  Time-point differences are GENUINE contradictions, NOT contextual.
  Different biological contexts (species, cell type, organ) are contextual.
  → YES = temporal.  Do NOT call this "contextual."

STEP 3  MAGNITUDE?
  Do BOTH claims agree on the DIRECTION of an effect (both say it increases, or both
  say it exists) but DISAGREE on HOW LARGE or HOW SIGNIFICANT it is?
  Examples: "significant reduction" vs "modest/non-significant effect";
  "strong association" vs "weak/inconsistent association."
  → YES = magnitude.  Do NOT call this "direct."

STEP 4  CONTEXTUAL?
  Can the difference be fully explained by different biological contexts: different
  species, cell lines, patient populations, organs, or experimental conditions?
  → YES = contextual.  is_genuine_contradiction = false.

STEP 5  If none of the above: DIRECT.
  The claims assert opposite directional effects on the same target under the same
  conditions (one says "increases" and the other says "decreases").

EXAMPLES:

methodological (NOT direct):
  A: "MRI showed high sensitivity (92%) for detecting liver metastases"
  B: "CT had lower sensitivity (74%) for the same lesions"
  Reason: Different imaging methods compared → methodological.

temporal (NOT contextual):
  A: "Acute treatment increased oxidative stress genes"
  B: "Chronic treatment increased cytoskeletal and ECM genes"
  Reason: Same system, different time-points → temporal. Time is NOT "context."

magnitude (NOT direct):
  A: "Statin use was associated with significant risk reduction of liver cancer"
  B: "This preventive effect might be overestimated due to confounding"
  Reason: Both acknowledge an effect exists but disagree on its true size → magnitude.

direct:
  A: "Gene X overexpression increases tumor growth"
  B: "Gene X overexpression decreases tumor growth"
  Reason: Same gene, same condition, opposite direction → direct.

contextual (not genuine):
  A: "In mice, compound Y reduced inflammation"
  B: "In human trials, compound Y showed no anti-inflammatory effect"
  Reason: Different species → contextual, not a genuine contradiction.
""",
"""\
Claim A: {claim_a}

Claim B: {claim_b}

Follow the 5-step decision procedure above. Answer each step:
1. METHODOLOGICAL? Are different methods/techniques being compared?
2. TEMPORAL? Do claims differ by time-point/phase/stage?
3. MAGNITUDE? Same direction but different effect size/significance?
4. CONTEXTUAL? Different biological contexts explain the difference?
5. If none above → DIRECT (opposite direction, same conditions).

Output ONLY a JSON object (no markdown, no extra text):
{{"is_genuine_contradiction": true, "contradiction_type": "methodological", "confidence": 0.90, "rationale": "Step 1: yes, MRI vs CT compared"}}"""
)

# --- contextual_first: contextual check FIRST, then genuine types ---
PROMPTS["contextual_first"] = (
"""\
You are a biomedical literature expert classifying contradictions between scientific claims.

DECISION PROCEDURE — follow these steps IN ORDER. Stop at the first YES.

STEP 1  CONTEXTUAL? (CHECK THIS FIRST — most claim pairs are contextual)
  Do the two claims describe findings from DIFFERENT biological contexts?
  Different contexts include ANY of:
    - Different species, strains, or cell lines (e.g., mice vs humans)
    - Different tissues, organs, or cellular compartments (e.g., muscle vs plasma)
    - Different doses, concentrations, or treatment intensities (e.g., moderate vs excessive)
    - Different genetic variants, isoforms, or mutants (e.g., apoE3 vs apoE4)
    - Different experimental conditions (in vivo vs in vitro, treated vs untreated)
    - One claim describes a general pattern while the other a specific exception/subset
    - Different cell types or immune populations (e.g., Treg vs B cells)
  If ANY of these contextual differences exist → contextual.
  is_genuine_contradiction = false.
  IMPORTANT: When in doubt between contextual and genuine, choose contextual.
  NOTE: Time-point differences (acute vs chronic, early vs late) are NOT contextual — see Step 3.

STEP 2  METHODOLOGICAL?
  Are two DIFFERENT measurement methods, assays, imaging modalities, or analytical
  techniques being compared, AND they yield different results for the SAME biological
  question in the SAME biological context (same species, tissue, conditions)?
  → YES = methodological.

STEP 3  TEMPORAL?
  Do the claims describe the SAME system in the SAME biological context but at
  DIFFERENT time-points, phases, or disease stages (e.g., acute vs chronic,
  baseline vs follow-up, early vs late, day 3 vs day 14)?
  Time-point differences are GENUINE contradictions, NOT contextual.
  The biological context (species, tissue, cell type) must be identical — only time differs.
  → YES = temporal.

STEP 4  MAGNITUDE?
  Do BOTH claims agree on the DIRECTION of an effect (both say it increases, or both
  say it exists) but DISAGREE on HOW LARGE or HOW SIGNIFICANT it is?
  → YES = magnitude.

STEP 5  If none of the above: DIRECT.
  The claims assert opposite directional effects on the same target under the same
  conditions (one says "increases" and the other says "decreases").

EXAMPLES:

contextual (NOT genuine — different tissue compartments):
  A: "NO2- levels increased in heart and skeletal muscles during exercise"
  B: "No significant changes were observed in plasma NO2- levels"
  Reason: Different tissue compartments (muscle vs plasma) → contextual.

contextual (NOT genuine — different treatment intensities):
  A: "Moderate exercise training enhances immunocompetence"
  B: "Excessive training leads to immunosuppression"
  Reason: Different exercise intensities (moderate vs excessive) → contextual.

contextual (NOT genuine — general pattern vs specific subset):
  A: "Endocrine pathway dysregulation observed (insulin, leptin, CCK defects)"
  B: "GLP-1 receptor responsiveness was preserved"
  Reason: General dysregulation vs one preserved pathway is a subset, not contradiction.

methodological:
  A: "MRI showed high sensitivity (92%) for detecting liver metastases"
  B: "CT had lower sensitivity (74%) for the same lesions"
  Reason: Same biological question, same context, different imaging methods → methodological.

temporal (NOT contextual — time is not context):
  A: "Acute treatment increased oxidative stress genes"
  B: "Chronic treatment increased cytoskeletal and ECM genes"
  Reason: Same system, same context, different time-points → temporal.

magnitude:
  A: "Statin use was associated with significant risk reduction of liver cancer"
  B: "This preventive effect might be overestimated due to confounding"
  Reason: Both acknowledge an effect exists but disagree on its true size → magnitude.

direct:
  A: "Gene X overexpression increases tumor growth"
  B: "Gene X overexpression decreases tumor growth"
  Reason: Same gene, same condition, opposite direction → direct.
""",
"""\
Claim A: {claim_a}

Claim B: {claim_b}

Follow the decision procedure. Check Step 1 (CONTEXTUAL) FIRST:
1. CONTEXTUAL? Are there ANY differences in biological context (species, tissue, dose, cell type, variant, condition, subset)?
2. METHODOLOGICAL? Same context but different methods/techniques compared?
3. TEMPORAL? Same context but different time-points/phases/stages?
4. MAGNITUDE? Same direction but different effect size/significance?
5. If none above → DIRECT (opposite direction, same conditions).

Output ONLY a JSON object (no markdown, no extra text):
{{"is_genuine_contradiction": false, "contradiction_type": "contextual", "confidence": 0.90, "rationale": "Step 1: yes, different tissue compartments"}}"""
)

# Active prompt (set by CLI)
_SYSTEM, _USER = PROMPTS["baseline"]


# ── Gemini API call ────────────────────────────────────────────────────────────
async def _call_gemini(client: httpx.AsyncClient, entry: dict) -> dict | None:
    payload = {
        "contents": [{"role": "user", "parts": [{"text": _USER.format(
            claim_a=entry["claim_a"][:400],
            claim_b=entry["claim_b"][:400],
        )}]}],
        "systemInstruction": {"parts": [{"text": _SYSTEM}]},
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 768,  # contrastive prompt needs longer responses
            "thinkingConfig": {"thinkingBudget": 0},  # prevent token truncation
        },
    }
    try:
        resp = await client.post(API_URL, json=payload, timeout=45.0)
        resp.raise_for_status()
        data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            log.warning("No candidates for %s: %s", entry["id"], data.get("promptFeedback", ""))
            return None

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return None

        text = parts[0].get("text", "")
        result = parse_gemini_response(text)
        if not result:
            log.warning("Unparseable for %s: %r", entry["id"], text[:100])
        return result

    except Exception as e:
        log.warning("API error for %s: %s", entry["id"], e)
        return None


# ── Main evaluation loop ───────────────────────────────────────────────────────
async def run_evaluation(
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

    log.info("Estimated time: %.0f min (%.1f sec/entry)", len(remaining) * sleep_time / 60, sleep_time)

    checkpoint_f = open(checkpoint_file, "a")
    ok = parse_fail = 0

    async with httpx.AsyncClient(timeout=60) as client:
        for i, entry in enumerate(remaining):
            pred = await _call_gemini(client, entry)
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
                binary_correct = sum(
                    1 for r in evaluable if r["pred_genuine"] == r["gold_genuine"]
                )
                acc = 100 * binary_correct / max(1, len(evaluable))
                log.info(
                    "  %d/%d | parse_ok=%d fail=%d | binary_acc=%.1f%%",
                    i + 1, len(remaining), ok, parse_fail, acc,
                )

            await asyncio.sleep(sleep_time)

    checkpoint_f.close()
    log.info("Evaluation complete: ok=%d parse_fail=%d", ok, parse_fail)
    return list(done.values())


# ── Hybrid merge (offline) ─────────────────────────────────────────────────────
def merge_hybrid_offline(
    baseline_ckpt: Path,
    contrastive_ckpt: Path,
    corpus_path: Path,
    output_dir: Path,
) -> list[dict]:
    """Merge baseline binary decisions with contrastive type predictions.

    Uses baseline's is_genuine_contradiction for binary classification and
    contrastive's contradiction_type for type assignment on genuine entries.
    No API calls needed — works entirely from existing checkpoint files.
    """
    base = {}
    for line in open(baseline_ckpt):
        if line.strip():
            r = json.loads(line)
            base[r["id"]] = r

    cont = {}
    for line in open(contrastive_ckpt):
        if line.strip():
            r = json.loads(line)
            cont[r["id"]] = r

    corpus = [json.loads(l) for l in open(corpus_path) if l.strip()]

    results = []
    skipped = 0
    for entry in corpus:
        eid = entry["id"]
        b = base.get(eid)
        c = cont.get(eid)
        if not b or not c:
            skipped += 1
            continue

        pred_genuine = b["pred_genuine"]
        # Use contrastive type when baseline says genuine; otherwise contextual
        if pred_genuine and c["pred_type"] and not c["parse_failed"]:
            pred_type = c["pred_type"]
        else:
            pred_type = "contextual"

        results.append({
            "id": eid,
            "gold_type": entry["contradiction_type"],
            "gold_genuine": entry["is_genuine_contradiction"],
            "domain": entry.get("domain", ""),
            "pred_type": pred_type,
            "pred_genuine": pred_genuine,
            "pred_confidence": b.get("pred_confidence"),
            "pred_rationale": "[hybrid]",
            "parse_failed": False,
        })

    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "eval_results.jsonl", "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    log.info("Hybrid merge: %d entries merged, %d skipped (no overlap)", len(results), skipped)
    return results


# ── Entry point ────────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR)
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP)
    parser.add_argument("--prompt", choices=list(PROMPTS.keys()), default="baseline")
    parser.add_argument("--mode", choices=["evaluate", "hybrid_merge"], default="evaluate")
    parser.add_argument("--baseline-ckpt", type=Path)
    parser.add_argument("--contrastive-ckpt", type=Path)
    args = parser.parse_args()

    corpus_path = args.corpus
    eval_dir = args.eval_dir
    results_file = eval_dir / "eval_results.jsonl"
    report_file = eval_dir / "eval_report.json"
    misclassified_file = eval_dir / "misclassified.jsonl"

    # ── Hybrid merge mode (no API calls) ──
    if args.mode == "hybrid_merge":
        if not args.baseline_ckpt or not args.contrastive_ckpt:
            raise RuntimeError("hybrid_merge requires --baseline-ckpt and --contrastive-ckpt")
        results = merge_hybrid_offline(args.baseline_ckpt, args.contrastive_ckpt, corpus_path, eval_dir)
        metrics = compute_metrics(results)
        print_report(metrics, corpus_name=corpus_path.name)
        save_error_analysis(results, corpus_path, misclassified_file)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, "w") as f:
            json.dump(metrics, f, indent=2)
        log.info("Hybrid report -> %s", report_file)
        return

    # ── Standard evaluation mode ──
    global _SYSTEM, _USER
    _SYSTEM, _USER = PROMPTS[args.prompt]
    log.info("Prompt variant: %s", args.prompt)

    if not API_KEY:
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY.")

    checkpoint_file = eval_dir / "checkpoint.jsonl"
    if args.reset and checkpoint_file.exists():
        checkpoint_file.unlink()
        log.info("Checkpoint cleared.")

    n_entries = len([l for l in open(corpus_path) if l.strip()])
    est = n_entries * args.sleep / 60
    print(f"\nCorpus Difficulty Validation — Gemini [{args.prompt}]")
    print(f"{corpus_path.name} | {n_entries} entries | ~{est:.0f} min | checkpoint-safe")

    results = await run_evaluation(
        corpus_path=corpus_path,
        eval_dir=eval_dir,
        sleep_time=args.sleep,
        dry_run=args.dry_run,
    )

    if not args.dry_run:
        metrics = compute_metrics(results)
        print_report(metrics, corpus_name=corpus_path.name,
                     note="corpus classified by Gemini -> partly measures self-consistency")
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
            print(f"  {r['id']}  gold={r['gold_type']}  "
                  f"pred={r['pred_type']}  conf={r['pred_confidence']}  match={match}")


if __name__ == "__main__":
    asyncio.run(main())
