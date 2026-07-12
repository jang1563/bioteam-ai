"""Tests for TableParser — bioinformatics TSV/CSV auto-detection."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.data_loaders.table_parser import TableParser, _normalize_col

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestNormalizeCol:
    """Unit tests for column name normalization."""

    def test_gene_aliases(self):
        assert _normalize_col("gene") == "gene"
        assert _normalize_col("Symbol") == "gene"
        assert _normalize_col("gene_symbol") == "gene"
        assert _normalize_col("Gene_Name") == "gene"
        assert _normalize_col("GENE_ID") == "gene"

    def test_logfc_aliases(self):
        assert _normalize_col("log2FoldChange") == "log2FC"
        assert _normalize_col("logFC") == "log2FC"
        assert _normalize_col("log2FC") == "log2FC"
        assert _normalize_col("LFC") == "log2FC"

    def test_padj_aliases(self):
        assert _normalize_col("padj") == "padj"
        assert _normalize_col("FDR") == "padj"
        assert _normalize_col("adj.P.Val") == "padj"
        assert _normalize_col("q_value") == "padj"

    def test_pvalue_aliases(self):
        assert _normalize_col("pvalue") == "pvalue"
        assert _normalize_col("P.Value") == "pvalue"
        assert _normalize_col("PValue") == "pvalue"

    def test_basemean_aliases(self):
        assert _normalize_col("baseMean") == "baseMean"
        assert _normalize_col("AveExpr") == "baseMean"

    def test_unknown_col_returns_none(self):
        assert _normalize_col("chromosome") is None
        assert _normalize_col("start_pos") is None


class TestTableParserDESeq2:
    """Tests for parsing DESeq2-format TSV files."""

    def test_parse_deseq2_fixture(self):
        parser = TableParser()
        table = parser.parse(str(FIXTURES / "sample_degs.tsv"))

        assert table.row_count == 50
        assert table.has_gene_column
        assert table.has_logfc_column
        assert table.has_padj_column
        assert table.detected_format == "deseq2"

    def test_gene_list_extraction(self):
        parser = TableParser()
        table = parser.parse(str(FIXTURES / "sample_degs.tsv"))
        genes = table.get_gene_list()

        assert len(genes) == 50
        assert "BRCA1" in genes
        assert "TP53" in genes
        assert "EGFR" in genes

    def test_deg_list_with_default_threshold(self):
        parser = TableParser()
        table = parser.parse(str(FIXTURES / "sample_degs.tsv"))
        degs = table.to_deg_list()  # padj < 0.05

        # Count genes with padj < 0.05
        assert len(degs) > 0
        for deg in degs:
            assert deg["padj"] < 0.05
            assert "gene" in deg
            assert "direction" in deg
            assert deg["direction"] in ("up", "down")

    def test_deg_list_directions(self):
        parser = TableParser()
        table = parser.parse(str(FIXTURES / "sample_degs.tsv"))
        degs = table.to_deg_list()

        deg_map = {d["gene"]: d for d in degs}
        # BRCA1 has log2FC=-2.45 → down
        assert deg_map["BRCA1"]["direction"] == "down"
        # EGFR has log2FC=3.21 → up
        assert deg_map["EGFR"]["direction"] == "up"

    def test_deg_list_with_logfc_threshold(self):
        parser = TableParser()
        table = parser.parse(str(FIXTURES / "sample_degs.tsv"))
        degs = table.to_deg_list(logfc_threshold=2.0)

        for deg in degs:
            assert abs(deg["log2FC"]) >= 2.0

    def test_deg_list_fold_change_values(self):
        parser = TableParser()
        table = parser.parse(str(FIXTURES / "sample_degs.tsv"))
        degs = table.to_deg_list()

        deg_map = {d["gene"]: d for d in degs}
        assert deg_map["BRCA1"]["log2FC"] == pytest.approx(-2.45)
        assert deg_map["EGFR"]["log2FC"] == pytest.approx(3.21)


class TestTableParserEdgeR:
    """Tests for parsing edgeR-format TSV files."""

    def test_parse_edger_fixture(self):
        parser = TableParser()
        table = parser.parse(str(FIXTURES / "sample_edger.tsv"))

        assert table.row_count == 4
        assert table.has_gene_column
        assert table.has_logfc_column
        assert table.has_padj_column
        assert table.detected_format == "edger"


class TestTableParserLimma:
    """Tests for parsing limma-format TSV files."""

    def test_parse_limma_fixture(self):
        parser = TableParser()
        table = parser.parse(str(FIXTURES / "sample_limma.tsv"))

        assert table.row_count == 3
        assert table.has_gene_column
        assert table.has_logfc_column
        assert table.has_padj_column
        assert table.detected_format == "limma"


class TestTableParserEdgeCases:
    """Edge case tests."""

    def test_file_not_found(self):
        parser = TableParser()
        with pytest.raises(FileNotFoundError):
            parser.parse("/nonexistent/path.tsv")

    def test_empty_file(self, tmp_path):
        empty = tmp_path / "empty.tsv"
        empty.write_text("")
        parser = TableParser()
        table = parser.parse(str(empty))
        assert table.row_count == 0
        assert len(table.warnings) > 0

    def test_header_only_file(self, tmp_path):
        header_only = tmp_path / "header.tsv"
        header_only.write_text("gene\tlog2FoldChange\tpadj\n")
        parser = TableParser()
        table = parser.parse(str(header_only))
        assert table.row_count == 0
        assert table.has_gene_column

    def test_csv_format(self, tmp_path):
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("gene,logFC,FDR\nBRCA1,-2.45,0.001\nTP53,1.82,0.003\n")
        parser = TableParser()
        table = parser.parse(str(csv_file))
        assert table.row_count == 2
        assert table.has_gene_column
        assert table.has_logfc_column

    def test_gene_list_only(self, tmp_path):
        gene_file = tmp_path / "genes.tsv"
        gene_file.write_text("gene\nBRCA1\nTP53\nEGFR\n")
        parser = TableParser()
        table = parser.parse(str(gene_file))
        assert table.row_count == 3
        assert table.detected_format == "gene_list"
        genes = table.get_gene_list()
        assert genes == ["BRCA1", "TP53", "EGFR"]

    def test_na_values_handled(self, tmp_path):
        na_file = tmp_path / "na_data.tsv"
        na_file.write_text("gene\tlog2FoldChange\tpadj\nBRCA1\t-2.45\t0.001\nTP53\tNA\tNA\n")
        parser = TableParser()
        table = parser.parse(str(na_file))
        degs = table.to_deg_list()
        # BRCA1 has valid data, TP53 has NA values
        assert len(degs) >= 1
        assert degs[0]["gene"] == "BRCA1"
