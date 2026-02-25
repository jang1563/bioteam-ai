"""Tests for data source integrations — word boundary matching, retry, multi-day fetch."""

import os
import sys
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

from app.integrations.biorxiv import BiorxivClient, BiorxivPaper
from app.integrations.github_trending import GithubTrendingClient, GithubRepo
from app.integrations.huggingface import HuggingFaceClient, HFPaper


# === bioRxiv Tests ===

class TestBiorxivWordBoundary:
    def _make_papers(self) -> list[BiorxivPaper]:
        return [
            BiorxivPaper(doi="10.1/a", title="RNA sequencing analysis", abstract="Study of RNA."),
            BiorxivPaper(doi="10.1/b", title="International Journal Review", abstract="A review article."),
            BiorxivPaper(doi="10.1/c", title="Protein folding with AI", abstract="Deep learning for proteins."),
            BiorxivPaper(doi="10.1/d", title="MRNA vaccine development", abstract="Novel mRNA delivery."),
        ]

    @patch.object(BiorxivClient, "search_recent")
    def test_word_boundary_no_substring(self, mock_search):
        """'rna' should NOT match 'international' or 'journal'."""
        mock_search.return_value = self._make_papers()
        client = BiorxivClient()
        results = client.search_by_topic("rna", days=7, max_results=30)
        titles = [p.title for p in results]
        assert "International Journal Review" not in titles

    @patch.object(BiorxivClient, "search_recent")
    def test_word_boundary_matches(self, mock_search):
        """'rna' should match 'RNA sequencing analysis'."""
        mock_search.return_value = self._make_papers()
        client = BiorxivClient()
        results = client.search_by_topic("rna", days=7, max_results=30)
        titles = [p.title for p in results]
        assert "RNA sequencing analysis" in titles

    @patch.object(BiorxivClient, "search_recent")
    def test_word_boundary_matches_mrna(self, mock_search):
        """'mrna' should match 'MRNA vaccine development'."""
        mock_search.return_value = self._make_papers()
        client = BiorxivClient()
        results = client.search_by_topic("mrna", days=7, max_results=30)
        titles = [p.title for p in results]
        assert "MRNA vaccine development" in titles

    @patch.object(BiorxivClient, "search_recent")
    def test_quoted_phrase(self, mock_search):
        """Quoted phrase should be kept as a single unit."""
        mock_search.return_value = self._make_papers()
        client = BiorxivClient()
        results = client.search_by_topic('"RNA sequencing"', days=7, max_results=30)
        titles = [p.title for p in results]
        assert "RNA sequencing analysis" in titles

    @patch.object(BiorxivClient, "search_recent")
    def test_larger_pool_size(self, mock_search):
        """Pool size should be at least 300."""
        mock_search.return_value = []
        client = BiorxivClient()
        client.search_by_topic("ai", days=7, max_results=10)
        # max(10 * 10, 300) = 300
        call_args = mock_search.call_args
        assert call_args[1]["max_results"] >= 300


# === GitHub Tests ===

class TestGithubRetryAndQuery:
    def test_trending_ai_bio_default_or_query(self):
        """Default query should use OR-based search."""
        client = GithubTrendingClient(token="test-token")
        with patch.object(client, "search_repos", return_value=[]) as mock_search:
            client.trending_ai_bio(days=7, max_results=20)
            query_arg = mock_search.call_args[1]["query"]
            assert "OR" in query_arg

    def test_trending_ai_bio_custom_query(self):
        """Custom query should be passed through."""
        client = GithubTrendingClient(token="test-token")
        with patch.object(client, "search_repos", return_value=[]) as mock_search:
            client.trending_ai_bio(query="protein folding", days=7, max_results=20)
            query_arg = mock_search.call_args[1]["query"]
            assert query_arg == "protein folding"

    @patch("app.integrations.github_trending.requests.get")
    @patch("app.integrations.github_trending.time.sleep")
    def test_retry_on_403(self, mock_sleep, mock_get):
        """Should retry on 403 rate limit."""
        # First call returns 403, second succeeds
        resp_403 = MagicMock()
        resp_403.status_code = 403
        resp_403.raise_for_status.side_effect = None

        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.raise_for_status.return_value = None
        resp_ok.json.return_value = {"items": []}

        mock_get.side_effect = [resp_403, resp_ok]

        client = GithubTrendingClient(token="test-token")
        result = client.search_repos("AI biology", max_results=5)
        assert result == []
        assert mock_sleep.called


# === HuggingFace Tests ===

class TestHuggingFaceMultiDay:
    def _make_papers(self, prefix: str) -> list[HFPaper]:
        return [
            HFPaper(
                paper_id=f"{prefix}_1",
                title=f"{prefix} AI Biology Paper",
                summary="AI for biology research.",
                upvotes=10,
            ),
            HFPaper(
                paper_id=f"{prefix}_2",
                title=f"{prefix} Protein Folding",
                summary="Protein structure prediction.",
                upvotes=5,
            ),
        ]

    @patch.object(HuggingFaceClient, "daily_papers")
    def test_multiday_fetch(self, mock_daily):
        """Should fetch from multiple days."""
        mock_daily.side_effect = [
            self._make_papers("day0"),
            self._make_papers("day1"),
            self._make_papers("day2"),
        ]
        client = HuggingFaceClient()
        results = client.search_papers("biology", max_results=30, fetch_days=3)
        assert mock_daily.call_count == 3

    @patch.object(HuggingFaceClient, "daily_papers")
    def test_word_boundary_filter(self, mock_daily):
        """Should use word-boundary matching, not substring."""
        papers = [
            HFPaper(paper_id="1", title="RNA Seq Analysis", summary="RNA sequencing."),
            HFPaper(paper_id="2", title="Internal Review Process", summary="Process review."),
        ]
        mock_daily.return_value = papers
        client = HuggingFaceClient()
        results = client.search_papers("rna", max_results=30, fetch_days=1)
        titles = [p.title for p in results]
        assert "RNA Seq Analysis" in titles
        assert "Internal Review Process" not in titles

    @patch.object(HuggingFaceClient, "daily_papers")
    def test_deduplicates_across_days(self, mock_daily):
        """Papers appearing in multiple days should not be duplicated."""
        same_papers = self._make_papers("shared")
        mock_daily.side_effect = [same_papers, same_papers]
        client = HuggingFaceClient()
        results = client.search_papers("biology", max_results=30, fetch_days=2)
        # Should have 2 unique papers, not 4
        ids = [p.paper_id for p in results]
        assert len(ids) == len(set(ids))


# === Pipeline source dispatch ===

class TestPipelineSourceDispatch:
    @patch("app.digest.pipeline.GithubTrendingClient")
    def test_github_receives_query(self, mock_cls):
        """Pipeline should pass topic query to GitHub trending_ai_bio."""
        from app.digest.pipeline import DigestPipeline

        mock_client = MagicMock()
        mock_client.trending_ai_bio.return_value = []
        mock_cls.return_value = mock_client

        pipeline = DigestPipeline()
        pipeline._clients["github"] = mock_client

        from app.models.digest import TopicProfile
        topic = TopicProfile(
            name="Test",
            queries=["machine learning biology", "AI genomics"],
            sources=["github"],
        )

        result = pipeline._fetch_sync("github", topic, 7)
        mock_client.trending_ai_bio.assert_called_once()
        call_kwargs = mock_client.trending_ai_bio.call_args
        assert "machine learning biology" in str(call_kwargs)
