"""Tests for bioRxiv integration.

Uses mocked HTTP responses to avoid live API calls during unit testing.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.integrations.biorxiv import BiorxivClient, BiorxivPaper


# === Dataclass Tests ===


def test_paper_to_dict():
    """BiorxivPaper.to_dict() should include source field."""
    paper = BiorxivPaper(
        doi="10.1101/2025.01.01.000001",
        title="Test Preprint",
        authors=["Author A", "Author B"],
        category="bioinformatics",
        date="2025-01-01",
        abstract="Test abstract.",
    )
    d = paper.to_dict()
    assert d["source"] == "biorxiv"
    assert d["doi"] == "10.1101/2025.01.01.000001"
    assert d["title"] == "Test Preprint"
    assert len(d["authors"]) == 2


def test_paper_to_dict_defaults():
    """Default values should be empty."""
    paper = BiorxivPaper(doi="10.1101/test")
    d = paper.to_dict()
    assert d["title"] == ""
    assert d["authors"] == []
    assert d["abstract"] == ""
    assert d["server"] == "biorxiv"


# === Client Tests (mocked HTTP) ===


def _mock_response(collection: list[dict], status_code: int = 200):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = {"collection": collection}
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def test_search_recent_parses_results():
    """search_recent should parse API response into BiorxivPaper objects."""
    items = [
        {
            "doi": "10.1101/2025.02.20.001",
            "title": "AI in genomics",
            "authors": "Kim J; Park S",
            "category": "bioinformatics",
            "date": "2025-02-20",
            "abstract": "We apply AI to genomic analysis.",
        },
        {
            "doi": "10.1101/2025.02.19.002",
            "title": "ML for proteins",
            "authors": "Lee H",
            "category": "bioinformatics",
            "date": "2025-02-19",
            "abstract": "Machine learning for protein folding.",
        },
    ]
    with patch("app.integrations.biorxiv.requests.get", return_value=_mock_response(items)):
        client = BiorxivClient()
        papers = client.search_recent(days=7, max_results=10)

    assert len(papers) == 2
    assert isinstance(papers[0], BiorxivPaper)
    assert papers[0].doi == "10.1101/2025.02.20.001"
    assert papers[0].authors == ["Kim J", "Park S"]
    assert papers[1].title == "ML for proteins"


def test_search_recent_empty_collection():
    """search_recent should return empty list when no papers."""
    with patch("app.integrations.biorxiv.requests.get", return_value=_mock_response([])):
        client = BiorxivClient()
        papers = client.search_recent(days=7)

    assert papers == []


def test_search_recent_max_results_cap():
    """search_recent should respect max_results limit."""
    items = [{"doi": f"10.1101/test.{i}", "title": f"Paper {i}", "authors": ""} for i in range(10)]
    with patch("app.integrations.biorxiv.requests.get", return_value=_mock_response(items)):
        client = BiorxivClient()
        papers = client.search_recent(days=7, max_results=3)

    assert len(papers) == 3


def test_search_recent_api_error():
    """search_recent should return empty list on API error."""
    with patch("app.integrations.biorxiv.requests.get", side_effect=Exception("Connection error")):
        client = BiorxivClient()
        papers = client.search_recent(days=7)

    assert papers == []


def test_search_by_topic_filters():
    """search_by_topic should filter by keyword match."""
    items = [
        {"doi": "10.1101/match", "title": "AI genomics study", "authors": "", "abstract": ""},
        {"doi": "10.1101/nomatch", "title": "Plant ecology review", "authors": "", "abstract": ""},
    ]
    with patch("app.integrations.biorxiv.requests.get", return_value=_mock_response(items)):
        client = BiorxivClient()
        papers = client.search_by_topic("AI genomics", days=7, max_results=10)

    assert len(papers) == 1
    assert papers[0].doi == "10.1101/match"


def test_to_paper_skips_no_doi():
    """_to_paper should return None for items without DOI."""
    result = BiorxivClient._to_paper({"title": "No DOI paper", "authors": ""}, "biorxiv")
    assert result is None


def test_medrxiv_server():
    """Should support medrxiv server parameter."""
    items = [{"doi": "10.1101/med.001", "title": "Med paper", "authors": ""}]
    with patch("app.integrations.biorxiv.requests.get", return_value=_mock_response(items)) as mock_get:
        client = BiorxivClient()
        papers = client.search_recent(days=7, server="medrxiv", max_results=5)

    assert len(papers) == 1
    call_url = mock_get.call_args[0][0]
    assert "/medrxiv/" in call_url
