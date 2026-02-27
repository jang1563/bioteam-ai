"""ChEMBL via MCP — compound search, bioactivity, drug mechanisms.

Available only when settings.mcp_enabled=True. No direct API fallback.
Uses the Anthropic-hosted ChEMBL MCP connector (ChEMBL v34, 2.4M+ compounds).

Tools available via the MCP connector:
- compound_search: Search by name, SMILES, or ChEMBL ID
- target_search: Find biological targets (proteins, receptors)
- get_bioactivity: IC50, EC50, Ki, Kd measurements
- get_mechanism: Mechanism of action descriptions
- drug_search: Approved medications by indication
- get_admet: ADMET property predictions
"""

from __future__ import annotations

import logging

import anthropic
from app.config import settings
from app.integrations.mcp_connector import BETA_FLAG, MCPSearchResult

logger = logging.getLogger(__name__)


class MCPChEMBLClient:
    """Client for ChEMBL database via MCP connector.

    Usage:
        client = MCPChEMBLClient(anthropic_client)
        result = await client.compound_search("imatinib")
    """

    def __init__(self, client: anthropic.AsyncAnthropic | None = None) -> None:
        self.client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key
        )

    async def compound_search(
        self, query: str, max_results: int = 10
    ) -> MCPSearchResult:
        """Search ChEMBL for compounds by name, SMILES, or ChEMBL ID."""
        url = settings.mcp_chembl_url
        if not url:
            return MCPSearchResult(source="chembl")

        response = await self.client.beta.messages.create(
            model=settings.model_sonnet,
            max_tokens=4096,
            betas=[BETA_FLAG],
            mcp_servers=[{"type": "url", "name": "chembl", "url": url}],
            tools=[{"type": "mcp_toolset", "mcp_server_name": "chembl"}],
            system=(
                "Search ChEMBL for compounds matching the query. "
                f"Return up to {max_results} results as JSON with keys: "
                '"compounds" (array of {chembl_id, name, smiles, molecular_formula}).'
            ),
            messages=[{"role": "user", "content": f"Search: {query}"}],
        )

        result = MCPSearchResult(source="chembl")
        usage = getattr(response, "usage", None)
        if usage:
            result.input_tokens = getattr(usage, "input_tokens", 0)
            result.output_tokens = getattr(usage, "output_tokens", 0)
        for block in getattr(response, "content", []):
            if getattr(block, "type", "") == "text":
                result.llm_summary += getattr(block, "text", "")

        return result

    async def drug_search(
        self, indication: str, max_results: int = 10
    ) -> MCPSearchResult:
        """Search ChEMBL for approved drugs by indication."""
        url = settings.mcp_chembl_url
        if not url:
            return MCPSearchResult(source="chembl")

        response = await self.client.beta.messages.create(
            model=settings.model_sonnet,
            max_tokens=4096,
            betas=[BETA_FLAG],
            mcp_servers=[{"type": "url", "name": "chembl", "url": url}],
            tools=[{"type": "mcp_toolset", "mcp_server_name": "chembl"}],
            system=(
                "Search ChEMBL for approved drugs for the given indication. "
                f"Return up to {max_results} results as JSON with keys: "
                '"drugs" (array of {chembl_id, name, indication, mechanism, max_phase}).'
            ),
            messages=[{"role": "user", "content": f"Find drugs for: {indication}"}],
        )

        result = MCPSearchResult(source="chembl")
        usage = getattr(response, "usage", None)
        if usage:
            result.input_tokens = getattr(usage, "input_tokens", 0)
            result.output_tokens = getattr(usage, "output_tokens", 0)
        for block in getattr(response, "content", []):
            if getattr(block, "type", "") == "text":
                result.llm_summary += getattr(block, "text", "")

        return result
