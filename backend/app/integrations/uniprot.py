"""UniProt REST v2 API client.

Provides structured access to UniProt protein entries, gene-based searches,
and protein-protein interaction data.

Auth: Not required (public API).
Rate limit: ~10 req/sec recommended; we use 0.1s delay between requests.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://rest.uniprot.org"
_TIMEOUT = 15


class UniProtClient:
    """Async client for UniProt REST API v2.

    Usage:
        client = UniProtClient()
        entry = await client.get_entry("P04637")  # TP53
        results = await client.search_by_gene("TP53", organism=9606)
    """

    def __init__(self, timeout: int = _TIMEOUT) -> None:
        self._timeout = timeout
        self._headers = {
            "Accept": "application/json",
            "User-Agent": "BioTeam-AI/1.0 (research; contact@bioteam.ai)",
        }

    async def get_entry(self, accession: str) -> dict | None:
        """Fetch a UniProt entry by accession (e.g., 'P04637').

        Returns the full entry dict with provenance tagging, or None on failure.
        """
        if not settings.uniprot_enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{_BASE_URL}/uniprotkb/{accession}",
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
                return self._tag(data, accession)
        except Exception as e:
            logger.debug("UniProt get_entry failed for %s: %s", accession, e)
            return None

    async def search_by_gene(
        self,
        gene_symbol: str,
        organism: int = 9606,
        reviewed_only: bool = True,
        max_results: int = 5,
    ) -> list[dict]:
        """Search UniProt entries by gene symbol and organism.

        Args:
            gene_symbol: HGNC gene symbol (e.g., 'BRCA1')
            organism: NCBI taxonomy ID (9606 = human, 10090 = mouse)
            reviewed_only: If True, return only SwissProt (curated) entries
            max_results: Maximum number of entries to return

        Returns:
            List of UniProt entry dicts with provenance tagging.
        """
        if not settings.uniprot_enabled:
            return []
        reviewed_filter = " AND (reviewed:true)" if reviewed_only else ""
        query = f"gene:{gene_symbol} AND (organism_id:{organism}){reviewed_filter}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{_BASE_URL}/uniprotkb/search",
                    params={"query": query, "format": "json", "size": max_results},
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                await asyncio.sleep(settings.uniprot_rate_limit_delay)
                return [self._tag(r, r.get("primaryAccession", "")) for r in results]
        except Exception as e:
            logger.debug("UniProt search_by_gene failed for %s: %s", gene_symbol, e)
            return []

    async def get_interactions(self, accession: str) -> list[dict]:
        """Get protein-protein interactions for an entry.

        Returns list of interaction partner dicts from the UniProt entry's
        interactions section.
        """
        if not settings.uniprot_enabled:
            return []
        entry = await self.get_entry(accession)
        if not entry:
            return []
        interactions = []
        for comment in entry.get("comments", []):
            if comment.get("commentType") == "INTERACTION":
                for interaction in comment.get("interactions", []):
                    partner = interaction.get("interactant", {})
                    interactions.append({
                        "partner_accession": partner.get("uniProtKBAccession", ""),
                        "gene_name": partner.get("geneName", ""),
                        "experiment_count": interaction.get("numberOfExperiments", 0),
                        "organism_differ": interaction.get("organismDiffer", False),
                    })
        return interactions

    def _tag(self, data: dict, accession: str) -> dict:
        """Add provenance tags to a UniProt entry."""
        data["_source"] = "UniProt REST v2"
        data["_retrieved_at"] = datetime.now(timezone.utc).isoformat()
        data["_accession"] = accession
        return data
