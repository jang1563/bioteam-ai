"""W6 runtime test for Gemini provider routing and zero-cost accounting."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.ambiguity_engine import (  # noqa: E402
    AmbiguityEngineAgent,
    ContradictionClassification,
    ResolutionHypothesis,
    ResolutionOutput,
)
from app.agents.base import BaseAgent  # noqa: E402
from app.agents.knowledge_manager import KnowledgeManagerAgent  # noqa: E402
from app.agents.registry import AgentRegistry  # noqa: E402
from app.config import settings  # noqa: E402
from app.llm.gemini_layer import GeminiLayer, GeminiResponse  # noqa: E402
from app.workflows.runners.w6_ambiguity import W6AmbiguityRunner  # noqa: E402


class _DummyLLM:
    """Minimal LLM stub for BaseAgent initialization."""

    def estimate_cost(self, *args, **kwargs):
        return 0.0

    def build_cached_system(self, text: str):
        return text


@pytest.mark.asyncio
async def test_w6_uses_gemini_provider_cost_zero(monkeypatch):
    """W6 classify/resolution steps should report Gemini model and zero cost."""

    async def _fake_complete_structured(self, messages, response_model, system=None, max_tokens=4096, temperature=0.0):
        if response_model.__name__ == "ContradictionClassification":
            result = ContradictionClassification(
                types=["direct"],
                confidence=0.9,
                type_reasoning={"direct": "Opposite direction under matched context."},
                is_genuine_contradiction=True,
            )
        elif response_model.__name__ == "ResolutionOutput":
            result = ResolutionOutput(
                hypotheses=[
                    ResolutionHypothesis(
                        hypothesis="Protocol harmonization could reconcile the findings.",
                        hypothesis_type="reconciling",
                        testable_prediction="Run both measurements in a shared blinded setup.",
                        confidence=0.7,
                    )
                ],
                discriminating_experiment="Joint blinded replication study.",
            )
        else:
            # KnowledgeManager SearchTerms (internal model)
            result = response_model(
                pubmed_queries=["spaceflight anemia"],
                semantic_scholar_queries=["spaceflight anemia"],
                keywords=["spaceflight", "anemia"],
            )

        meta = GeminiResponse(
            model_version=settings.gemini_model,
            input_tokens=100,
            output_tokens=50,
            cost=0.0,
        )
        return result, meta

    monkeypatch.setattr(GeminiLayer, "complete_structured", _fake_complete_structured)
    monkeypatch.setattr("app.agents.knowledge_manager.settings.knowledge_manager_llm_provider", "gemini")
    monkeypatch.setattr("app.agents.ambiguity_engine.settings.ambiguity_llm_provider", "gemini")
    monkeypatch.setattr("app.workflows.runners.w6_ambiguity.settings.knowledge_manager_llm_provider", "gemini")
    monkeypatch.setattr("app.workflows.runners.w6_ambiguity.settings.ambiguity_llm_provider", "gemini")
    monkeypatch.setattr("app.config.settings.google_api_key", "test-key")
    monkeypatch.setattr("app.agents.knowledge_manager.settings.google_api_key", "test-key")
    monkeypatch.setattr("app.agents.ambiguity_engine.settings.google_api_key", "test-key")
    monkeypatch.setattr("app.workflows.runners.w6_ambiguity.settings.google_api_key", "test-key")
    monkeypatch.setattr("app.workflows.runners.w6_ambiguity.settings.refinement_enabled", False)

    llm = _DummyLLM()
    registry = AgentRegistry()
    registry.register(KnowledgeManagerAgent(spec=BaseAgent.load_spec("knowledge_manager"), llm=llm))
    registry.register(AmbiguityEngineAgent(spec=BaseAgent.load_spec("ambiguity_engine"), llm=llm))

    runner = W6AmbiguityRunner(registry=registry)
    query = (
        "Claim A: VEGF expression increases in endothelial cells under simulated microgravity.\n"
        "Claim B: VEGF expression decreases in endothelial cells under simulated microgravity."
    )
    result = await runner.run(query=query)

    assert result["completed"] is True
    classify = result["step_results"]["CLASSIFY"]
    resolution = result["step_results"]["RESOLUTION_HYPOTHESES"]

    assert classify["model_version"] == settings.gemini_model
    assert classify["cost"] == 0.0
    assert classify["output"]["pairs_classified"] >= 1
    assert resolution["model_version"] == settings.gemini_model
    assert resolution["cost"] == 0.0
