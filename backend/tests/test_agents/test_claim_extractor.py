"""Tests for ClaimExtractor agent."""

from __future__ import annotations

import pytest

from app.agents.claim_extractor import ClaimExtractorAgent
from app.llm.mock_layer import MockLLMLayer
from app.models.agent import AgentSpec
from app.models.messages import ContextPackage


@pytest.fixture
def mock_llm():
    return MockLLMLayer()


@pytest.fixture
def claim_extractor(mock_llm):
    spec = AgentSpec(
        id="claim_extractor",
        name="Claim Extractor",
        tier="domain_expert",
        model_tier="sonnet",
        division="cross_cutting",
        criticality="optional",
        system_prompt_file="claim_extractor.md",
    )
    return ClaimExtractorAgent(spec=spec, llm=mock_llm)


@pytest.mark.asyncio
class TestClaimExtractor:
    async def test_run_returns_agent_output(self, claim_extractor):
        context = ContextPackage(
            task_description="## Results\nWe found that gene X was upregulated 2.5-fold (p<0.001, n=12)."
        )
        output = await claim_extractor.run(context)
        assert output.agent_id == "claim_extractor"
        # MockLLMLayer returns mock structured output
        assert output.output is not None

    async def test_run_with_empty_text(self, claim_extractor):
        context = ContextPackage(task_description="")
        output = await claim_extractor.run(context)
        assert "No paper text" in output.summary

    async def test_run_with_short_text(self, claim_extractor):
        context = ContextPackage(task_description="Hi")
        output = await claim_extractor.run(context)
        assert "No paper text" in output.summary

    async def test_truncates_long_text(self, claim_extractor):
        context = ContextPackage(task_description="A" * 100_000)
        output = await claim_extractor.run(context)
        # Should not error, just truncate
        assert output.agent_id == "claim_extractor"

    def test_spec_loading(self):
        """Verify that the claim_extractor spec YAML can be loaded."""
        from app.agents.base import BaseAgent
        spec = BaseAgent.load_spec("claim_extractor")
        assert spec.id == "claim_extractor"
        assert spec.model_tier == "sonnet"


class TestClaimExtractorRegistration:
    def test_registered_in_registry(self, mock_llm):
        """Verify claim_extractor is registered in create_registry."""
        from app.agents.registry import create_registry
        registry = create_registry(mock_llm, memory=None)
        agent = registry.get("claim_extractor")
        assert agent is not None
        assert agent.agent_id == "claim_extractor"
