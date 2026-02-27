"""STRING DB v12 API client.

Provides protein-protein interaction networks and functional enrichment.

Auth: Not required.
Rate limit: Conservative 0.5s delay (no formal limit stated).
Docs: https://string-db.org/help/api/
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://string-db.org/api"
_FORMAT = "json"
_CALLER = "BioTeamAI"
_TIMEOUT = 30
_HEADERS = {"Accept": "application/json"}


class STRINGClient:
    """Async client for STRING DB v12 protein interaction network.

    Usage:
        client = STRINGClient()
        interactions = await client.get_interactions(["BRCA1", "TP53", "ATM"])
        enrichment = await client.enrich_network(["BRCA1", "TP53"])
    """

    def __init__(self, timeout: int = _TIMEOUT) -> None:
        self._timeout = timeout

    async def get_interactions(
        self,
        identifiers: list[str],
        species: int = 9606,
        min_score: int = 400,
        limit: int = 50,
    ) -> list[dict]:
        """Get protein-protein interactions for a list of gene/protein names.

        Args:
            identifiers: List of gene symbols or protein names (e.g., ["BRCA1", "TP53"])
            species: NCBI taxonomy ID (9606 = human)
            min_score: Minimum combined score (0-1000). 400=medium, 700=high, 900=highest
            limit: Max interactions to return per protein

        Returns:
            List of interaction dicts with score, preferredName_A/B fields.
        """
        if not settings.stringdb_enabled or not identifiers:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{_BASE_URL}/{_FORMAT}/network",
                    data={
                        "identifiers": "%0d".join(identifiers),
                        "species": species,
                        "required_score": min_score,
                        "limit": limit,
                        "caller_identity": _CALLER,
                    },
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                results = resp.json()
                await asyncio.sleep(settings.stringdb_rate_limit_delay)
                return [self._tag(r) for r in results]
        except Exception as e:
            logger.debug("STRING get_interactions failed for %s: %s", identifiers[:3], e)
            return []

    async def enrich_network(
        self,
        identifiers: list[str],
        species: int = 9606,
    ) -> list[dict]:
        """Get functional enrichment for a set of proteins (GO, KEGG, Reactome, Pfam).

        Args:
            identifiers: List of gene symbols or protein names
            species: NCBI taxonomy ID (9606 = human)

        Returns:
            List of enrichment dicts with category, term, description, fdr fields.
        """
        if not settings.stringdb_enabled or not identifiers:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{_BASE_URL}/{_FORMAT}/enrichment",
                    data={
                        "identifiers": "%0d".join(identifiers),
                        "species": species,
                        "caller_identity": _CALLER,
                    },
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                results = resp.json()
                await asyncio.sleep(settings.stringdb_rate_limit_delay)
                return [self._tag(r) for r in results]
        except Exception as e:
            logger.debug("STRING enrich_network failed for %s: %s", identifiers[:3], e)
            return []

    async def resolve_identifiers(
        self,
        identifiers: list[str],
        species: int = 9606,
    ) -> list[dict]:
        """Resolve gene/protein names to STRING IDs.

        Args:
            identifiers: List of gene symbols or protein names
            species: NCBI taxonomy ID

        Returns:
            List of dicts with queryItem, stringId, preferredName, annotation fields.
        """
        if not settings.stringdb_enabled or not identifiers:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{_BASE_URL}/{_FORMAT}/get_string_ids",
                    data={
                        "identifiers": "%0d".join(identifiers),
                        "species": species,
                        "limit": 1,
                        "caller_identity": _CALLER,
                    },
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                await asyncio.sleep(settings.stringdb_rate_limit_delay)
                return resp.json()
        except Exception as e:
            logger.debug("STRING resolve_identifiers failed: %s", e)
            return []

    def _tag(self, data: dict) -> dict:
        data["_source"] = "STRING DB v12"
        data["_retrieved_at"] = datetime.now(timezone.utc).isoformat()
        return data
