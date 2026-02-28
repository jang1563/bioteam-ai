"""Tests for the Preprint Delta Detector engine and API."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.preprint_delta import router, set_llm_layer
from app.engines.preprint_delta import (
    DeltaClassification,
    PreprintDeltaDetector,
    PreprintDeltaResult,
    PreprintVersion,
)


# ── Fixtures / helpers ─────────────────────────────────────────────────────────

def _make_version(n: int, abstract: str = "", date: str = "") -> PreprintVersion:
    return PreprintVersion(
        version=n,
        doi=f"10.1101/test.doi",
        title="Test Preprint Title",
        date=date or f"2024-0{n}-01",
        abstract=abstract or f"Version {n} abstract text about biology.",
        authors=["Author A", "Author B"],
        server="biorxiv",
    )


def _mock_classification() -> DeltaClassification:
    return DeltaClassification(
        major_changes=["Sample size increased from n=50 to n=120", "New figure added"],
        minor_changes=["Typos corrected", "Added citation"],
        sample_size_changed=True,
        conclusion_shifted=False,
        methods_updated=True,
        overall_impact="Revision strengthens the evidence with a larger cohort.",
        confidence=0.85,
    )


def _biorxiv_response(n_versions: int = 2) -> dict:
    collection = []
    for i in range(1, n_versions + 1):
        collection.append({
            "preprint_doi": "10.1101/test.doi",
            "preprint_title": "Test Preprint Title",
            "preprint_authors": "Author A; Author B",
            "preprint_date": f"2024-0{i}-01",
            "preprint_abstract": f"Version {i} abstract. "
                + ("Added new method." if i > 1 else ""),
            "preprint_category": "neuroscience",
        })
    return {"collection": collection, "messages": [{"status": "ok"}]}


# ── PreprintDeltaDetector unit tests ──────────────────────────────────────────


class TestFetchVersions:
    @pytest.mark.asyncio
    async def test_fetch_returns_versions(self):
        detector = PreprintDeltaDetector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = _biorxiv_response(3)
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            versions = await detector.fetch_versions("10.1101/test.doi")

        assert len(versions) == 3
        assert versions[0].version == 1
        assert versions[-1].version == 3

    @pytest.mark.asyncio
    async def test_fetch_empty_collection_returns_empty_list(self):
        detector = PreprintDeltaDetector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"collection": [], "messages": [{"status": "ok"}]}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            versions = await detector.fetch_versions("10.1101/nonexistent")

        assert versions == []

    @pytest.mark.asyncio
    async def test_doi_normalization_strips_prefix(self):
        """DOI with https://doi.org/ prefix should be stripped before use."""
        detector = PreprintDeltaDetector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = _biorxiv_response(1)
        mock_resp.raise_for_status = MagicMock()
        captured_url = []

        async def mock_get(url, **kwargs):
            captured_url.append(url)
            return mock_resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=mock_get)
            mock_client_cls.return_value = mock_client

            await detector.fetch_versions("https://doi.org/10.1101/test.doi")

        assert "10.1101/test.doi" in captured_url[0]
        assert "https://doi.org/" not in captured_url[0]


class TestComputeDiff:
    def test_identical_texts_return_zero_diff(self):
        detector = PreprintDeltaDetector()
        changed, _ = detector.compute_diff("same text", "same text")
        assert changed == 0

    def test_changed_text_returns_nonzero_diff(self):
        detector = PreprintDeltaDetector()
        changed, diff_text = detector.compute_diff(
            "Original abstract.\nSample size was n=50.",
            "Revised abstract.\nSample size was n=120.",
        )
        assert changed > 0
        assert "+" in diff_text or "-" in diff_text

    def test_completely_different_texts(self):
        detector = PreprintDeltaDetector()
        changed, _ = detector.compute_diff("Text A\nLine 2", "Text B\nLine 3")
        assert changed >= 4  # 2 removed + 2 added

    def test_diff_capped_at_50_lines(self):
        detector = PreprintDeltaDetector()
        long_a = "\n".join(f"Line {i}" for i in range(100))
        long_b = "\n".join(f"Changed {i}" for i in range(100))
        _, diff_text = detector.compute_diff(long_a, long_b)
        # Diff text should be capped at 50 diff lines
        lines = diff_text.split("\n")
        assert len(lines) <= 55  # allow header lines


class TestClassifyDelta:
    @pytest.mark.asyncio
    async def test_classify_returns_none_without_llm(self):
        detector = PreprintDeltaDetector(llm_layer=None)
        result = await detector.classify_delta("Title", "v1 text", "v2 text", 2)
        assert result is None

    @pytest.mark.asyncio
    async def test_classify_returns_classification_with_llm(self):
        mock_llm = MagicMock()
        mock_llm.complete_structured = AsyncMock(
            return_value=(_mock_classification(), MagicMock())
        )
        detector = PreprintDeltaDetector(llm_layer=mock_llm)
        result = await detector.classify_delta("Title", "v1 text", "v2 text longer", 2)
        assert result is not None
        assert isinstance(result.major_changes, list)
        assert isinstance(result.confidence, float)

    @pytest.mark.asyncio
    async def test_classify_handles_llm_error_gracefully(self):
        mock_llm = MagicMock()
        mock_llm.complete_structured = AsyncMock(side_effect=Exception("LLM error"))
        detector = PreprintDeltaDetector(llm_layer=mock_llm)
        result = await detector.classify_delta("Title", "v1 text", "v2 text", 2)
        assert result is None


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_analyze_single_version_no_llm_call(self):
        """Single-version preprints should not trigger LLM classification."""
        mock_llm = MagicMock()
        mock_llm.complete_structured = AsyncMock()
        detector = PreprintDeltaDetector(llm_layer=mock_llm)

        detector.fetch_versions = AsyncMock(return_value=[_make_version(1)])

        result = await detector.analyze("10.1101/test.doi")
        assert result.total_versions == 1
        assert result.classification is None  # no LLM call for single version
        mock_llm.complete_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_analyze_two_identical_versions_no_llm_call(self):
        """Two versions with same abstract shouldn't trigger LLM."""
        mock_llm = MagicMock()
        mock_llm.complete_structured = AsyncMock()
        detector = PreprintDeltaDetector(llm_layer=mock_llm)

        detector.fetch_versions = AsyncMock(return_value=[
            _make_version(1, abstract="Same text"),
            _make_version(2, abstract="Same text"),
        ])

        result = await detector.analyze("10.1101/test.doi")
        assert result.abstract_diff_lines == 0
        mock_llm.complete_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_analyze_two_different_versions_triggers_llm(self):
        """Two versions with different abstracts should trigger LLM classification."""
        mock_llm = MagicMock()
        mock_llm.complete_structured = AsyncMock(
            return_value=(_mock_classification(), MagicMock())
        )
        detector = PreprintDeltaDetector(llm_layer=mock_llm)

        detector.fetch_versions = AsyncMock(return_value=[
            _make_version(1, abstract="Original abstract with sample size n=50."),
            _make_version(2, abstract="Revised abstract with sample size n=120 and new method."),
        ])

        result = await detector.analyze("10.1101/test.doi")
        assert result.total_versions == 2
        assert result.abstract_diff_lines > 0
        assert result.classification is not None
        assert result.classification.sample_size_changed is True

    @pytest.mark.asyncio
    async def test_analyze_fetch_error_returns_error_result(self):
        """Network error during fetch should return error result, not raise."""
        detector = PreprintDeltaDetector(llm_layer=None)
        detector.fetch_versions = AsyncMock(side_effect=Exception("Network timeout"))

        result = await detector.analyze("10.1101/bad.doi")
        assert result.error is not None
        assert result.total_versions == 0

    @pytest.mark.asyncio
    async def test_analyze_no_versions_returns_error(self):
        detector = PreprintDeltaDetector(llm_layer=None)
        detector.fetch_versions = AsyncMock(return_value=[])

        result = await detector.analyze("10.1101/empty.doi")
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_analyze_result_structure(self):
        detector = PreprintDeltaDetector(llm_layer=None)
        detector.fetch_versions = AsyncMock(return_value=[
            _make_version(1), _make_version(2),
        ])

        result = await detector.analyze("10.1101/test.doi")
        assert isinstance(result, PreprintDeltaResult)
        assert result.doi == "10.1101/test.doi"
        assert result.latest_version == 2
        assert result.v1_date == "2024-01-01"
        assert result.latest_date == "2024-02-01"


# ── API endpoint tests ─────────────────────────────────────────────────────────


@pytest.fixture()
def api_client():
    set_llm_layer(None)  # no LLM needed for most tests
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as c:
        yield c
    set_llm_layer(None)


class TestCompareEndpoint:
    def test_doi_too_short_returns_422(self, api_client):
        resp = api_client.post("/api/v1/preprint-delta/compare", json={
            "doi": "abc",  # too short (< 5 chars)
            "server": "biorxiv",
        })
        assert resp.status_code == 422

    def test_invalid_server_returns_422(self, api_client):
        resp = api_client.post("/api/v1/preprint-delta/compare", json={
            "doi": "10.1101/2024.01.01.123456",
            "server": "arxiv",  # not biorxiv or medrxiv
        })
        assert resp.status_code == 422

    def test_empty_versions_returns_404(self, api_client):
        """If the API returns no versions, endpoint should return 404."""
        with patch(
            "app.engines.preprint_delta.PreprintDeltaDetector.fetch_versions",
            new_callable=lambda: lambda self: AsyncMock(return_value=[]),
        ):
            # Patch analyze directly
            with patch.object(
                PreprintDeltaDetector, "analyze",
                AsyncMock(return_value=PreprintDeltaResult(
                    doi="10.1101/missing",
                    server="biorxiv",
                    title="",
                    total_versions=0,
                    v1_date="", latest_date="", latest_version=0,
                    v1_abstract="", latest_abstract="",
                    abstract_diff_lines=0, classification=None,
                    error="No versions found for this DOI",
                )),
            ):
                resp = api_client.post("/api/v1/preprint-delta/compare", json={
                    "doi": "10.1101/missing.doi",
                    "server": "biorxiv",
                })
            assert resp.status_code == 404

    def test_successful_compare_returns_delta(self, api_client):
        mock_result = PreprintDeltaResult(
            doi="10.1101/2024.01.01.123456",
            server="biorxiv",
            title="Test Preprint",
            total_versions=3,
            v1_date="2024-01-01",
            latest_date="2024-06-01",
            latest_version=3,
            v1_abstract="Original abstract with n=50.",
            latest_abstract="Revised abstract with n=150 and new results.",
            abstract_diff_lines=4,
            classification=None,
        )
        with patch.object(PreprintDeltaDetector, "analyze", AsyncMock(return_value=mock_result)):
            resp = api_client.post("/api/v1/preprint-delta/compare", json={
                "doi": "10.1101/2024.01.01.123456",
                "server": "biorxiv",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["doi"] == "10.1101/2024.01.01.123456"
        assert data["total_versions"] == 3
        assert data["abstract_diff_lines"] == 4

    def test_medrxiv_server_accepted(self, api_client):
        mock_result = PreprintDeltaResult(
            doi="10.1101/2024.01.01.123456",
            server="medrxiv",
            title="MedRxiv Paper",
            total_versions=1,
            v1_date="2024-01-01",
            latest_date="2024-01-01",
            latest_version=1,
            v1_abstract="Abstract",
            latest_abstract="Abstract",
            abstract_diff_lines=0,
            classification=None,
        )
        with patch.object(PreprintDeltaDetector, "analyze", AsyncMock(return_value=mock_result)):
            resp = api_client.post("/api/v1/preprint-delta/compare", json={
                "doi": "10.1101/2024.01.01.123456",
                "server": "medrxiv",
            })
        assert resp.status_code == 200
        assert resp.json()["server"] == "medrxiv"


class TestBatchEndpoint:
    def test_batch_too_many_dois_returns_422(self, api_client):
        resp = api_client.post("/api/v1/preprint-delta/batch", json={
            "dois": [f"10.1101/2024.01.01.{i:06d}" for i in range(11)],  # > 10
            "server": "biorxiv",
        })
        assert resp.status_code == 422

    def test_batch_empty_list_returns_422(self, api_client):
        resp = api_client.post("/api/v1/preprint-delta/batch", json={
            "dois": [],
            "server": "biorxiv",
        })
        assert resp.status_code == 422

    def test_batch_returns_results_for_all_dois(self, api_client):
        def mock_analyze(doi, server="biorxiv"):
            return PreprintDeltaResult(
                doi=doi, server=server, title=f"Paper {doi}",
                total_versions=2, v1_date="2024-01-01", latest_date="2024-06-01",
                latest_version=2,
                v1_abstract="v1", latest_abstract="v2",
                abstract_diff_lines=1, classification=None,
            )

        with patch.object(PreprintDeltaDetector, "analyze", AsyncMock(side_effect=mock_analyze)):
            resp = api_client.post("/api/v1/preprint-delta/batch", json={
                "dois": ["10.1101/first", "10.1101/second"],
                "server": "biorxiv",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["results"]) == 2
