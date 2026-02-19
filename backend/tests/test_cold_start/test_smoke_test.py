"""Tests for Cold Start Smoke Test."""

import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.registry import create_registry
from app.agents.research_director import QueryClassification
from app.llm.mock_layer import MockLLMLayer
from app.cold_start.smoke_test import SmokeTest, SmokeTestResult


def _make_smoke_test() -> SmokeTest:
    """Create a SmokeTest with mocked agents."""
    # Provide a mock for RD's classify_query (default run)
    mock = MockLLMLayer({
        "sonnet:QueryClassification": QueryClassification(
            type="simple_query",
            reasoning="Smoke test response",
            target_agent="t02_transcriptomics",
        ),
    })
    registry = create_registry(mock)
    return SmokeTest(registry=registry)


def test_smoke_test_passes():
    """Smoke test should pass with all agents registered and healthy."""
    smoke = _make_smoke_test()
    result = asyncio.run(smoke.run())

    assert isinstance(result, SmokeTestResult)
    assert result.passed is True

    assert result.checks["registry"]["passed"] is True
    assert result.checks["critical_health"]["passed"] is True
    assert result.checks["direct_query"]["passed"] is True
    print("  PASS: smoke_test_passes")


def test_smoke_test_empty_registry():
    """Smoke test should fail with an empty registry."""
    from app.agents.registry import AgentRegistry
    empty_registry = AgentRegistry()
    smoke = SmokeTest(registry=empty_registry)
    result = asyncio.run(smoke.run())

    assert result.passed is False
    assert result.checks["registry"]["passed"] is False
    assert result.checks["critical_health"]["passed"] is False
    assert result.checks["direct_query"]["passed"] is False
    print("  PASS: smoke_test_empty_registry")


if __name__ == "__main__":
    print("Testing Cold Start Smoke Test:")
    test_smoke_test_passes()
    test_smoke_test_empty_registry()
    print("\nAll Cold Start Smoke Test tests passed!")
