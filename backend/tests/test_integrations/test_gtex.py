"""Tests for GTEx Portal v2 client — uses mocked HTTP responses."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.gtex import GTExClient, GTEX_CITATION


@pytest.fixture
def client():
    return GTExClient()


@pytest.fixture
def mock_expression_data():
    return {
        "gencodeId": "ENSG00000012048.23",
        "geneSymbol": "BRCA1",
        "medianTranscriptExpression": [
            {"tissueSiteDetailId": "Breast_Mammary_Tissue", "median": 12.4},
            {"tissueSiteDetailId": "Ovary", "median": 8.7},
            {"tissueSiteDetailId": "Kidney_Cortex", "median": 2.1},
        ],
    }


class TestGTExClient:
    @pytest.mark.asyncio
    async def test_get_gene_expression_success(self, client, mock_expression_data):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"data": mock_expression_data})

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.get_gene_expression("ENSG00000012048.23")

        assert result is not None
        assert result["geneSymbol"] == "BRCA1"
        assert result["_source"] == "GTEx Portal v2 (V10)"
        assert result["_citation"] == GTEX_CITATION
        assert "_retrieved_at" in result

    @pytest.mark.asyncio
    async def test_get_gene_expression_disabled(self, client):
        with patch("app.integrations.gtex.settings") as mock_settings:
            mock_settings.gtex_enabled = False
            result = await client.get_gene_expression("ENSG00000012048")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_gene_expression_empty(self, client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"data": {}})

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.get_gene_expression("ENSG_NOTFOUND")

        assert result is None

    @pytest.mark.asyncio
    async def test_search_gene_success(self, client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "data": [{"gencodeId": "ENSG00000012048.23", "geneSymbol": "BRCA1"}]
        })

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.search_gene("BRCA1")

        assert result == "ENSG00000012048.23"

    @pytest.mark.asyncio
    async def test_search_gene_not_found(self, client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"data": []})

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.search_gene("NOTAREALGENEXXX")

        assert result is None

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self, client):
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=Exception("timeout"))

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.get_gene_expression("ENSG00000012048")

        assert result is None

    def test_gtex_citation_format(self):
        """GTEx citation must include V10, phs000424, and n=980."""
        assert "V10" in GTEX_CITATION
        assert "phs000424" in GTEX_CITATION
        assert "980" in GTEX_CITATION
