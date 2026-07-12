"""Published baseline results from external benchmarks for comparison.

Sources:
  - GenoTEX: arXiv:2406.15341 (GenoTEX, 2024)
  - GenoMAS: arXiv:2507.21035 (GenoMAS, 2025) — extended GenoTEX evaluation
  - BioAgent Bench: arXiv:2601.21800 (BioAgent Bench, 2026)

Baselines are hardcoded from published papers so that W9 results can be
compared without re-running external tool pipelines.
"""

from __future__ import annotations

from typing import Any

# Published baseline results keyed by benchmark name or dataset ID
PUBLISHED_BASELINES: dict[str, dict[str, Any]] = {
    # ── GenoTEX ──────────────────────────────────────────────────────────
    # Gene-trait association (unconditional, 132 traits)
    # Metric: Gene F1 on end-to-end pipeline evaluation
    "genotex": {
        "metric": "gene_f1",
        "description": "GenoTEX unconditional gene-trait association (132 traits)",
        "baselines": {
            "Human Expert": {"score": 0.7163, "source": "GenoMAS (2025)"},
            "GenoMAS (SOTA)": {"score": 0.6048, "source": "arXiv:2507.21035"},
            "Claude Sonnet 4 Thinking": {"score": 0.5298, "source": "GenoMAS (2025)"},
            "OpenAI o3": {"score": 0.4553, "source": "GenoMAS (2025)"},
            "Gemini 2.5 Flash": {"score": 0.4067, "source": "GenoMAS (2025)"},
            "GPT-4o": {"score": 0.2529, "source": "GenoMAS (2025)"},
            "Direct Prompting": {"score": 0.024, "source": "GenoTEX (2024)"},
        },
    },
    # ── BioAgent Bench ───────────────────────────────────────────────────
    # alzheimer-mouse pathway analysis task
    # Metric: pathway pass (≥1 expected pathway found) + gene Jaccard
    "bioagent_bench": {
        "metric": "pathway_pass",
        "description": "BioAgent Bench alzheimer-mouse pathway analysis",
        "baselines": {
            "Claude Opus 4.5": {
                "completion_rate": 1.0,
                "source": "arXiv:2601.21800",
            },
            "GPT-5.2": {
                "jaccard": 0.160,
                "pearson": 0.219,
                "source": "arXiv:2601.21800",
            },
        },
    },
    # ── Internal benchmarks (no published baselines) ─────────────────────
    "cancer_pathway": {
        "metric": "bioagent_score",
        "description": "TCGA BRCA pathway enrichment (knowledge benchmark)",
        "note": "Internal — first run establishes baseline.",
    },
    "gtex_tissue_markers": {
        "metric": "bioagent_score",
        "description": "GTEx tissue-specific marker genes (knowledge benchmark)",
        "note": "Internal — first run establishes baseline.",
    },
}


def get_baselines(benchmark_or_dataset_id: str) -> dict[str, Any] | None:
    """Get published baselines for a benchmark or dataset."""
    return PUBLISHED_BASELINES.get(benchmark_or_dataset_id)


def format_baseline_comparison(
    dataset_id: str,
    our_scores: dict[str, float],
) -> str:
    """Format a comparison string between our results and published baselines.

    Returns empty string if no baselines exist.
    """
    baseline = PUBLISHED_BASELINES.get(dataset_id)
    if not baseline or "baselines" not in baseline:
        note = baseline.get("note", "") if baseline else ""
        return f"  Note: {note}" if note else ""

    # In fair mode, always compare on F1 (standard metric matching GenoMAS methodology)
    is_fair = our_scores.get("fair_mode", False)
    if is_fair:
        metric_key = "gene_f1"
        lines = ["\n  Published Baselines (gene_f1, FAIR MODE):"]
    else:
        metric_key = baseline["metric"]
        lines = [f"\n  Published Baselines ({metric_key}):"]
    our_score = our_scores.get(metric_key, our_scores.get("gene_f1", 0.0))
    for name, info in baseline["baselines"].items():
        score = info.get("score", info.get("jaccard"))
        if isinstance(score, (int, float)):
            delta = our_score - score
            arrow = "+" if delta > 0 else "" if delta < 0 else "="
            lines.append(f"    {name:30s} {score:.3f}  ({arrow}{delta:.3f} vs ours)")
        else:
            # Non-numeric baselines (completion_rate, etc.)
            extras = {k: v for k, v in info.items() if k != "source"}
            lines.append(f"    {name:30s} {extras}")
    lines.append(f"    {'W9 (ours)':30s} {our_score:.3f}  <-- THIS RUN")

    return "\n".join(lines)
