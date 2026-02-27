"""Ensembl REST API + VEP (Variant Effect Predictor) client.

Provides variant annotation, gene lookup, and cross-reference queries.

Auth: Not required for GRCh38 REST API.
Rate limit: 15 req/sec max. We use 0.1s delay.
Docs: https://rest.ensembl.org
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://rest.ensembl.org"
_TIMEOUT = 20  # VEP can be slow for complex variants
_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}


class EnsemblClient:
    """Async client for Ensembl REST API and VEP.

    Usage:
        client = EnsemblClient()
        # Annotate by HGVS notation
        results = await client.vep_hgvs("9:g.107545939A>T")
        # Annotate by genomic coordinates
        results = await client.vep_region("17", 41234451, "A", "G")
        # Gene lookup
        gene = await client.get_gene("ENSG00000012048")
    """

    def __init__(self, timeout: int = _TIMEOUT) -> None:
        self._timeout = timeout

    async def vep_hgvs(self, hgvs: str) -> list[dict]:
        """Annotate a variant by HGVS notation (GRCh38).

        Args:
            hgvs: HGVS notation (e.g., "ENST00000357654.9:c.1A>G" or
                  "9:g.107545939A>T" for genomic)

        Returns:
            List of VEP consequence dicts with provenance tagging.
        """
        if not settings.ensembl_enabled:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{_BASE_URL}/vep/human/hgvs/{hgvs}",
                    headers=_HEADERS,
                    params={
                        "CADD": 1, "AlphaMissense": 1, "SpliceRegion": 1,
                        "canonical": 1, "protein": 1, "hgvs": 1,
                        "uniprot": 1, "domains": 1,
                    },
                )
                resp.raise_for_status()
                results = resp.json()
                await asyncio.sleep(settings.ensembl_rate_limit_delay)
                return [self._tag(r) for r in results]
        except Exception as e:
            logger.debug("VEP hgvs failed for %s: %s", hgvs, e)
            return []

    async def vep_region(
        self,
        chrom: str,
        pos: int,
        ref: str,
        alt: str,
        assembly: str = "GRCh38",
    ) -> list[dict]:
        """Annotate a variant by genomic coordinates.

        Args:
            chrom: Chromosome (e.g., "17")
            pos: 1-based position
            ref: Reference allele
            alt: Alternate allele

        Returns:
            List of VEP consequence dicts.
        """
        if not settings.ensembl_enabled:
            return []
        region = f"{chrom}:{pos}:{pos}/{ref}/{alt}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{_BASE_URL}/vep/human/region/{region}",
                    headers=_HEADERS,
                    params={
                        "CADD": 1, "AlphaMissense": 1, "SpliceRegion": 1,
                        "canonical": 1, "protein": 1, "hgvs": 1,
                    },
                )
                resp.raise_for_status()
                results = resp.json()
                await asyncio.sleep(settings.ensembl_rate_limit_delay)
                return [self._tag(r) for r in results]
        except Exception as e:
            logger.debug("VEP region failed for %s:%d %s>%s: %s", chrom, pos, ref, alt, e)
            return []

    async def vep_batch(self, variants: list[dict]) -> list[dict]:
        """Annotate multiple variants in a single POST request (up to 200).

        Args:
            variants: List of dicts with keys 'hgvs' or ('chr', 'start', 'ref', 'alt')

        Returns:
            List of VEP consequence dicts.
        """
        if not settings.ensembl_enabled or not variants:
            return []
        # Convert to Ensembl input format
        inputs = []
        for v in variants[:200]:
            if "hgvs" in v:
                inputs.append({"hgvs_notations": [v["hgvs"]]})
        try:
            async with httpx.AsyncClient(timeout=self._timeout * 3) as client:
                resp = await client.post(
                    f"{_BASE_URL}/vep/human/hgvs",
                    json={"hgvs_notations": [v.get("hgvs", "") for v in variants[:200] if "hgvs" in v]},
                    headers=_HEADERS,
                    params={"CADD": 1, "AlphaMissense": 1, "canonical": 1},
                )
                resp.raise_for_status()
                await asyncio.sleep(settings.ensembl_rate_limit_delay)
                return [self._tag(r) for r in resp.json()]
        except Exception as e:
            logger.debug("VEP batch failed: %s", e)
            return []

    async def get_gene(self, gene_id: str) -> dict | None:
        """Look up a gene by Ensembl gene ID (e.g., 'ENSG00000012048')."""
        if not settings.ensembl_enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{_BASE_URL}/lookup/id/{gene_id}",
                    headers=_HEADERS,
                    params={"expand": 1},
                )
                resp.raise_for_status()
                data = resp.json()
                return self._tag(data)
        except Exception as e:
            logger.debug("Ensembl get_gene failed for %s: %s", gene_id, e)
            return None

    async def get_xrefs(self, gene_id: str) -> list[dict]:
        """Get cross-references (UniProt, HGNC, RefSeq) for a gene."""
        if not settings.ensembl_enabled:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{_BASE_URL}/xrefs/id/{gene_id}",
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.debug("Ensembl get_xrefs failed for %s: %s", gene_id, e)
            return []

    def _tag(self, data: dict) -> dict:
        data["_source"] = "Ensembl VEP v112"
        data["_retrieved_at"] = datetime.now(timezone.utc).isoformat()
        return data
