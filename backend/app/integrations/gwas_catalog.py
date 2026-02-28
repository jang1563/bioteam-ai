"""GWAS Catalog REST API client.

Provides genome-wide association study data: variant-trait associations,
study metadata, and SNP-level results.

Auth: Not required.
Rate limit: Polite — 0.2s delay.
Docs: https://www.ebi.ac.uk/gwas/rest/docs/api
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from app.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.ebi.ac.uk/gwas/rest/api"
_TIMEOUT = 20
_HEADERS = {"Accept": "application/json"}


class GWASCatalogClient:
    """Async client for the GWAS Catalog REST API.

    Usage:
        client = GWASCatalogClient()
        assocs = await client.get_associations_by_gene("BRCA1")
        study = await client.get_study("GCST000392")
    """

    def __init__(self, timeout: int = _TIMEOUT) -> None:
        self._timeout = timeout

    async def get_associations_by_gene(
        self,
        symbol: str,
        p_threshold: float = 5e-8,
        page_size: int = 50,
    ) -> list[dict]:
        """Get GWAS associations for a gene symbol.

        Args:
            symbol: HGNC gene symbol (e.g., "BRCA1")
            p_threshold: Maximum p-value threshold (genome-wide = 5e-8)
            page_size: Max results per page

        Returns:
            List of association dicts with riskAlleleFrequency, pvalue, mappedGenes fields.
        """
        if not settings.gwas_enabled:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{_BASE_URL}/associations/search/findByGene",
                    params={"geneName": symbol, "size": page_size},
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                data = resp.json()
                await asyncio.sleep(0.2)
                associations = data.get("_embedded", {}).get("associations", [])
                # Filter by p-value threshold
                filtered = [
                    self._tag(a) for a in associations
                    if float(a.get("pvalue", 1.0) or 1.0) <= p_threshold
                ]
                return filtered
        except Exception as e:
            logger.debug("GWAS get_associations_by_gene failed for %s: %s", symbol, e)
            return []

    async def get_associations_by_snp(
        self,
        rsid: str,
        p_threshold: float = 5e-8,
    ) -> list[dict]:
        """Get GWAS associations for a specific SNP (rsID).

        Args:
            rsid: dbSNP rsID (e.g., "rs12345678")
            p_threshold: Maximum p-value threshold

        Returns:
            List of association dicts.
        """
        if not settings.gwas_enabled:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{_BASE_URL}/singleNucleotidePolymorphisms/{rsid}/associations",
                    params={"size": 20},
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                data = resp.json()
                await asyncio.sleep(0.2)
                associations = data.get("_embedded", {}).get("associations", [])
                return [
                    self._tag(a) for a in associations
                    if float(a.get("pvalue", 1.0) or 1.0) <= p_threshold
                ]
        except Exception as e:
            logger.debug("GWAS get_associations_by_snp failed for %s: %s", rsid, e)
            return []

    async def get_study(self, accession: str) -> dict | None:
        """Get GWAS study metadata by accession (e.g., 'GCST000392').

        Args:
            accession: GWAS Catalog study accession

        Returns:
            Study dict with title, pubmedId, ancestryLinks, initialSampleSize fields.
        """
        if not settings.gwas_enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{_BASE_URL}/studies/{accession}",
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                data = resp.json()
                await asyncio.sleep(0.2)
                return self._tag(data)
        except Exception as e:
            logger.debug("GWAS get_study failed for %s: %s", accession, e)
            return None

    async def get_trait_associations(
        self,
        efo_trait: str,
        p_threshold: float = 5e-8,
        page_size: int = 50,
    ) -> list[dict]:
        """Get associations for a specific EFO trait ID.

        Args:
            efo_trait: EFO trait accession (e.g., "EFO_0000305" for breast carcinoma)
            p_threshold: Maximum p-value threshold
            page_size: Max results per page

        Returns:
            List of association dicts.
        """
        if not settings.gwas_enabled:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{_BASE_URL}/efoTraits/{efo_trait}/associations",
                    params={"size": page_size},
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                data = resp.json()
                await asyncio.sleep(0.2)
                associations = data.get("_embedded", {}).get("associations", [])
                return [
                    self._tag(a) for a in associations
                    if float(a.get("pvalue", 1.0) or 1.0) <= p_threshold
                ]
        except Exception as e:
            logger.debug("GWAS get_trait_associations failed for %s: %s", efo_trait, e)
            return []

    def _tag(self, data: dict) -> dict:
        data["_source"] = "GWAS Catalog v1.0"
        data["_retrieved_at"] = datetime.now(timezone.utc).isoformat()
        return data
