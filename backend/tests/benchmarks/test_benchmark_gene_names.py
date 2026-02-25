"""Benchmark: Gene Name Checker — Ziemann et al. (2016, 2021) validation.

Tests GeneNameChecker against the GeneNameErrors2020 corpus patterns.
Validates detection of Excel date-corrupted gene names across 5 families:
MARCH(1-11), SEPT(1-12), DEC(1-2), OCT(1-4), FEB(1-2).

References:
- Ziemann et al. "Gene name errors are widespread in the scientific literature" (2016)
- Abeysooriya et al. "Gene name errors: Lessons not learned" (2021)
"""

import pytest

from app.engines.integrity.gene_name_checker import GeneNameChecker


# ── Ground truth: True positives ──
# Excel date patterns that should be detected as corrupted gene names.
# Format: (input_text, expected_corrected_symbol)

TRUE_POSITIVES = [
    # MARCH family (1-11) → MARCHF{n}
    ("1-Mar", "MARCHF1"),
    ("2-Mar", "MARCHF2"),
    ("3-Mar", "MARCHF3"),
    ("4-Mar", "MARCHF4"),
    ("5-Mar", "MARCHF5"),
    ("6-Mar", "MARCHF6"),
    ("7-Mar", "MARCHF7"),
    ("8-Mar", "MARCHF8"),
    ("9-Mar", "MARCHF9"),
    ("10-Mar", "MARCHF10"),
    ("11-Mar", "MARCHF11"),
    # SEPT family (1-12) → SEPTIN{n}
    ("1-Sep", "SEPTIN1"),
    ("2-Sep", "SEPTIN2"),
    ("7-Sep", "SEPTIN7"),
    ("9-Sep", "SEPTIN9"),
    ("11-Sep", "SEPTIN11"),
    ("12-Sep", "SEPTIN12"),
    # DEC family (1-2) → BHLHE40/41
    ("1-Dec", "BHLHE40"),
    ("2-Dec", "BHLHE41"),
    # OCT family (1-4) → OCT{n} (no standard renaming)
    ("1-Oct", "OCT1"),
    ("4-Oct", "OCT4"),
    # FEB family (1-2) → FEB{n} (no standard renaming)
    ("1-Feb", "FEB1"),
    ("2-Feb", "FEB2"),
    # Reverse format: Month-Number
    ("Mar-1", "MARCHF1"),
    ("Sep-7", "SEPTIN7"),
    ("Dec-1", "BHLHE40"),
    # With year suffix
    ("1-Sep-2024", "SEPTIN1"),
    ("1-Mar-22", "MARCHF1"),
]


# ── Ground truth: True negatives ──
# Patterns that should NOT be flagged as gene name errors.

TRUE_NEGATIVES = [
    # Clean HGNC gene names (post-rename or unrelated)
    "BRCA1",
    "TP53",
    "EGFR",
    "MARCHF1",
    "SEPTIN7",
    "BHLHE40",
    # Non-gene months (no gene family uses these months)
    "1-Jan",
    "1-Apr",
    "1-May",
    "1-Jun",
    "1-Jul",
    "1-Aug",
    "1-Nov",
    # Out-of-range member numbers
    "15-Mar",   # MARCH max = 11
    "13-Sep",   # SEPT max = 12
    "3-Dec",    # DEC max = 2
    "5-Oct",    # OCT max = 4
    "3-Feb",    # FEB max = 2
]


# ══════════════════════════════════════════════════════════════════
# 1. True positive detection
# ══════════════════════════════════════════════════════════════════


class TestZiemannTruePositives:
    """Each corrupted gene name pattern should be detected with correct symbol."""

    @pytest.mark.parametrize(
        "text, expected_symbol",
        TRUE_POSITIVES,
        ids=[f"{t[0]}→{t[1]}" for t in TRUE_POSITIVES],
    )
    def test_detects_corrupted_gene(self, text: str, expected_symbol: str):
        checker = GeneNameChecker()
        findings = checker.check_text(text)
        assert len(findings) >= 1, f"Should detect '{text}' as corrupted gene name"
        assert findings[0].corrected_symbol == expected_symbol, (
            f"'{text}': expected {expected_symbol}, got {findings[0].corrected_symbol}"
        )
        assert findings[0].error_type == "excel_date"
        assert findings[0].severity == "warning"  # free text → warning


# ══════════════════════════════════════════════════════════════════
# 2. True negative guard
# ══════════════════════════════════════════════════════════════════


class TestZiemannTrueNegatives:
    """Clean gene names, non-gene months, and out-of-range should NOT be flagged."""

    @pytest.mark.parametrize("text", TRUE_NEGATIVES, ids=TRUE_NEGATIVES)
    def test_no_false_positive(self, text: str):
        checker = GeneNameChecker()
        findings = checker.check_text(text)
        assert len(findings) == 0, f"False positive on '{text}': {findings}"


# ══════════════════════════════════════════════════════════════════
# 3. Table data detection
# ══════════════════════════════════════════════════════════════════


class TestZiemannTableData:
    """Table context should flag with severity='error' and higher confidence."""

    def test_mixed_table(self):
        """Table with corrupted and clean gene names."""
        checker = GeneNameChecker()
        headers = ["Gene", "FC", "p-value"]
        rows = [
            ["1-Mar", "2.5", "0.001"],      # corrupted: MARCH1
            ["BRCA1", "1.8", "0.01"],        # clean
            ["7-Sep", "-1.2", "0.05"],       # corrupted: SEPT7
            ["TP53", "3.0", "0.001"],        # clean
            ["1-Dec", "0.5", "0.1"],         # corrupted: DEC1
            ["EGFR", "1.0", "0.5"],          # clean
        ]
        findings = checker.check_table_data(headers, rows)

        assert len(findings) == 3, f"Expected 3 findings, got {len(findings)}"
        corrected = {f.corrected_symbol for f in findings}
        assert corrected == {"MARCHF1", "SEPTIN7", "BHLHE40"}

        for f in findings:
            assert f.severity == "error", f"Table context should be severity='error'"
            assert f.confidence == 0.9, f"Table confidence should be 0.9"

    def test_deduplication(self):
        """Same corrupted gene appearing multiple times should be deduplicated."""
        checker = GeneNameChecker()
        headers = ["Gene"]
        rows = [
            ["1-Mar"],
            ["1-Mar"],  # duplicate
            ["1-Mar"],  # duplicate
        ]
        findings = checker.check_table_data(headers, rows)
        assert len(findings) == 1, f"Should deduplicate to 1 finding, got {len(findings)}"


# ══════════════════════════════════════════════════════════════════
# 4. Realistic paragraph context
# ══════════════════════════════════════════════════════════════════


class TestZiemannRealisticParagraphs:
    """Gene names embedded in realistic scientific text."""

    def test_supplementary_table_mention(self):
        text = (
            "Supplementary Table S3 lists differentially expressed genes including "
            "1-Mar, 7-Sep, and BRCA1 (FC > 2, FDR < 0.05)."
        )
        checker = GeneNameChecker()
        findings = checker.check_text(text)
        assert len(findings) == 2  # 1-Mar and 7-Sep
        symbols = {f.corrected_symbol for f in findings}
        assert symbols == {"MARCHF1", "SEPTIN7"}

    def test_clean_paragraph_no_flags(self):
        text = (
            "We identified MARCHF1, SEPTIN7, and BHLHE40 as significantly "
            "upregulated genes in the treatment group (p < 0.001)."
        )
        checker = GeneNameChecker()
        findings = checker.check_text(text)
        assert len(findings) == 0


# ══════════════════════════════════════════════════════════════════
# 5. Scorecard: Precision / Recall / F1
# ══════════════════════════════════════════════════════════════════


class TestGeneNameScorecard:
    """Aggregate metrics across all ground-truth cases."""

    def test_gene_name_metrics(self):
        checker = GeneNameChecker()
        tp = fp = fn = tn = 0

        # True positives
        for text, _expected in TRUE_POSITIVES:
            findings = checker.check_text(text)
            if len(findings) >= 1:
                tp += 1
            else:
                fn += 1

        # True negatives
        for text in TRUE_NEGATIVES:
            findings = checker.check_text(text)
            if len(findings) == 0:
                tn += 1
            else:
                fp += 1

        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        print(f"\n=== Gene Name Scorecard (Ziemann) ===")
        print(f"TP={tp} FP={fp} FN={fn} TN={tn}")
        print(f"Precision: {precision:.3f}")
        print(f"Recall:    {recall:.3f}")
        print(f"F1 Score:  {f1:.3f}")

        assert recall >= 0.85, f"Gene name recall {recall:.3f} below 0.85"
        assert precision >= 0.85, f"Gene name precision {precision:.3f} below 0.85"
