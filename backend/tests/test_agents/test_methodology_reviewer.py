"""Tests for MethodologyReviewer agent."""

from __future__ import annotations

import pytest
from app.agents.methodology_reviewer import MethodologyReviewerAgent
from app.llm.mock_layer import MockLLMLayer
from app.models.agent import AgentSpec
from app.models.messages import ContextPackage


@pytest.fixture
def mock_llm():
    return MockLLMLayer()


@pytest.fixture
def methodology_reviewer(mock_llm):
    spec = AgentSpec(
        id="methodology_reviewer",
        name="Methodology Reviewer",
        tier="domain_expert",
        model_tier="opus",
        division="cross_cutting",
        criticality="optional",
        system_prompt_file="methodology_reviewer.md",
    )
    return MethodologyReviewerAgent(spec=spec, llm=mock_llm)


@pytest.mark.asyncio
class TestMethodologyReviewer:
    async def test_run_returns_agent_output(self, methodology_reviewer):
        context = ContextPackage(
            task_description="## Methods\nWe performed RNA-seq on n=12 samples using DESeq2."
        )
        output = await methodology_reviewer.run(context)
        assert output.agent_id == "methodology_reviewer"
        assert output.output is not None

    async def test_run_with_empty_text(self, methodology_reviewer):
        context = ContextPackage(task_description="")
        output = await methodology_reviewer.run(context)
        assert "No paper text" in output.summary

    async def test_run_with_prior_outputs(self, methodology_reviewer):
        context = ContextPackage(
            task_description="## Methods\nWe performed RNA-seq.",
            prior_step_outputs=[
                {
                    "step_id": "EXTRACT_CLAIMS",
                    "output": {
                        "claims": [
                            {"claim_text": "Gene X upregulated", "claim_type": "main_finding"},
                        ],
                    },
                },
                {
                    "step_id": "BACKGROUND_LIT",
                    "output": {
                        "summary": "Literature shows mixed results for Gene X expression.",
                    },
                },
            ],
        )
        output = await methodology_reviewer.run(context)
        assert output.agent_id == "methodology_reviewer"

    def test_spec_loading(self):
        """Verify that the methodology_reviewer spec YAML can be loaded."""
        from app.agents.base import BaseAgent
        spec = BaseAgent.load_spec("methodology_reviewer")
        assert spec.id == "methodology_reviewer"
        assert spec.model_tier == "opus"


class TestMethodologyReviewerRegistration:
    def test_registered_in_registry(self, mock_llm):
        """Verify methodology_reviewer is registered in create_registry."""
        from app.agents.registry import create_registry
        registry = create_registry(mock_llm, memory=None)
        agent = registry.get("methodology_reviewer")
        assert agent is not None
        assert agent.agent_id == "methodology_reviewer"
