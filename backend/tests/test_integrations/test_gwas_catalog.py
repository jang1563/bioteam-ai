"""Tests for GWAS Catalog REST client — uses mocked HTTP responses."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.integrations.gwas_catalog import GWASCatalogClient


@pytest.fixture
def client():
    return GWASCatalogClient()


@pytest.fixture
def mock_association():
    return {
        "pvalue": 3.2e-12,
        "pvalueMantissa": 3.2,
        "pvalueExponent": -12,
        "riskAlleleName": "rs12345-A",
        "riskFrequency": "0.35",
        "betaNum": "0.12",
        "orPerCopyNum": "1.13",
        "mappedGenes": "BRCA1",
        "strongestRiskAlleles": [{"riskAlleleName": "rs12345-A"}],
    }


class TestGWASCatalogClient:
    @pytest.mark.asyncio
    async def test_get_associations_by_gene_success(self, client, mock_association):
        response_data = {
            "_embedded": {"associations": [mock_association]}
        }
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=response_data)

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await client.get_associations_by_gene("BRCA1")

        assert len(results) == 1
        assert results[0]["_source"] == "GWAS Catalog v1.0"
        assert "_retrieved_at" in results[0]

    @pytest.mark.asyncio
    async def test_get_associations_filters_by_pvalue(self, client):
        """Only return associations below p_threshold."""
        high_pval = {**{"pvalue": 0.05, "mappedGenes": "BRCA1"}}
        low_pval = {**{"pvalue": 1e-10, "mappedGenes": "BRCA1"}}
        response_data = {"_embedded": {"associations": [high_pval, low_pval]}}

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=response_data)

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await client.get_associations_by_gene("BRCA1", p_threshold=5e-8)

        assert len(results) == 1
        assert results[0]["pvalue"] == 1e-10

    @pytest.mark.asyncio
    async def test_get_associations_disabled(self, client):
        with patch("app.integrations.gwas_catalog.settings") as mock_settings:
            mock_settings.gwas_enabled = False
            results = await client.get_associations_by_gene("BRCA1")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_study_success(self, client):
        study_data = {
            "accessionId": "GCST000392",
            "title": "Genome-wide association study of breast cancer",
            "pubmedId": "20453838",
            "initialSampleSize": "1145 breast cancer cases, 1142 controls",
        }
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=study_data)

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.get_study("GCST000392")

        assert result is not None
        assert result["accessionId"] == "GCST000392"
        assert result["_source"] == "GWAS Catalog v1.0"

    @pytest.mark.asyncio
    async def test_get_study_disabled(self, client):
        with patch("app.integrations.gwas_catalog.settings") as mock_settings:
            mock_settings.gwas_enabled = False
            result = await client.get_study("GCST000392")
        assert result is None

    @pytest.mark.asyncio
    async def test_network_error_returns_empty(self, client):
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=Exception("connection refused"))

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await client.get_associations_by_gene("BRCA1")

        assert results == []
