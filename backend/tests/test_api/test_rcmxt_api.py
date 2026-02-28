"""Tests for /api/v1/rcmxt endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.rcmxt import router, set_llm_layer
from app.models.evidence import AxisExplanation, LLMRCMXTResponse, RCMXTScore


# ── Mock LLM layer ─────────────────────────────────────────────────────────────

def _make_llm_rcmxt_response(claim: str = "test claim") -> LLMRCMXTResponse:
    return LLMRCMXTResponse(
        claim_text=claim,
        axes=[
            AxisExplanation(axis="R", score=0.7, reasoning="Replicated by 3 groups"),
            AxisExplanation(axis="C", score=0.6, reasoning="Observed in 2 contexts"),
            AxisExplanation(axis="M", score=0.8, reasoning="RCT design, large n"),
            AxisExplanation(axis="T", score=0.75, reasoning="10+ years of data"),
        ],
        x_applicable=False,
        overall_assessment="Strong evidence for this claim.",
        confidence_in_scoring=0.85,
    )


def _make_rcmxt_score(claim: str = "test claim") -> RCMXTScore:
    return RCMXTScore(
        claim=claim,
        R=0.7, C=0.6, M=0.8, X=None, T=0.75,
        composite=0.714,
    )


def _mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.build_cached_system = MagicMock(return_value=[])

    # complete_structured returns (LLMRCMXTResponse, meta)
    # model_version is set from meta.model — must be a real string
    meta = MagicMock()
    meta.model = "claude-sonnet-4-6"
    meta.model_version = "claude-sonnet-4-6"
    meta.cost = 0.001
    llm.complete_structured = AsyncMock(
        return_value=(_make_llm_rcmxt_response(), meta)
    )
    return llm


# ── App fixture ────────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    mock_llm = _mock_llm()
    set_llm_layer(mock_llm)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as c:
        yield c, mock_llm
    # Reset
    set_llm_layer(None)  # type: ignore[arg-type]


# ── /score endpoint tests ──────────────────────────────────────────────────────


class TestScoreEndpoint:
    def test_score_returns_200(self, client):
        c, _ = client
        resp = c.post("/api/v1/rcmxt/score", json={
            "claim": "KRAS G12C mutation predicts sensitivity to sotorasib in NSCLC.",
            "context": "Phase III RCT (CodeBreaK200), NEJM 2023.",
            "mode": "llm",
        })
        assert resp.status_code == 200

    def test_score_contains_axes(self, client):
        c, _ = client
        resp = c.post("/api/v1/rcmxt/score", json={
            "claim": "KRAS G12C mutation predicts sensitivity to sotorasib in NSCLC.",
            "context": "",
            "mode": "llm",
        })
        data = resp.json()
        assert "score" in data
        assert "R" in data["score"]
        assert "C" in data["score"]
        assert "M" in data["score"]
        assert "T" in data["score"]
        assert "composite" in data

    def test_score_explanation_present_for_llm_mode(self, client):
        c, _ = client
        resp = c.post("/api/v1/rcmxt/score", json={
            "claim": "TP53 is mutated in 50% of solid tumors.",
            "context": "TCGA pan-cancer analysis.",
            "mode": "llm",
        })
        data = resp.json()
        assert data["explanation"] is not None
        assert "axes" in data["explanation"]
        assert len(data["explanation"]["axes"]) >= 4

    def test_score_claim_too_short_returns_422(self, client):
        c, _ = client
        resp = c.post("/api/v1/rcmxt/score", json={
            "claim": "short",
            "context": "",
            "mode": "llm",
        })
        assert resp.status_code == 422

    def test_score_heuristic_mode_no_llm_needed(self):
        """Heuristic mode should work without LLM dependency."""
        set_llm_layer(MagicMock())  # LLM injected but shouldn't be called in heuristic mode
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as c:
            resp = c.post("/api/v1/rcmxt/score", json={
                "claim": "Adult hippocampal neurogenesis declines in humans after age 13.",
                "context": "Sorrells et al. Nature 2018.",
                "mode": "heuristic",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "heuristic"
        assert data["explanation"] is None  # heuristic mode has no explanation

    def test_score_composite_in_range(self, client):
        c, _ = client
        resp = c.post("/api/v1/rcmxt/score", json={
            "claim": "EGFR L858R mutation predicts erlotinib sensitivity in NSCLC.",
            "context": "Multiple RCTs.",
            "mode": "llm",
        })
        data = resp.json()
        assert 0.0 <= data["composite"] <= 1.0

    def test_score_503_when_no_llm(self):
        """No LLM injected → 503."""
        set_llm_layer(None)  # type: ignore[arg-type]
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as c:
            resp = c.post("/api/v1/rcmxt/score", json={
                "claim": "Some valid long enough claim about biology.",
                "mode": "llm",
            })
        assert resp.status_code == 503


# ── /batch endpoint tests ──────────────────────────────────────────────────────


class TestBatchEndpoint:
    def test_batch_single_claim(self, client):
        c, _ = client
        resp = c.post("/api/v1/rcmxt/batch", json={
            "claims": [
                {"claim_id": "SB-001", "claim_text": "Long-duration spaceflight increases red blood cell hemolysis.",
                 "context": "Trudel et al. 2022."},
            ],
            "mode": "llm",
            "runs_per_claim": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_claims"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["claim_id"] == "SB-001"

    def test_batch_multiple_claims(self, client):
        c, _ = client
        claims = [
            {"claim_id": f"CG-00{i}", "claim_text": f"Biological claim number {i} with enough text for validation.",
             "context": ""}
            for i in range(1, 4)
        ]
        resp = c.post("/api/v1/rcmxt/batch", json={
            "claims": claims,
            "mode": "llm",
            "runs_per_claim": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_claims"] == 3
        assert len(data["results"]) == 3

    def test_batch_axis_summary_present(self, client):
        c, _ = client
        resp = c.post("/api/v1/rcmxt/batch", json={
            "claims": [
                {"claim_id": "T1", "claim_text": "BRCA1 mutations confer 70% lifetime breast cancer risk.",
                 "context": "Large consortium studies."},
            ],
            "mode": "llm",
            "runs_per_claim": 1,
        })
        data = resp.json()
        assert "axis_summary" in data
        assert "R" in data["axis_summary"]
        assert "mean" in data["axis_summary"]["R"]
        assert "std" in data["axis_summary"]["R"]

    def test_batch_ground_truth_diff_computed(self, client):
        c, _ = client
        resp = c.post("/api/v1/rcmxt/batch", json={
            "claims": [
                {
                    "claim_id": "SB-001",
                    "claim_text": "Spaceflight causes 54% increase in red blood cell hemolysis.",
                    "context": "Trudel et al. 2022.",
                    "ground_truth": {"R": 0.55, "C": 0.50, "M": 0.60, "T": 0.40},
                },
            ],
            "mode": "llm",
            "runs_per_claim": 1,
        })
        data = resp.json()
        result = data["results"][0]
        # Ground truth diff should be populated
        assert result["ground_truth_diff"] is not None
        assert "R" in result["ground_truth_diff"]

    def test_batch_empty_claims_returns_422(self, client):
        c, _ = client
        resp = c.post("/api/v1/rcmxt/batch", json={
            "claims": [],
            "mode": "llm",
        })
        assert resp.status_code == 422

    def test_batch_runs_per_claim_validation(self, client):
        c, _ = client
        resp = c.post("/api/v1/rcmxt/batch", json={
            "claims": [
                {"claim_id": "T1", "claim_text": "Some claim with enough text for validation.",
                 "context": ""},
            ],
            "mode": "llm",
            "runs_per_claim": 10,  # exceeds max of 5
        })
        assert resp.status_code == 422


# ── /corpus-stats endpoint tests ───────────────────────────────────────────────


class TestCorpusStatsEndpoint:
    def test_corpus_stats_returns_200(self, client):
        c, _ = client
        resp = c.get("/api/v1/rcmxt/corpus-stats")
        assert resp.status_code == 200

    def test_corpus_stats_has_required_fields(self, client):
        c, _ = client
        resp = c.get("/api/v1/rcmxt/corpus-stats")
        data = resp.json()
        assert "total_claims" in data
        assert "domains" in data
        assert "mean_scores" in data
        assert "entries" in data

    def test_corpus_stats_total_matches_seed(self, client):
        """Seed corpus has 15 claims (5 SB + 5 CG + 5 NS)."""
        c, _ = client
        resp = c.get("/api/v1/rcmxt/corpus-stats")
        data = resp.json()
        # Should have at least the 15 seed claims (may have more)
        assert data["total_claims"] >= 15

    def test_corpus_stats_domain_filter(self, client):
        c, _ = client
        resp = c.get("/api/v1/rcmxt/corpus-stats?domain=spaceflight_biology")
        data = resp.json()
        # All returned entries should be spaceflight_biology
        for entry in data["entries"]:
            assert entry["domain"] == "spaceflight_biology"

    def test_corpus_stats_mean_scores_in_range(self, client):
        c, _ = client
        resp = c.get("/api/v1/rcmxt/corpus-stats")
        data = resp.json()
        for ax in ["R", "C", "M", "T"]:
            mean = data["mean_scores"][ax]
            if mean is not None:
                assert 0.0 <= mean <= 1.0

    def test_corpus_entries_have_composite(self, client):
        c, _ = client
        resp = c.get("/api/v1/rcmxt/corpus-stats")
        data = resp.json()
        for entry in data["entries"]:
            # Composite should be computed if R,C,M,T are present
            if all(entry[k] is not None for k in ["r_score", "c_score", "m_score", "t_score"]):
                assert entry["composite"] is not None
                assert 0.0 <= entry["composite"] <= 1.0

    def test_corpus_empty_domain_filter_returns_empty(self, client):
        c, _ = client
        resp = c.get("/api/v1/rcmxt/corpus-stats?domain=nonexistent_domain_xyz")
        data = resp.json()
        assert data["total_claims"] == 0
        assert data["entries"] == []
