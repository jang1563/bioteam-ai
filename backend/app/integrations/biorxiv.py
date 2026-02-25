"""bioRxiv / medRxiv API integration.

Provides structured access to bioRxiv preprint search via the public REST API.
No authentication required. Pagination via cursor (100 per page).

API docs: https://api.biorxiv.org/
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)


@dataclass
class BiorxivPaper:
    """Structured representation of a bioRxiv preprint."""

    doi: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    category: str = ""
    date: str = ""  # YYYY-MM-DD
    abstract: str = ""
    server: str = "biorxiv"  # "biorxiv" or "medrxiv"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source"] = "biorxiv"
        return d


class BiorxivClient:
    """Client for the bioRxiv / medRxiv public API.

    Usage:
        client = BiorxivClient()
        papers = client.search_recent(days=7, max_results=30)
        for paper in papers:
            print(paper.title, paper.doi)
    """

    BASE_URL = "https://api.biorxiv.org"

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout

    def search_recent(
        self,
        days: int = 7,
        server: str = "biorxiv",
        max_results: int = 50,
    ) -> list[BiorxivPaper]:
        """Fetch recent papers by date range.

        Args:
            days: Number of days to look back from today.
            server: "biorxiv" or "medrxiv".
            max_results: Maximum number of papers to return.

        Returns:
            List of BiorxivPaper objects, newest first.
        """
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

        papers: list[BiorxivPaper] = []
        cursor = 0

        while len(papers) < max_results:
            url = f"{self.BASE_URL}/pubs/{server}/{start_date}/{end_date}/{cursor}"
            try:
                resp = requests.get(url, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning("bioRxiv API error (cursor=%d): %s", cursor, e)
                break

            collection = data.get("collection", [])
            if not collection:
                break

            for item in collection:
                if len(papers) >= max_results:
                    break
                paper = self._to_paper(item, server)
                if paper:
                    papers.append(paper)

            # bioRxiv returns up to 100 per page; advance cursor
            if len(collection) < 100:
                break
            cursor += 100

        return papers

    def search_by_topic(
        self,
        query: str,
        days: int = 30,
        server: str = "biorxiv",
        max_results: int = 30,
    ) -> list[BiorxivPaper]:
        """Fetch recent papers and filter by keyword match in title/abstract.

        Uses word-boundary regex matching to avoid false positives
        (e.g. "rna" won't match "journal").

        Args:
            query: Keywords to match (case-insensitive).
            days: Number of days to look back.
            server: "biorxiv" or "medrxiv".
            max_results: Maximum filtered results.

        Returns:
            Papers matching the query keywords.
        """
        import re

        # Fetch a larger pool, then filter
        pool_size = max(max_results * 10, 300)
        all_papers = self.search_recent(days=days, server=server, max_results=pool_size)

        # Build word-boundary regex patterns
        patterns: list[re.Pattern] = []
        # Extract quoted phrases first
        quoted = re.findall(r'"([^"]+)"', query)
        remainder = re.sub(r'"[^"]*"', '', query)
        keywords = [p.lower() for p in quoted] + [w.lower() for w in remainder.split() if len(w) > 2]

        for kw in keywords:
            try:
                patterns.append(re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE))
            except re.error:
                continue

        if not patterns:
            return all_papers[:max_results]

        # Require at least 2 keyword matches to filter out irrelevant papers
        min_matches = min(2, len(patterns))

        matched = []
        for paper in all_papers:
            text = f"{paper.title} {paper.abstract}"
            hit_count = sum(1 for pat in patterns if pat.search(text))
            if hit_count >= min_matches:
                matched.append(paper)
                if len(matched) >= max_results:
                    break

        return matched

    @staticmethod
    def _to_paper(item: dict, server: str) -> BiorxivPaper | None:
        """Convert a bioRxiv API response item to BiorxivPaper.

        The /pubs endpoint uses preprint_* prefixed keys (e.g. preprint_doi,
        preprint_title), while /details uses unprefixed keys. Support both.
        """
        doi = item.get("preprint_doi", "") or item.get("doi", "")
        if not doi:
            return None

        # Authors come as a semicolon-separated string
        authors_str = item.get("preprint_authors", "") or item.get("authors", "")
        authors = [a.strip() for a in authors_str.split(";") if a.strip()] if authors_str else []

        return BiorxivPaper(
            doi=doi,
            title=item.get("preprint_title", "") or item.get("title", ""),
            authors=authors,
            category=item.get("preprint_category", "") or item.get("category", ""),
            date=item.get("preprint_date", "") or item.get("date", ""),
            abstract=item.get("preprint_abstract", "") or item.get("abstract", ""),
            server=server,
        )
