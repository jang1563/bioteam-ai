"""Open Peer Review corpus client — eLife (primary), PLOS (secondary).

eLife v2 API: https://api.elifesciences.org/articles/{id}
  - Returns JSON with full article metadata and review files
  - Review file download: https://cdn.elifesciences.org/articles/{id}/elife-{id}-decision-letter-v*.xml

PLOS ONE: JATS XML at https://journals.plos.org/plosone/article/file?id={doi}&type=manuscript

Toggle: settings.peer_review_corpus_enabled (default False)
Rate limit: 2 req/s (eLife CDN) with 3× exponential backoff
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from app.config import settings

logger = logging.getLogger(__name__)

ELIFE_API = "https://api.elifesciences.org"
ELIFE_CDN = "https://cdn.elifesciences.org"
PLOS_API = "https://journals.plos.org/plosone/article/file"

ELIFE_CITATION = (
    "eLife Sciences Publications Ltd. Open Peer Review. "
    "Reviewed Preprints and Decision Letters. CC-BY 4.0."
)


class PeerReviewCorpusClient:
    """Async client for fetching open peer review articles and their reviews.

    Supports eLife (JSON API + XML CDN) and PLOS ONE (JATS XML).
    """

    def __init__(self) -> None:
        self._timeout = httpx.Timeout(30.0, connect=10.0)

    # ── eLife ────────────────────────────────────────────────────────────────

    async def get_elife_article_meta(self, article_id: str) -> dict | None:
        """Fetch eLife article metadata from the v2 API.

        Returns dict with id, doi, title, published_year, status, etc.
        or None if disabled / not found.
        """
        if not settings.peer_review_corpus_enabled:
            return None
        url = f"{ELIFE_API}/articles/{article_id}"
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(url, headers={"Accept": "application/vnd.elife.article-vor+json"})
                    resp.raise_for_status()
                    data = resp.json()
                    return {
                        "id": str(data.get("id", article_id)),
                        "doi": data.get("doi", ""),
                        "title": data.get("title", ""),
                        "published_year": self._extract_year(data.get("published", "")),
                        "journal": "eLife",
                        "_source": "eLife API v2",
                        "_citation": ELIFE_CITATION,
                        "_retrieved_at": datetime.now(timezone.utc).isoformat(),
                    }
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    logger.debug("eLife article %s not found", article_id)
                    return None
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.warning("eLife API error for %s (attempt %d): %s", article_id, attempt + 1, e)
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
        return None

    async def get_elife_reviews_xml(self, article_id: str, version: int = 1) -> str | None:
        """Fetch the decision letter + author response XML from eLife CDN.

        Returns raw XML string or None if unavailable.
        """
        if not settings.peer_review_corpus_enabled:
            return None
        # Try decision letter XML
        url = f"{ELIFE_CDN}/articles/{article_id}/elife-{article_id}-decision-letter-v{version}.xml"
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        return resp.text
                    if resp.status_code == 404 and version == 1:
                        # Try version 2
                        return await self.get_elife_reviews_xml(article_id, version=2)
                    return None
            except Exception as e:
                logger.warning("eLife CDN error for %s v%d: %s", article_id, version, e)
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
        return None

    async def search_elife_articles(
        self,
        subject: str = "",
        start_date: str = "2020-01-01",
        page_size: int = 20,
        page: int = 1,
    ) -> list[dict]:
        """Search eLife articles by subject and date range.

        Returns list of article metadata dicts (id, doi, title, published_year).
        """
        if not settings.peer_review_corpus_enabled:
            return []
        params: dict = {
            "page": page,
            "per-page": page_size,
            "order": "desc",
            "start-date": start_date,
        }
        if subject:
            params["subject[]"] = subject
        url = f"{ELIFE_API}/articles"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                items = data.get("items", [])
                return [
                    {
                        "id": str(item.get("id", "")),
                        "doi": item.get("doi", ""),
                        "title": item.get("title", ""),
                        "published_year": self._extract_year(item.get("published", "")),
                        "journal": "eLife",
                    }
                    for item in items
                ]
        except Exception as e:
            logger.warning("eLife search failed: %s", e)
            return []

    # ── PLOS ─────────────────────────────────────────────────────────────────

    async def get_plos_review_xml(self, doi: str) -> str | None:
        """Fetch PLOS article XML which includes review sections.

        PLOS embeds peer review reports in its JATS XML under <sec sec-type="peer-review">.
        """
        if not settings.peer_review_corpus_enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    PLOS_API,
                    params={"id": doi, "type": "manuscript"},
                )
                if resp.status_code == 200:
                    return resp.text
                return None
        except Exception as e:
            logger.warning("PLOS XML fetch failed for %s: %s", doi, e)
            return None

    # ── Internal ─────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_year(date_str: str) -> int | None:
        """Extract year from ISO date string like '2023-05-15'."""
        if date_str and len(date_str) >= 4:
            try:
                return int(date_str[:4])
            except ValueError:
                return None
        return None
