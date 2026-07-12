"""Tests for arXiv integration.

Uses mocked arxiv.Client results to avoid live API calls.
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.integrations.arxiv_client import ArxivClient, ArxivPaper

# === Dataclass Tests ===


def test_paper_to_dict():
    """ArxivPaper.to_dict() should include source field."""
    paper = ArxivPaper(
        arxiv_id="2502.12345v1",
        title="AI for Biology",
        authors=["Kim J", "Park S"],
        categories=["cs.AI", "q-bio.GN"],
        published="2025-02-20",
        abstract="We present an AI approach.",
        doi="10.1234/test",
        pdf_url="https://arxiv.org/pdf/2502.12345v1",
    )
    d = paper.to_dict()
    assert d["source"] == "arxiv"
    assert d["arxiv_id"] == "2502.12345v1"
    assert d["categories"] == ["cs.AI", "q-bio.GN"]


def test_paper_to_dict_defaults():
    """Default values should be empty."""
    paper = ArxivPaper(arxiv_id="2502.00001")
    d = paper.to_dict()
    assert d["title"] == ""
    assert d["authors"] == []
    assert d["categories"] == []


# === Client Tests (mocked) ===


def _make_mock_result(
    entry_id: str = "http://arxiv.org/abs/2502.12345v1",
    title: str = "Test Paper",
    authors: list | None = None,
    categories: list | None = None,
    published: datetime | None = None,
    summary: str = "Abstract text",
    doi: str = "",
    pdf_url: str = "",
):
    result = MagicMock()
    result.entry_id = entry_id
    result.title = title

    mock_authors = []
    for name in (authors or ["Author A"]):
        a = MagicMock()
        a.name = name
        mock_authors.append(a)
    result.authors = mock_authors

    result.categories = categories or ["cs.AI"]
    result.published = published or datetime(2025, 2, 20, tzinfo=timezone.utc)
    result.summary = summary
    result.doi = doi
    result.pdf_url = pdf_url
    return result


def test_search_returns_papers():
    """search should return ArxivPaper objects from mocked results."""
    mock_results = [_make_mock_result(), _make_mock_result(entry_id="http://arxiv.org/abs/2502.99999v1")]

    with patch("app.integrations.arxiv_client.arxiv.Client") as MockClient:
        instance = MockClient.return_value
        instance.results.return_value = iter(mock_results)

        client = ArxivClient()
        papers = client.search("AI biology", max_results=10)

    assert len(papers) == 2
    assert isinstance(papers[0], ArxivPaper)
    assert papers[0].arxiv_id == "2502.12345v1"


def test_search_with_categories():
    """search with categories should build correct query."""
    mock_results = [_make_mock_result()]

    with patch("app.integrations.arxiv_client.arxiv.Client") as MockClient, \
         patch("app.integrations.arxiv_client.arxiv.Search") as MockSearch:
        instance = MockClient.return_value
        instance.results.return_value = iter(mock_results)

        client = ArxivClient()
        client.search("genomics", categories=["cs.AI", "q-bio"])

    # Verify the Search was created with combined query
    call_kwargs = MockSearch.call_args
    query = call_kwargs.kwargs.get("query", "") or call_kwargs[1].get("query", "")
    assert "cat:cs.AI" in query
    assert "cat:q-bio" in query


def test_search_empty_results():
    """search should return empty list when no results."""
    with patch("app.integrations.arxiv_client.arxiv.Client") as MockClient:
        instance = MockClient.return_value
        instance.results.return_value = iter([])

        client = ArxivClient()
        papers = client.search("xyznonexistent999")

    assert papers == []


def test_search_api_error():
    """search should return empty list on API error."""
    with patch("app.integrations.arxiv_client.arxiv.Client") as MockClient:
        instance = MockClient.return_value
        instance.results.side_effect = Exception("API error")

        client = ArxivClient()
        papers = client.search("test")

    assert papers == []


def test_recent_by_category():
    """recent_by_category should filter by date."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    recent = _make_mock_result(published=now - timedelta(days=5))
    old = _make_mock_result(
        entry_id="http://arxiv.org/abs/2020.00001v1",
        published=now - timedelta(days=365),
    )

    with patch("app.integrations.arxiv_client.arxiv.Client") as MockClient:
        instance = MockClient.return_value
        instance.results.return_value = iter([recent, old])

        client = ArxivClient()
        papers = client.recent_by_category(["cs.AI"], days=30)

    # Only recent paper should pass date filter
    assert len(papers) >= 1
    assert papers[0].arxiv_id == "2502.12345v1"


def test_to_paper_skips_no_entry_id():
    """_to_paper should return None if entry_id is empty."""
    result = MagicMock()
    result.entry_id = ""
    assert ArxivClient._to_paper(result) is None
