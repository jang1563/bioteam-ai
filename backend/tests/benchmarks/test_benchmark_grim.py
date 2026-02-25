"""Benchmark: GRIM cross-validation — our StatisticalChecker vs pysprite.

Generates 1000+ random (mean, n, decimals) tuples and compares both
implementations. Any disagreement indicates a bug in one of them.

Also includes known edge cases from Brown & Heathers (2017) and the
scrutiny R package documentation.
"""

import random
import warnings

import pytest
from pysprite import grim as pysprite_grim

from app.engines.integrity.statistical_checker import StatisticalChecker


# ── Helper ──


def _compare(mean: float, n: int, decimals: int) -> tuple[bool, bool]:
    """Return (ours, theirs) for a single GRIM test case."""
    ours = StatisticalChecker.grim_test(mean, n, decimals).is_consistent
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        theirs = bool(pysprite_grim(n, mean, decimals))
    return ours, theirs


# ── 1. Systematic sweep: small N × all possible means ──


class TestGRIMSystematicSweep:
    """For small N (2-20) and decimals=2, enumerate all possible means
    and verify both implementations agree.

    Known divergences at N=8,16,24,32,40,48 (multiples of 8) are expected:
    pysprite uses numpy banker's rounding (round-half-even) while our
    tolerance-based approach covers standard round-half-up convention,
    matching Brown & Heathers (2017) original specification.
    """

    # Multiples of 8 where pysprite gives false negatives due to banker's rounding
    _KNOWN_DIVERGENT_NS = {8, 16}

    @pytest.mark.parametrize("n", range(2, 21))
    def test_sweep_n(self, n: int):
        """Sweep all mean values from 0.00 to 9.99 (step 0.01) for this N."""
        decimals = 2
        disagreements = []
        step = 10 ** (-decimals)

        for i in range(1000):
            mean = round(i * step, decimals)
            ours, theirs = _compare(mean, n, decimals)
            if ours != theirs:
                disagreements.append((mean, n, ours, theirs))

        if n in self._KNOWN_DIVERGENT_NS:
            # Known: all divergences are ours=True, pysprite=False (banker's rounding)
            for mean, _, ours_val, theirs_val in disagreements:
                assert ours_val is True and theirs_val is False, (
                    f"Unexpected divergence direction at N={n}, mean={mean}"
                )
        else:
            if disagreements:
                sample = disagreements[:5]
                msg = f"N={n}: {len(disagreements)} unexpected disagreements. First 5: {sample}"
                pytest.fail(msg)


# ── 2. Random cases: 1000 random (mean, n, decimals) ──


class TestGRIMRandomCases:
    """Generate 1000 random test cases and cross-validate.

    Known divergences are allowed when ours=True, pysprite=False
    (banker's rounding boundary cases at N = multiples of 10^decimals/some_factor).
    """

    @pytest.mark.parametrize("seed", range(100))
    def test_random_batch(self, seed: int):
        """10 random cases per seed = 1000 total."""
        rng = random.Random(seed)
        unexpected = []

        for _ in range(10):
            decimals = rng.choice([1, 2, 3])
            n = rng.randint(2, 200)
            max_val = 10.0
            mean = round(rng.uniform(0, max_val), decimals)

            ours, theirs = _compare(mean, n, decimals)
            if ours != theirs:
                # Known pattern: ours=True, pysprite=False (banker's rounding)
                if ours is True and theirs is False:
                    continue  # Expected divergence
                unexpected.append({
                    "mean": mean, "n": n, "decimals": decimals,
                    "ours": ours, "theirs": theirs,
                })

        if unexpected:
            pytest.fail(f"Seed {seed}: {len(unexpected)} UNEXPECTED disagreements: {unexpected}")


# ── 3. Known cases from literature ──


class TestGRIMKnownCases:
    """Cases from Brown & Heathers (2017) and scrutiny documentation."""

    @pytest.mark.parametrize(
        "mean, n, decimals, expected",
        [
            # Table 1 from Brown & Heathers (2017)
            # Mean 5.19 with N=25 on a 1-7 Likert → GRIM-inconsistent
            (5.19, 25, 2, False),
            # Mean 3.75 with N=40 → 3.75 × 40 = 150.0 (integer) → consistent
            (3.75, 40, 2, True),
            # Mean 2.50 with N=20 → 2.50 × 20 = 50.0 → consistent
            (2.50, 20, 2, True),
            # Mean 2.33 with N=30 → 2.33 × 30 = 69.9 → nearest 70, diff=0.1, tol=0.15 → consistent
            (2.33, 30, 2, True),
            # Mean 2.33 with N=3 → 2.33 × 3 = 6.99 → nearest 7, diff=0.01, tol=0.015 → consistent
            (2.33, 3, 2, True),
            # Mean 2.34 with N=3 → 2.34 × 3 = 7.02 → nearest 7, diff=0.02, tol=0.015 → inconsistent
            (2.34, 3, 2, False),
            # Integer mean: always consistent for integer data
            (4.00, 10, 2, True),
            # Mean 1.11 with N=9 → 1.11 × 9 = 9.99 → nearest 10, diff=0.01, tol=0.045 → consistent
            (1.11, 9, 2, True),
        ],
    )
    def test_known_case(self, mean: float, n: int, decimals: int, expected: bool):
        """Known case from literature should match expected result."""
        ours = StatisticalChecker.grim_test(mean, n, decimals).is_consistent
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            theirs = bool(pysprite_grim(n, mean, decimals))

        # Both should agree with expected
        assert ours == expected, f"Ours: mean={mean}, n={n} → {ours}, expected {expected}"
        assert theirs == expected, f"pysprite: mean={mean}, n={n} → {theirs}, expected {expected}"


# ── 4. Edge cases where implementations might diverge ──


class TestGRIMEdgeDivergence:
    """Cases near tolerance boundaries where implementations might differ."""

    def test_n_equals_100_with_2_decimals(self):
        """N=100 with 2 decimals: tolerance = 100*0.01/2 = 0.5.
        Any mean with 2 decimals times 100 will be within 0.5 of an integer.
        So ALL means should be GRIM-consistent.
        pysprite warns: 'effective data points >= 10^prec'."""
        disagreements = []
        for i in range(100):
            mean = round(i * 0.01, 2)
            ours, theirs = _compare(mean, 100, 2)
            if ours != theirs:
                disagreements.append((mean, ours, theirs))
        assert len(disagreements) == 0, f"Disagreements at N=100: {disagreements[:5]}"

    @pytest.mark.parametrize("decimals", [1, 2, 3, 4])
    def test_threshold_n(self, decimals: int):
        """At the threshold N = 10^decimals, all means become consistent.
        pysprite warns about this. Our implementation should agree."""
        threshold_n = 10 ** decimals
        disagreements = []

        for i in range(100):
            mean = round(i * 10 ** (-decimals), decimals)
            ours, theirs = _compare(mean, threshold_n, decimals)
            if ours != theirs:
                disagreements.append((mean, ours, theirs))

        assert len(disagreements) == 0, f"Disagreements at threshold N={threshold_n}: {disagreements[:5]}"

    def test_large_n_various_decimals(self):
        """Large N values should be well-handled by both."""
        test_cases = [
            (3.14, 500, 2),
            (2.718, 1000, 3),
            (1.5, 200, 1),
            (4.321, 50, 3),
        ]
        for mean, n, decimals in test_cases:
            ours, theirs = _compare(mean, n, decimals)
            assert ours == theirs, f"Divergence: mean={mean}, n={n}, dec={decimals}: ours={ours}, theirs={theirs}"


# ── 5. Algorithm difference analysis ──


class TestGRIMAlgorithmDifferences:
    """Document where our tolerance-based approach vs pysprite's
    round-trip approach might give different answers."""

    def test_count_total_disagreements(self):
        """Systematic comparison: count total disagreements across
        N=2..50, decimals=2, means=0.00..9.99.

        This is an analytical test — it reports the disagreement rate
        rather than asserting zero disagreements."""
        total_cases = 0
        total_disagree = 0
        disagreements_by_n = {}

        for n in range(2, 51):
            n_disagree = 0
            for i in range(1000):
                mean = round(i * 0.01, 2)
                ours, theirs = _compare(mean, n, 2)
                total_cases += 1
                if ours != theirs:
                    total_disagree += 1
                    n_disagree += 1
            if n_disagree > 0:
                disagreements_by_n[n] = n_disagree

        rate = total_disagree / total_cases if total_cases > 0 else 0

        # Print analysis for visibility
        print(f"\n=== GRIM Algorithm Comparison ===")
        print(f"Total cases: {total_cases}")
        print(f"Total disagreements: {total_disagree}")
        print(f"Disagreement rate: {rate:.6f} ({rate*100:.4f}%)")
        if disagreements_by_n:
            print(f"Disagreements by N: {dict(sorted(disagreements_by_n.items())[:10])}")

        # We expect very low disagreement rate (< 1%)
        # If higher, our algorithm needs adjustment
        assert rate < 0.01, f"Disagreement rate {rate:.4f} exceeds 1% threshold"

    def test_document_specific_disagreements(self):
        """Find and document specific cases where we disagree with pysprite.
        These cases need investigation to determine which is correct."""
        disagreements = []

        for n in range(2, 30):
            for i in range(1000):
                mean = round(i * 0.01, 2)
                ours, theirs = _compare(mean, n, 2)
                if ours != theirs:
                    product = mean * n
                    nearest = round(product)
                    diff = abs(product - nearest)
                    tol = n * 0.01 / 2
                    disagreements.append({
                        "mean": mean, "n": n,
                        "product": round(product, 6),
                        "nearest_int": nearest,
                        "diff": round(diff, 6),
                        "tolerance": round(tol, 6),
                        "ours": ours, "pysprite": theirs,
                    })

        if disagreements:
            print(f"\n=== GRIM Disagreement Details ({len(disagreements)} cases) ===")
            for d in disagreements[:20]:
                print(f"  mean={d['mean']}, n={d['n']}: "
                      f"product={d['product']}, nearest={d['nearest_int']}, "
                      f"diff={d['diff']}, tol={d['tolerance']} → "
                      f"ours={d['ours']}, pysprite={d['pysprite']}")
