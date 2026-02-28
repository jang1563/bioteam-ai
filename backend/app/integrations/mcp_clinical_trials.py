"""ClinicalTrials.gov via MCP — search trials, eligibility, endpoints.

Available only when settings.mcp_enabled=True. No direct API fallback.
Uses the Anthropic-hosted ClinicalTrials.gov MCP connector.

Tools available via the MCP connector:
- search_trials: Search by condition, intervention, location, status
- get_trial_details: Full protocol for an NCT number
- search_by_eligibility: Match patients to trials by demographics
- analyze_endpoints: Compare outcome measures across trials
- search_investigators: Find PIs and research sites
- search_by_sponsor: All trials by a company/institution
"""

from __future__ import annotations

import logging

import anthropic
from app.config import settings
from app.integrations.mcp_connector import BETA_FLAG, MCPSearchResult

logger = logging.getLogger(__name__)


class MCPClinicalTrialsClient:
    """Client for ClinicalTrials.gov via MCP connector.

    Usage:
        client = MCPClinicalTrialsClient(anthropic_client)
        result = await client.search_trials("spaceflight bone loss", phase="Phase 2")
    """

    def __init__(self, client: anthropic.AsyncAnthropic | None = None) -> None:
        self.client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key
        )

    async def search_trials(
        self,
        condition: str,
        intervention: str = "",
        location: str = "",
        phase: str = "",
        status: str = "RECRUITING",
        max_results: int = 10,
    ) -> MCPSearchResult:
        """Search ClinicalTrials.gov via MCP connector."""
        query_parts = [f"condition: {condition}"]
        if intervention:
            query_parts.append(f"intervention: {intervention}")
        if location:
            query_parts.append(f"location: {location}")
        if phase:
            query_parts.append(f"phase: {phase}")
        if status:
            query_parts.append(f"status: {status}")
        query = ", ".join(query_parts)

        url = settings.mcp_clinical_trials_url
        if not url:
            return MCPSearchResult(source="clinical_trials")

        response = await self.client.beta.messages.create(
            model=settings.model_sonnet,
            max_tokens=4096,
            betas=[BETA_FLAG],
            mcp_servers=[{"type": "url", "name": "clinical_trials", "url": url}],
            tools=[{"type": "mcp_toolset", "mcp_server_name": "clinical_trials"}],
            system=(
                "Search ClinicalTrials.gov for matching trials. "
                f"Return up to {max_results} results as JSON with keys: "
                '"trials" (array of {nct_id, title, status, phase, conditions, interventions}).'
            ),
            messages=[{"role": "user", "content": f"Search: {query}"}],
        )

        result = MCPSearchResult(source="clinical_trials")
        usage = getattr(response, "usage", None)
        if usage:
            result.input_tokens = getattr(usage, "input_tokens", 0)
            result.output_tokens = getattr(usage, "output_tokens", 0)
        for block in getattr(response, "content", []):
            if getattr(block, "type", "") == "text":
                result.llm_summary += getattr(block, "text", "")

        return result
