"""Benchmark: statcheck comparison — our StatisticalChecker vs statcheck Python.

Feeds identical APA-style text to both systems and compares:
1. Detection rate — do both find the same statistical reports?
2. P-value recalculation — do both flag the same inconsistencies?
3. Regex coverage — which patterns does each system handle?

Ground truth: manually verified test cases with known correct/incorrect p-values.

NOTE: statcheck Python package (v0.0.7) has numpy compatibility issues with
modern numpy/scipy. Tests that call statcheck are wrapped with try/except
and will skip gracefully if statcheck crashes.
"""

import warnings

import pandas as pd
import pytest

from app.engines.integrity.statistical_checker import (
    StatisticalChecker,
    _APA_STAT_RE,
    _Z_STAT_RE,
    _recalculate_p_value,
)


# ── Ground truth test cases ──
# Each case: (text, expected extraction, expected error, description)
# "is_error=True" means the reported p-value does NOT match the test statistic.

GROUND_TRUTH_CASES = [
    # === Correct p-values (no errors) ===
    {
        "id": "t_correct_1",
        "text": "The difference was significant, t(28) = 2.05, p = .050.",
        "test_type": "t",
        "statistic": 2.05,
        "df": 28,
        "reported_p": 0.05,
        "is_error": False,
        "description": "Correct t-test: t(28)=2.05, p=.050 ≈ .0499",
    },
    {
        "id": "t_correct_2",
        "text": "Results showed t(100) = 1.98, p = .050.",
        "test_type": "t",
        "statistic": 1.98,
        "df": 100,
        "reported_p": 0.05,
        "is_error": False,
        "description": "Correct t-test: t(100)=1.98, p=.050",
    },
    {
        "id": "F_correct_1",
        "text": "The ANOVA revealed F(1, 58) = 4.00, p = .050.",
        "test_type": "F",
        "statistic": 4.00,
        "df": (1, 58),
        "reported_p": 0.05,
        "is_error": False,
        "description": "Correct F-test: F(1,58)=4.00, p≈.0503",
    },
    {
        "id": "F_correct_2",
        "text": "We found F(2, 97) = 3.09, p = .050.",
        "test_type": "F",
        "statistic": 3.09,
        "df": (2, 97),
        "reported_p": 0.05,
        "is_error": False,
        "description": "Correct F-test: F(2,97)=3.09, p≈.0502",
    },
    {
        "id": "r_correct_1",
        "text": "The correlation was r(30) = .45, p = .010.",
        "test_type": "r",
        "statistic": 0.45,
        "df": 30,
        "reported_p": 0.01,
        "is_error": False,
        "description": "Correct correlation: r(30)=.45, p≈.0099",
    },
    # === Incorrect p-values (errors) ===
    {
        "id": "t_error_1",
        "text": "The result was t(20) = 2.09, p = .500.",
        "test_type": "t",
        "statistic": 2.09,
        "df": 20,
        "reported_p": 0.5,
        "is_error": True,
        "description": "WRONG: t(20)=2.09 → p≈.049, reported .500",
    },
    {
        "id": "t_error_2",
        "text": "We observed t(50) = 0.50, p = .001.",
        "test_type": "t",
        "statistic": 0.50,
        "df": 50,
        "reported_p": 0.001,
        "is_error": True,
        "description": "WRONG: t(50)=0.50 → p≈.619, reported .001",
    },
    {
        "id": "F_error_1",
        "text": "The ANOVA showed F(1, 100) = 50.0, p = .500.",
        "test_type": "F",
        "statistic": 50.0,
        "df": (1, 100),
        "reported_p": 0.5,
        "is_error": True,
        "description": "WRONG: F(1,100)=50 → p≈0.000, reported .500",
    },
    {
        "id": "F_error_2",
        "text": "Results indicated F(3, 200) = 1.00, p = .001.",
        "test_type": "F",
        "statistic": 1.00,
        "df": (3, 200),
        "reported_p": 0.001,
        "is_error": True,
        "description": "WRONG: F(3,200)=1.00 → p≈.394, reported .001",
    },
    {
        "id": "r_error_1",
        "text": "The correlation was r(50) = .10, p = .001.",
        "test_type": "r",
        "statistic": 0.10,
        "df": 50,
        "reported_p": 0.001,
        "is_error": True,
        "description": "WRONG: r(50)=.10 → p≈.482, reported .001",
    },
    # === Borderline cases ===
    {
        "id": "t_borderline_1",
        "text": "The test showed t(30) = 2.04, p = .050.",
        "test_type": "t",
        "statistic": 2.04,
        "df": 30,
        "reported_p": 0.05,
        "is_error": False,
        "description": "Borderline: t(30)=2.04, p≈.0503 — within rounding",
    },
    # === Decision errors (p-value wrong side of .05) ===
    {
        "id": "decision_error_1",
        "text": "The result was significant, t(25) = 1.50, p = .040.",
        "test_type": "t",
        "statistic": 1.50,
        "df": 25,
        "reported_p": 0.04,
        "is_error": True,
        "description": "Decision error: t(25)=1.50 → p≈.146, reported .040",
    },
    {
        "id": "decision_error_2",
        "text": "The effect was non-significant, F(1, 50) = 8.00, p = .100.",
        "test_type": "F",
        "statistic": 8.00,
        "df": (1, 50),
        "reported_p": 0.1,
        "is_error": True,
        "description": "Decision error: F(1,50)=8.00 → p≈.007, reported .100",
    },
    # === Extended: chi-square (Nuijten et al. 2016 patterns) ===
    {
        "id": "chi2_correct_1",
        "text": "The test was significant, χ²(2) = 8.41, p = .015.",
        "test_type": "chi2",
        "statistic": 8.41,
        "df": 2,
        "reported_p": 0.015,
        "is_error": False,
        "description": "Correct chi2: χ²(2)=8.41, p≈.0149",
    },
    {
        "id": "chi2_correct_2",
        "text": "We found χ²(4) = 9.49, p = .050.",
        "test_type": "chi2",
        "statistic": 9.49,
        "df": 4,
        "reported_p": 0.05,
        "is_error": False,
        "description": "Correct chi2: χ²(4)=9.49, p≈.050",
    },
    {
        "id": "chi2_error_1",
        "text": "The result was χ²(1) = 0.50, p = .001.",
        "test_type": "chi2",
        "statistic": 0.50,
        "df": 1,
        "reported_p": 0.001,
        "is_error": True,
        "description": "WRONG: χ²(1)=0.50 → p≈.480, reported .001",
    },
    {
        "id": "chi2_error_2",
        "text": "Analysis showed χ²(3) = 25.0, p = .500.",
        "test_type": "chi2",
        "statistic": 25.0,
        "df": 3,
        "reported_p": 0.5,
        "is_error": True,
        "description": "WRONG: χ²(3)=25.0 → p≈.000, reported .500",
    },
    # === Extended: Z-tests ===
    {
        "id": "z_correct_1",
        "text": "The Z-test was significant, Z = 1.96, p = .050.",
        "test_type": "z",
        "statistic": 1.96,
        "df": 0,
        "reported_p": 0.05,
        "is_error": False,
        "description": "Correct Z: Z=1.96, p≈.050",
    },
    {
        "id": "z_correct_2",
        "text": "We observed Z = 2.58, p = .010.",
        "test_type": "z",
        "statistic": 2.58,
        "df": 0,
        "reported_p": 0.01,
        "is_error": False,
        "description": "Correct Z: Z=2.58, p≈.010",
    },
    {
        "id": "z_error_1",
        "text": "The proportion test showed Z = 0.50, p = .001.",
        "test_type": "z",
        "statistic": 0.50,
        "df": 0,
        "reported_p": 0.001,
        "is_error": True,
        "description": "WRONG: Z=0.50 → p≈.617, reported .001",
    },
    # === Extended: Q-tests (heterogeneity) ===
    {
        "id": "q_correct_1",
        "text": "Heterogeneity was significant, Q(5) = 12.3, p = .031.",
        "test_type": "q",
        "statistic": 12.3,
        "df": 5,
        "reported_p": 0.031,
        "is_error": False,
        "description": "Correct Q: Q(5)=12.3, p≈.031",
    },
    {
        "id": "q_error_1",
        "text": "The Q-test showed Q(10) = 5.0, p = .001.",
        "test_type": "q",
        "statistic": 5.0,
        "df": 10,
        "reported_p": 0.001,
        "is_error": True,
        "description": "WRONG: Q(10)=5.0 → p≈.891, reported .001",
    },
    # === Extended: borderline correct ===
    {
        "id": "t_borderline_2",
        "text": "Results showed t(40) = 2.02, p = .050.",
        "test_type": "t",
        "statistic": 2.02,
        "df": 40,
        "reported_p": 0.05,
        "is_error": False,
        "description": "Borderline: t(40)=2.02, p≈.050",
    },
    {
        "id": "t_borderline_3",
        "text": "The comparison was t(10) = 2.23, p = .050.",
        "test_type": "t",
        "statistic": 2.23,
        "df": 10,
        "reported_p": 0.05,
        "is_error": False,
        "description": "Borderline: t(10)=2.23, p≈.050",
    },
    {
        "id": "F_borderline_1",
        "text": "ANOVA showed F(2, 60) = 3.15, p = .050.",
        "test_type": "F",
        "statistic": 3.15,
        "df": (2, 60),
        "reported_p": 0.05,
        "is_error": False,
        "description": "Borderline: F(2,60)=3.15, p≈.050",
    },
    # === Extended: more errors ===
    {
        "id": "t_error_3",
        "text": "The effect was t(15) = 3.00, p = .500.",
        "test_type": "t",
        "statistic": 3.00,
        "df": 15,
        "reported_p": 0.5,
        "is_error": True,
        "description": "WRONG: t(15)=3.00 → p≈.009, reported .500",
    },
    {
        "id": "r_error_2",
        "text": "The correlation was r(20) = .80, p = .500.",
        "test_type": "r",
        "statistic": 0.80,
        "df": 20,
        "reported_p": 0.5,
        "is_error": True,
        "description": "WRONG: r(20)=.80 → p≈.000, reported .500",
    },
    # === Extended: more correct ===
    {
        "id": "F_correct_3",
        "text": "We found F(1, 30) = 4.17, p = .050.",
        "test_type": "F",
        "statistic": 4.17,
        "df": (1, 30),
        "reported_p": 0.05,
        "is_error": False,
        "description": "Correct F: F(1,30)=4.17, p≈.050",
    },
    {
        "id": "r_correct_2",
        "text": "The correlation was r(100) = .20, p = .045.",
        "test_type": "r",
        "statistic": 0.20,
        "df": 100,
        "reported_p": 0.045,
        "is_error": False,
        "description": "Correct correlation: r(100)=.20, p≈.044",
    },
    # === Extended: negative t-statistic ===
    {
        "id": "t_negative_1",
        "text": "The decrease was t(25) = -2.06, p = .050.",
        "test_type": "t",
        "statistic": -2.06,
        "df": 25,
        "reported_p": 0.05,
        "is_error": False,
        "description": "Correct negative t: t(25)=-2.06, p≈.050",
    },
]


# ── Helpers ──


def _run_statcheck_safe(text: str) -> pd.DataFrame | None:
    """Run statcheck on text, return results DataFrame or None if it crashes."""
    try:
        from statcheck.checkdir import statcheck as run_statcheck
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res, _ = run_statcheck([text], messages=False)
        return res
    except Exception:
        return None


# ── Tests: Our System Performance ──


class TestOurDetectionAccuracy:
    """Test our system against ground truth cases."""

    @pytest.mark.parametrize("case", GROUND_TRUTH_CASES, ids=lambda c: c["id"])
    def test_detection(self, case):
        """Our system should correctly detect (or not) p-value errors."""
        checker = StatisticalChecker()
        findings = checker.extract_and_check_stats(case["text"])

        if case["is_error"]:
            assert len(findings) >= 1, (
                f"Case {case['id']}: Should detect p-value error. "
                f"Text: {case['text']}"
            )
        else:
            flagged = [f for f in findings if not f.p_value_result.is_consistent]
            assert len(flagged) == 0, (
                f"Case {case['id']}: False positive! Flagged correct p-value. "
                f"Text: {case['text']}"
            )


class TestOurPValueRecalculation:
    """Verify our recalculated p-values against scipy ground truth."""

    @pytest.mark.parametrize(
        "test_type, statistic, df, expected_p_approx",
        [
            ("t", 2.05, 28, 0.0499),
            ("t", 1.98, 100, 0.0504),
            ("t", 2.09, 20, 0.0494),
            ("t", 0.50, 50, 0.619),
            ("f", 4.00, (1, 58), 0.0503),
            ("f", 50.0, (1, 100), 0.0000),
            ("f", 1.00, (3, 200), 0.394),
            ("r", 0.45, 30, 0.0099),
            ("r", 0.10, 50, 0.482),
            ("z", 2.58, 0, 0.0099),
            ("z", 1.96, 0, 0.0500),
            # chi2 recalculations
            ("chi2", 8.41, 2, 0.0149),
            ("chi2", 0.50, 1, 0.4795),
            # Q-test recalculations (uses chi2 distribution internally)
            ("q", 12.3, 5, 0.0309),
            ("q", 5.0, 10, 0.8912),
        ],
    )
    def test_recalculated_p(self, test_type, statistic, df, expected_p_approx):
        """Our recalculated p should be within 0.01 of expected."""
        result = _recalculate_p_value(test_type, statistic, df)
        assert result is not None, f"Failed to recalculate {test_type}({df})={statistic}"
        assert abs(result - expected_p_approx) < 0.01, (
            f"{test_type}({df})={statistic}: got p={result:.6f}, expected ≈{expected_p_approx}"
        )


class TestRegexCoverage:
    """Test regex coverage for all supported patterns."""

    REGEX_TEST_CASES = [
        # (text, should_match_main, should_match_z, description)
        ("t(28) = 2.05, p = .050", True, False, "standard t"),
        ("F(1, 58) = 4.00, p = .050", True, False, "standard F"),
        ("r(30) = .45, p = .010", True, False, "standard r with leading dot stat"),
        ("χ²(2) = 8.41, p = .015", True, False, "chi2 unicode"),
        ("chi2(2) = 8.41, p = .015", True, False, "chi2 ascii"),
        ("t(28)=2.05,p=.050", True, False, "no spaces"),
        ("t(45) = 5.0, p < .001", True, False, "p less than"),
        ("t(20) = -2.086, p = .050", True, False, "negative t"),
        ("Q(5) = 12.3, p = .031", True, False, "Q-test with parens"),
        ("Z = 2.58, p = .010", False, True, "Z-test no parens"),
    ]

    @pytest.mark.parametrize(
        "text, expect_main, expect_z, desc",
        REGEX_TEST_CASES,
        ids=lambda x: x if isinstance(x, str) and len(x) < 30 else None,
    )
    def test_regex_match(self, text, expect_main, expect_z, desc):
        """Pattern should be matched by the correct regex."""
        main_match = _APA_STAT_RE.search(text) is not None
        z_match = _Z_STAT_RE.search(text) is not None

        if expect_main:
            assert main_match, f"[{desc}] Main regex should match: {text}"
        if expect_z:
            assert z_match, f"[{desc}] Z regex should match: {text}"
        # At least one must match
        assert main_match or z_match, f"[{desc}] No regex matched: {text}"

    def test_trailing_period_not_captured(self):
        """Sentence-ending period should NOT be captured in p-value."""
        m = _APA_STAT_RE.search("t(28) = 2.05, p = .050.")
        assert m is not None
        assert m.group("p_value") == "050"  # NOT "050."

    def test_leading_dot_statistic_captured(self):
        """Statistics like .45, .10 should be captured."""
        m = _APA_STAT_RE.search("r(30) = .45, p = .010")
        assert m is not None
        assert m.group("statistic") == ".45"

    def test_p_value_with_leading_zero(self):
        """p = 0.003 should be correctly captured."""
        m = _APA_STAT_RE.search("t(28) = 2.05, p = 0.003")
        assert m is not None
        assert m.group("p_value") == "0.003"


class TestMultiStatParagraphs:
    """Test extraction from realistic multi-stat paragraphs."""

    PARAGRAPHS = [
        {
            "id": "methods_paragraph",
            "text": (
                "A 2×2 ANOVA revealed a significant main effect of condition, "
                "F(1, 78) = 12.45, p = .001, and a significant interaction, "
                "F(1, 78) = 6.32, p = .014. Post-hoc t-tests showed that "
                "the experimental group (M = 4.52, SD = 1.23) scored higher "
                "than the control group, t(78) = 3.53, p < .001."
            ),
            "expected_extractions_min": 3,
        },
        {
            "id": "results_section",
            "text": (
                "The correlation between age and performance was significant, "
                "r(120) = .34, p < .001. After controlling for education, "
                "the partial correlation remained significant, r(117) = .28, "
                "p = .002."
            ),
            "expected_extractions_min": 2,
        },
        {
            "id": "mixed_errors",
            "text": (
                "Study 1 found t(45) = 0.50, p = .001. "
                "Study 2 found t(45) = 3.50, p = .001. "
                "Study 3 found F(1, 100) = 50.0, p = .500."
            ),
            "expected_extractions_min": 3,
            "expected_errors_min": 2,  # Study 1 and Study 3 are wrong
        },
    ]

    @pytest.mark.parametrize("para", PARAGRAPHS, ids=lambda p: p["id"])
    def test_multi_stat_extraction_count(self, para):
        """Our system should find the expected minimum extractions."""
        from app.engines.integrity.statistical_checker import _extract_all_stat_matches
        matches = _extract_all_stat_matches(para["text"])
        assert len(matches) >= para["expected_extractions_min"], (
            f"[{para['id']}] Expected ≥{para['expected_extractions_min']} "
            f"extractions, got {len(matches)}"
        )

    @pytest.mark.parametrize(
        "para",
        [p for p in PARAGRAPHS if "expected_errors_min" in p],
        ids=lambda p: p["id"],
    )
    def test_multi_stat_error_detection(self, para):
        """Error detection in multi-stat paragraph."""
        checker = StatisticalChecker()
        findings = checker.extract_and_check_stats(para["text"])
        assert len(findings) >= para["expected_errors_min"], (
            f"[{para['id']}] Expected ≥{para['expected_errors_min']} errors, "
            f"got {len(findings)}"
        )


class TestAggregateMetrics:
    """Compute aggregate precision/recall metrics vs ground truth."""

    def test_our_precision_recall(self):
        """Our system should achieve high precision and recall."""
        checker = StatisticalChecker()
        tp = fp = fn = tn = 0

        for case in GROUND_TRUTH_CASES:
            findings = checker.extract_and_check_stats(case["text"])
            detected_error = len(findings) > 0

            if case["is_error"] and detected_error:
                tp += 1
            elif case["is_error"] and not detected_error:
                fn += 1
            elif not case["is_error"] and detected_error:
                fp += 1
            else:
                tn += 1

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        print(f"\n=== Our System Metrics ===")
        print(f"TP={tp}, FP={fp}, FN={fn}, TN={tn}")
        print(f"Precision: {precision:.3f}")
        print(f"Recall:    {recall:.3f}")
        print(f"F1 Score:  {f1:.3f}")

        assert recall >= 0.85, f"Recall {recall:.3f} below 0.85 threshold"
        assert precision >= 0.85, f"Precision {precision:.3f} below 0.85 threshold"

    def test_head_to_head_vs_statcheck(self):
        """Compare our system vs statcheck on error cases (informational)."""
        checker = StatisticalChecker()
        our_catches = []
        sc_catches = []
        sc_crashes = 0

        error_cases = [c for c in GROUND_TRUTH_CASES if c["is_error"]]

        for case in error_cases:
            our_found = len(checker.extract_and_check_stats(case["text"])) > 0
            if our_found:
                our_catches.append(case["id"])

            sc_res = _run_statcheck_safe(case["text"])
            if sc_res is None:
                sc_crashes += 1
            elif len(sc_res) > 0 and sc_res["Error"].any():
                sc_catches.append(case["id"])

        print(f"\n=== Head-to-Head ({len(error_cases)} error cases) ===")
        print(f"Our catches:      {len(our_catches)}/{len(error_cases)} — {our_catches}")
        print(f"statcheck catches: {len(sc_catches)}/{len(error_cases)} — {sc_catches}")
        print(f"statcheck crashes: {sc_crashes}/{len(error_cases)}")

        # We should catch at least as many as statcheck (minus crashes)
        assert len(our_catches) >= len(sc_catches)
