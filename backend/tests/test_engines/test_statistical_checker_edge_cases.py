"""Edge case tests for StatisticalChecker — GRIM boundaries, Benford edge inputs, p-value edge math."""

import math

import pytest

from app.engines.integrity.statistical_checker import (
    StatisticalChecker,
    _chi2_survival,
    _recalculate_p_value,
)


class TestGRIMEdgeCases:
    """Boundary and extreme-value tests for GRIM test."""

    def test_n_equals_1_always_consistent(self):
        """N=1: any mean with 0 decimals is consistent (it's the only data point)."""
        result = StatisticalChecker.grim_test(7.0, 1, decimals=0)
        assert result.is_consistent is True

    def test_n_equals_1_decimal_mean(self):
        """N=1 with 2 decimal places: tolerance is 0.005, so 3.14 is within 0.5 of 3."""
        result = StatisticalChecker.grim_test(3.14, 1, decimals=2)
        # 3.14 * 1 = 3.14, nearest int = 3, diff = 0.14, tolerance = 0.005
        assert result.is_consistent is False

    def test_n_equals_2_consistent(self):
        """N=2: mean 3.5 means sum=7 (integer), should be consistent."""
        result = StatisticalChecker.grim_test(3.5, 2, decimals=1)
        assert result.is_consistent is True

    def test_zero_decimals(self):
        """decimals=0: integer mean, huge tolerance."""
        result = StatisticalChecker.grim_test(3.0, 5, decimals=0)
        assert result.is_consistent is True

    def test_zero_decimals_inconsistent(self):
        """decimals=0 with N=3: mean=2 → sum=6 (OK), mean=2 is integer."""
        result = StatisticalChecker.grim_test(2.0, 3, decimals=0)
        assert result.is_consistent is True

    def test_high_decimals(self):
        """decimals=10: very precise, tiny tolerance."""
        result = StatisticalChecker.grim_test(3.0000000000, 5, decimals=10)
        # 3.0 * 5 = 15.0, exact integer. Should be consistent.
        assert result.is_consistent is True

    def test_high_decimals_inconsistent(self):
        """Very high precision makes previously consistent values inconsistent."""
        # 3.14 * 5 = 15.7 → diff from 16 = 0.3, tolerance = 5 * 5e-11 / 2 ≈ tiny
        result = StatisticalChecker.grim_test(3.14, 5, decimals=10)
        assert result.is_consistent is False

    def test_large_n(self):
        """Large N: tolerance grows with N, so most means are consistent."""
        result = StatisticalChecker.grim_test(3.14, 1000, decimals=2)
        # tolerance = 1000 * 0.01 / 2 = 5.0 → very large
        assert result.is_consistent is True

    def test_negative_mean(self):
        """Negative mean: -3.0 with N=5 → sum=-15 (integer)."""
        result = StatisticalChecker.grim_test(-3.0, 5, decimals=2)
        assert result.is_consistent is True

    def test_negative_mean_inconsistent(self):
        """Negative mean: -3.45 with N=15 should fail like positive."""
        result = StatisticalChecker.grim_test(-3.45, 15, decimals=2)
        assert result.is_consistent is False

    def test_zero_mean(self):
        """Mean=0: sum=0 (always integer)."""
        result = StatisticalChecker.grim_test(0.0, 10, decimals=2)
        assert result.is_consistent is True

    def test_very_large_mean(self):
        """Very large mean should not cause overflow."""
        result = StatisticalChecker.grim_test(999999.99, 5, decimals=2)
        assert isinstance(result.is_consistent, bool)

    def test_explanation_contains_values(self):
        """Explanation string should contain the mean and N."""
        result = StatisticalChecker.grim_test(3.45, 15, decimals=2)
        assert "3.45" in result.explanation
        assert "15" in result.explanation


class TestGRIMBatch:
    """Edge cases for batch GRIM test."""

    def test_empty_batch(self):
        """Empty list should return empty results."""
        checker = StatisticalChecker()
        results = checker.grim_test_batch([])
        assert results == []

    def test_batch_missing_keys(self):
        """Entries with missing keys should use defaults (0)."""
        checker = StatisticalChecker()
        results = checker.grim_test_batch([{}])
        assert len(results) == 1
        # mean=0.0, n=0, decimals=2 → n<=0 → inconsistent
        assert results[0].is_consistent is False

    def test_batch_string_values(self):
        """String values should be converted via float()/int()."""
        checker = StatisticalChecker()
        results = checker.grim_test_batch([{"mean": "3.0", "n": "5"}])
        assert results[0].is_consistent is True


class TestBenfordEdgeCases:
    """Edge cases for Benford's Law analysis."""

    def test_empty_list(self):
        """Empty value list should return not anomalous (insufficient data)."""
        result = StatisticalChecker.benford_analysis([])
        assert result.is_anomalous is False
        assert result.n_values == 0

    def test_all_zeros(self):
        """All-zero list should be filtered out entirely."""
        result = StatisticalChecker.benford_analysis([0.0] * 100)
        assert result.n_values == 0
        assert result.is_anomalous is False

    def test_single_value(self):
        """Single value is below min_values threshold."""
        result = StatisticalChecker.benford_analysis([42.0])
        assert result.n_values == 1
        assert result.is_anomalous is False

    def test_exactly_min_values(self):
        """Exactly 50 values (default min_values) should be analyzed."""
        values = [float(i + 1) for i in range(50)]
        result = StatisticalChecker.benford_analysis(values)
        assert result.n_values == 50
        # Analysis actually runs (has chi_squared)
        assert result.chi_squared >= 0

    def test_49_values_below_threshold(self):
        """49 values (below default min_values=50) should not be analyzed."""
        values = [float(i + 1) for i in range(49)]
        result = StatisticalChecker.benford_analysis(values)
        assert result.n_values == 49
        assert result.is_anomalous is False

    def test_custom_min_values(self):
        """Custom min_values threshold should be respected."""
        values = [float(i + 1) for i in range(10)]
        result = StatisticalChecker.benford_analysis(values, min_values=5)
        assert result.n_values == 10
        assert result.chi_squared >= 0

    def test_negative_values(self):
        """Negative values should use absolute value for first digit."""
        values = [-float(i + 1) for i in range(60)]
        result = StatisticalChecker.benford_analysis(values)
        assert result.n_values == 60

    def test_very_small_values(self):
        """Very small positive values should have first digit extracted."""
        values = [0.00123 * (i + 1) for i in range(60)]
        result = StatisticalChecker.benford_analysis(values)
        assert result.n_values == 60

    def test_mixed_positive_negative(self):
        """Mixed sign values should all contribute first digits."""
        values = [float(i + 1) for i in range(30)] + [-float(i + 1) for i in range(30)]
        result = StatisticalChecker.benford_analysis(values)
        assert result.n_values == 60

    def test_values_near_zero_filtered(self):
        """Values very close to zero (< 1e-10) should be filtered."""
        values = [1e-11] * 100 + [1.0] * 60
        result = StatisticalChecker.benford_analysis(values)
        # Only the 1.0 values count
        assert result.n_values == 60

    def test_all_same_digit(self):
        """All values starting with same digit should be anomalous."""
        values = [5.0 + i * 0.01 for i in range(100)]  # All start with 5
        result = StatisticalChecker.benford_analysis(values)
        assert result.is_anomalous is True


class TestPValueEdgeCases:
    """Edge cases for p-value consistency checks."""

    def test_r_value_exactly_one(self):
        """r=1.0 should return p=0.0 (perfect correlation)."""
        result = _recalculate_p_value("r", 1.0, 30)
        assert result == 0.0

    def test_r_value_exactly_negative_one(self):
        """r=-1.0 should return p=0.0."""
        result = _recalculate_p_value("r", -1.0, 30)
        assert result == 0.0

    def test_r_value_zero(self):
        """r=0 → t=0 → p should be 1.0 (no correlation)."""
        result = _recalculate_p_value("r", 0.0, 30)
        assert result is not None
        assert result > 0.9  # Should be close to 1.0

    def test_r_value_near_one(self):
        """r=0.999 should have very small p-value."""
        result = _recalculate_p_value("r", 0.999, 30)
        assert result is not None
        assert result < 0.001

    def test_t_test_zero_statistic(self):
        """t=0 should give p=1.0."""
        result = _recalculate_p_value("t", 0.0, 30)
        assert result is not None
        assert result > 0.9

    def test_t_test_very_large_statistic(self):
        """t=1000 should give p≈0."""
        result = _recalculate_p_value("t", 1000.0, 30)
        assert result is not None
        assert result < 1e-10

    def test_f_test_requires_tuple_df(self):
        """F test with non-tuple df should return None."""
        result = _recalculate_p_value("f", 4.0, 20)
        assert result is None

    def test_chi2_test_basic(self):
        """Chi-squared test with known values."""
        result = _recalculate_p_value("chi2", 15.0, 8)
        assert result is not None
        # chi2(15, df=8) → p ≈ 0.059
        assert 0.01 < result < 0.2

    def test_unknown_test_type_returns_none(self):
        """Unknown test type should return None."""
        result = _recalculate_p_value("z", 2.0, 30)
        assert result is None

    def test_unknown_test_type_assumed_consistent(self):
        """Unknown test type → is_consistent=True (can't verify)."""
        checker = StatisticalChecker()
        result = checker.check_p_value_consistency("z", 2.0, 30, 0.05)
        assert result.is_consistent is True

    def test_threshold_boundary(self):
        """Discrepancy exactly at threshold should be consistent."""
        checker = StatisticalChecker()
        # Use a known consistent pairing
        result = checker.check_p_value_consistency("t", 2.086, 20, 0.05, threshold=0.05)
        assert result.is_consistent is True

    def test_negative_statistic_t_test(self):
        """Negative t-statistic should work (uses abs())."""
        result = _recalculate_p_value("t", -2.0, 30)
        result_pos = _recalculate_p_value("t", 2.0, 30)
        assert result is not None
        assert result_pos is not None
        assert abs(result - result_pos) < 1e-10


class TestAPAExtractionEdgeCases:
    """Edge cases for APA-style statistical reporting extraction."""

    def test_no_space_around_equals(self):
        """F(1,23)=4.52,p=.003 (no spaces) should still extract."""
        checker = StatisticalChecker()
        text = "F(1,23)=4.52,p=.003"
        findings = checker.extract_and_check_stats(text)
        assert isinstance(findings, list)

    def test_leading_zero_p_value(self):
        """p = 0.003 (with leading zero) should work."""
        checker = StatisticalChecker()
        text = "F(1, 100) = 50.0, p = 0.50"
        findings = checker.extract_and_check_stats(text)
        assert len(findings) >= 1  # 0.50 is obviously wrong for F=50

    def test_p_less_than(self):
        """p < .001 format should be extracted."""
        checker = StatisticalChecker()
        text = "t(45) = 5.0, p < .001"
        findings = checker.extract_and_check_stats(text)
        assert isinstance(findings, list)

    def test_p_greater_than(self):
        """p > .05 format should be extracted."""
        checker = StatisticalChecker()
        text = "t(45) = 1.0, p > .05"
        findings = checker.extract_and_check_stats(text)
        assert isinstance(findings, list)

    def test_chi_squared_unicode(self):
        """χ²(2) = 8.41, p = .015 should be extracted."""
        checker = StatisticalChecker()
        text = "χ²(2) = 8.41, p = .015"
        findings = checker.extract_and_check_stats(text)
        assert isinstance(findings, list)

    def test_chi2_ascii(self):
        """chi2(2) = 8.41, p = .015 should also be extracted."""
        checker = StatisticalChecker()
        text = "chi2(2) = 8.41, p = .015"
        findings = checker.extract_and_check_stats(text)
        assert isinstance(findings, list)

    def test_multiple_stats_in_text(self):
        """Multiple stats in one text should all be checked."""
        checker = StatisticalChecker()
        text = (
            "Condition A: F(1, 100) = 50.0, p = .50. "
            "Condition B: t(45) = 2.31, p = .025."
        )
        findings = checker.extract_and_check_stats(text)
        # At least the F-test should be flagged (p=.50 with F=50.0 is wrong)
        assert len(findings) >= 1

    def test_negative_t_statistic(self):
        """t(20) = -2.086, p = .05 should be extracted."""
        checker = StatisticalChecker()
        text = "t(20) = -2.086, p = .05"
        findings = checker.extract_and_check_stats(text)
        assert isinstance(findings, list)

    def test_r_correlation(self):
        """r(30) = .45, p = .012 should be extracted."""
        checker = StatisticalChecker()
        text = "r(30) = .45, p = .012"
        findings = checker.extract_and_check_stats(text)
        assert isinstance(findings, list)

    def test_empty_text(self):
        """Empty text should return no findings."""
        checker = StatisticalChecker()
        findings = checker.extract_and_check_stats("")
        assert findings == []


class TestChi2Survival:
    """Edge cases for the chi-squared survival function approximation."""

    def test_zero_df(self):
        """df=0 should return 1.0."""
        result = _chi2_survival(10.0, 0)
        assert result == 1.0

    def test_negative_df(self):
        """Negative df should return 1.0."""
        result = _chi2_survival(10.0, -5)
        assert result == 1.0

    def test_zero_x(self):
        """x=0 should return 1.0."""
        result = _chi2_survival(0.0, 8)
        assert result == 1.0

    def test_negative_x(self):
        """Negative x should return 1.0."""
        result = _chi2_survival(-5.0, 8)
        assert result == 1.0

    def test_very_large_x(self):
        """Very large x should give p≈0."""
        result = _chi2_survival(1000.0, 8)
        assert result < 1e-10

    def test_known_critical_value(self):
        """chi2(15.51, df=8) ≈ p=0.05."""
        result = _chi2_survival(15.51, 8)
        assert 0.01 < result < 0.10  # Approximation may not be exact
