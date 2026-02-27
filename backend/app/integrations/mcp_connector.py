"""MCP Healthcare Connector — Anthropic-hosted MCP servers for literature search.

Uses the Anthropic beta MCP client API (mcp-client-2025-11-20) to let Claude
call PubMed, bioRxiv, ClinicalTrials, ChEMBL, and ICD-10 tools natively.

MCP tool calls require full API round-trips. Each tool invocation by Claude
triggers a server-side MCP call. Multi-tool chains are handled automatically
by the Anthropic API's agentic loop.

Toggle: settings.mcp_enabled (default False).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import anthropic
from app.config import MODEL_MAP, settings

logger = logging.getLogger(__name__)

# Registry of MCP server configurations
MCP_SERVERS: dict[str, dict[str, str]] = {
    "pubmed": {
        "type": "url",
        "name": "pubmed",
        "url_config_key": "mcp_pubmed_url",
    },
    "biorxiv": {
        "type": "url",
        "name": "biorxiv",
        "url_config_key": "mcp_biorxiv_url",
    },
    "clinical_trials": {
        "type": "url",
        "name": "clinical_trials",
        "url_config_key": "mcp_clinical_trials_url",
    },
    "chembl": {
        "type": "url",
        "name": "chembl",
        "url_config_key": "mcp_chembl_url",
    },
    "icd10": {
        "type": "url",
        "name": "icd10",
        "url_config_key": "mcp_icd10_url",
    },
}

BETA_FLAG = "mcp-client-2025-11-20"


@dataclass
class MCPSearchResult:
    """Unified result from an MCP-powered search."""

    source: str  # e.g. "pubmed", "biorxiv", "pubmed,biorxiv"
    papers: list[dict] = field(default_factory=list)
    raw_tool_outputs: list[dict] = field(default_factory=list)
    llm_summary: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    model: str = ""


class MCPConnector:
    """Adapter for Anthropic-hosted MCP healthcare servers.

    Wraps client.beta.messages.create() with MCP server configuration.
    Claude autonomously selects and invokes MCP tools to answer queries.

    Usage:
        connector = MCPConnector(client)
        result = await connector.search(
            query="spaceflight anemia erythropoiesis",
            sources=["pubmed", "biorxiv"],
            model_tier="sonnet",
            max_results=20,
        )
    """

    def __init__(self, client: anthropic.AsyncAnthropic | None = None) -> None:
        self.client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key
        )

    def _build_mcp_servers(self, sources: list[str]) -> list[dict]:
        """Build MCP server config list for the given sources."""
        servers = []
        for source in sources:
            cfg = MCP_SERVERS.get(source)
            if cfg is None:
                logger.warning("Unknown MCP source: %s", source)
                continue
            url = getattr(settings, cfg["url_config_key"], "")
            if not url:
                logger.warning("MCP source %s has no URL configured", source)
                continue
            servers.append({
                "type": cfg["type"],
                "name": cfg["name"],
                "url": url,
            })
        return servers

    def _build_tools(self, sources: list[str]) -> list[dict]:
        """Build tool definitions — one mcp_toolset per source."""
        return [
            {"type": "mcp_toolset", "mcp_server_name": source}
            for source in sources
            if source in MCP_SERVERS
        ]

    async def search(
        self,
        query: str,
        sources: list[str],
        model_tier: str = "sonnet",
        max_results: int = 20,
        system_prompt: str = "",
    ) -> MCPSearchResult:
        """Execute an MCP-powered literature search.

        Claude autonomously calls MCP tools to search the specified sources,
        then returns structured results.

        Args:
            query: Research query to search for.
            sources: List of source names (e.g. ["pubmed", "biorxiv"]).
            model_tier: Model tier for the search call.
            max_results: Hint for max results per source.
            system_prompt: Optional custom system prompt.

        Returns:
            MCPSearchResult with papers, summaries, and token usage.
        """
        mcp_servers = self._build_mcp_servers(sources)
        tools = self._build_tools(sources)

        if not mcp_servers:
            logger.warning("No MCP servers configured for sources: %s", sources)
            return MCPSearchResult(source=",".join(sources))

        default_system = (
            "You are a biomedical literature search assistant. "
            "Use the available MCP tools to search for papers matching the query. "
            f"Return up to {max_results} most relevant results. "
            "For each paper found, extract: title, authors (list), year, "
            "DOI or PMID, abstract (first 300 chars). "
            "After searching all sources, provide a brief summary of findings. "
            "Format your final output as JSON with keys: "
            '"papers" (array of objects) and "summary" (string).'
        )

        messages = [{"role": "user", "content": f"Search for: {query}"}]

        response = await self.client.beta.messages.create(
            model=MODEL_MAP.get(model_tier, MODEL_MAP["sonnet"]),
            max_tokens=8192,
            betas=[BETA_FLAG],
            mcp_servers=mcp_servers,
            tools=tools,
            system=system_prompt or default_system,
            messages=messages,
        )

        return self._parse_response(response, sources)

    def _parse_response(
        self, response: Any, sources: list[str]
    ) -> MCPSearchResult:
        """Extract structured data from the MCP API response."""
        result = MCPSearchResult(
            source=",".join(sources),
            model=getattr(response, "model", ""),
        )

        # Extract token usage
        usage = getattr(response, "usage", None)
        if usage:
            result.input_tokens = getattr(usage, "input_tokens", 0)
            result.output_tokens = getattr(usage, "output_tokens", 0)
            result.cached_input_tokens = (
                getattr(usage, "cache_read_input_tokens", 0) or 0
            )

        # Extract text blocks and try to parse papers from JSON
        text_parts: list[str] = []
        for block in getattr(response, "content", []):
            block_type = getattr(block, "type", "")
            if block_type == "text":
                text_parts.append(getattr(block, "text", ""))

        full_text = "\n".join(text_parts)
        result.llm_summary = full_text

        # Try to extract structured papers from JSON in the response
        result.papers = self._extract_papers_from_text(full_text)

        return result

    @staticmethod
    def _extract_papers_from_text(text: str) -> list[dict]:
        """Try to extract a papers list from JSON in the LLM response text."""
        # Look for JSON block in the text
        import re

        # Try full JSON parse first
        json_patterns = [
            re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL),
            re.compile(r"```\s*(\{.*?\})\s*```", re.DOTALL),
            re.compile(r"(\{[^{}]*\"papers\"[^{}]*\[.*?\]\s*[^{}]*\})", re.DOTALL),
        ]

        for pattern in json_patterns:
            match = pattern.search(text)
            if match:
                try:
                    data = json.loads(match.group(1))
                    if isinstance(data, dict) and "papers" in data:
                        return data["papers"]
                except (json.JSONDecodeError, KeyError):
                    continue

        # Try to find a JSON array directly
        array_pattern = re.compile(r"\[\s*\{.*?\}\s*(?:,\s*\{.*?\}\s*)*\]", re.DOTALL)
        match = array_pattern.search(text)
        if match:
            try:
                papers = json.loads(match.group(0))
                if isinstance(papers, list) and papers and isinstance(papers[0], dict):
                    return papers
            except json.JSONDecodeError:
                pass

        return []
