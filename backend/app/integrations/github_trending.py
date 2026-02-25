"""GitHub trending / search integration.

Provides access to trending research repositories via the GitHub Search API.
No authentication required for public repos (10 req/min unauthenticated,
30 req/min with token).
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF = [2, 4, 8]  # seconds


@dataclass
class GithubRepo:
    """Structured representation of a GitHub repository."""

    full_name: str  # "owner/repo"
    description: str = ""
    url: str = ""
    stars: int = 0
    language: str = ""
    topics: list[str] = field(default_factory=list)
    created_at: str = ""
    pushed_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source"] = "github"
        return d


class GithubTrendingClient:
    """Client for GitHub repository search.

    Usage:
        client = GithubTrendingClient()
        repos = client.search_repos("AI biology", max_results=20)
        for repo in repos:
            print(repo.full_name, repo.stars)
    """

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str = "") -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN", "")

    def search_repos(
        self,
        query: str,
        sort: str = "stars",
        created_after: str = "",
        max_results: int = 30,
    ) -> list[GithubRepo]:
        """Search repositories via GitHub Search API.

        Retries up to 3 times on 403/429 (rate limit) with exponential backoff.

        Args:
            query: Search query keywords.
            sort: Sort field — "stars", "forks", "updated".
            created_after: ISO date string (YYYY-MM-DD) for filtering.
            max_results: Maximum results (capped at 100 by GitHub API).

        Returns:
            List of GithubRepo objects.
        """
        q = query
        if created_after:
            q += f" created:>{created_after}"

        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        params = {
            "q": q,
            "sort": sort,
            "order": "desc",
            "per_page": min(max_results, 100),
        }

        for attempt in range(_MAX_RETRIES):
            try:
                resp = requests.get(
                    f"{self.BASE_URL}/search/repositories",
                    headers=headers,
                    params=params,
                    timeout=15,
                )
                if resp.status_code in (403, 429) and attempt < _MAX_RETRIES - 1:
                    wait = _RETRY_BACKOFF[attempt]
                    logger.warning("GitHub rate limited (attempt %d), retrying in %ds", attempt + 1, wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
            except requests.exceptions.HTTPError:
                if attempt < _MAX_RETRIES - 1:
                    continue
                logger.warning("GitHub search failed after %d attempts", _MAX_RETRIES)
                return []
            except Exception as e:
                logger.warning("GitHub search error: %s", e)
                return []
        else:
            return []

        repos: list[GithubRepo] = []
        for item in data.get("items", []):
            repo = self._to_repo(item)
            if repo:
                repos.append(repo)

        return repos[:max_results]

    def trending_ai_bio(
        self,
        query: str = "",
        days: int = 7,
        max_results: int = 20,
    ) -> list[GithubRepo]:
        """Search for trending AI + biology repos created in the last N days.

        Args:
            query: Custom search query. If empty, uses a broad OR-based default.
            days: Look back period in days.
            max_results: Maximum results.

        Returns:
            Trending repos matching AI + biology topics.
        """
        if not query:
            query = '"AI biology" OR "machine learning genomics" OR bioinformatics OR "computational biology"'
        created_after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        return self.search_repos(
            query=query,
            sort="stars",
            created_after=created_after,
            max_results=max_results,
        )

    @staticmethod
    def _to_repo(item: dict) -> GithubRepo | None:
        """Convert a GitHub API item to GithubRepo."""
        full_name = item.get("full_name", "")
        if not full_name:
            return None

        return GithubRepo(
            full_name=full_name,
            description=item.get("description", "") or "",
            url=item.get("html_url", ""),
            stars=item.get("stargazers_count", 0),
            language=item.get("language", "") or "",
            topics=item.get("topics", []) or [],
            created_at=item.get("created_at", ""),
            pushed_at=item.get("pushed_at", ""),
        )
