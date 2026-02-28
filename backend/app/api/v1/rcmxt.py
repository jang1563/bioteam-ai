"""RCMXT Claim Scorer API.

POST /api/v1/rcmxt/score       — Score a single claim (LLM or heuristic mode)
POST /api/v1/rcmxt/batch       — Score multiple claims, compute ICC summary
GET  /api/v1/rcmxt/corpus-stats — Corpus ground-truth stats from seed CSV

This API exposes the RCMXTScorer engine for direct LLM-based claim scoring,
enabling both interactive use (single claim) and calibration (batch + ICC).
"""

from __future__ import annotations

import csv
import logging
import statistics
from pathlib import Path
from typing import Any

from app.engines.rcmxt_scorer import RCMXTScorer, ScoringMode
from app.llm.layer import LLMLayer
from app.models.evidence import LLMRCMXTResponse, RCMXTScore
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rcmxt", tags=["rcmxt"])

# ── LLM dependency ─────────────────────────────────────────────────────────────

_llm_layer: LLMLayer | None = None


def set_llm_layer(layer: LLMLayer) -> None:
    global _llm_layer
    _llm_layer = layer


def get_llm_layer() -> LLMLayer:
    if _llm_layer is None:
        raise HTTPException(status_code=503, detail="LLM layer not available")
    return _llm_layer


# ── Path to seed corpus ────────────────────────────────────────────────────────

_CORPUS_CSV = Path(__file__).resolve().parents[4] / "docs" / "annotation" / "claim_corpus_template.csv"


# ── Request / response models ─────────────────────────────────────────────────


class ScoreRequest(BaseModel):
    claim: str = Field(min_length=10, max_length=2000, description="Biological claim to score")
    context: str = Field(default="", max_length=1000, description="Domain/paper context for the claim")
    mode: ScoringMode = Field(default="llm", description="Scoring mode: llm | heuristic | hybrid")


class ScoreResponse(BaseModel):
    claim: str
    mode: str
    score: dict  # RCMXTScore serialized
    composite: float | None
    explanation: dict | None  # LLMRCMXTResponse serialized (null for heuristic mode)


class BatchClaimInput(BaseModel):
    claim_id: str = Field(max_length=20)
    claim_text: str = Field(min_length=10, max_length=2000)
    context: str = Field(default="", max_length=1000)
    ground_truth: dict | None = None  # Optional {R, C, M, X, T} for ICC computation


class BatchRequest(BaseModel):
    claims: list[BatchClaimInput] = Field(min_length=1, max_length=50)
    mode: ScoringMode = Field(default="llm")
    runs_per_claim: int = Field(default=1, ge=1, le=5, description="LLM runs per claim (for ICC)")


class AxisICCResult(BaseModel):
    axis: str
    scores: list[float]
    mean: float
    std: float
    # Simple agreement with ground truth (if provided)
    mae_vs_ground_truth: float | None = None


class BatchResponse(BaseModel):
    total_claims: int
    mode: str
    results: list[dict]
    axis_summary: dict[str, AxisICCResult]


class CorpusEntry(BaseModel):
    claim_id: str
    domain: str
    claim_text: str
    context: str
    r_score: float | None
    c_score: float | None
    m_score: float | None
    x_score: float | None
    t_score: float | None
    composite: float | None
    uncertain: str
    notes: str


class CorpusStatsResponse(BaseModel):
    total_claims: int
    domains: dict[str, int]
    mean_scores: dict[str, float | None]
    entries: list[CorpusEntry]


# ── Helper ─────────────────────────────────────────────────────────────────────

RCMXT_WEIGHTS = {"R": 0.30, "C": 0.20, "M": 0.25, "X": 0.15, "T": 0.10}


def _weighted_composite(r: float, c: float, m: float, x: float | None, t: float) -> float:
    """Compute RCMXT composite with weight renormalization when X=NULL."""
    if x is None:
        denom = 1.0 - RCMXT_WEIGHTS["X"]
        return round((RCMXT_WEIGHTS["R"] * r + RCMXT_WEIGHTS["C"] * c +
                      RCMXT_WEIGHTS["M"] * m + RCMXT_WEIGHTS["T"] * t) / denom, 3)
    return round(sum([
        RCMXT_WEIGHTS["R"] * r,
        RCMXT_WEIGHTS["C"] * c,
        RCMXT_WEIGHTS["M"] * m,
        RCMXT_WEIGHTS["X"] * x,
        RCMXT_WEIGHTS["T"] * t,
    ]), 3)


def _score_to_dict(score: RCMXTScore) -> dict:
    return {
        "R": round(score.R, 3),
        "C": round(score.C, 3),
        "M": round(score.M, 3),
        "X": round(score.X, 3) if score.X is not None else None,
        "T": round(score.T, 3),
        "composite": score.composite,
        "scorer_version": score.scorer_version,
    }


def _explanation_to_dict(exp: LLMRCMXTResponse | None) -> dict | None:
    if exp is None:
        return None
    return {
        "axes": [
            {
                "axis": ae.axis,
                "score": ae.score,
                "reasoning": ae.reasoning,
                "key_evidence": ae.key_evidence,
            }
            for ae in exp.axes
        ],
        "x_applicable": exp.x_applicable,
        "overall_assessment": exp.overall_assessment,
        "confidence_in_scoring": exp.confidence_in_scoring,
    }


def _load_corpus() -> list[dict]:
    """Load seed corpus from CSV. Returns empty list if not found."""
    if not _CORPUS_CSV.exists():
        return []
    rows = []
    with open(_CORPUS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def _safe_float(val: str) -> float | None:
    if not val or val.strip().upper() in ("NULL", "NA", "N/A", ""):
        return None
    try:
        return float(val)
    except ValueError:
        return None


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/score", response_model=ScoreResponse)
async def score_claim(
    req: ScoreRequest,
    llm: LLMLayer = Depends(get_llm_layer),
) -> ScoreResponse:
    """Score a single biological claim using RCMXT framework.

    LLM mode uses Sonnet with prompt-cached rubric for consistent scoring.
    Heuristic mode is instant but uses pipeline metadata heuristics (less precise for standalone claims).
    """
    scorer = RCMXTScorer(mode=req.mode, llm_layer=llm if req.mode != "heuristic" else None)

    score, explanation = await scorer.score_benchmark_claim(req.claim, domain=req.context)
    score.compute_composite()
    # Override composite with weighted formula
    score.composite = _weighted_composite(score.R, score.C, score.M, score.X, score.T)

    return ScoreResponse(
        claim=req.claim,
        mode=req.mode,
        score=_score_to_dict(score),
        composite=score.composite,
        explanation=_explanation_to_dict(explanation),
    )


@router.post("/batch", response_model=BatchResponse)
async def batch_score(
    req: BatchRequest,
    llm: LLMLayer = Depends(get_llm_layer),
) -> BatchResponse:
    """Score multiple claims and compute per-axis summary statistics.

    Supports `runs_per_claim` > 1 for intra-run consistency measurement (pseudo-ICC).
    When ground_truth is provided per claim, also computes MAE vs ground truth.
    Results are returned in claim order.
    """
    scorer = RCMXTScorer(mode=req.mode, llm_layer=llm if req.mode != "heuristic" else None)

    results: list[dict] = []
    axis_scores: dict[str, list[float]] = {"R": [], "C": [], "M": [], "X": [], "T": []}
    axis_gt_diffs: dict[str, list[float]] = {"R": [], "C": [], "M": [], "X": [], "T": []}

    for item in req.claims:
        run_scores: list[RCMXTScore] = []
        run_explanations: list[LLMRCMXTResponse | None] = []

        for _ in range(req.runs_per_claim):
            s, exp = await scorer.score_benchmark_claim(item.claim_text, domain=item.context)
            s.compute_composite()
            s.composite = _weighted_composite(s.R, s.C, s.M, s.X, s.T)
            run_scores.append(s)
            run_explanations.append(exp)

        # Average across runs
        avg_r = statistics.mean(s.R for s in run_scores)
        avg_c = statistics.mean(s.C for s in run_scores)
        avg_m = statistics.mean(s.M for s in run_scores)
        x_vals = [s.X for s in run_scores if s.X is not None]
        avg_x: float | None = statistics.mean(x_vals) if x_vals else None
        avg_t = statistics.mean(s.T for s in run_scores)
        composite = _weighted_composite(avg_r, avg_c, avg_m, avg_x, avg_t)

        # Ground truth comparison
        gt_diff: dict[str, float | None] = {}
        if item.ground_truth:
            for ax, val in [("R", avg_r), ("C", avg_c), ("M", avg_m), ("T", avg_t)]:
                gt = item.ground_truth.get(ax)
                if gt is not None:
                    diff = abs(val - float(gt))
                    gt_diff[ax] = round(diff, 3)
                    axis_gt_diffs[ax].append(diff)
            x_gt = item.ground_truth.get("X")
            if x_gt is not None and avg_x is not None:
                diff = abs(avg_x - float(x_gt))
                gt_diff["X"] = round(diff, 3)
                axis_gt_diffs["X"].append(diff)

        # Accumulate for summary
        for ax, val in [("R", avg_r), ("C", avg_c), ("M", avg_m), ("T", avg_t)]:
            axis_scores[ax].append(val)
        if avg_x is not None:
            axis_scores["X"].append(avg_x)

        result: dict[str, Any] = {
            "claim_id": item.claim_id,
            "claim_text": item.claim_text[:120],
            "runs": req.runs_per_claim,
            "scores": {"R": round(avg_r, 3), "C": round(avg_c, 3), "M": round(avg_m, 3),
                       "X": round(avg_x, 3) if avg_x is not None else None, "T": round(avg_t, 3)},
            "composite": composite,
            "ground_truth_diff": gt_diff if gt_diff else None,
        }
        # Include last explanation
        if run_explanations[-1]:
            result["explanation"] = _explanation_to_dict(run_explanations[-1])
        results.append(result)

    # Build axis summary
    axis_summary: dict[str, AxisICCResult] = {}
    for ax in ["R", "C", "M", "X", "T"]:
        vals = axis_scores[ax]
        if not vals:
            continue
        mae = round(statistics.mean(axis_gt_diffs[ax]), 3) if axis_gt_diffs[ax] else None
        axis_summary[ax] = AxisICCResult(
            axis=ax,
            scores=vals,
            mean=round(statistics.mean(vals), 3),
            std=round(statistics.stdev(vals), 3) if len(vals) > 1 else 0.0,
            mae_vs_ground_truth=mae,
        )

    return BatchResponse(
        total_claims=len(req.claims),
        mode=req.mode,
        results=results,
        axis_summary=axis_summary,
    )


@router.get("/corpus-stats", response_model=CorpusStatsResponse)
async def corpus_stats(
    domain: str | None = Query(default=None, description="Filter by domain"),
) -> CorpusStatsResponse:
    """Return statistics from the seed claim corpus CSV.

    Useful for pre-flight calibration checks and monitoring corpus coverage.
    Does NOT make any LLM calls.
    """
    rows = _load_corpus()
    if not rows:
        return CorpusStatsResponse(
            total_claims=0,
            domains={},
            mean_scores={ax: None for ax in ["R", "C", "M", "X", "T"]},
            entries=[],
        )

    if domain:
        rows = [r for r in rows if r.get("domain", "") == domain]

    entries = []
    domain_counts: dict[str, int] = {}
    axis_vals: dict[str, list[float]] = {"R": [], "C": [], "M": [], "X": [], "T": []}

    for row in rows:
        dom = row.get("domain", "unknown")
        domain_counts[dom] = domain_counts.get(dom, 0) + 1

        r_s = _safe_float(row.get("R_score", ""))
        c_s = _safe_float(row.get("C_score", ""))
        m_s = _safe_float(row.get("M_score", ""))
        x_s = _safe_float(row.get("X_score", ""))
        t_s = _safe_float(row.get("T_score", ""))

        for ax, val in [("R", r_s), ("C", c_s), ("M", m_s), ("X", x_s), ("T", t_s)]:
            if val is not None:
                axis_vals[ax].append(val)

        comp: float | None = None
        if all(v is not None for v in [r_s, c_s, m_s, t_s]):
            comp = _weighted_composite(r_s, c_s, m_s, x_s, t_s)  # type: ignore[arg-type]

        entries.append(CorpusEntry(
            claim_id=row.get("claim_id", ""),
            domain=dom,
            claim_text=row.get("claim_text", ""),
            context=row.get("context", ""),
            r_score=r_s,
            c_score=c_s,
            m_score=m_s,
            x_score=x_s,
            t_score=t_s,
            composite=comp,
            uncertain=row.get("uncertain", ""),
            notes=row.get("notes", ""),
        ))

    mean_scores = {
        ax: round(statistics.mean(vals), 3) if vals else None
        for ax, vals in axis_vals.items()
    }

    return CorpusStatsResponse(
        total_claims=len(entries),
        domains=domain_counts,
        mean_scores=mean_scores,
        entries=entries,
    )
