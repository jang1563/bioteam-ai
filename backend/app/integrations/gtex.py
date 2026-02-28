"""GTEx Portal v2 API client.

Provides gene expression data across 54 human tissues (GTEx Analysis V10).

Auth: Not required.
Rate limit: 0.2s delay (no formal limit stated).
Docs: https://gtexportal.org/api/v2/swagger
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from app.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://gtexportal.org/api/v2"
_TIMEOUT = 20
_HEADERS = {"Accept": "application/json"}

# GTEx citation — must be included in agent outputs
GTEX_CITATION = "GTEx Analysis V10 (hg38); dbGaP phs000424.v10; n=980 donors, 54 tissues"


class GTExClient:
    """Async client for GTEx Portal v2 expression data.

    Usage:
        client = GTExClient()
        expr = await client.get_gene_expression("ENSG00000012048")
        top = await client.get_top_expressed_tissues("BRCA1")
    """

    def __init__(self, timeout: int = _TIMEOUT) -> None:
        self._timeout = timeout

    async def get_gene_expression(
        self,
        gene_id: str,
        dataset_id: str = "gtex_v10",
    ) -> dict | None:
        """Get expression data for a gene across all GTEx tissues.

        Args:
            gene_id: Ensembl gene ID (e.g., "ENSG00000012048") or gene symbol
            dataset_id: GTEx dataset version (default: gtex_v10)

        Returns:
            Dict with geneId, geneName, and list of tissueMedianTpms.
        """
        if not settings.gtex_enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{_BASE_URL}/expression/medianGeneExpression",
                    params={"gencodeId": gene_id, "datasetId": dataset_id},
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                data = resp.json()
                await asyncio.sleep(0.2)
                result = data.get("data", {})
                if result:
                    result = self._tag(result)
                    result["_citation"] = GTEX_CITATION
                return result or None
        except Exception as e:
            logger.debug("GTEx get_gene_expression failed for %s: %s", gene_id, e)
            return None

    async def get_top_expressed_tissues(
        self,
        gene_symbol: str,
        top_n: int = 5,
        dataset_id: str = "gtex_v10",
    ) -> list[dict]:
        """Get the top N tissues by median TPM for a gene symbol.

        Args:
            gene_symbol: HGNC gene symbol (e.g., "BRCA1")
            top_n: Number of top tissues to return
            dataset_id: GTEx dataset version

        Returns:
            List of {tissue, median_tpm} dicts sorted by median_tpm descending.
        """
        if not settings.gtex_enabled:
            return []
        # First, resolve symbol to Ensembl ID
        ensembl_id = await self.search_gene(gene_symbol)
        if not ensembl_id:
            return []
        data = await self.get_gene_expression(ensembl_id, dataset_id=dataset_id)
        if not data:
            return []
        tissue_data = data.get("medianTranscriptExpression") or data.get("data", [])
        if not isinstance(tissue_data, list):
            return []
        sorted_tissues = sorted(
            [{"tissue": t.get("tissueSiteDetailId", ""), "median_tpm": t.get("median", 0.0)} for t in tissue_data],
            key=lambda x: x["median_tpm"],
            reverse=True,
        )
        return sorted_tissues[:top_n]

    async def search_gene(self, symbol: str) -> str | None:
        """Search for a gene by symbol and return its Ensembl ID.

        Args:
            symbol: HGNC gene symbol (e.g., "BRCA1")

        Returns:
            Ensembl gene ID (versioned, e.g., "ENSG00000012048.22") or None.
        """
        if not settings.gtex_enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{_BASE_URL}/reference/gene",
                    params={"geneSymbol": symbol, "gencodeVersion": "v26", "genomeBuild": "GRCh38/hg38"},
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                data = resp.json()
                await asyncio.sleep(0.2)
                genes = data.get("data", [])
                if genes:
                    return genes[0].get("gencodeId")
                return None
        except Exception as e:
            logger.debug("GTEx search_gene failed for %s: %s", symbol, e)
            return None

    async def get_eqtl(
        self,
        gene_id: str,
        tissue: str,
        dataset_id: str = "gtex_v10",
        page_size: int = 20,
    ) -> list[dict]:
        """Get significant eQTLs for a gene in a specific tissue.

        Args:
            gene_id: Ensembl gene ID (versioned, e.g., "ENSG00000012048.22")
            tissue: GTEx tissue site detail ID (e.g., "Breast_Mammary_Tissue")
            dataset_id: GTEx dataset version

        Returns:
            List of eQTL dicts with variantId, pValue, slope fields.
        """
        if not settings.gtex_enabled:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{_BASE_URL}/association/singleTissueEqtl",
                    params={
                        "gencodeId": gene_id,
                        "tissueSiteDetailId": tissue,
                        "datasetId": dataset_id,
                        "numResults": page_size,
                    },
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                data = resp.json()
                await asyncio.sleep(0.2)
                return [self._tag(r) for r in data.get("data", [])]
        except Exception as e:
            logger.debug("GTEx get_eqtl failed for %s/%s: %s", gene_id, tissue, e)
            return []

    def _tag(self, data: dict) -> dict:
        data["_source"] = "GTEx Portal v2 (V10)"
        data["_retrieved_at"] = datetime.now(timezone.utc).isoformat()
        return data
