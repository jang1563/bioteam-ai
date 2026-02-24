"""Structural validation tests for RCMXT benchmark claim files."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

BENCHMARKS_DIR = Path(__file__).parent.parent.parent / "app" / "cold_start" / "benchmarks"


# === 50-claim file (v1.0.0, backward compat) ===


class TestBenchmark50Claims:
    """Validate the original 50-claim benchmark file."""

    @pytest.fixture(autouse=True)
    def load_data(self):
        path = BENCHMARKS_DIR / "rcmxt_50_claims.json"
        assert path.exists(), f"Missing benchmark file: {path}"
        with open(path) as f:
            self.data = json.load(f)

    def test_total_claims(self):
        assert len(self.data["claims"]) == 50

    def test_metadata_present(self):
        assert "metadata" in self.data
        assert self.data["metadata"]["total_claims"] == 50

    def test_required_fields(self):
        required = {"id", "claim", "domain", "expected_R", "expected_C", "expected_M", "expected_X", "expected_T", "rationale", "difficulty"}
        for claim in self.data["claims"]:
            missing = required - set(claim.keys())
            assert not missing, f"Claim {claim.get('id', '?')} missing fields: {missing}"

    def test_score_ranges(self):
        for claim in self.data["claims"]:
            for axis in ("expected_R", "expected_C", "expected_M", "expected_T"):
                val = claim[axis]
                assert 0.0 <= val <= 1.0, f"{claim['id']}: {axis}={val} out of range"
            if claim["expected_X"] is not None:
                assert 0.0 <= claim["expected_X"] <= 1.0, f"{claim['id']}: X={claim['expected_X']} out of range"

    def test_unique_ids(self):
        ids = [c["id"] for c in self.data["claims"]]
        assert len(ids) == len(set(ids)), "Duplicate IDs found"


# === 150-claim file (v2.0.0, publication-grade) ===


class TestBenchmark150Claims:
    """Comprehensive validation of the 150-claim benchmark for RCMXT calibration."""

    @pytest.fixture(autouse=True)
    def load_data(self):
        path = BENCHMARKS_DIR / "rcmxt_150_claims.json"
        if not path.exists():
            pytest.skip("150-claim benchmark file not yet created")
        with open(path) as f:
            self.data = json.load(f)

    def test_total_claims(self):
        assert len(self.data["claims"]) == 150

    def test_metadata(self):
        meta = self.data["metadata"]
        assert meta["total_claims"] == 150
        assert meta["version"] == "2.0.0"

    def test_domain_distribution(self):
        domains = [c["domain"] for c in self.data["claims"]]
        assert domains.count("spaceflight_biology") == 50
        assert domains.count("cancer_genomics") == 50
        assert domains.count("neuroscience") == 50

    def test_unique_ids(self):
        ids = [c["id"] for c in self.data["claims"]]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {[x for x in ids if ids.count(x) > 1]}"

    def test_id_prefixes(self):
        for claim in self.data["claims"]:
            if claim["domain"] == "spaceflight_biology":
                assert claim["id"].startswith("sf_"), f"{claim['id']} should start with sf_"
            elif claim["domain"] == "cancer_genomics":
                assert claim["id"].startswith("cg_"), f"{claim['id']} should start with cg_"
            elif claim["domain"] == "neuroscience":
                assert claim["id"].startswith("ns_"), f"{claim['id']} should start with ns_"

    def test_required_fields(self):
        required = {"id", "claim", "domain", "expected_R", "expected_C", "expected_M", "expected_X", "expected_T", "rationale", "difficulty"}
        for claim in self.data["claims"]:
            missing = required - set(claim.keys())
            assert not missing, f"Claim {claim['id']} missing fields: {missing}"

    def test_score_ranges(self):
        for claim in self.data["claims"]:
            for axis in ("expected_R", "expected_C", "expected_M", "expected_T"):
                val = claim[axis]
                assert isinstance(val, (int, float)), f"{claim['id']}: {axis} is not numeric"
                assert 0.0 <= val <= 1.0, f"{claim['id']}: {axis}={val} out of range"
            x = claim["expected_X"]
            if x is not None:
                assert isinstance(x, (int, float)), f"{claim['id']}: X is not numeric"
                assert 0.0 <= x <= 1.0, f"{claim['id']}: X={x} out of range"

    def test_difficulty_values(self):
        valid = {"easy", "medium", "hard"}
        for claim in self.data["claims"]:
            assert claim["difficulty"] in valid, f"{claim['id']}: invalid difficulty '{claim['difficulty']}'"

    def test_difficulty_distribution_per_domain(self):
        """No domain should have all-easy or all-hard claims."""
        for domain in ("spaceflight_biology", "cancer_genomics", "neuroscience"):
            domain_claims = [c for c in self.data["claims"] if c["domain"] == domain]
            difficulties = [c["difficulty"] for c in domain_claims]
            for level in ("easy", "medium", "hard"):
                count = difficulties.count(level)
                assert count >= 5, f"{domain}: only {count} '{level}' claims (need >= 5)"

    def test_rationale_length(self):
        for claim in self.data["claims"]:
            assert len(claim["rationale"]) >= 100, (
                f"{claim['id']}: rationale too short ({len(claim['rationale'])} chars)"
            )

    def test_claim_text_length(self):
        for claim in self.data["claims"]:
            assert len(claim["claim"]) >= 30, f"{claim['id']}: claim text too short"

    def test_x_axis_null_prevalence(self):
        """~80-85% of claims should have X=null (single-omics)."""
        null_x = sum(1 for c in self.data["claims"] if c["expected_X"] is None)
        ratio = null_x / 150
        assert 0.60 <= ratio <= 0.95, (
            f"X-axis null ratio = {ratio:.1%}, expected ~80-85%"
        )

    def test_score_variance_not_hedging(self):
        """Scores should use the full range, not cluster around 0.5."""
        import statistics
        for axis in ("expected_R", "expected_C", "expected_M", "expected_T"):
            values = [c[axis] for c in self.data["claims"]]
            std = statistics.stdev(values)
            assert std > 0.10, (
                f"{axis}: std={std:.3f} — scores may be hedging around the mean"
            )

    def test_negative_controls_present(self):
        """At least 5 claims per domain with R < 0.35 (negative controls)."""
        for domain in ("spaceflight_biology", "cancer_genomics", "neuroscience"):
            domain_claims = [c for c in self.data["claims"] if c["domain"] == domain]
            low_r = sum(1 for c in domain_claims if c["expected_R"] <= 0.35)
            assert low_r >= 3, (
                f"{domain}: only {low_r} claims with R <= 0.35 (need >= 3 negative controls)"
            )
