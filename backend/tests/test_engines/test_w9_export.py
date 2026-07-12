"""Tests for W9 result export (TSV, HTML, JSON)."""

from __future__ import annotations

from pathlib import Path

from app.engines.w9_export import (
    export_degs_tsv,
    export_html,
    export_json,
    export_pathways_tsv,
    export_variants_tsv,
    export_w9_report,
)

SAMPLE_REPORT = {
    "workflow_id": "test-w9-001",
    "query": "BRCA1 variants in breast cancer",
    "generated_at": "2026-03-19T12:00:00Z",
    "total_cost_usd": 2.50,
    "executive_summary": "Analysis identified 5 DEGs and 3 pathways.",
    "key_findings": [
        "BRCA1 is significantly downregulated (log2FC=-2.45)",
        "PI3K-Akt pathway enriched (p<0.001)",
    ],
    "limitations": ["Small sample size", "No experimental validation"],
    "expression_analysis": {
        "total_degs": 5,
        "comparison": "tumor vs normal",
        "up_regulated": [
            {"gene": "EGFR", "log2FC": 3.21, "padj": 0.0001},
            {"gene": "MYC", "log2FC": 1.82, "padj": 0.003},
        ],
        "down_regulated": [
            {"gene": "BRCA1", "log2FC": -2.45, "padj": 0.001},
            {"gene": "PTEN", "log2FC": -1.05, "padj": 0.042},
        ],
    },
    "variant_annotation": {
        "total_variants": 100,
        "high_impact_variants": [
            {"gene": "BRCA1", "consequence": "frameshift", "significance": "pathogenic"},
            {"gene": "TP53", "consequence": "missense", "significance": "likely_pathogenic"},
        ],
    },
    "pathway_enrichment": {
        "significant_terms": 15,
        "top_pathways": [
            {"source": "KEGG", "name": "PI3K-Akt signaling pathway", "pvalue": 1e-10, "genes": ["PIK3CA", "AKT1"]},
            {"source": "Reactome", "name": "DNA Repair", "pvalue": 1e-8, "genes": ["BRCA1", "RAD51"]},
        ],
    },
}


class TestDegsTSV:
    def test_header_present(self):
        tsv = export_degs_tsv(SAMPLE_REPORT)
        lines = tsv.strip().splitlines()
        assert lines[0].strip() == "gene\tlog2FC\tpadj\tdirection"

    def test_row_count(self):
        tsv = export_degs_tsv(SAMPLE_REPORT)
        lines = tsv.strip().split("\n")
        assert len(lines) == 5  # header + 2 up + 2 down

    def test_up_regulated_direction(self):
        tsv = export_degs_tsv(SAMPLE_REPORT)
        assert "EGFR\t3.21\t0.0001\tup" in tsv

    def test_down_regulated_direction(self):
        tsv = export_degs_tsv(SAMPLE_REPORT)
        assert "BRCA1\t-2.45\t0.001\tdown" in tsv

    def test_empty_expression(self):
        tsv = export_degs_tsv({})
        assert "gene\tlog2FC\tpadj\tdirection" in tsv


class TestVariantsTSV:
    def test_header_present(self):
        tsv = export_variants_tsv(SAMPLE_REPORT)
        assert "gene\tvariant_type\tconsequence\tsignificance" in tsv

    def test_variant_rows(self):
        tsv = export_variants_tsv(SAMPLE_REPORT)
        lines = tsv.strip().split("\n")
        assert len(lines) == 3  # header + 2 variants


class TestPathwaysTSV:
    def test_header_present(self):
        tsv = export_pathways_tsv(SAMPLE_REPORT)
        assert "source\tterm\tpvalue\tgene_ratio\tgenes" in tsv

    def test_pathway_rows(self):
        tsv = export_pathways_tsv(SAMPLE_REPORT)
        assert "PI3K-Akt signaling pathway" in tsv
        assert "KEGG" in tsv

    def test_genes_joined(self):
        tsv = export_pathways_tsv(SAMPLE_REPORT)
        assert "PIK3CA,AKT1" in tsv


class TestHTMLExport:
    def test_is_valid_html(self):
        html = export_html(SAMPLE_REPORT)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_contains_query(self):
        html = export_html(SAMPLE_REPORT)
        assert "BRCA1 variants in breast cancer" in html

    def test_contains_key_findings(self):
        html = export_html(SAMPLE_REPORT)
        assert "BRCA1 is significantly downregulated" in html

    def test_contains_deg_table(self):
        html = export_html(SAMPLE_REPORT)
        assert "EGFR" in html
        assert "3.21" in html

    def test_contains_pathway_table(self):
        html = export_html(SAMPLE_REPORT)
        assert "PI3K-Akt signaling pathway" in html

    def test_contains_variant_table(self):
        html = export_html(SAMPLE_REPORT)
        assert "frameshift" in html

    def test_contains_limitations(self):
        html = export_html(SAMPLE_REPORT)
        assert "Small sample size" in html

    def test_empty_report(self):
        html = export_html({"query": "empty test"})
        assert "<!DOCTYPE html>" in html


class TestJSONExport:
    def test_valid_json(self):
        import json
        json_str = export_json(SAMPLE_REPORT)
        parsed = json.loads(json_str)
        assert parsed["workflow_id"] == "test-w9-001"


class TestUnifiedExport:
    def test_exports_all_formats(self, tmp_path):
        result = export_w9_report(SAMPLE_REPORT, str(tmp_path))
        assert "degs_tsv" in result
        assert "variants_tsv" in result
        assert "pathways_tsv" in result
        assert "html" in result
        assert "json" in result

        # Verify files exist
        assert Path(result["degs_tsv"]).exists()
        assert Path(result["html"]).exists()
        assert Path(result["json"]).exists()

    def test_exports_subset(self, tmp_path):
        result = export_w9_report(SAMPLE_REPORT, str(tmp_path), formats=["html"])
        assert "html" in result
        assert "degs_tsv" not in result

    def test_creates_output_dir(self, tmp_path):
        out_dir = tmp_path / "nested" / "output"
        result = export_w9_report(SAMPLE_REPORT, str(out_dir))
        assert out_dir.exists()
        assert len(result) > 0
