"""Narrative Consistency Engine — checks manuscript section alignment with StoryFrame.

Used by W4 NARRATIVE_CHECK_DRAFT and NARRATIVE_CHECK_FINAL code steps.

For each major writing step (DRAFT, REVISION), scores how well the generated
text aligns with the selected StoryFrame (hook, core_claim, central_tension).

Score thresholds:
  >= 0.75 → on_track (log only, no SSE)
  0.50–0.74 → minor_drift (SSE warning broadcast)
  < 0.50 → major_drift (SSE warning, severity=major)

Never pauses the workflow — SSE-only. Always continues.
Haiku model: ~$0.01 per check, 2 checks per W4 run = ~$0.02 total.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.models.story_frame import NarrativeDriftReport

if TYPE_CHECKING:
    from app.llm.layer import LLMLayer

logger = logging.getLogger(__name__)

# ── Prompts ────────────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a scientific editor evaluating whether a manuscript section is aligned
with the paper's narrative frame. Be concise and objective. Score 0.0–1.0.
"""

_CHECK_PROMPT = """\
## Narrative Frame
- Hook: {hook}
- Core Claim: {core_claim}
- Central Tension: {central_tension}

## Manuscript Section ({section_id})
{section_text}

Evaluate how well this section aligns with the narrative frame above.

- consistency_score: 0.0 (completely divergent) to 1.0 (perfectly aligned)
- drift_summary: If score < 0.75, briefly explain the primary divergence (null if on_track)
- recommendation: "on_track" if >= 0.75, "minor_drift" if 0.50–0.74, "major_drift" if < 0.50
- specific_divergences: Up to 3 specific sentences or claims that diverge (empty if on_track)
"""


# ── Engine ─────────────────────────────────────────────────────────────────────


class NarrativeConsistencyChecker:
    """Checks if a manuscript section aligns with the selected StoryFrame.

    Uses Haiku for cost efficiency. Called by W4 at DRAFT and REVISION.
    """

    # Characters of section text sent to LLM (keep cost/token low)
    _MAX_SECTION_CHARS: int = 2500

    def __init__(self, llm_layer: LLMLayer) -> None:
        self._llm = llm_layer

    async def check(
        self,
        section_id: str,
        section_text: str,
        story_frame: dict,  # StoryFrame.model_dump(mode="json")
    ) -> NarrativeDriftReport:
        """Score section alignment with StoryFrame.

        Args:
            section_id: Step name (e.g. "DRAFT", "REVISION").
            section_text: Generated manuscript text for this section.
            story_frame: Dict from StoryFrame.model_dump(mode="json").

        Returns:
            NarrativeDriftReport with consistency_score, recommendation, and divergences.
            On any LLM failure, returns a safe default (score=1.0, on_track) so W4 continues.
        """
        hook = story_frame.get("hook", "")
        core_claim = story_frame.get("core_claim", "")
        central_tension = story_frame.get("central_tension", "")

        if not hook and not core_claim:
            logger.warning("NarrativeConsistencyChecker: story_frame missing hook/core_claim — skipping")
            return self._default_report(section_id)

        messages = [
            {
                "role": "user",
                "content": _CHECK_PROMPT.format(
                    hook=hook,
                    core_claim=core_claim,
                    central_tension=central_tension,
                    section_id=section_id,
                    section_text=section_text[: self._MAX_SECTION_CHARS],
                ),
            }
        ]

        try:
            result, _meta = await self._llm.complete_structured(
                messages=messages,
                model_tier="haiku",
                response_model=NarrativeDriftReport,
                system=_SYSTEM,
                temperature=0.0,
                max_tokens=512,
            )
            # Ensure section_id is set correctly (LLM may return its own)
            if result.section_id != section_id:
                result = result.model_copy(update={"section_id": section_id})
            return result

        except Exception as e:
            logger.warning(
                "NarrativeConsistencyChecker: LLM call failed for %s — %s. Returning safe default.",
                section_id,
                e,
            )
            return self._default_report(section_id)

    def _default_report(self, section_id: str) -> NarrativeDriftReport:
        """Safe default when LLM is unavailable — assume on_track so W4 continues."""
        return NarrativeDriftReport(
            section_id=section_id,
            consistency_score=1.0,
            drift_summary=None,
            recommendation="on_track",
            specific_divergences=[],
        )
