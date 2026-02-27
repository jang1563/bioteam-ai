"""ICD-10 Codes via MCP — diagnosis/procedure code lookup and validation.

Available only when settings.mcp_enabled=True. No direct API fallback.
Uses the Anthropic-hosted ICD-10 MCP connector (2026 code sets).

Tools available via the MCP connector:
- lookup_code: Get details for a specific ICD-10 code
- search_codes: Search by prefix or description keyword
- validate_code: Check format, billability, HIPAA compliance
- get_hierarchy: Parent categories and child codes
- get_by_category: Codes by chapter or 3-character category
- get_by_body_system: ICD-10-PCS procedure codes by anatomical system
"""

from __future__ import annotations

import logging

import anthropic
from app.config import settings
from app.integrations.mcp_connector import BETA_FLAG, MCPSearchResult

logger = logging.getLogger(__name__)


class MCPICD10Client:
    """Client for ICD-10 code lookup via MCP connector.

    Usage:
        client = MCPICD10Client(anthropic_client)
        result = await client.lookup_code("E11.65")
    """

    def __init__(self, client: anthropic.AsyncAnthropic | None = None) -> None:
        self.client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key
        )

    async def lookup_code(self, code: str) -> MCPSearchResult:
        """Look up details for a specific ICD-10 code."""
        url = settings.mcp_icd10_url
        if not url:
            return MCPSearchResult(source="icd10")

        response = await self.client.beta.messages.create(
            model=settings.model_haiku,
            max_tokens=2048,
            betas=[BETA_FLAG],
            mcp_servers=[{"type": "url", "name": "icd10", "url": url}],
            tools=[{"type": "mcp_toolset", "mcp_server_name": "icd10"}],
            system="Look up the ICD-10 code and return its details as JSON.",
            messages=[{"role": "user", "content": f"Look up ICD-10 code: {code}"}],
        )

        result = MCPSearchResult(source="icd10")
        usage = getattr(response, "usage", None)
        if usage:
            result.input_tokens = getattr(usage, "input_tokens", 0)
            result.output_tokens = getattr(usage, "output_tokens", 0)
        for block in getattr(response, "content", []):
            if getattr(block, "type", "") == "text":
                result.llm_summary += getattr(block, "text", "")

        return result

    async def search_codes(
        self, query: str, code_type: str = "diagnosis", max_results: int = 10
    ) -> MCPSearchResult:
        """Search ICD-10 codes by description keyword."""
        url = settings.mcp_icd10_url
        if not url:
            return MCPSearchResult(source="icd10")

        response = await self.client.beta.messages.create(
            model=settings.model_haiku,
            max_tokens=2048,
            betas=[BETA_FLAG],
            mcp_servers=[{"type": "url", "name": "icd10", "url": url}],
            tools=[{"type": "mcp_toolset", "mcp_server_name": "icd10"}],
            system=(
                f"Search for ICD-10 {code_type} codes matching the query. "
                f"Return up to {max_results} results as JSON."
            ),
            messages=[{"role": "user", "content": f"Search: {query}"}],
        )

        result = MCPSearchResult(source="icd10")
        usage = getattr(response, "usage", None)
        if usage:
            result.input_tokens = getattr(usage, "input_tokens", 0)
            result.output_tokens = getattr(usage, "output_tokens", 0)
        for block in getattr(response, "content", []):
            if getattr(block, "type", "") == "text":
                result.llm_summary += getattr(block, "text", "")

        return result
