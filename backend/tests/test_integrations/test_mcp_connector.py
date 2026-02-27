"""Tests for the MCP Healthcare Connector adapter.

Tests are purely unit-level with mocked Anthropic beta API.
No real MCP server calls are made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.mcp_connector import (
    BETA_FLAG,
    MCP_SERVERS,
    MCPConnector,
    MCPSearchResult,
)


# ── Fixtures ──


@pytest.fixture
def mock_client():
    """Mock AsyncAnthropic client with beta.messages.create."""
    client = MagicMock()
    client.beta = MagicMock()
    client.beta.messages = MagicMock()
    client.beta.messages.create = AsyncMock()
    return client


@pytest.fixture
def connector(mock_client):
    return MCPConnector(client=mock_client)


def _make_mock_response(text: str = "test response", papers_json: str = ""):
    """Create a mock MCP API response."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = papers_json or text

    usage = MagicMock()
    usage.input_tokens = 500
    usage.output_tokens = 200
    usage.cache_read_input_tokens = 50

    resp = MagicMock()
    resp.content = [text_block]
    resp.usage = usage
    resp.model = "claude-sonnet-4-5-20250929"
    return resp


# ── Tests: _build_mcp_servers ──


class TestBuildMCPServers:
    def test_filters_unknown_sources(self, connector):
        servers = connector._build_mcp_servers(["pubmed", "unknown_source"])
        assert len(servers) == 1
        assert servers[0]["name"] == "pubmed"

    def test_includes_known_sources(self, connector):
        servers = connector._build_mcp_servers(["pubmed", "biorxiv"])
        assert len(servers) == 2
        names = {s["name"] for s in servers}
        assert names == {"pubmed", "biorxiv"}

    def test_empty_sources(self, connector):
        servers = connector._build_mcp_servers([])
        assert servers == []

    def test_all_sources(self, connector):
        all_sources = list(MCP_SERVERS.keys())
        servers = connector._build_mcp_servers(all_sources)
        assert len(servers) == len(MCP_SERVERS)


# ── Tests: _build_tools ──


class TestBuildTools:
    def test_creates_toolset_per_source(self, connector):
        tools = connector._build_tools(["pubmed", "biorxiv"])
        assert len(tools) == 2
        for t in tools:
            assert t["type"] == "mcp_toolset"
        names = {t["mcp_server_name"] for t in tools}
        assert names == {"pubmed", "biorxiv"}

    def test_skips_unknown_sources(self, connector):
        tools = connector._build_tools(["pubmed", "nonexistent"])
        assert len(tools) == 1
        assert tools[0]["mcp_server_name"] == "pubmed"


# ── Tests: search ──


class TestSearch:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_servers(self, connector):
        result = await connector.search(
            query="test", sources=["nonexistent_source"]
        )
        assert isinstance(result, MCPSearchResult)
        assert result.papers == []
        assert result.llm_summary == ""

    @pytest.mark.asyncio
    async def test_calls_beta_api_with_mcp_servers(self, connector, mock_client):
        mock_client.beta.messages.create.return_value = _make_mock_response(
            papers_json='{"papers": [{"pmid": "123", "title": "Test Paper"}], "summary": "Found 1 paper"}'
        )

        result = await connector.search(
            query="spaceflight anemia",
            sources=["pubmed"],
            model_tier="sonnet",
        )

        # Verify API was called with correct beta flag
        call_kwargs = mock_client.beta.messages.create.call_args
        assert BETA_FLAG in call_kwargs.kwargs["betas"]
        assert len(call_kwargs.kwargs["mcp_servers"]) == 1
        assert call_kwargs.kwargs["mcp_servers"][0]["name"] == "pubmed"

    @pytest.mark.asyncio
    async def test_extracts_token_usage(self, connector, mock_client):
        mock_client.beta.messages.create.return_value = _make_mock_response()

        result = await connector.search(query="test", sources=["pubmed"])

        assert result.input_tokens == 500
        assert result.output_tokens == 200
        assert result.cached_input_tokens == 50

    @pytest.mark.asyncio
    async def test_extracts_papers_from_json(self, connector, mock_client):
        papers_json = (
            '```json\n'
            '{"papers": [{"pmid": "12345", "title": "Paper A"}, '
            '{"pmid": "67890", "title": "Paper B"}], '
            '"summary": "Found 2 papers"}\n'
            '```'
        )
        mock_client.beta.messages.create.return_value = _make_mock_response(
            papers_json=papers_json
        )

        result = await connector.search(query="test", sources=["pubmed"])

        assert len(result.papers) == 2
        assert result.papers[0]["pmid"] == "12345"
        assert result.papers[1]["title"] == "Paper B"


# ── Tests: _extract_papers_from_text ──


class TestExtractPapers:
    def test_extracts_from_json_code_block(self):
        text = '```json\n{"papers": [{"pmid": "1"}]}\n```'
        papers = MCPConnector._extract_papers_from_text(text)
        assert len(papers) == 1

    def test_extracts_from_bare_json(self):
        text = 'Some text {"papers": [{"pmid": "1"}]} more text'
        papers = MCPConnector._extract_papers_from_text(text)
        assert len(papers) == 1

    def test_extracts_from_array(self):
        text = 'Here are papers: [{"pmid": "1"}, {"pmid": "2"}]'
        papers = MCPConnector._extract_papers_from_text(text)
        assert len(papers) == 2

    def test_returns_empty_for_no_json(self):
        papers = MCPConnector._extract_papers_from_text("No JSON here")
        assert papers == []

    def test_returns_empty_for_invalid_json(self):
        papers = MCPConnector._extract_papers_from_text('{"papers": invalid}')
        assert papers == []


# ── Tests: MCPSearchResult dataclass ──


class TestMCPSearchResult:
    def test_defaults(self):
        r = MCPSearchResult(source="pubmed")
        assert r.source == "pubmed"
        assert r.papers == []
        assert r.llm_summary == ""
        assert r.input_tokens == 0
