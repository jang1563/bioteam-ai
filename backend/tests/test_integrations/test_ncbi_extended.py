"""Tests for NCBI extended client (Gene + ClinVar) — uses mocked HTTP responses."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.integrations.ncbi_extended import NCBIExtendedClient


@pytest.fixture
def client():
    return NCBIExtendedClient()


@pytest.fixture
def mock_gene_summary():
    return {
        "uid": "672",
        "name": "BRCA1",
        "description": "BRCA1 DNA repair associated",
        "chromosome": "17",
        "maplocation": "17q21.31",
        "summary": "This gene encodes a tumor suppressor protein...",
        "otheraliases": "BRCAI, BRCC1, IRIS, PNCA4",
        "status": "",
    }


@pytest.fixture
def mock_clinvar_summary():
    return {
        "uid": "12345",
        "title": "NM_007294.4(BRCA1):c.5266dupC (p.Gln1756ProfsTer25)",
        "variation_set": [{"variation_name": "NM_007294.4(BRCA1):c.5266dupC"}],
        "clinical_significance": {"description": "Pathogenic"},
        "review_status": "reviewed by expert panel",
        "trait_set": [{"trait_name": "Hereditary breast and ovarian cancer syndrome"}],
    }


class TestNCBIExtendedClient:
    @pytest.mark.asyncio
    async def test_get_gene_info_success(self, client, mock_gene_summary):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"result": {"672": mock_gene_summary}})

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.get_gene_info("672")

        assert result is not None
        assert result["name"] == "BRCA1"
        assert result["_source"] == "NCBI Gene"
        assert "_retrieved_at" in result

    @pytest.mark.asyncio
    async def test_get_gene_info_not_found(self, client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"result": {}})

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.get_gene_info("9999999")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_gene_info_disabled(self, client):
        with patch("app.integrations.ncbi_extended.settings") as mock_settings:
            mock_settings.ncbi_extended_enabled = False
            result = await client.get_gene_info("672")
        assert result is None

    @pytest.mark.asyncio
    async def test_search_gene_by_symbol_success(self, client, mock_gene_summary):
        search_resp = MagicMock()
        search_resp.raise_for_status = MagicMock()
        search_resp.json = MagicMock(return_value={
            "esearchresult": {"idlist": ["672"]}
        })

        summary_resp = MagicMock()
        summary_resp.raise_for_status = MagicMock()
        summary_resp.json = MagicMock(return_value={"result": {"672": mock_gene_summary}})

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=[search_resp, summary_resp])

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.search_gene_by_symbol("BRCA1")

        assert result is not None
        assert result["name"] == "BRCA1"

    @pytest.mark.asyncio
    async def test_search_gene_not_found(self, client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "esearchresult": {"idlist": []}
        })

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.search_gene_by_symbol("NOTAREALGENEXXX")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_clinvar_variants_success(self, client, mock_clinvar_summary):
        search_resp = MagicMock()
        search_resp.raise_for_status = MagicMock()
        search_resp.json = MagicMock(return_value={
            "esearchresult": {"idlist": ["12345"]}
        })

        summary_resp = MagicMock()
        summary_resp.raise_for_status = MagicMock()
        summary_resp.json = MagicMock(return_value={
            "result": {"12345": mock_clinvar_summary}
        })

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=[search_resp, summary_resp])

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await client.get_clinvar_variants("BRCA1")

        assert len(results) == 1
        assert results[0]["_source"] == "NCBI ClinVar"
        assert "_retrieved_at" in results[0]

    @pytest.mark.asyncio
    async def test_get_clinvar_variants_empty(self, client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "esearchresult": {"idlist": []}
        })

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await client.get_clinvar_variants("NOTAREALGENEXXX")

        assert results == []

    @pytest.mark.asyncio
    async def test_get_clinvar_variants_disabled(self, client):
        with patch("app.integrations.ncbi_extended.settings") as mock_settings:
            mock_settings.ncbi_extended_enabled = False
            results = await client.get_clinvar_variants("BRCA1")
        assert results == []

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self, client):
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=Exception("connection refused"))

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.get_gene_info("672")

        assert result is None
