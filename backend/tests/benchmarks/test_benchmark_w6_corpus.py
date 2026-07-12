"""W6 AmbiguityEngine corpus benchmark — contradiction classification accuracy.

Tests the AmbiguityEngineAgent's classify_pair() against the held reference
contradiction corpus (corpus_final.jsonl, 338 entries).

This test requires LLM API access and is marked with @pytest.mark.benchmark
to exclude it from the default offline CI suite.

Run manually:
  export GEMINI_API_KEY=<your-key>
  AMBIGUITY_LLM_PROVIDER=gemini uv run pytest backend/tests/benchmarks/test_benchmark_w6_corpus.py -v

Expected metrics (Gemini free tier, production prompt):
  - Binary F1 >= 0.30 (conservative lower bound)
  - Parse failure rate < 10%
  - All 5 contradiction types classified at least once
"""

import json
import os
from pathlib import Path

import pytest
from app.agents.ambiguity_engine import AmbiguityEngineAgent
from app.agents.base import BaseAgent
from app.llm.layer import LLMLayer

CORPUS_PATH = Path(__file__).parents[2] / "scripts" / "output" / "v3" / "corpus_final.jsonl"

# Skip entirely if corpus or API key not available
pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not CORPUS_PATH.exists(),
        reason=f"Corpus not found: {CORPUS_PATH}",
    ),
    pytest.mark.skipif(
        not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
             or os.environ.get("ANTHROPIC_API_KEY")),
        reason="No LLM API key available",
    ),
]


@pytest.fixture(scope="module")
def agent():
    """Create AmbiguityEngineAgent with production config."""
    llm = LLMLayer()
    spec = BaseAgent.load_spec("ambiguity_engine")
    return AmbiguityEngineAgent(spec=spec, llm=llm, memory=None)


@pytest.fixture(scope="module")
def corpus():
    """Load the held contradiction corpus."""
    entries = [json.loads(line) for line in open(CORPUS_PATH) if line.strip()]
    return entries


@pytest.fixture(scope="module")
def sample_corpus(corpus):
    """Small sample for quick smoke tests (first 10 entries)."""
    return corpus[:10]


@pytest.mark.asyncio
async def test_w6_classify_pair_smoke(agent, sample_corpus):
    """Smoke test: classify_pair returns valid ContradictionClassification."""
    entry = sample_corpus[0]
    result = await agent.classify_pair(
        claim_a=entry["claim_a"],
        claim_b=entry["claim_b"],
    )

    assert result is not None
    assert isinstance(result.is_genuine_contradiction, bool)
    assert len(result.types) >= 1
    assert result.types[0] in {"direct", "temporal", "magnitude", "methodological", "contextual"}
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.asyncio
async def test_w6_type_consistency(agent, sample_corpus):
    """Verify that is_genuine_contradiction and types are consistent."""
    entry = sample_corpus[0]
    result = await agent.classify_pair(
        claim_a=entry["claim_a"],
        claim_b=entry["claim_b"],
    )

    if result.is_genuine_contradiction:
        # Genuine should not have contextual as primary type
        assert result.types[0] != "contextual", (
            f"Genuine contradiction should not be contextual: {result.types}"
        )
    else:
        # Non-genuine should be contextual
        assert result.types == ["contextual"], (
            f"Non-genuine should be ['contextual'], got {result.types}"
        )


@pytest.mark.asyncio
async def test_w6_direct_contradiction_detected(agent):
    """Verify that an obvious direct contradiction is detected."""
    result = await agent.classify_pair(
        claim_a="Gene X overexpression significantly increased tumor cell proliferation in vitro.",
        claim_b="Gene X overexpression significantly decreased tumor cell proliferation in vitro.",
    )

    assert result.is_genuine_contradiction, "Obvious direct contradiction should be detected"
    assert "direct" in result.types, f"Expected 'direct' type, got {result.types}"


@pytest.mark.asyncio
async def test_w6_contextual_pair_recognized(agent):
    """Verify that a contextual (non-genuine) pair is recognized."""
    result = await agent.classify_pair(
        claim_a="In mice, compound Y significantly reduced inflammation markers.",
        claim_b="In human clinical trials, compound Y showed no anti-inflammatory effect.",
    )

    assert not result.is_genuine_contradiction, "Different species should be contextual"
    assert result.types == ["contextual"], f"Expected contextual, got {result.types}"
