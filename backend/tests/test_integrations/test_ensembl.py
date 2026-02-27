"""Tests for Ensembl REST + VEP client — uses mocked HTTP responses."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.ensembl import EnsemblClient


@pytest.fixture
def client():
    return EnsemblClient()


@pytest.fixture
def mock_vep_result():
    return {
        "id": "9:107545939-107545939",
        "most_severe_consequence": "missense_variant",
        "transcript_consequences": [
            {
                "transcript_id": "ENST00000371953",
                "gene_id": "ENSG00000136997",
                "gene_symbol": "MYC",
                "consequence_terms": ["missense_variant"],
                "cadd_phred": 25.3,
                "am_class": "likely_benign",
                "am_pathogenicity": 0.12,
            }
        ],
    }


class TestEnsemblClient:
    @pytest.mark.asyncio
    async def test_vep_hgvs_success(self, client, mock_vep_result):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=[mock_vep_result])

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await client.vep_hgvs("9:g.107545939A>T")

        assert len(results) == 1
        assert results[0]["most_severe_consequence"] == "missense_variant"
        assert results[0]["_source"] == "Ensembl VEP v112"
        assert "_retrieved_at" in results[0]

    @pytest.mark.asyncio
    async def test_vep_hgvs_disabled(self, client):
        with patch("app.integrations.ensembl.settings") as mock_settings:
            mock_settings.ensembl_enabled = False
            results = await client.vep_hgvs("9:g.107545939A>T")
        assert results == []

    @pytest.mark.asyncio
    async def test_vep_region_success(self, client, mock_vep_result):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=[mock_vep_result])

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await client.vep_region("17", 41234451, "A", "G")

        assert len(results) == 1
        assert results[0]["_source"] == "Ensembl VEP v112"

    @pytest.mark.asyncio
    async def test_vep_batch_success(self, client, mock_vep_result):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=[mock_vep_result])

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            variants = [{"hgvs": "9:g.107545939A>T"}, {"hgvs": "17:g.41234451A>G"}]
            results = await client.vep_batch(variants)

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_vep_batch_empty_list(self, client):
        results = await client.vep_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_get_gene_success(self, client):
        mock_data = {
            "id": "ENSG00000012048",
            "display_name": "BRCA1",
            "description": "BRCA1 DNA repair associated",
            "biotype": "protein_coding",
        }
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=mock_data)

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.get_gene("ENSG00000012048")

        assert result is not None
        assert result["display_name"] == "BRCA1"
        assert result["_source"] == "Ensembl VEP v112"

    @pytest.mark.asyncio
    async def test_get_gene_disabled(self, client):
        with patch("app.integrations.ensembl.settings") as mock_settings:
            mock_settings.ensembl_enabled = False
            result = await client.get_gene("ENSG00000012048")
        assert result is None

    @pytest.mark.asyncio
    async def test_network_error_returns_empty(self, client):
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=Exception("timeout"))

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await client.vep_hgvs("9:g.107545939A>T")

        assert results == []
