"""HuggingFace Daily Papers API integration.

Provides access to the HuggingFace community-curated daily papers feed.
No authentication required. Public JSON API.

API: https://huggingface.co/api/daily_papers
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

import requests

logger = logging.getLogger(__name__)


@dataclass
class HFPaper:
    """Structured representation of a HuggingFace daily paper."""

    paper_id: str  # arXiv ID typically
    title: str = ""
    authors: list[str] = field(default_factory=list)
    summary: str = ""
    published_at: str = ""
    upvotes: int = 0
    source_url: str = ""  # Link to HF paper page

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source"] = "huggingface"
        return d


class HuggingFaceClient:
    """Client for HuggingFace Daily Papers API.

    Usage:
        client = HuggingFaceClient()
        papers = client.daily_papers()
        for paper in papers:
            print(paper.title, paper.upvotes)
    """

    BASE_URL = "https://huggingface.co/api"

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout

    def daily_papers(
        self,
        date: str | None = None,
        max_results: int = 50,
    ) -> list[HFPaper]:
        """Fetch daily papers from HuggingFace.

        Args:
            date: Optional date string (YYYY-MM-DD). Defaults to today.
            max_results: Maximum number of papers.

        Returns:
            List of HFPaper objects sorted by upvotes (descending).
        """
        url = f"{self.BASE_URL}/daily_papers"
        params: dict = {}
        if date:
            params["date"] = date

        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("HuggingFace daily_papers error: %s", e)
            return []

        if not isinstance(data, list):
            logger.warning("HuggingFace API unexpected format: %s", type(data))
            return []

        papers: list[HFPaper] = []
        for item in data:
            paper = self._to_paper(item)
            if paper:
                papers.append(paper)

        # Sort by upvotes descending
        papers.sort(key=lambda p: p.upvotes, reverse=True)
        return papers[:max_results]

    def search_papers(
        self,
        query: str,
        max_results: int = 30,
    ) -> list[HFPaper]:
        """Search daily papers by keyword match in title/summary.

        Args:
            query: Keywords to match (case-insensitive).
            max_results: Maximum filtered results.

        Returns:
            Papers matching the query.
        """
        all_papers = self.daily_papers(max_results=100)
        query_lower = query.lower()
        keywords = query_lower.split()

        matched = []
        for paper in all_papers:
            text = f"{paper.title} {paper.summary}".lower()
            if any(kw in text for kw in keywords):
                matched.append(paper)
                if len(matched) >= max_results:
                    break

        return matched

    @staticmethod
    def _to_paper(item: dict) -> HFPaper | None:
        """Convert a HuggingFace API item to HFPaper."""
        # The API returns nested structure: {paper: {id, title, ...}, ...}
        paper_data = item.get("paper", item)
        paper_id = paper_data.get("id", "") or paper_data.get("paperId", "")
        if not paper_id:
            return None

        # Extract authors
        authors_raw = paper_data.get("authors", []) or []
        authors = []
        for a in authors_raw:
            if isinstance(a, dict):
                name = a.get("name", "") or a.get("user", {}).get("fullname", "")
                if name:
                    authors.append(name)
            elif isinstance(a, str):
                authors.append(a)

        return HFPaper(
            paper_id=paper_id,
            title=paper_data.get("title", ""),
            authors=authors,
            summary=paper_data.get("summary", "") or paper_data.get("abstract", ""),
            published_at=paper_data.get("publishedAt", "") or paper_data.get("published", ""),
            upvotes=item.get("numUpvotes", 0) or item.get("upvotes", 0),
            source_url=f"https://huggingface.co/papers/{paper_id}" if paper_id else "",
        )
