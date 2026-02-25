"""Unified integrity benchmark suite — aggregate metrics across all checkers.

Runs every deterministic checker against ground-truth test cases and produces
a per-checker precision / recall / F1 scorecard. Serves as a regression gate:
if any checker drops below 85 % recall, the test fails.

Checkers covered (6):
  - GRIM (mean consistency)
  - GRIMMER SD (standard deviation consistency)
  - GRIMMER percentage (percentage consistency)
  - p-value recalculation (statcheck-equivalent)
  - Gene name (Excel date corruption)
  - Retraction (retracted/corrected/EOC/PubPeer)
  - Text extraction (SD, percentage, APA stats from realistic paragraphs)
"""


import pytest
from app.engines.integrity.finding_models import RetractionStatus
from app.engines.integrity.gene_name_checker import GeneNameChecker
from app.engines.integrity.retraction_checker import RetractionChecker
from app.engines.integrity.statistical_checker import StatisticalChecker

# ══════════════════════════════════════════════════════════════════
# Ground-truth datasets
# ══════════════════════════════════════════════════════════════════


GRIM_CASES = [
    # (mean, n, decimals, is_inconsistent)
    (5.19, 25, 2, True),
    (3.75, 40, 2, False),
    (2.50, 20, 2, False),
    (2.33, 30, 2, False),
    (2.33, 3, 2, False),
    (2.34, 3, 2, True),
    (4.00, 10, 2, False),
    (1.11, 9, 2, False),
    (3.57, 7, 2, False),     # 3.57 × 7 = 24.99 → within tol (0.035)
    (3.58, 7, 2, True),      # 3.58 × 7 = 25.06 → diff 0.06 > tol 0.035
]

GRIMMER_SD_CASES = [
    # (sd, n, decimals, is_inconsistent)
    (1.00, 10, 2, False),   # SSD = 9.0 → integer
    (0.00, 5, 2, False),    # all identical
    (2.00, 2, 2, False),    # SSD = 4.0
    (1.41, 2, 2, False),    # SSD range includes 2
    (1.42, 2, 2, True),     # SSD range [2.002, 2.031] → no integer
    (0.50, 5, 2, False),    # SSD = 1.0
    (0.71, 3, 2, False),    # SSD range includes 1
    (3.00, 10, 2, False),   # SSD = 81.0
    (1.00, 1, 2, True),     # n=1 → always inconsistent
    (-1.0, 10, 2, True),    # negative → always inconsistent
]

GRIMMER_PCT_CASES = [
    # (pct, n, decimals, is_inconsistent)
    (50.0, 10, 1, False),   # 50.0% × 10 / 100 = 5.0
    (33.3, 3, 1, False),    # within tolerance
    (33.4, 3, 1, True),     # exceeds tolerance
    (25.0, 100, 1, False),  # 25.0
    (10.0, 10, 1, False),   # 1.0
    (15.0, 10, 1, True),    # 1.5 → not integer within tol
    (75.00, 4, 2, False),   # 3.0
    (0.0, 10, 1, False),    # 0
    (100.0, 10, 1, False),  # 10
    (50.0, 0, 1, True),     # n=0 → inconsistent
]

PVALUE_CASES = [
    # (text, is_error, description)
    ("t(28) = 2.05, p = .050", False, "correct t-test"),
    ("t(100) = 1.98, p = .050", False, "correct t-test large df"),
    ("F(1, 58) = 4.00, p = .050", False, "correct F-test"),
    ("r(30) = .45, p = .010", False, "correct correlation"),
    ("t(20) = 2.09, p = .500", True, "wrong p for t"),
    ("t(50) = 0.50, p = .001", True, "wrong p for t (2)"),
    ("F(1, 100) = 50.0, p = .500", True, "wrong p for F"),
    ("F(3, 200) = 1.00, p = .001", True, "wrong p for F (2)"),
    ("r(50) = .10, p = .001", True, "wrong p for r"),
    ("t(25) = 1.50, p = .040", True, "decision error: p flipped"),
    ("F(1, 50) = 8.00, p = .100", True, "decision error: F flipped"),
    ("t(30) = 2.04, p = .050", False, "borderline correct"),
]

GENE_NAME_CASES = [
    # (text, has_finding) — condensed from Ziemann corpus
    ("1-Mar", True),    # MARCH1
    ("7-Sep", True),    # SEPT7
    ("1-Dec", True),    # DEC1
    ("4-Oct", True),    # OCT4
    ("1-Feb", True),    # FEB1
    ("BRCA1", False),   # clean
    ("TP53", False),    # clean
    ("MARCHF1", False), # renamed (clean)
    ("1-Jan", False),   # non-gene month
    ("1-Apr", False),   # non-gene month
    ("15-Mar", False),  # out of range (MARCH max=11)
    ("3-Dec", False),   # out of range (DEC max=2)
]

# Retraction mock data for unified suite
_RETRACTION_CASES_RAW = [
    # (doi, mock_status, has_finding, description)
    ("10.1234/ret1", {"is_retracted": True}, True, "retracted"),
    ("10.1234/ret2", {"is_retracted": True}, True, "retracted"),
    ("10.1234/cor1", {"is_corrected": True}, True, "corrected"),
    ("10.1234/eoc1", {"has_expression_of_concern": True}, True, "EOC"),
    ("10.1234/clean1", {}, False, "clean"),
    ("10.1234/clean2", {}, False, "clean"),
    ("10.1234/clean3", {}, False, "clean"),
    ("10.1234/clean4", {}, False, "clean"),
]

TEXT_EXTRACTION_CASES = [
    # (text, expected_sd_flags, expected_pct_flags, expected_pval_flags, description)
    (
        "M = 4.56, SD = 1.50, N = 10 on the Likert scale.",
        1, 0, 0, "SD inconsistency extracted",
    ),
    (
        "M = 3.00, SD = 1.00, N = 10 on the anxiety scale.",
        0, 0, 0, "SD consistent — no flag",
    ),
    (
        "33.4% of participants (N = 3) reported improvement.",
        0, 1, 0, "percentage inconsistency extracted",
    ),
    (
        "50.0% of participants (N = 10) completed the study.",
        0, 0, 0, "percentage consistent — no flag",
    ),
    (
        "The result was t(20) = 2.09, p = .500 and SD = 1.00, N = 10.",
        0, 0, 1, "mixed: only p-value flagged",
    ),
    (
        "Group A: M = 3.20, SD = 1.00, N = 10. "
        "Group B: M = 4.50, SD = 1.50, N = 10.",
        1, 0, 0, "multiple SDs: only inconsistent one flagged",
    ),
]


# ══════════════════════════════════════════════════════════════════
# Scorecard helpers
# ══════════════════════════════════════════════════════════════════


def _metrics(tp: int, fp: int, fn: int, tn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "P": precision, "R": recall, "F1": f1}


class _MockCrossrefClient:
    """Minimal mock for unified suite retraction tests."""

    def __init__(self, status_map: dict[str, RetractionStatus]):
        self._map = status_map

    async def check_retraction(self, doi: str) -> RetractionStatus:
        return self._map.get(doi, RetractionStatus(doi=doi))


def _build_retraction_checker() -> RetractionChecker:
    """Build checker with mock crossref for unified suite."""
    status_map: dict[str, RetractionStatus] = {}
    for doi, kwargs, _, _ in _RETRACTION_CASES_RAW:
        if kwargs:
            status_map[doi] = RetractionStatus(doi=doi, **kwargs)
    return RetractionChecker(
        crossref_client=_MockCrossrefClient(status_map),
        pubpeer_client=None,
    )


# ══════════════════════════════════════════════════════════════════
# Individual checker scorecards
# ══════════════════════════════════════════════════════════════════


class TestGRIMScorecard:
    """GRIM checker precision/recall on ground-truth cases."""

    def test_grim_metrics(self):
        tp = fp = fn = tn = 0
        for mean, n, decimals, is_incon in GRIM_CASES:
            result = StatisticalChecker.grim_test(mean, n, decimals)
            detected = not result.is_consistent
            if is_incon and detected:
                tp += 1
            elif is_incon and not detected:
                fn += 1
            elif not is_incon and detected:
                fp += 1
            else:
                tn += 1

        m = _metrics(tp, fp, fn, tn)
        print("\n=== GRIM Scorecard ===")
        print(f"TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']}")
        print(f"P={m['P']:.3f} R={m['R']:.3f} F1={m['F1']:.3f}")
        assert m["R"] >= 0.85, f"GRIM recall {m['R']:.3f} < 0.85"
        assert m["P"] >= 0.85, f"GRIM precision {m['P']:.3f} < 0.85"


class TestGRIMMERSDScorecard:
    """GRIMMER SD checker precision/recall."""

    def test_grimmer_sd_metrics(self):
        tp = fp = fn = tn = 0
        for sd, n, decimals, is_incon in GRIMMER_SD_CASES:
            result = StatisticalChecker.grimmer_sd_test(sd, n, decimals)
            detected = not result.is_consistent
            if is_incon and detected:
                tp += 1
            elif is_incon and not detected:
                fn += 1
            elif not is_incon and detected:
                fp += 1
            else:
                tn += 1

        m = _metrics(tp, fp, fn, tn)
        print("\n=== GRIMMER SD Scorecard ===")
        print(f"TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']}")
        print(f"P={m['P']:.3f} R={m['R']:.3f} F1={m['F1']:.3f}")
        assert m["R"] >= 0.85, f"GRIMMER SD recall {m['R']:.3f} < 0.85"
        assert m["P"] >= 0.85, f"GRIMMER SD precision {m['P']:.3f} < 0.85"


class TestGRIMMERPctScorecard:
    """GRIMMER percentage checker precision/recall."""

    def test_grimmer_pct_metrics(self):
        tp = fp = fn = tn = 0
        for pct, n, decimals, is_incon in GRIMMER_PCT_CASES:
            result = StatisticalChecker.grimmer_percent_test(pct, n, decimals)
            detected = not result.is_consistent
            if is_incon and detected:
                tp += 1
            elif is_incon and not detected:
                fn += 1
            elif not is_incon and detected:
                fp += 1
            else:
                tn += 1

        m = _metrics(tp, fp, fn, tn)
        print("\n=== GRIMMER Pct Scorecard ===")
        print(f"TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']}")
        print(f"P={m['P']:.3f} R={m['R']:.3f} F1={m['F1']:.3f}")
        assert m["R"] >= 0.85, f"GRIMMER Pct recall {m['R']:.3f} < 0.85"
        assert m["P"] >= 0.85, f"GRIMMER Pct precision {m['P']:.3f} < 0.85"


class TestPValueScorecard:
    """p-value recalculation checker precision/recall."""

    def test_pvalue_metrics(self):
        checker = StatisticalChecker()
        tp = fp = fn = tn = 0
        for text, is_error, desc in PVALUE_CASES:
            findings = checker.extract_and_check_stats(text)
            detected = len(findings) > 0
            if is_error and detected:
                tp += 1
            elif is_error and not detected:
                fn += 1
            elif not is_error and detected:
                fp += 1
            else:
                tn += 1

        m = _metrics(tp, fp, fn, tn)
        print("\n=== P-Value Scorecard ===")
        print(f"TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']}")
        print(f"P={m['P']:.3f} R={m['R']:.3f} F1={m['F1']:.3f}")
        assert m["R"] >= 0.85, f"P-value recall {m['R']:.3f} < 0.85"
        assert m["P"] >= 0.85, f"P-value precision {m['P']:.3f} < 0.85"


class TestGeneNameScorecard:
    """Gene name checker precision/recall on Ziemann-derived cases."""

    def test_gene_name_metrics(self):
        checker = GeneNameChecker()
        tp = fp = fn = tn = 0
        for text, has_finding in GENE_NAME_CASES:
            findings = checker.check_text(text)
            detected = len(findings) > 0
            if has_finding and detected:
                tp += 1
            elif has_finding and not detected:
                fn += 1
            elif not has_finding and detected:
                fp += 1
            else:
                tn += 1

        m = _metrics(tp, fp, fn, tn)
        print("\n=== Gene Name Scorecard ===")
        print(f"TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']}")
        print(f"P={m['P']:.3f} R={m['R']:.3f} F1={m['F1']:.3f}")
        assert m["R"] >= 0.85, f"Gene name recall {m['R']:.3f} < 0.85"
        assert m["P"] >= 0.85, f"Gene name precision {m['P']:.3f} < 0.85"


class TestRetractionScorecard:
    """Retraction checker precision/recall on mock cases."""

    @pytest.mark.asyncio
    async def test_retraction_metrics(self):
        checker = _build_retraction_checker()
        tp = fp = fn = tn = 0
        for doi, _, has_finding, _ in _RETRACTION_CASES_RAW:
            findings = await checker.check_doi(doi)
            detected = len(findings) > 0
            if has_finding and detected:
                tp += 1
            elif has_finding and not detected:
                fn += 1
            elif not has_finding and detected:
                fp += 1
            else:
                tn += 1

        m = _metrics(tp, fp, fn, tn)
        print("\n=== Retraction Scorecard ===")
        print(f"TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']}")
        print(f"P={m['P']:.3f} R={m['R']:.3f} F1={m['F1']:.3f}")
        assert m["R"] >= 0.85, f"Retraction recall {m['R']:.3f} < 0.85"
        assert m["P"] >= 0.85, f"Retraction precision {m['P']:.3f} < 0.85"


# ══════════════════════════════════════════════════════════════════
# Text extraction integration test
# ══════════════════════════════════════════════════════════════════


class TestTextExtractionIntegration:
    """End-to-end: text → regex → checker → correct findings."""

    @pytest.mark.parametrize(
        "text, exp_sd, exp_pct, exp_pval, desc",
        TEXT_EXTRACTION_CASES,
        ids=[c[4] for c in TEXT_EXTRACTION_CASES],
    )
    def test_extraction_case(self, text, exp_sd, exp_pct, exp_pval, desc):
        checker = StatisticalChecker()
        grimmer = checker.extract_and_check_grimmer(text)
        stats = checker.extract_and_check_stats(text)

        sd_flags = [f for f in grimmer if f.category == "grimmer_sd_failure"]
        pct_flags = [f for f in grimmer if f.category == "grimmer_percent_failure"]

        assert len(sd_flags) == exp_sd, (
            f"[{desc}] SD flags: expected {exp_sd}, got {len(sd_flags)}"
        )
        assert len(pct_flags) == exp_pct, (
            f"[{desc}] Pct flags: expected {exp_pct}, got {len(pct_flags)}"
        )
        assert len(stats) == exp_pval, (
            f"[{desc}] P-value flags: expected {exp_pval}, got {len(stats)}"
        )


# ══════════════════════════════════════════════════════════════════
# Unified report
# ══════════════════════════════════════════════════════════════════


class TestUnifiedReport:
    """Generate a single combined report across all checkers.

    This is the primary regression gate — if any checker drops below
    85 % recall, the entire suite fails.
    """

    @pytest.mark.asyncio
    async def test_combined_report(self):
        stat_checker = StatisticalChecker()
        gene_checker = GeneNameChecker()
        retraction_checker = _build_retraction_checker()
        results: dict[str, dict] = {}

        # --- GRIM ---
        tp = fp = fn = tn = 0
        for mean, n, decimals, is_incon in GRIM_CASES:
            detected = not StatisticalChecker.grim_test(mean, n, decimals).is_consistent
            if is_incon and detected:
                tp += 1
            elif is_incon and not detected:
                fn += 1
            elif not is_incon and detected:
                fp += 1
            else:
                tn += 1
        results["grim"] = _metrics(tp, fp, fn, tn)

        # --- GRIMMER SD ---
        tp = fp = fn = tn = 0
        for sd, n, decimals, is_incon in GRIMMER_SD_CASES:
            detected = not StatisticalChecker.grimmer_sd_test(sd, n, decimals).is_consistent
            if is_incon and detected:
                tp += 1
            elif is_incon and not detected:
                fn += 1
            elif not is_incon and detected:
                fp += 1
            else:
                tn += 1
        results["grimmer_sd"] = _metrics(tp, fp, fn, tn)

        # --- GRIMMER Pct ---
        tp = fp = fn = tn = 0
        for pct, n, decimals, is_incon in GRIMMER_PCT_CASES:
            detected = not StatisticalChecker.grimmer_percent_test(pct, n, decimals).is_consistent
            if is_incon and detected:
                tp += 1
            elif is_incon and not detected:
                fn += 1
            elif not is_incon and detected:
                fp += 1
            else:
                tn += 1
        results["grimmer_pct"] = _metrics(tp, fp, fn, tn)

        # --- p-value ---
        tp = fp = fn = tn = 0
        for text, is_error, desc in PVALUE_CASES:
            detected = len(stat_checker.extract_and_check_stats(text)) > 0
            if is_error and detected:
                tp += 1
            elif is_error and not detected:
                fn += 1
            elif not is_error and detected:
                fp += 1
            else:
                tn += 1
        results["p_value"] = _metrics(tp, fp, fn, tn)

        # --- Gene name ---
        tp = fp = fn = tn = 0
        for text, has_finding in GENE_NAME_CASES:
            detected = len(gene_checker.check_text(text)) > 0
            if has_finding and detected:
                tp += 1
            elif has_finding and not detected:
                fn += 1
            elif not has_finding and detected:
                fp += 1
            else:
                tn += 1
        results["gene_name"] = _metrics(tp, fp, fn, tn)

        # --- Retraction ---
        tp = fp = fn = tn = 0
        for doi, _, has_finding, _ in _RETRACTION_CASES_RAW:
            detected = len(await retraction_checker.check_doi(doi)) > 0
            if has_finding and detected:
                tp += 1
            elif has_finding and not detected:
                fn += 1
            elif not has_finding and detected:
                fp += 1
            else:
                tn += 1
        results["retraction"] = _metrics(tp, fp, fn, tn)

        # --- Print combined report ---
        print("\n" + "=" * 60)
        print("  UNIFIED INTEGRITY BENCHMARK REPORT")
        print("=" * 60)
        print(f"{'Checker':<14} {'TP':>3} {'FP':>3} {'FN':>3} {'TN':>3}  {'P':>5} {'R':>5} {'F1':>5}")
        print("-" * 60)
        for name, m in results.items():
            print(
                f"{name:<14} {m['tp']:>3} {m['fp']:>3} {m['fn']:>3} {m['tn']:>3}"
                f"  {m['P']:>5.3f} {m['R']:>5.3f} {m['F1']:>5.3f}"
            )
        print("-" * 60)

        # Aggregate
        total_tp = sum(m["tp"] for m in results.values())
        total_fp = sum(m["fp"] for m in results.values())
        total_fn = sum(m["fn"] for m in results.values())
        total_tn = sum(m["tn"] for m in results.values())
        agg = _metrics(total_tp, total_fp, total_fn, total_tn)
        print(
            f"{'AGGREGATE':<14} {agg['tp']:>3} {agg['fp']:>3} {agg['fn']:>3} {agg['tn']:>3}"
            f"  {agg['P']:>5.3f} {agg['R']:>5.3f} {agg['F1']:>5.3f}"
        )
        print("=" * 60)

        # Regression gate: every checker must have ≥ 85% recall
        for name, m in results.items():
            assert m["R"] >= 0.85, f"{name} recall {m['R']:.3f} dropped below 85%"
            assert m["P"] >= 0.85, f"{name} precision {m['P']:.3f} dropped below 85%"

        # Overall aggregate should be ≥ 90%
        assert agg["R"] >= 0.90, f"Aggregate recall {agg['R']:.3f} dropped below 90%"
        assert agg["P"] >= 0.90, f"Aggregate precision {agg['P']:.3f} dropped below 90%"
