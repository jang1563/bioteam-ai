"""arXiv API integration.

Provides structured access to arXiv paper search using the ``arxiv`` Python
package. No authentication required.

Dependency: pip install arxiv
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

import arxiv

logger = logging.getLogger(__name__)


@dataclass
class ArxivPaper:
    """Structured representation of an arXiv paper."""

    arxiv_id: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    published: str = ""  # YYYY-MM-DD
    abstract: str = ""
    doi: str = ""
    pdf_url: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source"] = "arxiv"
        return d


class ArxivClient:
    """Client for arXiv search using the ``arxiv`` Python package.

    Usage:
        client = ArxivClient()
        papers = client.search("AI biology genomics", max_results=20)
        for paper in papers:
            print(paper.title, paper.arxiv_id)
    """

    # Categories relevant to biology + AI research
    BIO_AI_CATEGORIES = ["cs.AI", "cs.LG", "q-bio", "cs.CL", "stat.ML"]

    def search(
        self,
        query: str,
        max_results: int = 30,
        categories: list[str] | None = None,
        sort_by: str = "submittedDate",
    ) -> list[ArxivPaper]:
        """Search arXiv by query.

        Args:
            query: Search query string.
            max_results: Maximum results.
            categories: Optional arXiv category filter (e.g. ["cs.AI", "q-bio"]).
            sort_by: Sort criterion — "submittedDate" or "relevance".

        Returns:
            List of ArxivPaper objects.
        """
        # Build query with category filter
        full_query = query
        if categories:
            cat_filter = " OR ".join(f"cat:{c}" for c in categories)
            full_query = f"({query}) AND ({cat_filter})"

        sort_criterion = (
            arxiv.SortCriterion.SubmittedDate
            if sort_by == "submittedDate"
            else arxiv.SortCriterion.Relevance
        )

        client = arxiv.Client()
        search = arxiv.Search(
            query=full_query,
            max_results=max_results,
            sort_by=sort_criterion,
            sort_order=arxiv.SortOrder.Descending,
        )

        papers: list[ArxivPaper] = []
        try:
            for result in client.results(search):
                paper = self._to_paper(result)
                if paper:
                    papers.append(paper)
        except Exception as e:
            logger.warning("arXiv search error: %s", e)

        return papers

    def recent_by_category(
        self,
        categories: list[str],
        days: int = 7,
        max_results: int = 50,
    ) -> list[ArxivPaper]:
        """Get recent papers in specific arXiv categories.

        Args:
            categories: List of arXiv categories (e.g. ["cs.AI", "q-bio.GN"]).
            days: Look back period in days.
            max_results: Maximum results.

        Returns:
            Recent papers in the given categories.
        """
        # Use a broad query with date filtering
        cat_filter = " OR ".join(f"cat:{c}" for c in categories)
        query = f"({cat_filter})"

        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        papers: list[ArxivPaper] = []
        try:
            for result in client.results(search):
                # Filter by publication date
                pub_date = result.published
                if pub_date:
                    # Ensure timezone-aware comparison
                    if pub_date.tzinfo is None:
                        pub_date = pub_date.replace(tzinfo=timezone.utc)
                    if pub_date < cutoff:
                        continue
                paper = self._to_paper(result)
                if paper:
                    papers.append(paper)
        except Exception as e:
            logger.warning("arXiv recent_by_category error: %s", e)

        return papers

    @staticmethod
    def _to_paper(result) -> ArxivPaper | None:
        """Convert an arxiv.Result to ArxivPaper."""
        arxiv_id = result.entry_id.split("/abs/")[-1] if result.entry_id else ""
        if not arxiv_id:
            return None

        published = ""
        if result.published:
            published = result.published.strftime("%Y-%m-%d")

        return ArxivPaper(
            arxiv_id=arxiv_id,
            title=result.title or "",
            authors=[a.name for a in (result.authors or [])],
            categories=list(result.categories or []),
            published=published,
            abstract=result.summary or "",
            doi=result.doi or "",
            pdf_url=result.pdf_url or "",
        )
