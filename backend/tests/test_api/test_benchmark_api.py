"""Tests for the benchmark REST API."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture()
def fake_runs_dir(tmp_path):
    """Create a temp dir with fake benchmark results."""
    runs = tmp_path / "runs"
    runs.mkdir()

    # Write two fake results
    result_a = {
        "dataset_id": "maqc_a_vs_b",
        "run_id": "bench_aaaa1111",
        "template": "rnaseq_dea",
        "cost_mode": "quick",
        "gene_recall": 0.65,
        "gene_precision": 0.55,
        "gene_f1": 0.60,
        "gene_jaccard": 0.42,
        "pathway_overlap": 0.50,
        "direction_accuracy": 0.80,
        "fc_correlation": 0.70,
        "biology_score": 0.75,
        "bioagent_score": 0.62,
        "total_cost_usd": 0.48,
        "runtime_seconds": 120.5,
        "timestamp": "2026-03-19T10:00:00Z",
    }
    result_b = {
        "dataset_id": "maqc_a_vs_b",
        "run_id": "bench_bbbb2222",
        "template": "rnaseq_dea",
        "cost_mode": "standard",
        "gene_recall": 0.75,
        "gene_precision": 0.60,
        "gene_f1": 0.67,
        "gene_jaccard": 0.50,
        "pathway_overlap": 0.60,
        "direction_accuracy": 0.85,
        "fc_correlation": 0.80,
        "biology_score": 0.80,
        "bioagent_score": 0.72,
        "total_cost_usd": 18.50,
        "runtime_seconds": 600.0,
        "timestamp": "2026-03-19T11:00:00Z",
    }

    (runs / "maqc_a_vs_b_2026-03-19T100000.json").write_text(json.dumps(result_a))
    (runs / "maqc_a_vs_b_2026-03-19T110000.json").write_text(json.dumps(result_b))

    return runs


class TestBenchmarkAPI:
    def test_list_datasets(self, client):
        response = client.get("/api/v1/benchmarks/datasets")
        assert response.status_code == 200
        datasets = response.json()
        assert len(datasets) >= 4
        ids = [d["id"] for d in datasets]
        assert "cancer_pathway" in ids
        # Check new fields
        cancer = next(d for d in datasets if d["id"] == "cancer_pathway")
        assert cancer["is_query_only"] is True
        assert cancer["benchmark_type"] == "knowledge"

    def test_list_suites(self, client):
        response = client.get("/api/v1/benchmarks/suites")
        assert response.status_code == 200
        suites = response.json()
        assert "core_bioinfo" in suites

    def test_list_results_empty(self, client):
        with patch("app.api.v1.benchmarks.RUNS_DIR", Path("/tmp/nonexistent_benchmark_dir_xyz")):
            response = client.get("/api/v1/benchmarks/results")
            assert response.status_code == 200
            assert response.json() == []

    def test_list_results_with_data(self, client, fake_runs_dir):
        with patch("app.api.v1.benchmarks.RUNS_DIR", fake_runs_dir):
            response = client.get("/api/v1/benchmarks/results")
            assert response.status_code == 200
            results = response.json()
            assert len(results) == 2
            # Each result should have benchmark_type annotation
            assert all(r.get("benchmark_type") == "w9_bioinfo" for r in results)

    def test_get_result_by_run_id(self, client, fake_runs_dir):
        with patch("app.api.v1.benchmarks.RUNS_DIR", fake_runs_dir):
            response = client.get("/api/v1/benchmarks/results/bench_aaaa1111")
            assert response.status_code == 200
            assert response.json()["run_id"] == "bench_aaaa1111"

    def test_get_result_not_found(self, client, fake_runs_dir):
        with patch("app.api.v1.benchmarks.RUNS_DIR", fake_runs_dir):
            response = client.get("/api/v1/benchmarks/results/nonexistent")
            assert response.status_code == 404

    def test_compare_results(self, client, fake_runs_dir):
        with patch("app.api.v1.benchmarks.RUNS_DIR", fake_runs_dir):
            response = client.get("/api/v1/benchmarks/compare?a=bench_aaaa1111&b=bench_bbbb2222")
            assert response.status_code == 200
            comparison = response.json()
            assert "metric_deltas" in comparison
            assert comparison["metric_deltas"]["gene_recall"] > 0  # b is better

    def test_compare_not_found(self, client, fake_runs_dir):
        with patch("app.api.v1.benchmarks.RUNS_DIR", fake_runs_dir):
            response = client.get("/api/v1/benchmarks/compare?a=nonexistent&b=bench_bbbb2222")
            assert response.status_code == 404

    def test_trends(self, client, fake_runs_dir):
        with patch("app.api.v1.benchmarks.RUNS_DIR", fake_runs_dir):
            response = client.get("/api/v1/benchmarks/trends?metric=bioagent_score")
            assert response.status_code == 200
            trends = response.json()
            assert len(trends) == 2
            assert all("value" in t for t in trends)

    def test_filter_by_dataset(self, client, fake_runs_dir):
        with patch("app.api.v1.benchmarks.RUNS_DIR", fake_runs_dir):
            response = client.get("/api/v1/benchmarks/results?dataset_id=maqc_a_vs_b")
            assert response.status_code == 200
            assert len(response.json()) == 2

            response = client.get("/api/v1/benchmarks/results?dataset_id=nonexistent")
            assert response.status_code == 200
            assert len(response.json()) == 0


class TestBenchmarkRunAPI:
    """Tests for POST /run and run status endpoints."""

    def test_post_run_returns_202(self, client):
        """POST /run should return 202 with run_id."""
        response = client.post("/api/v1/benchmarks/run", json={
            "dataset_id": "cancer_pathway",
            "template": "literature_only",
            "cost_mode": "quick",
            "fair": True,
        })
        assert response.status_code == 202
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "pending"
        assert data["fair"] is True

    def test_post_run_400_no_target(self, client):
        """POST /run without dataset_id/suite_id/external should fail."""
        response = client.post("/api/v1/benchmarks/run", json={
            "template": "literature_only",
        })
        assert response.status_code == 400

    def test_active_run_idle(self, client):
        """GET /runs/active should show idle when nothing is running."""
        # Reset tracker to ensure clean state
        import app.api.v1.benchmarks as bm
        bm._tracker = None
        response = client.get("/api/v1/benchmarks/runs/active")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "idle"

    def test_run_status_not_found(self, client):
        """GET /runs/{run_id}/status for unknown run should 404."""
        import app.api.v1.benchmarks as bm
        bm._tracker = None
        response = client.get("/api/v1/benchmarks/runs/nonexistent_run_id/status")
        assert response.status_code == 404

    def test_suites_include_new_suites(self, client):
        """Verify new suites (query_only, ci_quick) are available."""
        response = client.get("/api/v1/benchmarks/suites")
        suites = response.json()
        assert "query_only" in suites
        assert "ci_quick" in suites


@pytest.fixture()
def fake_w8_runs_dir(tmp_path):
    """Create a temp dir with fake W8 benchmark results."""
    runs = tmp_path / "w8_runs"
    runs.mkdir()

    w8_run = {
        "schema_version": "1.0",
        "label": "pilot",
        "source": "pilot",
        "created_at": "2026-03-11T02:51:51Z",
        "config": {"match_mode": "token_cosine", "similarity_threshold": 0.05},
        "aggregate": {
            "article_count": 2,
            "overall_concern_recall_avg": 0.80,
            "major_concern_recall_avg": None,
            "concern_precision_avg": 0.41,
            "decision_accuracy": None,
            "articles_with_decision": 0,
            "articles_with_precision": 2,
            "articles_with_recall": 2,
        },
        "articles": [
            {
                "article_id": "00969",
                "source": "pilot",
                "human_concerns_total": 5,
                "human_major_concerns": 3,
                "overall_concern_recall": 0.80,
                "concern_precision": 0.50,
            },
        ],
    }

    (runs / "w8_benchmark_run_pilot_20260311.json").write_text(json.dumps(w8_run))
    return runs


class TestBenchmarkConfigAPI:
    """Tests for GET /config endpoint."""

    def test_config_returns_200(self, client):
        response = client.get("/api/v1/benchmarks/config")
        assert response.status_code == 200
        data = response.json()
        assert "w8" in data
        assert "w9" in data

    def test_config_w8_fields(self, client):
        response = client.get("/api/v1/benchmarks/config")
        w8 = response.json()["w8"]
        assert w8["similarity_threshold"] == 0.65
        assert w8["token_cosine_threshold"] == 0.05
        assert w8["match_mode"] == "token_cosine"
        assert w8["corpus_version"] == "elife_v1"

    def test_config_w9_fields(self, client):
        response = client.get("/api/v1/benchmarks/config")
        w9 = response.json()["w9"]
        assert w9["regression_threshold"] == 0.05
        assert w9["default_budget"] == 25.0
        assert "bioagent_weights" in w9
        weights = w9["bioagent_weights"]
        assert abs(sum(weights.values()) - 1.0) < 0.001


class TestW8BenchmarkAPI:
    """Tests for W8 peer review benchmark endpoints."""

    def test_list_w8_results_empty(self, client):
        with patch("app.api.v1.benchmarks.W8_RUNS_DIR", Path("/tmp/nonexistent_w8_dir")):
            response = client.get("/api/v1/benchmarks/w8/results")
            assert response.status_code == 200
            assert response.json() == []

    def test_list_w8_results_with_data(self, client, fake_w8_runs_dir):
        with patch("app.api.v1.benchmarks.W8_RUNS_DIR", fake_w8_runs_dir):
            response = client.get("/api/v1/benchmarks/w8/results")
            assert response.status_code == 200
            results = response.json()
            assert len(results) == 1
            assert results[0]["benchmark_type"] == "w8_peer_review"

    def test_w8_result_has_aggregate(self, client, fake_w8_runs_dir):
        with patch("app.api.v1.benchmarks.W8_RUNS_DIR", fake_w8_runs_dir):
            response = client.get("/api/v1/benchmarks/w8/results")
            result = response.json()[0]
            assert "aggregate" in result
            assert result["aggregate"]["article_count"] == 2
            assert result["aggregate"]["overall_concern_recall_avg"] == 0.80

    def test_w8_result_has_articles(self, client, fake_w8_runs_dir):
        with patch("app.api.v1.benchmarks.W8_RUNS_DIR", fake_w8_runs_dir):
            response = client.get("/api/v1/benchmarks/w8/results")
            result = response.json()[0]
            assert "articles" in result
            assert len(result["articles"]) == 1
            assert result["articles"][0]["article_id"] == "00969"

    def test_get_w8_result_by_run_id(self, client, fake_w8_runs_dir):
        with patch("app.api.v1.benchmarks.W8_RUNS_DIR", fake_w8_runs_dir):
            # run_id defaults to filename stem
            response = client.get("/api/v1/benchmarks/w8/results/w8_benchmark_run_pilot_20260311")
            assert response.status_code == 200
            assert response.json()["label"] == "pilot"

    def test_get_w8_result_not_found(self, client, fake_w8_runs_dir):
        with patch("app.api.v1.benchmarks.W8_RUNS_DIR", fake_w8_runs_dir):
            response = client.get("/api/v1/benchmarks/w8/results/nonexistent")
            assert response.status_code == 404
