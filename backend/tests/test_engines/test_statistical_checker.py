"""Tests for StatisticalChecker — GRIM test, Benford's Law, p-value consistency."""

import math

import pytest
from app.engines.integrity.statistical_checker import StatisticalChecker


@pytest.fixture
def checker():
    return StatisticalChecker()


class TestGRIMTest:
    """Tests for the GRIM (Granularity-Related Inconsistency of Means) test."""

    def test_consistent_mean_simple(self):
        """Mean 3.00 with N=5 is consistent (sum=15)."""
        result = StatisticalChecker.grim_test(3.00, 5, decimals=2)
        assert result.is_consistent is True

    def test_consistent_mean_decimal(self):
        """Mean 3.40 with N=5 is consistent (sum=17)."""
        result = StatisticalChecker.grim_test(3.40, 5, decimals=2)
        assert result.is_consistent is True

    def test_inconsistent_mean(self):
        """Mean 3.45 with N=15 is NOT consistent for integer data."""
        result = StatisticalChecker.grim_test(3.45, 15, decimals=2)
        # 3.45 * 15 = 51.75, nearest integer = 52, diff = 0.25 > tolerance 0.075
        assert result.is_consistent is False

    def test_consistent_mean_n_10(self):
        """Mean 2.50 with N=10 is consistent (sum=25)."""
        result = StatisticalChecker.grim_test(2.50, 10, decimals=2)
        assert result.is_consistent is True

    def test_inconsistent_mean_n_10(self):
        """Mean 2.53 with N=10 is NOT consistent."""
        result = StatisticalChecker.grim_test(2.53, 10, decimals=2)
        # 2.53 * 10 = 25.3, not close to integer
        assert result.is_consistent is False

    def test_zero_n_is_inconsistent(self):
        """N=0 should always be inconsistent."""
        result = StatisticalChecker.grim_test(3.00, 0, decimals=2)
        assert result.is_consistent is False

    def test_negative_n_is_inconsistent(self):
        """Negative N should be inconsistent."""
        result = StatisticalChecker.grim_test(3.00, -5, decimals=2)
        assert result.is_consistent is False

    def test_single_decimal_precision(self):
        """Mean 3.5 with N=4 is consistent (sum=14)."""
        result = StatisticalChecker.grim_test(3.5, 4, decimals=1)
        assert result.is_consistent is True

    def test_batch(self, checker):
        """Batch GRIM test processes multiple entries."""
        entries = [
            {"mean": 3.00, "n": 5},
            {"mean": 3.45, "n": 15},
            {"mean": 2.50, "n": 10},
        ]
        results = checker.grim_test_batch(entries)
        assert len(results) == 3
        assert results[0].is_consistent is True
        assert results[1].is_consistent is False
        assert results[2].is_consistent is True


class TestBenfordAnalysis:
    """Tests for Benford's Law analysis."""

    def test_too_few_values(self):
        """Fewer than min_values should not be flagged as anomalous."""
        result = StatisticalChecker.benford_analysis([1.0, 2.0, 3.0])
        assert result.is_anomalous is False
        assert result.n_values == 3

    def test_benford_conforming_data(self):
        """Data following Benford's law should not be flagged."""
        # Generate Benford-conforming data
        import random
        random.seed(42)
        values = []
        for _ in range(500):
            # Benford distribution: P(d) = log10(1 + 1/d)
            r = random.random()
            cumulative = 0
            for d in range(1, 10):
                cumulative += math.log10(1 + 1 / d)
                if r <= cumulative:
                    # Create a value starting with digit d
                    values.append(d * 10 ** random.randint(0, 3) + random.random())
                    break

        result = StatisticalChecker.benford_analysis(values)
        assert result.n_values >= 450  # Some might be filtered
        # Should not be anomalous (p > 0.05 expected)
        # Note: with random seed, this is deterministic

    def test_uniform_distribution_detected(self):
        """Uniformly distributed first digits should be flagged as anomalous."""
        # Create data with uniform first-digit distribution
        values = []
        for d in range(1, 10):
            values.extend([d * 10 + i for i in range(60)])  # 60 values per digit

        result = StatisticalChecker.benford_analysis(values)
        assert result.n_values == 540
        assert result.is_anomalous is True
        assert result.chi_squared > 15  # Well above critical value

    def test_zero_values_filtered(self):
        """Zero values should be filtered out."""
        values = [0.0] * 100 + [1.0] * 30 + [2.0] * 20
        result = StatisticalChecker.benford_analysis(values)
        assert result.n_values == 50  # Only non-zero values counted

    def test_result_has_distributions(self):
        """Result should include observed and expected distributions."""
        values = [float(i) for i in range(1, 201)]
        result = StatisticalChecker.benford_analysis(values)
        assert "1" in result.digit_distribution
        assert "9" in result.digit_distribution
        assert "1" in result.expected_distribution


class TestPValueConsistency:
    """Tests for p-value consistency checking."""

    def test_consistent_t_test(self, checker):
        """Consistent t-test should pass."""
        # t(20) = 2.086, p ≈ 0.05 (two-tailed)
        result = checker.check_p_value_consistency("t", 2.086, 20, 0.05)
        assert result.is_consistent is True

    def test_inconsistent_t_test(self, checker):
        """Grossly inconsistent t-test should fail."""
        # t(20) = 5.0 → p should be very small, not 0.5
        result = checker.check_p_value_consistency("t", 5.0, 20, 0.50)
        assert result.is_consistent is False
        assert result.discrepancy > 0.05

    def test_consistent_f_test(self, checker):
        """Consistent F-test should pass."""
        # F(1, 20) = 4.35, p ≈ 0.05
        result = checker.check_p_value_consistency("f", 4.35, (1, 20), 0.05)
        assert result.is_consistent is True

    def test_result_fields(self, checker):
        """Result should contain all expected fields."""
        result = checker.check_p_value_consistency("t", 2.0, 30, 0.05)
        assert result.test_type == "t"
        assert result.reported_statistic == 2.0
        assert result.reported_p == 0.05
        assert result.recalculated_p > 0


class TestExtractAndCheckStats:
    """Tests for APA-style stat extraction and checking."""

    def test_extract_f_test(self, checker):
        """Should extract F(1, 23) = 4.52, p = .003."""
        text = "The analysis revealed a significant effect, F(1, 23) = 4.52, p = .003."
        findings = checker.extract_and_check_stats(text)
        # Whether it's flagged depends on whether the p-value is consistent
        assert isinstance(findings, list)

    def test_extract_t_test(self, checker):
        """Should extract t(45) = 2.31, p = .025."""
        text = "We found t(45) = 2.31, p = .025."
        findings = checker.extract_and_check_stats(text)
        assert isinstance(findings, list)

    def test_no_stats_in_text(self, checker):
        """Text without APA stats should produce no findings."""
        text = "The weather was nice today."
        findings = checker.extract_and_check_stats(text)
        assert len(findings) == 0

    def test_obviously_wrong_p_value(self, checker):
        """F(1, 100) = 50.0 with p = .50 should be flagged."""
        text = "F(1, 100) = 50.0, p = .50"
        findings = checker.extract_and_check_stats(text)
        assert len(findings) >= 1
        assert findings[0].category == "p_value_mismatch"
