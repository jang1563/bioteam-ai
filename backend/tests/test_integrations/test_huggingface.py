"""Tests for HuggingFace integration.

Uses mocked HTTP responses to avoid live API calls.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.integrations.huggingface import HuggingFaceClient, HFPaper


# === Dataclass Tests ===


def test_paper_to_dict():
    """HFPaper.to_dict() should include source field."""
    paper = HFPaper(
        paper_id="2502.12345",
        title="Foundation Models for Biology",
        authors=["Kim J"],
        summary="A survey of foundation models.",
        upvotes=42,
        source_url="https://huggingface.co/papers/2502.12345",
    )
    d = paper.to_dict()
    assert d["source"] == "huggingface"
    assert d["paper_id"] == "2502.12345"
    assert d["upvotes"] == 42
    assert d["source_url"] == "https://huggingface.co/papers/2502.12345"


def test_paper_to_dict_defaults():
    """Default values should be empty."""
    paper = HFPaper(paper_id="test")
    d = paper.to_dict()
    assert d["title"] == ""
    assert d["authors"] == []
    assert d["summary"] == ""


# === Client Tests (mocked HTTP) ===


def _mock_response(data: list, status_code: int = 200):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = data
    mock_resp.raise_for_status.return_value = None
    return mock_resp


SAMPLE_HF_RESPONSE = [
    {
        "paper": {
            "id": "2502.11111",
            "title": "AI for Drug Discovery",
            "authors": [{"name": "Alice"}, {"name": "Bob"}],
            "summary": "AI-driven drug discovery pipeline.",
            "publishedAt": "2025-02-20T00:00:00Z",
        },
        "numUpvotes": 120,
    },
    {
        "paper": {
            "id": "2502.22222",
            "title": "Protein Language Models",
            "authors": [{"name": "Charlie"}],
            "summary": "Large language models for protein sequences.",
            "publishedAt": "2025-02-19T00:00:00Z",
        },
        "numUpvotes": 85,
    },
    {
        "paper": {
            "id": "2502.33333",
            "title": "Image Classification Survey",
            "authors": [{"name": "Dave"}],
            "summary": "A review of image classification methods.",
            "publishedAt": "2025-02-18T00:00:00Z",
        },
        "numUpvotes": 30,
    },
]


def test_daily_papers_parses_results():
    """daily_papers should parse nested API response."""
    with patch("app.integrations.huggingface.requests.get", return_value=_mock_response(SAMPLE_HF_RESPONSE)):
        client = HuggingFaceClient()
        papers = client.daily_papers()

    assert len(papers) == 3
    assert isinstance(papers[0], HFPaper)
    # Should be sorted by upvotes descending
    assert papers[0].upvotes >= papers[1].upvotes
    assert papers[0].paper_id == "2502.11111"
    assert papers[0].authors == ["Alice", "Bob"]


def test_daily_papers_empty():
    """daily_papers should return empty list when API returns empty."""
    with patch("app.integrations.huggingface.requests.get", return_value=_mock_response([])):
        client = HuggingFaceClient()
        papers = client.daily_papers()

    assert papers == []


def test_daily_papers_api_error():
    """daily_papers should return empty list on error."""
    with patch("app.integrations.huggingface.requests.get", side_effect=Exception("Network error")):
        client = HuggingFaceClient()
        papers = client.daily_papers()

    assert papers == []


def test_search_papers_filters():
    """search_papers should filter by keyword match."""
    with patch("app.integrations.huggingface.requests.get", return_value=_mock_response(SAMPLE_HF_RESPONSE)):
        client = HuggingFaceClient()
        papers = client.search_papers("protein")

    assert len(papers) == 1
    assert papers[0].paper_id == "2502.22222"


def test_to_paper_skips_no_id():
    """_to_paper should return None for items without paper ID."""
    result = HuggingFaceClient._to_paper({"paper": {"title": "No ID"}})
    assert result is None
