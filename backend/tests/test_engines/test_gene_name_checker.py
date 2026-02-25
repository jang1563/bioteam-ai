"""Tests for GeneNameChecker — Excel date corruption detection."""

import pytest
from app.engines.integrity.gene_name_checker import GeneNameChecker


@pytest.fixture
def checker():
    return GeneNameChecker()


class TestExcelDateDetection:
    """Tests for Excel date-mangled gene name detection."""

    def test_detect_1_mar_as_march1(self, checker):
        """1-Mar should be flagged as likely MARCH1."""
        findings = checker.check_text("Gene 1-Mar showed increased expression.")
        assert len(findings) == 1
        assert findings[0].corrected_symbol == "MARCHF1"
        assert findings[0].error_type == "excel_date"

    def test_detect_sep_7_as_sept7(self, checker):
        """Sep-7 should be flagged as likely SEPT7."""
        findings = checker.check_text("The gene Sep-7 was upregulated.")
        assert len(findings) == 1
        assert findings[0].corrected_symbol == "SEPTIN7"

    def test_detect_1_dec_as_dec1(self, checker):
        """1-Dec should be flagged as likely DEC1 (BHLHE40)."""
        findings = checker.check_text("Results for 1-Dec are shown in Table 2.")
        assert len(findings) == 1
        assert findings[0].corrected_symbol == "BHLHE40"

    def test_detect_2_dec_as_dec2(self, checker):
        """2-Dec should be flagged as likely DEC2 (BHLHE41)."""
        findings = checker.check_text("Results for 2-Dec are shown.")
        assert len(findings) == 1
        assert findings[0].corrected_symbol == "BHLHE41"

    def test_detect_4_oct_as_oct4(self, checker):
        """4-Oct should be flagged as likely OCT4."""
        findings = checker.check_text("Expression of 4-Oct in stem cells.")
        assert len(findings) == 1
        # OCT has no renamed_to, so corrected_symbol = OCT4
        assert findings[0].corrected_symbol == "OCT4"

    def test_no_false_positive_on_june(self, checker):
        """Jun-1 should not be flagged (no JUN gene family in our list)."""
        findings = checker.check_text("The date Jun-1 was recorded.")
        assert len(findings) == 0

    def test_no_false_positive_on_april(self, checker):
        """Apr-15 should not be flagged."""
        findings = checker.check_text("Deadline is Apr-15.")
        assert len(findings) == 0

    def test_multiple_corruptions_in_text(self, checker):
        """Multiple gene corruptions in one text should all be found."""
        text = "Table: 1-Mar, 7-Sep, 2-Dec genes were analyzed."
        findings = checker.check_text(text)
        assert len(findings) == 3

    def test_out_of_range_member_not_flagged(self, checker):
        """15-Mar should not be flagged (MARCH only goes to 11)."""
        findings = checker.check_text("Gene 15-Mar was found.")
        assert len(findings) == 0

    def test_month_first_format(self, checker):
        """Mar-1 format (month first) should also be detected."""
        findings = checker.check_text("Gene Mar-1 was expressed.")
        assert len(findings) == 1
        assert findings[0].corrected_symbol == "MARCHF1"

    def test_with_year_suffix_still_detected(self, checker):
        """1-Mar-2024 should still be detected."""
        findings = checker.check_text("Recorded 1-Sep-2024 in data.")
        assert len(findings) == 1


class TestTableData:
    """Tests for table data scanning."""

    def test_table_data_detection(self, checker):
        """Gene name errors in table data should be found with higher confidence."""
        headers = ["Gene", "Expression", "p-value"]
        rows = [
            ["1-Mar", "2.5", "0.001"],
            ["BRCA1", "1.8", "0.05"],
            ["7-Sep", "3.1", "0.003"],
        ]
        findings = checker.check_table_data(headers, rows)
        assert len(findings) == 2
        # Table context → error severity (not warning)
        assert all(f.severity == "error" for f in findings)

    def test_table_deduplication(self, checker):
        """Duplicate entries in table should be deduplicated."""
        headers = ["Gene"]
        rows = [["1-Mar"], ["1-Mar"], ["1-Mar"]]
        findings = checker.check_table_data(headers, rows)
        assert len(findings) == 1

    def test_empty_table(self, checker):
        """Empty table should produce no findings."""
        findings = checker.check_table_data([], [])
        assert len(findings) == 0

    def test_table_confidence_higher(self, checker):
        """Table context should give higher confidence than free text."""
        text_findings = checker.check_text("1-Mar")
        table_findings = checker.check_table_data(["Gene"], [["1-Mar"]])
        assert table_findings[0].confidence > text_findings[0].confidence


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_text(self, checker):
        """Empty text should produce no findings."""
        assert checker.check_text("") == []

    def test_no_genes_in_text(self, checker):
        """Normal text with no gene patterns should produce no findings."""
        assert checker.check_text("The experiment was conducted on Monday.") == []

    def test_slash_separator(self, checker):
        """1/Mar format should also be detected."""
        findings = checker.check_text("Gene 1/Sep was detected.")
        assert len(findings) == 1
