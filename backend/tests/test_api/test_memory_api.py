"""Tests for /api/v1/memory — semantic search and stats endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.v1.memory import router, set_dependencies
from fastapi import FastAPI

# Build a minimal FastAPI app for testing (no rate-limit middleware)
_app = FastAPI()
_app.include_router(router)


def _make_memory(
    counts: dict[str, int] | None = None,
    search_results: list[dict] | None = None,
) -> MagicMock:
    """Build a mock SemanticMemory."""
    mem = MagicMock()
    _counts = counts or {"literature": 5, "synthesis": 2, "lab_kb": 1}
    mem.count.side_effect = lambda name: _counts.get(name, 0)
    _results = search_results if search_results is not None else [
        {
            "id": "doi:10.1234/test",
            "text": "BRCA1 mutations increase breast cancer risk.",
            "metadata": {"title": "BRCA1 Study", "doi": "10.1234/test"},
            "distance": 0.1,
            "collection": "literature",
        }
    ]
    mem.search.return_value = [dict(r) for r in _results]
    mem.search_all.return_value = [dict(r, collection="literature") for r in _results]
    return mem


@pytest.fixture(autouse=True)
def inject_memory():
    """Inject a mock memory into the router before each test."""
    mem = _make_memory()
    set_dependencies(mem)
    yield mem
    set_dependencies(None)  # type: ignore[arg-type]


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app)


# === /memory/stats ===


class TestMemoryStats:
    def test_returns_200(self, client: TestClient):
        resp = client.get("/api/v1/memory/stats")
        assert resp.status_code == 200

    def test_returns_all_three_collections(self, client: TestClient):
        resp = client.get("/api/v1/memory/stats")
        data = resp.json()
        names = [c["name"] for c in data["collections"]]
        assert "literature" in names
        assert "synthesis" in names
        assert "lab_kb" in names

    def test_total_matches_sum(self, client: TestClient):
        resp = client.get("/api/v1/memory/stats")
        data = resp.json()
        total = sum(c["count"] for c in data["collections"])
        assert data["total_documents"] == total

    def test_503_when_memory_not_initialized(self, client: TestClient):
        set_dependencies(None)  # type: ignore[arg-type]
        resp = client.get("/api/v1/memory/stats")
        assert resp.status_code == 503
        # restore
        set_dependencies(_make_memory())

    def test_handles_count_exception(self, client: TestClient, inject_memory: MagicMock):
        inject_memory.count.side_effect = Exception("chroma down")
        resp = client.get("/api/v1/memory/stats")
        # Gracefully returns 0 for each, not 500
        assert resp.status_code == 200
        data = resp.json()
        assert all(c["count"] == 0 for c in data["collections"])


# === /memory/search ===


class TestMemorySearch:
    def test_search_all_returns_200(self, client: TestClient):
        resp = client.get("/api/v1/memory/search", params={"q": "BRCA1"})
        assert resp.status_code == 200

    def test_search_result_structure(self, client: TestClient):
        resp = client.get("/api/v1/memory/search", params={"q": "BRCA1"})
        data = resp.json()
        assert "query" in data
        assert "results" in data
        assert "total" in data
        assert data["query"] == "BRCA1"

    def test_similarity_computed_from_distance(self, client: TestClient):
        resp = client.get("/api/v1/memory/search", params={"q": "BRCA1"})
        data = resp.json()
        r = data["results"][0]
        # distance=0.1 → similarity=0.9
        assert abs(r["similarity"] - 0.9) < 0.01

    def test_search_specific_collection(self, client: TestClient, inject_memory: MagicMock):
        inject_memory.search.return_value = [
            {
                "id": "pmid:123",
                "text": "Some paper.",
                "metadata": {},
                "distance": 0.2,
                "collection": "literature",
            }
        ]
        resp = client.get(
            "/api/v1/memory/search",
            params={"q": "cancer", "collection": "literature"},
        )
        assert resp.status_code == 200
        inject_memory.search.assert_called_once()
        inject_memory.search_all.assert_not_called()

    def test_invalid_collection_returns_400(self, client: TestClient):
        resp = client.get(
            "/api/v1/memory/search",
            params={"q": "test", "collection": "invalid_coll"},
        )
        assert resp.status_code == 400

    def test_empty_query_returns_422(self, client: TestClient):
        resp = client.get("/api/v1/memory/search", params={"q": ""})
        assert resp.status_code == 422

    def test_n_param_respected(self, client: TestClient, inject_memory: MagicMock):
        client.get("/api/v1/memory/search", params={"q": "test", "n": "20"})
        # search_all called with n_results=20
        call_kwargs = inject_memory.search_all.call_args
        assert call_kwargs is not None
        _, kwargs = call_kwargs
        assert kwargs.get("n_results") == 20

    def test_503_when_memory_not_initialized(self, client: TestClient):
        set_dependencies(None)  # type: ignore[arg-type]
        resp = client.get("/api/v1/memory/search", params={"q": "BRCA1"})
        assert resp.status_code == 503
        set_dependencies(_make_memory())

    def test_500_when_search_raises(self, client: TestClient, inject_memory: MagicMock):
        inject_memory.search_all.side_effect = Exception("chroma error")
        resp = client.get("/api/v1/memory/search", params={"q": "test"})
        assert resp.status_code == 500

    def test_empty_results_returns_total_zero(self, client: TestClient, inject_memory: MagicMock):
        inject_memory.search_all.return_value = []
        resp = client.get("/api/v1/memory/search", params={"q": "obscure query"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["results"] == []

    def test_similarity_capped_at_zero_for_distance_gt_1(
        self, client: TestClient, inject_memory: MagicMock
    ):
        inject_memory.search_all.return_value = [
            {"id": "x", "text": "t", "metadata": {}, "distance": 1.5, "collection": "synthesis"}
        ]
        resp = client.get("/api/v1/memory/search", params={"q": "test"})
        data = resp.json()
        assert data["results"][0]["similarity"] == 0.0

    def test_collection_field_present_in_results(self, client: TestClient):
        resp = client.get("/api/v1/memory/search", params={"q": "test"})
        data = resp.json()
        for r in data["results"]:
            assert "collection" in r

    def test_default_n_is_8(self, client: TestClient, inject_memory: MagicMock):
        client.get("/api/v1/memory/search", params={"q": "test"})
        call_kwargs = inject_memory.search_all.call_args
        _, kwargs = call_kwargs
        assert kwargs.get("n_results") == 8
