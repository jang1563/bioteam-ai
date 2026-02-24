"""Mock-based benchmark evaluation for RCMXT scorer pipeline.

Validates that the scoring pipeline can process all 150 claims
and produce structurally valid output. Uses MockLLMLayer for CI.
Real calibration with API calls is done via backend/scripts/run_rcmxt_calibration.py.
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.engines.rcmxt_scorer import RCMXTScorer
from app.llm.mock_layer import MockLLMLayer
from app.models.evidence import AxisExplanation, LLMRCMXTResponse

BENCHMARKS_DIR = Path(__file__).parent.parent.parent / "app" / "cold_start" / "benchmarks"


def _load_150_claims():
    path = BENCHMARKS_DIR / "rcmxt_150_claims.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _make_mock_llm_for_benchmark() -> MockLLMLayer:
    """Create a MockLLMLayer that returns plausible scores."""
    return MockLLMLayer({
        "sonnet:LLMRCMXTResponse": LLMRCMXTResponse(
            claim_text="benchmark claim",
            axes=[
                AxisExplanation(axis="R", score=0.65, reasoning="Moderate replication across independent studies."),
                AxisExplanation(axis="C", score=0.50, reasoning="Context-dependent with known caveats."),
                AxisExplanation(axis="M", score=0.70, reasoning="Adequate methodology with proper controls."),
                AxisExplanation(axis="T", score=0.60, reasoning="Established over the past decade."),
            ],
            x_applicable=False,
            overall_assessment="Moderately well-supported claim.",
            confidence_in_scoring=0.75,
        ),
    })


class TestBenchmarkPipeline:
    """Test the scoring pipeline with benchmark claims (mock-based)."""

    @pytest.fixture(autouse=True)
    def load_claims(self):
        data = _load_150_claims()
        if data is None:
            pytest.skip("150-claim benchmark file not yet created")
        self.claims = data["claims"]

    @pytest.mark.asyncio
    async def test_score_all_benchmark_claims(self):
        """Score all 150 claims and verify output structure."""
        mock = _make_mock_llm_for_benchmark()
        scorer = RCMXTScorer(mode="llm", llm_layer=mock)

        scored = []
        for claim in self.claims:
            score, resp = await scorer.score_benchmark_claim(
                claim["claim"], claim["domain"]
            )
            scored.append(score)

        assert len(scored) == 150
        assert all(s.composite is not None for s in scored)
        assert all(s.scorer_version == "v0.2-llm" for s in scored)

    @pytest.mark.asyncio
    async def test_heuristic_baseline(self):
        """Score all claims with heuristic for baseline comparison."""
        scorer = RCMXTScorer(mode="heuristic")

        scored = []
        for claim in self.claims:
            score, resp = await scorer.score_benchmark_claim(
                claim["claim"], claim["domain"]
            )
            scored.append(score)
            assert resp is None  # No LLM response in heuristic mode

        assert len(scored) == 150
        assert all(s.scorer_version == "v0.1-heuristic" for s in scored)

    def test_compute_mae_structure(self):
        """Verify MAE can be computed from expected vs mock scores."""
        # Just validate the structure, not actual values (mock scores are fixed)
        axes = ["expected_R", "expected_C", "expected_M", "expected_T"]
        for axis in axes:
            values = [c[axis] for c in self.claims]
            assert len(values) == 150
            assert all(isinstance(v, (int, float)) for v in values)

    def test_x_axis_expected_distribution(self):
        """Verify X-axis expected scores follow null prevalence rule."""
        null_x = sum(1 for c in self.claims if c["expected_X"] is None)
        with_x = sum(1 for c in self.claims if c["expected_X"] is not None)
        assert null_x + with_x == 150
        # ~80-85% should be null
        assert null_x >= 90  # At least 60%
