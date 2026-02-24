"""RCMXTScorer — evidence claim scorer with heuristic and LLM modes.

v0.1: Deterministic heuristic scorer (no LLM calls).
v0.2: + LLM-based scoring via LLMLayer.complete_structured().

Axes:
  R — Reproducibility: independent replications confirming the claim
  C — Condition Specificity: how context-dependent the effect is
  M — Methodological Robustness: study design quality
  X — Cross-Omics: NULL if single technology, concordance score if multi
  T — Temporal Stability: consistency of finding over time
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from app.models.evidence import LLMRCMXTResponse, RCMXTScore

if TYPE_CHECKING:
    from app.llm.layer import LLMLayer, LLMResponse

logger = logging.getLogger(__name__)

ScoringMode = Literal["heuristic", "llm", "hybrid"]

# === RCMXT Scoring Rubric (system prompt for LLM mode) ===

RCMXT_SCORING_RUBRIC = """\
You are an expert biomedical evidence assessor. Score the given scientific claim \
on the 5 axes of the RCMXT evidence confidence framework.

## Axis Definitions and Scoring Rubric

### R — Reproducibility (0.0–1.0)
How many independent research groups have confirmed this finding?
- 0.0–0.2: No independent replication. Single study, single lab.
- 0.2–0.4: One partial replication or same-lab repeat.
- 0.4–0.6: 2–3 independent groups with partial agreement.
- 0.6–0.8: Multiple independent replications with consistent results.
- 0.8–1.0: Textbook-level finding replicated across many labs and conditions.

### C — Condition Specificity (0.0–1.0)
How broadly generalizable is this finding across biological contexts?
- 0.0–0.2: Absolutist language ("always", "universally") that is demonstrably incorrect, \
or finding so context-specific it applies to a single cell line/organism/condition.
- 0.2–0.4: Finding observed in narrow conditions, generalizability unknown.
- 0.4–0.6: Finding confirmed in 2–3 contexts but significant exceptions exist.
- 0.6–0.8: Finding generalizes across multiple species/conditions with known caveats.
- 0.8–1.0: Fundamental biological principle.

### M — Methodological Robustness (0.0–1.0)
What is the quality of study designs supporting this claim?
- 0.0–0.2: No peer review, pre-print only, no methods, or clearly flawed design.
- 0.2–0.4: Published but small sample sizes (n<5), no controls, single timepoint.
- 0.4–0.6: Published with adequate methods but limited statistical power.
- 0.6–0.8: Well-designed studies with proper controls, adequate sample sizes, validated methods.
- 0.8–1.0: Gold-standard methodology (RCTs, multi-site validation, pre-registered studies).

### X — Cross-Omics Concordance (0.0–1.0 or NULL)
If multi-omics data exists, do different omics layers agree?
- NULL: Single-omics or non-omics data only. Clinical measurements, imaging, behavioral data.
- 0.0–0.3: Multi-omics data exists but actively contradicts.
- 0.3–0.5: Multi-omics data is mixed or inconclusive.
- 0.5–0.7: Partial concordance across 2+ omics layers.
- 0.7–1.0: Strong agreement across multiple omics layers.
CRITICAL: If the claim involves only one data modality, X MUST be null. Do NOT assign 0.5 \
for unknown — use null by setting x_applicable=false.

### T — Temporal Stability (0.0–1.0)
Has this finding been consistent over time?
- 0.0–0.2: Very recent (<2 years) with no follow-up, or actively contradicted by later work.
- 0.2–0.4: Recent with limited follow-up, or finding whose interpretation has shifted.
- 0.4–0.6: Finding from last 5–10 years with some consistent support.
- 0.6–0.8: Established finding (10+ years) with consistent support despite evolving methods.
- 0.8–1.0: Decades-old finding that has withstood multiple technological revolutions.

## Instructions
1. Read the claim carefully. Identify any absolutist language that should lower C.
2. Consider the domain context provided.
3. Score each applicable axis independently. Do NOT anchor to other axes.
4. For X: FIRST decide if multi-omics data is relevant. If not, set x_applicable=false \
and omit X from axes.
5. Provide specific evidence (author names, years, journals) in your reasoning.
6. Be calibrated: use the full 0.0–1.0 range. Do NOT hedge around 0.5.
7. Known-false claims should score R < 0.3 and C < 0.3.
"""


class RCMXTScorer:
    """Score claims using heuristic, LLM, or hybrid mode.

    v0.1: Deterministic heuristic only (default, backward-compatible).
    v0.2: + LLM scoring via LLMLayer + hybrid fallback.

    Usage (heuristic — backward compatible):
        scorer = RCMXTScorer()
        scorer.load_step_data(search_output, extract_output, synthesis_output)
        scores = scorer.score_all()

    Usage (LLM):
        scorer = RCMXTScorer(mode="llm", llm_layer=llm)
        scorer.load_step_data(search_output, extract_output, synthesis_output)
        scores = await scorer.score_all_async()
    """

    def __init__(
        self,
        mode: ScoringMode = "heuristic",
        llm_layer: LLMLayer | None = None,
    ) -> None:
        if mode in ("llm", "hybrid") and llm_layer is None:
            raise ValueError(f"llm_layer is required for mode='{mode}'")
        self._mode = mode
        self._llm = llm_layer
        self._cached_system: list[dict] | None = None

        # Pipeline data (populated by load_step_data)
        self._papers: list[dict] = []
        self._extracted: list[dict] = []
        self._key_findings: list[str] = []
        self._sources_cited: list[str] = []
        self._organisms: set[str] = set()
        self._technologies: set[str] = set()
        self._years: list[int] = []

    def load_step_data(
        self,
        search_output: dict | None = None,
        extract_output: dict | None = None,
        synthesis_output: dict | None = None,
    ) -> None:
        """Load data from prior pipeline step outputs."""
        if search_output:
            self._papers = search_output.get("papers", [])
            for p in self._papers:
                year = p.get("year")
                if year is not None:
                    try:
                        self._years.append(int(year))
                    except (ValueError, TypeError):
                        pass

        if extract_output:
            self._extracted = extract_output.get("papers", [])
            for ep in self._extracted:
                if org := ep.get("organism"):
                    self._organisms.add(str(org).lower())
                if tech := ep.get("technology"):
                    self._technologies.add(str(tech).lower())

        if synthesis_output:
            self._key_findings = synthesis_output.get("key_findings", [])
            self._sources_cited = synthesis_output.get("sources_cited", [])

    # === Synchronous heuristic methods (v0.1, unchanged) ===

    def score_claim(self, claim: str) -> RCMXTScore:
        """Score a single claim using heuristics."""
        r_score = self._compute_r()
        c_score = self._compute_c()
        m_score = self._compute_m()
        x_score = self._compute_x()
        t_score = self._compute_t()

        source_ids = [
            p.get("doi") or p.get("pmid") or p.get("paper_id", "")
            for p in self._papers[:10]
        ]

        score = RCMXTScore(
            claim=claim,
            R=round(r_score, 3),
            C=round(c_score, 3),
            M=round(m_score, 3),
            X=round(x_score, 3) if x_score is not None else None,
            T=round(t_score, 3),
            sources=[s for s in source_ids if s],
            scorer_version="v0.1-heuristic",
            model_version="deterministic",
        )
        score.compute_composite()
        return score

    def score_all(self) -> list[RCMXTScore]:
        """Score all key findings from synthesis (heuristic)."""
        if not self._key_findings:
            return []
        return [self.score_claim(finding) for finding in self._key_findings]

    # === Async methods (v0.2, mode-aware) ===

    async def score_claim_async(
        self,
        claim: str,
        context: str = "",
    ) -> RCMXTScore:
        """Score a single claim using the configured mode.

        Args:
            claim: The scientific claim to score.
            context: Optional domain context (e.g., "spaceflight_biology").

        Returns:
            RCMXTScore with scorer_version reflecting the mode used.
        """
        if self._mode == "heuristic":
            return self.score_claim(claim)

        if self._mode == "llm":
            score, _ = await self._score_via_llm(claim, context)
            return score

        # hybrid: try LLM, fallback to heuristic
        try:
            score, _ = await self._score_via_llm(claim, context)
            return score
        except Exception as e:
            logger.warning("LLM scoring failed, falling back to heuristic: %s", e)
            return self.score_claim(claim)

    async def score_all_async(self) -> list[RCMXTScore]:
        """Score all key findings using the configured mode."""
        if not self._key_findings:
            return []
        results = []
        for finding in self._key_findings:
            score = await self.score_claim_async(finding)
            results.append(score)
        return results

    async def score_benchmark_claim(
        self,
        claim: str,
        domain: str,
    ) -> tuple[RCMXTScore, LLMRCMXTResponse | None]:
        """Score a benchmark claim, returning both RCMXTScore and raw LLM response.

        Used for calibration — returns the full LLM explanation for audit.
        Falls back to (heuristic_score, None) if LLM unavailable.
        """
        if self._mode == "heuristic" or self._llm is None:
            return self.score_claim(claim), None

        try:
            score, llm_resp = await self._score_via_llm(claim, context=domain)
            return score, llm_resp
        except Exception as e:
            logger.warning("Benchmark LLM scoring failed: %s", e)
            return self.score_claim(claim), None

    # === LLM scoring internals ===

    async def _score_via_llm(
        self,
        claim: str,
        context: str,
    ) -> tuple[RCMXTScore, LLMRCMXTResponse]:
        """Score a claim via LLM and return both the mapped score and raw response."""
        assert self._llm is not None  # Guaranteed by __init__ validation

        # Build cached system prompt (reused across claims in a batch)
        if self._cached_system is None:
            self._cached_system = self._llm.build_cached_system(RCMXT_SCORING_RUBRIC)

        messages = self._build_scoring_messages(claim, context)

        llm_resp, meta = await self._llm.complete_structured(
            messages=messages,
            model_tier="sonnet",
            response_model=LLMRCMXTResponse,
            system=self._cached_system,
            temperature=0.0,
        )

        score = self._llm_response_to_rcmxt_score(llm_resp, meta)
        return score, llm_resp

    def _build_scoring_messages(self, claim: str, context: str) -> list[dict]:
        """Build the user message for LLM scoring."""
        parts = [f"## Claim to Score\n\n{claim}"]

        if context:
            parts.append(f"\n\n## Domain Context\n\n{context}")

        # Add pipeline context if available
        if self._papers:
            n_papers = len(self._papers)
            parts.append(f"\n\n## Supporting Evidence Summary\n\n- {n_papers} papers retrieved")
        if self._organisms:
            parts.append(f"- Organisms studied: {', '.join(sorted(self._organisms))}")
        if self._technologies:
            parts.append(f"- Technologies used: {', '.join(sorted(self._technologies))}")
        if self._years:
            parts.append(f"- Publication year range: {min(self._years)}–{max(self._years)}")
        if self._extracted:
            with_size = sum(
                1 for p in self._extracted
                if p.get("sample_size", 0) and int(p.get("sample_size", 0)) > 0
            )
            parts.append(f"- Papers with reported sample sizes: {with_size}/{len(self._extracted)}")

        return [{"role": "user", "content": "\n".join(parts)}]

    def _llm_response_to_rcmxt_score(
        self,
        llm_resp: LLMRCMXTResponse,
        meta: LLMResponse,
    ) -> RCMXTScore:
        """Convert LLM structured response to RCMXTScore for storage."""
        axis_map = {ae.axis: ae.score for ae in llm_resp.axes}

        source_ids = [
            p.get("doi") or p.get("pmid") or p.get("paper_id", "")
            for p in self._papers[:10]
        ]

        score = RCMXTScore(
            claim=llm_resp.claim_text,
            R=round(axis_map["R"], 3),
            C=round(axis_map["C"], 3),
            M=round(axis_map["M"], 3),
            X=round(axis_map.get("X", None), 3) if axis_map.get("X") is not None else None,
            T=round(axis_map["T"], 3),
            sources=[s for s in source_ids if s],
            scorer_version="v0.2-llm",
            model_version=meta.model_version,
        )
        score.compute_composite()
        return score

    # === Heuristic axis computation (v0.1, unchanged) ===

    def _compute_r(self) -> float:
        """R: Reproducibility = unique sources / max(5, total)."""
        if not self._papers:
            return 0.0
        unique = len({
            p.get("doi") or p.get("pmid") or p.get("paper_id", f"p{i}")
            for i, p in enumerate(self._papers)
        })
        return min(1.0, unique / max(5, len(self._papers)))

    def _compute_c(self) -> float:
        """C: Condition Specificity = organism/condition metadata present."""
        if not self._organisms:
            return 0.0
        # More organisms = higher specificity (studies define conditions)
        return min(1.0, len(self._organisms) / 3.0)

    def _compute_m(self) -> float:
        """M: Methodological Robustness from sample sizes."""
        if not self._extracted:
            return 0.3  # Baseline when no extraction data
        with_size = sum(
            1 for p in self._extracted
            if p.get("sample_size", 0) and int(p.get("sample_size", 0)) > 0
        )
        return min(1.0, 0.3 + (with_size / max(len(self._extracted), 1)) * 0.7)

    def _compute_x(self) -> float | None:
        """X: Cross-Omics = NULL if single tech, score if multi."""
        if len(self._technologies) <= 1:
            return None
        return min(1.0, len(self._technologies) / 3.0)

    def _compute_t(self) -> float:
        """T: Temporal Stability = weighted recency + year range."""
        if not self._years:
            return 0.3  # Baseline when no year data
        current_year = datetime.now(timezone.utc).year
        recency = max(0.0, 1.0 - (current_year - max(self._years)) / 10.0)
        year_range = max(self._years) - min(self._years)
        stability = min(1.0, year_range / 10.0)
        return round(recency * 0.6 + stability * 0.4, 3)
