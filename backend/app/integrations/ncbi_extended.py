"""NCBI E-utilities extended client.

Supplements the existing pubmed.py with Gene database and ClinVar queries.
Reuses NCBI_API_KEY and NCBI_EMAIL from environment (same as pubmed.py).

Auth: API key optional (10 req/sec with key, 3 req/sec without).
Rate limit: Managed automatically via delay.
Docs: https://www.ncbi.nlm.nih.gov/books/NBK25499/
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_TIMEOUT = 20
_HEADERS = {"Accept": "application/json"}

# Delay: 0.1s with API key (10/sec), 0.34s without (3/sec)
_DELAY_WITH_KEY = 0.1
_DELAY_NO_KEY = 0.35


def _get_delay() -> float:
    return _DELAY_WITH_KEY if settings.ncbi_api_key else _DELAY_NO_KEY


def _base_params() -> dict:
    """Base parameters shared across all E-utilities calls."""
    params: dict = {"retmode": "json", "tool": "BioTeamAI"}
    if settings.ncbi_api_key:
        params["api_key"] = settings.ncbi_api_key
    if settings.ncbi_email:
        params["email"] = settings.ncbi_email
    return params


class NCBIExtendedClient:
    """Async client for NCBI Gene database and ClinVar.

    Complements pubmed.py (which handles literature search).

    Usage:
        client = NCBIExtendedClient()
        gene = await client.get_gene_info("672")         # by Gene ID
        gene = await client.search_gene_by_symbol("BRCA1")  # by symbol
        variants = await client.get_clinvar_variants("BRCA1")
    """

    def __init__(self, timeout: int = _TIMEOUT) -> None:
        self._timeout = timeout

    async def get_gene_info(self, gene_id: str) -> dict | None:
        """Get full gene summary from NCBI Gene database.

        Args:
            gene_id: NCBI Gene ID (e.g., "672" for BRCA1)

        Returns:
            Gene info dict with name, description, chromosome, maplocation,
            summary, and cross-references.
        """
        if not settings.ncbi_extended_enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{_BASE_URL}/esummary.fcgi",
                    params={**_base_params(), "db": "gene", "id": gene_id},
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                data = resp.json()
                await asyncio.sleep(_get_delay())
                result = data.get("result", {}).get(str(gene_id))
                if result:
                    return self._tag(result, "Gene")
                return None
        except Exception as e:
            logger.debug("NCBI get_gene_info failed for %s: %s", gene_id, e)
            return None

    async def search_gene_by_symbol(
        self,
        symbol: str,
        organism: str = "Homo sapiens[Organism]",
    ) -> dict | None:
        """Search NCBI Gene database by gene symbol.

        Args:
            symbol: HGNC gene symbol (e.g., "BRCA1")
            organism: NCBI organism filter

        Returns:
            First matching gene info dict, or None.
        """
        if not settings.ncbi_extended_enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                # Step 1: Search
                search_resp = await client.get(
                    f"{_BASE_URL}/esearch.fcgi",
                    params={
                        **_base_params(),
                        "db": "gene",
                        "term": f'"{symbol}"[Gene Name] AND {organism}',
                        "retmax": 1,
                    },
                    headers=_HEADERS,
                )
                search_resp.raise_for_status()
                search_data = search_resp.json()
                await asyncio.sleep(_get_delay())

                ids = search_data.get("esearchresult", {}).get("idlist", [])
                if not ids:
                    return None

                # Step 2: Fetch summary
                return await self.get_gene_info(ids[0])
        except Exception as e:
            logger.debug("NCBI search_gene_by_symbol failed for %s: %s", symbol, e)
            return None

    async def get_clinvar_variants(
        self,
        gene_symbol: str,
        clinical_significance: list[str] | None = None,
        max_results: int = 50,
    ) -> list[dict]:
        """Get ClinVar variant entries for a gene.

        Args:
            gene_symbol: HGNC gene symbol (e.g., "BRCA1")
            clinical_significance: Filter by significance (e.g., ["Pathogenic", "Likely pathogenic"])
            max_results: Maximum variants to return

        Returns:
            List of ClinVar variant summaries with variationId, name,
            clinicalSignificance, reviewStatus, conditions fields.
        """
        if not settings.ncbi_extended_enabled:
            return []
        if clinical_significance is None:
            clinical_significance = ["Pathogenic", "Likely pathogenic"]

        sig_filter = " OR ".join(
            f'"{s}"[Clinical significance]' for s in clinical_significance
        )
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                # Search ClinVar
                search_resp = await client.get(
                    f"{_BASE_URL}/esearch.fcgi",
                    params={
                        **_base_params(),
                        "db": "clinvar",
                        "term": f'"{gene_symbol}"[Gene Name] AND ({sig_filter})',
                        "retmax": max_results,
                    },
                    headers=_HEADERS,
                )
                search_resp.raise_for_status()
                search_data = search_resp.json()
                await asyncio.sleep(_get_delay())

                ids = search_data.get("esearchresult", {}).get("idlist", [])
                if not ids:
                    return []

                # Fetch summaries in batch
                summary_resp = await client.get(
                    f"{_BASE_URL}/esummary.fcgi",
                    params={
                        **_base_params(),
                        "db": "clinvar",
                        "id": ",".join(ids),
                    },
                    headers=_HEADERS,
                )
                summary_resp.raise_for_status()
                summary_data = summary_resp.json()
                await asyncio.sleep(_get_delay())

                result_map = summary_data.get("result", {})
                variants = []
                for uid in ids:
                    entry = result_map.get(str(uid))
                    if entry:
                        variants.append(self._tag(entry, "ClinVar"))
                return variants
        except Exception as e:
            logger.debug("NCBI get_clinvar_variants failed for %s: %s", gene_symbol, e)
            return []

    async def get_gene_neighbors(
        self,
        gene_id: str,
        max_genes: int = 10,
    ) -> list[dict]:
        """Get neighboring genes in the same chromosomal region (eLink).

        Args:
            gene_id: NCBI Gene ID
            max_genes: Maximum neighboring genes to return

        Returns:
            List of gene summary dicts for neighbors.
        """
        if not settings.ncbi_extended_enabled:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{_BASE_URL}/elink.fcgi",
                    params={
                        **_base_params(),
                        "db": "gene",
                        "dbfrom": "gene",
                        "id": gene_id,
                        "linkname": "gene_gene_neighbors",
                    },
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                data = resp.json()
                await asyncio.sleep(_get_delay())
                # eLink in JSON returns complex structure
                linksets = data.get("linksets", [])
                if not linksets:
                    return []
                links = linksets[0].get("linksetdbs", [])
                if not links:
                    return []
                neighbor_ids = [str(l) for l in links[0].get("links", [])[:max_genes]]
                if not neighbor_ids:
                    return []
                # Fetch summaries
                sum_resp = await client.get(
                    f"{_BASE_URL}/esummary.fcgi",
                    params={
                        **_base_params(),
                        "db": "gene",
                        "id": ",".join(neighbor_ids),
                    },
                    headers=_HEADERS,
                )
                sum_resp.raise_for_status()
                sum_data = sum_resp.json()
                await asyncio.sleep(_get_delay())
                result_map = sum_data.get("result", {})
                return [
                    self._tag(result_map[gid], "NCBI Gene")
                    for gid in neighbor_ids
                    if gid in result_map
                ]
        except Exception as e:
            logger.debug("NCBI get_gene_neighbors failed for %s: %s", gene_id, e)
            return []

    def _tag(self, data: dict, db: str) -> dict:
        data["_source"] = f"NCBI {db}"
        data["_retrieved_at"] = datetime.now(timezone.utc).isoformat()
        return data
