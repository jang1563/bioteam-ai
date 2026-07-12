"""Tests for GitHub trending integration.

Uses mocked HTTP responses to avoid live API calls.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.integrations.github_trending import GithubRepo, GithubTrendingClient

# === Dataclass Tests ===


def test_repo_to_dict():
    """GithubRepo.to_dict() should include source field."""
    repo = GithubRepo(
        full_name="user/repo",
        description="A cool AI biology tool",
        url="https://github.com/user/repo",
        stars=150,
        language="Python",
        topics=["ai", "biology"],
    )
    d = repo.to_dict()
    assert d["source"] == "github"
    assert d["full_name"] == "user/repo"
    assert d["stars"] == 150


def test_repo_to_dict_defaults():
    """Default values should be empty."""
    repo = GithubRepo(full_name="user/repo")
    d = repo.to_dict()
    assert d["description"] == ""
    assert d["topics"] == []
    assert d["stars"] == 0


# === Client Tests (mocked HTTP) ===


def _mock_response(items: list[dict], status_code: int = 200):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = {"items": items, "total_count": len(items)}
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def test_search_repos_parses_results():
    """search_repos should parse API response into GithubRepo objects."""
    items = [
        {
            "full_name": "org/ai-bio-tool",
            "description": "AI tool for biology",
            "html_url": "https://github.com/org/ai-bio-tool",
            "stargazers_count": 500,
            "language": "Python",
            "topics": ["ai", "biology"],
            "created_at": "2025-02-01T00:00:00Z",
            "pushed_at": "2025-02-20T00:00:00Z",
        },
    ]
    with patch("app.integrations.github_trending.requests.get", return_value=_mock_response(items)):
        client = GithubTrendingClient()
        repos = client.search_repos("AI biology", max_results=10)

    assert len(repos) == 1
    assert isinstance(repos[0], GithubRepo)
    assert repos[0].full_name == "org/ai-bio-tool"
    assert repos[0].stars == 500


def test_search_repos_empty():
    """search_repos should return empty list when no results."""
    with patch("app.integrations.github_trending.requests.get", return_value=_mock_response([])):
        client = GithubTrendingClient()
        repos = client.search_repos("xyznonexistent")

    assert repos == []


def test_search_repos_api_error():
    """search_repos should return empty list on API error."""
    with patch("app.integrations.github_trending.requests.get", side_effect=Exception("Network error")):
        client = GithubTrendingClient()
        repos = client.search_repos("test")

    assert repos == []


def test_search_repos_with_auth():
    """search_repos should include auth header when token provided."""
    with patch("app.integrations.github_trending.requests.get", return_value=_mock_response([])) as mock_get:
        client = GithubTrendingClient(token="ghp_test123")
        client.search_repos("test")

    headers = mock_get.call_args.kwargs.get("headers", {})
    assert "Authorization" in headers
    assert "ghp_test123" in headers["Authorization"]


def test_trending_ai_bio():
    """trending_ai_bio should use date filter."""
    items = [
        {"full_name": "new/repo", "stargazers_count": 100, "html_url": ""},
    ]
    with patch("app.integrations.github_trending.requests.get", return_value=_mock_response(items)) as mock_get:
        client = GithubTrendingClient()
        repos = client.trending_ai_bio(days=7)

    assert len(repos) == 1
    # Verify the query includes a created: date filter
    params = mock_get.call_args.kwargs.get("params", {})
    assert "created:>" in params["q"]
