"""Tests for UniProt REST v2 client — uses mocked HTTP responses."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.uniprot import UniProtClient


@pytest.fixture
def client():
    return UniProtClient()


@pytest.fixture
def mock_entry():
    return {
        "primaryAccession": "P04637",
        "uniProtkbId": "P53_HUMAN",
        "organism": {"scientificName": "Homo sapiens", "taxonId": 9606},
        "proteinDescription": {"recommendedName": {"fullName": {"value": "Cellular tumor antigen p53"}}},
        "genes": [{"geneName": {"value": "TP53"}}],
        "annotationScore": 5,
        "reviewed": True,
        "sequence": {"length": 393, "molWeight": 43653},
        "features": [],
    }


class TestUniProtClient:
    @pytest.mark.asyncio
    async def test_get_entry_success(self, client, mock_entry):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=mock_entry)

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.get_entry("P04637")

        assert result is not None
        assert result["primaryAccession"] == "P04637"
        assert result["_source"] == "UniProt REST v2"
        assert "_retrieved_at" in result

    @pytest.mark.asyncio
    async def test_get_entry_disabled(self, client):
        with patch("app.integrations.uniprot.settings") as mock_settings:
            mock_settings.uniprot_enabled = False
            result = await client.get_entry("P04637")
        assert result is None

    @pytest.mark.asyncio
    async def test_search_by_gene_success(self, client, mock_entry):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"results": [mock_entry]})

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await client.search_by_gene("TP53")

        assert len(results) == 1
        assert results[0]["primaryAccession"] == "P04637"

    @pytest.mark.asyncio
    async def test_search_by_gene_empty(self, client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"results": []})

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await client.search_by_gene("NOTAREALPROTEIN999")

        assert results == []

    @pytest.mark.asyncio
    async def test_get_interactions_success(self, client):
        # get_interactions calls get_entry internally and parses comments
        mock_entry = {
            "primaryAccession": "P04637",
            "comments": [
                {
                    "commentType": "INTERACTION",
                    "interactions": [
                        {
                            "interactant": {"uniProtKBAccession": "Q00987", "geneName": "MDM2"},
                            "numberOfExperiments": 5,
                            "organismDiffer": False,
                        }
                    ],
                }
            ],
        }
        with patch.object(client, "get_entry", AsyncMock(return_value=mock_entry)):
            results = await client.get_interactions("P04637")

        assert len(results) == 1
        assert results[0]["partner_accession"] == "Q00987"
        assert results[0]["gene_name"] == "MDM2"

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self, client):
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=Exception("connection refused"))

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.get_entry("P04637")

        assert result is None

    @pytest.mark.asyncio
    async def test_search_network_error_returns_empty(self, client):
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=Exception("timeout"))

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await client.search_by_gene("TP53")

        assert results == []
