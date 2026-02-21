"""RCMXTScorer — deterministic heuristic scorer for evidence claims.

v0.1: No LLM calls. Scores each key_finding from SynthesisReport
using metadata from SEARCH, SCREEN, EXTRACT step outputs.

Axes:
  R — Reproducibility: unique sources supporting the claim
  C — Condition Specificity: organism/condition metadata present
  M — Methodological Robustness: sample sizes and study metadata
  X — Cross-Omics: NULL if single technology, score if multi
  T — Temporal Stability: recency + year range of supporting papers
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.evidence import RCMXTScore


class RCMXTScorer:
    """Score claims using deterministic heuristics from pipeline metadata.

    Usage:
        scorer = RCMXTScorer()
        scorer.load_step_data(search_output, extract_output, synthesis_output)
        scores = scorer.score_all()
    """

    def __init__(self) -> None:
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
        """Score all key findings from synthesis."""
        if not self._key_findings:
            return []
        return [self.score_claim(finding) for finding in self._key_findings]

    # --- Axis computation ---

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
