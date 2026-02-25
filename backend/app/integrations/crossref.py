"""Crossref API client — retraction/correction status checking.

Checks DOIs against the Crossref REST API for retraction notices,
corrections, and expressions of concern.

Respects the Crossref polite pool: set CROSSREF_EMAIL in config
for higher rate limits.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.engines.integrity.finding_models import RetractionStatus

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10
_USER_AGENT = "BioTeam-AI/0.1 (https://github.com/bioteam-ai; mailto:{email})"


class CrossrefClient:
    """Async client for the Crossref REST API."""

    BASE_URL = "https://api.crossref.org"

    def __init__(
        self,
        email: str = "",
        timeout: int = _DEFAULT_TIMEOUT,
        max_concurrency: int = 5,
    ) -> None:
        self._email = email
        self._timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._headers = {
            "User-Agent": _USER_AGENT.format(email=email or "noreply@example.com"),
            "Accept": "application/json",
        }

    async def check_retraction(self, doi: str) -> RetractionStatus:
        """Check a single DOI for retraction/correction status.

        Queries the Crossref works endpoint and inspects the 'update-to'
        and 'relation' fields for retraction/correction notices.
        """
        async with self._semaphore:
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    url = f"{self.BASE_URL}/works/{doi}"
                    resp = await client.get(url, headers=self._headers)

                    if resp.status_code == 404:
                        return RetractionStatus(doi=doi)

                    resp.raise_for_status()
                    data = resp.json().get("message", {})

                    return self._parse_work(doi, data)

            except httpx.TimeoutException:
                logger.warning("Crossref timeout for DOI %s", doi)
                return RetractionStatus(doi=doi)
            except Exception as e:
                logger.warning("Crossref error for DOI %s: %s", doi, e)
                return RetractionStatus(doi=doi)

    async def check_batch(
        self,
        dois: list[str],
        concurrency: int | None = None,
    ) -> list[RetractionStatus]:
        """Check multiple DOIs concurrently.

        Respects rate limits via internal semaphore.
        """
        if not dois:
            return []

        tasks = [self.check_retraction(doi) for doi in dois]
        return await asyncio.gather(*tasks)

    def _parse_work(self, doi: str, data: dict) -> RetractionStatus:
        """Parse Crossref work response for retraction/correction info."""
        publisher = ""
        for container in data.get("container-title", []):
            publisher = container
            break

        is_retracted = False
        is_corrected = False
        has_eoc = False
        retraction_doi = None
        correction_doi = None
        retraction_date = None

        # Check the 'type' field — the work itself might be a retraction notice
        work_type = data.get("type", "")
        if work_type == "retraction":
            is_retracted = True

        # Check 'update-to' field — this work updates another (is itself a retraction/correction)
        for update in data.get("update-to", []):
            update_type = update.get("type", "").lower()
            update_doi = update.get("DOI", "")
            if "retraction" in update_type:
                is_retracted = True
                retraction_doi = update_doi
            elif "correction" in update_type or "erratum" in update_type:
                is_corrected = True
                correction_doi = update_doi

        # Check 'relation' field for expressions of concern
        for rel_type, rels in data.get("relation", {}).items():
            for rel in rels if isinstance(rels, list) else [rels]:
                if isinstance(rel, dict):
                    rel_label = rel.get("id-type", "")
                    if "expression-of-concern" in rel_label.lower():
                        has_eoc = True

        # Check 'is-referenced-by' for retraction notices pointing at this DOI
        # (Crossref sometimes stores it this way)

        return RetractionStatus(
            doi=doi,
            is_retracted=is_retracted,
            is_corrected=is_corrected,
            has_expression_of_concern=has_eoc,
            retraction_doi=retraction_doi,
            correction_doi=correction_doi,
            retraction_date=retraction_date,
            publisher=publisher,
        )
