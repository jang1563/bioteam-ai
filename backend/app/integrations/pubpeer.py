"""PubPeer API client — post-publication commentary checking.

Queries PubPeer for DOIs that have received community commentary,
which may indicate integrity concerns.
"""

from __future__ import annotations

import logging

import httpx
from app.engines.integrity.finding_models import PubPeerStatus

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10


class PubPeerClient:
    """Client for the PubPeer API."""

    BASE_URL = "https://pubpeer.com/api/v1"

    def __init__(self, timeout: int = _DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout

    async def check_doi(self, doi: str) -> PubPeerStatus:
        """Check a DOI for PubPeer commentary.

        Returns PubPeerStatus with comment count.
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                url = f"{self.BASE_URL}/publications"
                params = {"devkey": "", "doi": doi}
                resp = await client.get(url, params=params)

                if resp.status_code == 404:
                    return PubPeerStatus(doi=doi)

                resp.raise_for_status()
                data = resp.json()

                publications = data.get("publications", [])
                if not publications:
                    return PubPeerStatus(doi=doi)

                pub = publications[0]
                comment_count = pub.get("total_comments", 0)
                pub_url = pub.get("url", "")

                return PubPeerStatus(
                    doi=doi,
                    comment_count=comment_count,
                    has_comments=comment_count > 0,
                    url=pub_url,
                )

        except httpx.TimeoutException:
            logger.debug("PubPeer timeout for DOI %s", doi)
            return PubPeerStatus(doi=doi)
        except Exception as e:
            logger.debug("PubPeer error for DOI %s: %s", doi, e)
            return PubPeerStatus(doi=doi)
