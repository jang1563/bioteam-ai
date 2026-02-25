"""Benchmark: GRIMMER cross-validation — SD and percentage consistency tests.

Extends GRIM to standard deviations and percentages per Heathers (2019).

SD test: SD² × (n-1) should produce an achievable sum of squared deviations.
Percent test: percentage × n / 100 should yield an integer count.

Tests include:
- Known cases with manually verified expected results
- Systematic sweeps for internal consistency
- Edge cases and boundary conditions
- Text extraction from realistic paragraphs
"""

import math

import pytest

from app.engines.integrity.statistical_checker import StatisticalChecker


# ── Helpers ──


def _is_valid_ssd(sd: float, n: int, decimals: int) -> bool:
    """Reference implementation: check if any integer SSD is achievable.

    For integer data with n items, SSD = sum of (x_i - mean)² must be
    an integer. Given reported SD with `decimals` decimal places, the
    true SD could be anywhere in [sd - g/2, sd + g/2] where g = 10^(-decimals).
    """
    # Special cases matching the implementation
    if n <= 1:
        return False
    if sd < 0:
        return False
    if sd == 0.0:
        return True  # All values identical → SSD = 0 (integer)

    g = 10 ** (-decimals)
    sd_low = sd - g / 2
    sd_high = sd + g / 2
    ssd_low = max(0.0, sd_low ** 2 * (n - 1))
    ssd_high = sd_high ** 2 * (n - 1)
    return math.ceil(ssd_low - 1e-9) <= math.floor(ssd_high + 1e-9)


def _is_valid_pct(pct: float, n: int, decimals: int) -> bool:
    """Reference implementation: check if percentage × n / 100 ≈ integer."""
    product = pct * n / 100
    g = 10 ** (-decimals)
    tolerance = n * g / 200
    nearest = round(product)
    return abs(product - nearest) <= tolerance + 1e-10


# ══════════════════════════════════════════════════════════════════
# 1. GRIMMER SD — Known Cases
# ══════════════════════════════════════════════════════════════════


class TestGRIMMERSDKnownCases:
    """Manually verified SD test cases."""

    @pytest.mark.parametrize(
        "sd, n, decimals, expected",
        [
            # SD = 1.00, N = 10: SSD = 1² × 9 = 9.0 → integer → consistent
            (1.00, 10, 2, True),
            # SD = 0.00, N = 5: all identical → always consistent
            (0.00, 5, 2, True),
            # SD = 2.00, N = 2: SSD = 4 × 1 = 4.0 → integer → consistent
            (2.00, 2, 2, True),
            # SD = 1.41, N = 2: SSD = 1.41² × 1 = 1.9881. Range [1.96, 2.0164] → contains 2 → consistent
            (1.41, 2, 2, True),
            # SD = 1.42, N = 2: SSD = 1.42² × 1 = 2.0164. Range [2.0022, 2.0306] → contains none? → check
            # Actually range = [(1.415)²×1, (1.425)²×1] = [2.002225, 2.030625] → contains none (nearest 2 is below) → inconsistent
            (1.42, 2, 2, False),
            # SD = 0.50, N = 5: SSD = 0.25 × 4 = 1.0 → integer → consistent
            (0.50, 5, 2, True),
            # SD = 0.71, N = 3: SSD = 0.5041 × 2 = 1.0082. Range [0.4356, 0.5776]×2=[0.8712, 1.1552] → 1 in range → consistent
            (0.71, 3, 2, True),
            # SD = 3.00, N = 10: SSD = 9 × 9 = 81.0 → integer → consistent
            (3.00, 10, 2, True),
            # Negative SD → always inconsistent
            (-1.0, 10, 2, False),
            # N = 1 → always inconsistent (can't compute SD with 1 sample)
            (1.00, 1, 2, False),
        ],
    )
    def test_known_sd_case(self, sd: float, n: int, decimals: int, expected: bool):
        result = StatisticalChecker.grimmer_sd_test(sd, n, decimals)
        assert result.is_consistent == expected, (
            f"SD={sd}, N={n}: expected {expected}, got {result.is_consistent}. "
            f"{result.explanation}"
        )


# ══════════════════════════════════════════════════════════════════
# 2. GRIMMER SD — Systematic Sweep
# ══════════════════════════════════════════════════════════════════


class TestGRIMMERSDSystematicSweep:
    """Sweep N=2-20, SD 0.00-5.00, verify our result matches reference."""

    @pytest.mark.parametrize("n", range(2, 21))
    def test_sweep_n(self, n: int):
        decimals = 2
        disagreements = []

        for i in range(501):  # 0.00 to 5.00
            sd = round(i * 0.01, 2)
            ours = StatisticalChecker.grimmer_sd_test(sd, n, decimals).is_consistent
            ref = _is_valid_ssd(sd, n, decimals)
            if ours != ref:
                disagreements.append((sd, n, ours, ref))

        if disagreements:
            sample = disagreements[:5]
            pytest.fail(
                f"N={n}: {len(disagreements)} disagreements with reference. "
                f"First 5: {sample}"
            )


# ══════════════════════════════════════════════════════════════════
# 3. GRIMMER SD — Edge Cases
# ══════════════════════════════════════════════════════════════════


class TestGRIMMERSDEdgeCases:
    """Boundary conditions for GRIMMER SD test."""

    def test_sd_zero_always_consistent(self):
        """SD = 0 means all values identical."""
        for n in [2, 5, 10, 100]:
            result = StatisticalChecker.grimmer_sd_test(0.0, n, 2)
            assert result.is_consistent is True

    def test_n_equals_1_always_inconsistent(self):
        """Can't compute SD with one sample."""
        for sd in [0.5, 1.0, 2.0]:
            result = StatisticalChecker.grimmer_sd_test(sd, 1, 2)
            assert result.is_consistent is False

    def test_negative_sd_inconsistent(self):
        """SD cannot be negative."""
        result = StatisticalChecker.grimmer_sd_test(-0.5, 10, 2)
        assert result.is_consistent is False

    def test_large_n_relaxes_constraint(self):
        """With large N, more SD values become possible."""
        # N=100: the SSD range becomes very wide → most SDs are consistent
        consistent_count = 0
        for i in range(100):
            sd = round(i * 0.05, 2)
            if StatisticalChecker.grimmer_sd_test(sd, 100, 2).is_consistent:
                consistent_count += 1
        # Most should be consistent for large N
        assert consistent_count >= 90, f"Only {consistent_count}/100 consistent at N=100"

    @pytest.mark.parametrize("decimals", [1, 2, 3])
    def test_integer_sd_always_consistent(self, decimals: int):
        """Integer SD × integer (n-1) = integer SSD → always consistent."""
        for sd in [1, 2, 3]:
            for n in [2, 5, 10]:
                result = StatisticalChecker.grimmer_sd_test(float(sd), n, decimals)
                assert result.is_consistent is True, f"SD={sd}, N={n}, dec={decimals}"


# ══════════════════════════════════════════════════════════════════
# 4. GRIMMER Percentage — Known Cases
# ══════════════════════════════════════════════════════════════════


class TestGRIMMERPercentKnownCases:
    """Manually verified percentage test cases."""

    @pytest.mark.parametrize(
        "pct, n, decimals, expected",
        [
            # 50.0% × 10 / 100 = 5.0 → integer → consistent
            (50.0, 10, 1, True),
            # 33.3% × 3 / 100 = 0.999 → tolerance = 3×0.1/200 = 0.0015 → |0.999-1|=0.001 ≤ 0.0015 → consistent
            (33.3, 3, 1, True),
            # 33.4% × 3 / 100 = 1.002 → |1.002-1| = 0.002 > 0.0015 → inconsistent
            (33.4, 3, 1, False),
            # 25.0% × 100 / 100 = 25.0 → integer → consistent
            (25.0, 100, 1, True),
            # 10.0% × 10 / 100 = 1.0 → integer → consistent
            (10.0, 10, 1, True),
            # 15.0% × 10 / 100 = 1.5 → tolerance = 10×0.1/200 = 0.005 → |1.5-2|=0.5 > 0.005 → inconsistent
            (15.0, 10, 1, False),
            # 75.00% × 4 / 100 = 3.0 → integer → consistent
            (75.00, 4, 2, True),
            # 0.0% × 10 / 100 = 0.0 → integer → consistent
            (0.0, 10, 1, True),
            # 100.0% × 10 / 100 = 10.0 → integer → consistent
            (100.0, 10, 1, True),
            # N=0 → always inconsistent
            (50.0, 0, 1, False),
        ],
    )
    def test_known_percent_case(
        self, pct: float, n: int, decimals: int, expected: bool,
    ):
        result = StatisticalChecker.grimmer_percent_test(pct, n, decimals)
        assert result.is_consistent == expected, (
            f"{pct}%, N={n}: expected {expected}, got {result.is_consistent}. "
            f"{result.explanation}"
        )


# ══════════════════════════════════════════════════════════════════
# 5. GRIMMER Percentage — Systematic Sweep
# ══════════════════════════════════════════════════════════════════


class TestGRIMMERPercentSystematicSweep:
    """Sweep N=2-20, percentages 0.0-100.0, verify vs reference."""

    @pytest.mark.parametrize("n", range(2, 21))
    def test_sweep_n(self, n: int):
        decimals = 1
        disagreements = []

        for i in range(1001):  # 0.0 to 100.0
            pct = round(i * 0.1, 1)
            ours = StatisticalChecker.grimmer_percent_test(pct, n, decimals).is_consistent
            ref = _is_valid_pct(pct, n, decimals)
            if ours != ref:
                disagreements.append((pct, n, ours, ref))

        if disagreements:
            sample = disagreements[:5]
            pytest.fail(
                f"N={n}: {len(disagreements)} disagreements. First 5: {sample}"
            )


# ══════════════════════════════════════════════════════════════════
# 6. GRIMMER Percentage — Edge Cases
# ══════════════════════════════════════════════════════════════════


class TestGRIMMERPercentEdgeCases:
    """Boundary conditions for percentage test."""

    def test_zero_percent_always_consistent(self):
        """0% of N always = 0 items."""
        for n in [1, 5, 10, 100]:
            result = StatisticalChecker.grimmer_percent_test(0.0, n, 1)
            assert result.is_consistent is True

    def test_hundred_percent_always_consistent(self):
        """100% of N always = N items."""
        for n in [1, 5, 10, 100]:
            result = StatisticalChecker.grimmer_percent_test(100.0, n, 1)
            assert result.is_consistent is True

    def test_negative_n_inconsistent(self):
        result = StatisticalChecker.grimmer_percent_test(50.0, -1, 1)
        assert result.is_consistent is False

    def test_large_n_mostly_consistent(self):
        """With N=1000 and 1 decimal, all percentages are achievable.

        count = pct × 1000/100 = pct × 10. For 1-decimal pct, this is
        always an integer. tolerance = 1000 × 0.1 / 200 = 0.5.
        """
        inconsistent = []
        for i in range(1001):
            pct = round(i * 0.1, 1)
            if not StatisticalChecker.grimmer_percent_test(pct, 1000, 1).is_consistent:
                inconsistent.append(pct)
        assert len(inconsistent) == 0, f"Unexpected inconsistencies at N=1000: {inconsistent[:5]}"


# ══════════════════════════════════════════════════════════════════
# 7. scrutiny R package pigs5 dataset
# ══════════════════════════════════════════════════════════════════


class TestGRIMMERScrutinyPigs5:
    """Validate against scrutiny R package pigs5 dataset (SD test only).

    Source: https://github.com/lhdjung/scrutiny (pigs5)
    12 rows of (mean, sd, n) with decimals=2.

    NOTE: scrutiny's grimmer_test() checks GRIM of the mean AND SD
    together, but our grimmer_sd_test() only checks SD. With large n
    (30-38) and 2-decimal SDs, SSD ranges are wide so most SDs will
    be consistent. This test validates internal consistency of our
    SSD range algorithm against our own reference implementation.
    """

    # (mean, sd, n)
    PIGS5_DATA = [
        (7.22, 5.30, 38),
        (4.74, 6.55, 31),
        (5.23, 2.55, 35),
        (2.57, 2.57, 30),
        (6.77, 2.18, 33),
        (2.68, 2.59, 34),
        (7.01, 6.68, 35),
        (7.38, 3.65, 32),
        (3.14, 5.32, 33),
        (6.89, 4.18, 37),
        (5.00, 2.18, 31),
        (0.24, 6.43, 34),
    ]

    @pytest.mark.parametrize(
        "mean, sd, n",
        PIGS5_DATA,
        ids=[f"x={m}_sd={s}_n={n}" for m, s, n in PIGS5_DATA],
    )
    def test_pigs5_internal_consistency(self, mean: float, sd: float, n: int):
        """Our grimmer_sd_test should agree with reference _is_valid_ssd."""
        ours = StatisticalChecker.grimmer_sd_test(sd, n, 2).is_consistent
        ref = _is_valid_ssd(sd, n, 2)
        assert ours == ref, (
            f"pigs5: sd={sd}, n={n}: our result={ours}, reference={ref}"
        )

    def test_pigs5_large_n_relaxation(self):
        """With n=30-38, most 2-decimal SDs should be consistent."""
        consistent_count = sum(
            1 for _, sd, n in self.PIGS5_DATA
            if StatisticalChecker.grimmer_sd_test(sd, n, 2).is_consistent
        )
        # Large n makes SSD ranges wide; expect most/all consistent
        assert consistent_count >= 10, (
            f"Expected ≥10 of 12 consistent with large n, got {consistent_count}"
        )


# ══════════════════════════════════════════════════════════════════
# 8. GRIMMER Text Extraction
# ══════════════════════════════════════════════════════════════════


class TestGRIMMERTextExtraction:
    """Test regex extraction and checking from realistic text."""

    def test_sd_with_n_detected(self):
        """SD = X, N = Y pattern should be extracted and checked."""
        text = "The sample showed M = 4.56, SD = 1.50, N = 10 on the Likert scale."
        checker = StatisticalChecker()
        findings = checker.extract_and_check_grimmer(text)
        # SD=1.50, N=10 → SSD = 2.25 × 9 = 20.25. Range [20.1152, 20.3852] → no int → inconsistent
        assert len(findings) >= 1
        assert findings[0].category == "grimmer_sd_failure"
        assert findings[0].grimmer_sd_result is not None

    def test_sd_consistent_no_finding(self):
        """Consistent SD should produce NO findings."""
        text = "M = 3.00, SD = 1.00, N = 10 on the anxiety scale."
        checker = StatisticalChecker()
        findings = checker.extract_and_check_grimmer(text)
        sd_findings = [f for f in findings if f.category == "grimmer_sd_failure"]
        assert len(sd_findings) == 0

    def test_percentage_with_n_detected(self):
        """Percentage pattern with N should be extracted."""
        text = "33.4% of participants (N = 3) reported improvement."
        checker = StatisticalChecker()
        findings = checker.extract_and_check_grimmer(text)
        pct_findings = [f for f in findings if f.category == "grimmer_percent_failure"]
        # 33.4% × 3 / 100 = 1.002, tolerance = 0.0015, diff = 0.002 > 0.0015 → inconsistent
        assert len(pct_findings) >= 1

    def test_percentage_consistent_no_finding(self):
        """Consistent percentage should produce NO findings."""
        text = "50.0% of participants (N = 10) completed the study."
        checker = StatisticalChecker()
        findings = checker.extract_and_check_grimmer(text)
        pct_findings = [f for f in findings if f.category == "grimmer_percent_failure"]
        assert len(pct_findings) == 0

    def test_sd_without_n_skipped(self):
        """SD without sample size should not be checked."""
        text = "The overall SD = 1.50 across all conditions."
        checker = StatisticalChecker()
        findings = checker.extract_and_check_grimmer(text)
        assert len(findings) == 0

    def test_multiple_stats_in_paragraph(self):
        """Multiple SD reports in one paragraph."""
        text = (
            "Group A: M = 3.20, SD = 1.00, N = 10. "
            "Group B: M = 4.50, SD = 1.50, N = 10. "
        )
        checker = StatisticalChecker()
        findings = checker.extract_and_check_grimmer(text)
        # Group A: SD=1.00, N=10 → SSD=9.0 → consistent (no finding)
        # Group B: SD=1.50, N=10 → SSD=20.25 → inconsistent (finding)
        sd_findings = [f for f in findings if f.category == "grimmer_sd_failure"]
        assert len(sd_findings) == 1  # Only Group B flagged
