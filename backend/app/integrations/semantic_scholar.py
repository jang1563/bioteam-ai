"""Semantic Scholar API integration.

Provides structured access to Semantic Scholar for:
- Paper search (semantic similarity)
- Citation graph navigation
- Author search

Uses the official semanticscholar Python client.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

from semanticscholar import SemanticScholar

_MAX_RETRIES = 3
_RETRY_BACKOFF = [2, 4, 8]  # seconds


@dataclass
class S2Paper:
    """Structured representation of a Semantic Scholar result."""

    paper_id: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    abstract: str = ""
    doi: str = ""
    citation_count: int = 0
    influential_citation_count: int = 0
    venue: str = ""
    url: str = ""
    tldr: str = ""  # AI-generated TLDR (if available)

    def to_dict(self) -> dict:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "abstract": self.abstract,
            "doi": self.doi,
            "citation_count": self.citation_count,
            "influential_citation_count": self.influential_citation_count,
            "venue": self.venue,
            "url": self.url,
            "tldr": self.tldr,
            "source": "semantic_scholar",
        }


class SemanticScholarClient:
    """Client for Semantic Scholar API.

    Usage:
        client = SemanticScholarClient()
        papers = client.search("spaceflight anemia erythropoiesis", limit=10)
        for paper in papers:
            print(paper.title, paper.citation_count)

        # Get citations for a paper
        citing = client.get_citations("10.1038/s41586-020-2521-4", limit=5)
    """

    def __init__(self, timeout: int = 15, api_key: str = "") -> None:
        from app.config import settings
        key = api_key or getattr(settings, "s2_api_key", "")
        self.sch = SemanticScholar(
            api_key=key if key else None,
            timeout=timeout,
        )

    def search(
        self,
        query: str,
        limit: int = 10,
        year: str | None = None,
        fields_of_study: list[str] | None = None,
    ) -> list[S2Paper]:
        """Search for papers by query string.

        Retries up to 3 times on rate limit errors.

        Args:
            query: Natural language search query.
            limit: Maximum number of results.
            year: Year range filter (e.g., "2020-2025" or "2023-").
            fields_of_study: Filter by field (e.g., ["Biology", "Medicine"]).

        Returns:
            List of S2Paper objects.
        """
        for attempt in range(_MAX_RETRIES):
            try:
                results = self.sch.search_paper(
                    query,
                    limit=limit,
                    year=year,
                    fields_of_study=fields_of_study,
                    fields=[
                        "paperId", "title", "authors", "year", "abstract",
                        "externalIds", "citationCount", "influentialCitationCount",
                        "venue", "url", "tldr",
                    ],
                )

                papers = []
                for item in results:
                    paper = self._to_s2paper(item)
                    if paper:
                        papers.append(paper)
                return papers
            except Exception as e:
                err_str = str(e).lower()
                if ("429" in err_str or "rate" in err_str) and attempt < _MAX_RETRIES - 1:
                    wait = _RETRY_BACKOFF[attempt]
                    logger.warning("S2 rate limited (attempt %d), retrying in %ds", attempt + 1, wait)
                    time.sleep(wait)
                    continue
                logger.warning("S2 search failed: %s", e)
                return []
        return []

    def get_paper(self, paper_id: str) -> S2Paper | None:
        """Get details for a specific paper by DOI or S2 paper ID.

        Args:
            paper_id: DOI (e.g., "10.1038/...") or S2 paper ID.

        Returns:
            S2Paper or None if not found.
        """
        try:
            result = self.sch.get_paper(
                paper_id,
                fields=[
                    "paperId", "title", "authors", "year", "abstract",
                    "externalIds", "citationCount", "influentialCitationCount",
                    "venue", "url", "tldr",
                ],
            )
            return self._to_s2paper(result)
        except Exception as e:
            logger.warning("S2 get_paper(%s) failed: %s", paper_id, e)
            return None

    def get_citations(self, paper_id: str, limit: int = 10) -> list[S2Paper]:
        """Get papers that cite the given paper.

        Args:
            paper_id: DOI or S2 paper ID.
            limit: Maximum number of citing papers.

        Returns:
            List of citing S2Paper objects.
        """
        try:
            results = self.sch.get_paper_citations(
                paper_id,
                limit=limit,
                fields=["paperId", "title", "authors", "year", "externalIds", "citationCount"],
            )
            papers = []
            for item in results:
                citing_paper = getattr(item, "citingPaper", None)
                if citing_paper:
                    paper = self._to_s2paper(citing_paper)
                    if paper:
                        papers.append(paper)
            return papers
        except Exception as e:
            logger.warning("S2 get_citations(%s) failed: %s", paper_id, e)
            return []

    def get_references(self, paper_id: str, limit: int = 10) -> list[S2Paper]:
        """Get papers referenced by the given paper.

        Args:
            paper_id: DOI or S2 paper ID.
            limit: Maximum number of referenced papers.

        Returns:
            List of referenced S2Paper objects.
        """
        try:
            results = self.sch.get_paper_references(
                paper_id,
                limit=limit,
                fields=["paperId", "title", "authors", "year", "externalIds", "citationCount"],
            )
            papers = []
            for item in results:
                cited_paper = getattr(item, "citedPaper", None)
                if cited_paper:
                    paper = self._to_s2paper(cited_paper)
                    if paper:
                        papers.append(paper)
            return papers
        except Exception as e:
            logger.warning("S2 get_references(%s) failed: %s", paper_id, e)
            return []

    @staticmethod
    def _to_s2paper(item) -> S2Paper | None:
        """Convert a Semantic Scholar API result to S2Paper."""
        if item is None:
            return None

        paper_id = getattr(item, "paperId", None) or ""
        if not paper_id:
            return None

        # Extract DOI from externalIds
        external_ids = getattr(item, "externalIds", {}) or {}
        doi = external_ids.get("DOI", "") if isinstance(external_ids, dict) else ""

        # Extract authors
        authors_raw = getattr(item, "authors", []) or []
        authors = []
        for a in authors_raw:
            name = getattr(a, "name", None) or (a.get("name") if isinstance(a, dict) else str(a))
            if name:
                authors.append(name)

        # Extract TLDR
        tldr_obj = getattr(item, "tldr", None)
        tldr = ""
        if tldr_obj:
            tldr = getattr(tldr_obj, "text", "") or (tldr_obj.get("text", "") if isinstance(tldr_obj, dict) else "")

        return S2Paper(
            paper_id=paper_id,
            title=getattr(item, "title", "") or "",
            authors=authors,
            year=getattr(item, "year", None),
            abstract=getattr(item, "abstract", "") or "",
            doi=doi,
            citation_count=getattr(item, "citationCount", 0) or 0,
            influential_citation_count=getattr(item, "influentialCitationCount", 0) or 0,
            venue=getattr(item, "venue", "") or "",
            url=getattr(item, "url", "") or "",
            tldr=tldr,
        )
