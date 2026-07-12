"""Tests for Crossref API client — uses mocked HTTP responses."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.integrations.crossref import CrossrefClient


@pytest.fixture
def client():
    return CrossrefClient(email="test@example.com")


def _make_mock_response(status_code: int, json_data: dict | None = None):
    """Create a MagicMock response (httpx Response methods are synchronous)."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


def _patch_async_client(mock_response):
    """Patch httpx.AsyncClient as async context manager returning mock_response on get()."""
    mock_instance = AsyncMock()
    mock_instance.get.return_value = mock_response
    mock_instance.__aenter__.return_value = mock_instance
    mock_instance.__aexit__.return_value = False
    return patch("app.integrations.crossref.httpx.AsyncClient", return_value=mock_instance)


class TestCrossrefClient:
    """Tests with mocked HTTP responses."""

    @pytest.mark.asyncio
    async def test_clean_paper(self, client):
        """Non-retracted paper returns clean status."""
        resp = _make_mock_response(200, {
            "message": {
                "DOI": "10.1234/clean",
                "type": "journal-article",
                "container-title": ["Nature"],
            }
        })
        with _patch_async_client(resp):
            status = await client.check_retraction("10.1234/clean")

        assert status.doi == "10.1234/clean"
        assert status.is_retracted is False
        assert status.is_corrected is False
        assert status.publisher == "Nature"

    @pytest.mark.asyncio
    async def test_retracted_paper(self, client):
        """Retracted paper detected via update-to field."""
        resp = _make_mock_response(200, {
            "message": {
                "DOI": "10.1234/retracted",
                "type": "journal-article",
                "container-title": ["Science"],
                "update-to": [
                    {"type": "retraction", "DOI": "10.1234/retraction-notice"}
                ],
            }
        })
        with _patch_async_client(resp):
            status = await client.check_retraction("10.1234/retracted")

        assert status.is_retracted is True
        assert status.retraction_doi == "10.1234/retraction-notice"

    @pytest.mark.asyncio
    async def test_corrected_paper(self, client):
        """Corrected paper detected via update-to field."""
        resp = _make_mock_response(200, {
            "message": {
                "DOI": "10.1234/corrected",
                "update-to": [
                    {"type": "correction", "DOI": "10.1234/erratum"}
                ],
            }
        })
        with _patch_async_client(resp):
            status = await client.check_retraction("10.1234/corrected")

        assert status.is_corrected is True
        assert status.correction_doi == "10.1234/erratum"

    @pytest.mark.asyncio
    async def test_404_returns_clean_status(self, client):
        """DOI not found returns clean status."""
        resp = _make_mock_response(404)
        with _patch_async_client(resp):
            status = await client.check_retraction("10.1234/notfound")

        assert status.doi == "10.1234/notfound"
        assert status.is_retracted is False

    @pytest.mark.asyncio
    async def test_batch_check(self, client):
        """Batch check processes multiple DOIs."""
        resp = _make_mock_response(200, {"message": {"DOI": "test", "type": "journal-article"}})
        with _patch_async_client(resp):
            results = await client.check_batch(["10.1/a", "10.1/b", "10.1/c"])

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_empty_batch(self, client):
        """Empty batch returns empty list."""
        results = await client.check_batch([])
        assert results == []
