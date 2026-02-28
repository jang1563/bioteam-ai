"""Tests for STRING DB v12 client — uses mocked HTTP responses."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.integrations.stringdb import STRINGClient


@pytest.fixture
def client():
    return STRINGClient()


@pytest.fixture
def mock_interactions():
    return [
        {
            "stringId_A": "9606.ENSP00000269305",
            "stringId_B": "9606.ENSP00000350546",
            "preferredName_A": "TP53",
            "preferredName_B": "MDM2",
            "score": 0.999,
        },
        {
            "stringId_A": "9606.ENSP00000269305",
            "stringId_B": "9606.ENSP00000265433",
            "preferredName_A": "TP53",
            "preferredName_B": "BRCA1",
            "score": 0.835,
        },
    ]


class TestSTRINGClient:
    @pytest.mark.asyncio
    async def test_get_interactions_success(self, client, mock_interactions):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=mock_interactions)

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await client.get_interactions(["TP53", "MDM2", "BRCA1"])

        assert len(results) == 2
        assert results[0]["preferredName_A"] == "TP53"
        assert results[0]["_source"] == "STRING DB v12"
        assert "_retrieved_at" in results[0]

    @pytest.mark.asyncio
    async def test_get_interactions_disabled(self, client):
        with patch("app.integrations.stringdb.settings") as mock_settings:
            mock_settings.stringdb_enabled = False
            results = await client.get_interactions(["TP53"])
        assert results == []

    @pytest.mark.asyncio
    async def test_get_interactions_empty_list(self, client):
        results = await client.get_interactions([])
        assert results == []

    @pytest.mark.asyncio
    async def test_enrich_network_success(self, client):
        mock_enrichment = [
            {
                "category": "KEGG",
                "term": "hsa04110",
                "description": "Cell cycle",
                "number_of_genes": 15,
                "fdr": 1.2e-8,
            }
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=mock_enrichment)

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await client.enrich_network(["TP53", "MDM2", "CDKN1A"])

        assert len(results) == 1
        assert results[0]["category"] == "KEGG"
        assert results[0]["_source"] == "STRING DB v12"

    @pytest.mark.asyncio
    async def test_enrich_network_disabled(self, client):
        with patch("app.integrations.stringdb.settings") as mock_settings:
            mock_settings.stringdb_enabled = False
            results = await client.enrich_network(["TP53"])
        assert results == []

    @pytest.mark.asyncio
    async def test_network_error_returns_empty(self, client):
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=Exception("connection refused"))

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await client.get_interactions(["TP53"])

        assert results == []

    @pytest.mark.asyncio
    async def test_min_score_passed_in_request(self, client):
        """Verify min_score is included in POST body."""
        call_data = {}

        async def capture_post(url, data=None, **kwargs):
            nonlocal call_data
            call_data = data or {}
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json = MagicMock(return_value=[])
            return mock_resp

        mock_http = AsyncMock()
        mock_http.post = capture_post

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await client.get_interactions(["TP53", "MDM2"], min_score=700)

        assert call_data.get("required_score") == 700
