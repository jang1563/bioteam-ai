"""W9 cost mode configurations — quick/standard/deep.

Controls which LLM tier to use, enabling Gemini free tier for rapid
low-cost analysis or full Opus+Sonnet for deep research.

Usage:
    from app.workflows.w9_cost_modes import COST_MODE_CONFIG
    mode = COST_MODE_CONFIG["quick"]
    tier = mode["default_tier"]  # "gemini"
"""

from __future__ import annotations

COST_MODE_CONFIG: dict[str, dict] = {
    "quick": {
        # ~$0.50, Gemini 2.5 Flash for all agent steps
        "default_tier": "gemini",
        "opus_override": "gemini",      # Opus steps also use Gemini
        "budget": 2.0,
    },
    "standard": {
        # ~$25, existing (Opus + Sonnet) mix
        "default_tier": "sonnet",
        "opus_override": None,          # Opus steps stay Opus
        "budget": 25.0,
    },
    "deep": {
        # ~$40, all domain analysis steps get agentic mode
        "default_tier": "sonnet",
        "opus_override": None,
        "extra_agentic": frozenset({
            "EXPRESSION_ANALYSIS", "PATHWAY_ENRICHMENT",
            "NETWORK_ANALYSIS", "PROTEIN_ANALYSIS",
        }),
        "budget": 50.0,
    },
}
