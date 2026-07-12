"""Tests for VCFLoader — genomic variant file parser."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.data_loaders.vcf_loader import VCFLoader

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestVCFLoader:
    """Tests for VCF parsing."""

    def test_load_sample_vcf(self):
        loader = VCFLoader()
        variants = loader.load(str(FIXTURES / "sample.vcf"))

        # 20 total lines, 2 have LowQual → 18 PASS variants
        assert len(variants) == 18

    def test_variant_fields(self):
        loader = VCFLoader()
        variants = loader.load(str(FIXTURES / "sample.vcf"))

        first = variants[0]
        assert first["chrom"] == "chr1"
        assert first["pos"] == 12345
        assert first["ref"] == "A"
        assert first["alt"] == "G"
        assert first["qual"] == 99.0
        assert first["filter"] == "PASS"

    def test_filter_pass_only(self):
        loader = VCFLoader()
        variants = loader.load(str(FIXTURES / "sample.vcf"), filter_pass_only=True)

        for v in variants:
            assert v["filter"] in ("PASS", ".")

    def test_no_filter(self):
        loader = VCFLoader()
        variants = loader.load(str(FIXTURES / "sample.vcf"), filter_pass_only=False)

        # Should include all 20 variants
        assert len(variants) == 20

    def test_min_qual_filter(self):
        loader = VCFLoader()
        variants = loader.load(str(FIXTURES / "sample.vcf"), filter_pass_only=False, min_qual=50.0)

        for v in variants:
            assert v["qual"] >= 50.0

    def test_max_variants(self):
        loader = VCFLoader()
        variants = loader.load(str(FIXTURES / "sample.vcf"), max_variants=5)

        assert len(variants) == 5

    def test_rs_ids_parsed(self):
        loader = VCFLoader()
        variants = loader.load(str(FIXTURES / "sample.vcf"))

        rs_variants = [v for v in variants if v["id"] is not None]
        assert len(rs_variants) > 0
        assert rs_variants[0]["id"].startswith("rs")

    def test_null_ids(self):
        loader = VCFLoader()
        variants = loader.load(str(FIXTURES / "sample.vcf"))

        null_id_variants = [v for v in variants if v["id"] is None]
        assert len(null_id_variants) > 0

    def test_file_not_found(self):
        loader = VCFLoader()
        with pytest.raises(FileNotFoundError):
            loader.load("/nonexistent/path.vcf")

    def test_get_header(self):
        loader = VCFLoader()
        header = loader.get_header(str(FIXTURES / "sample.vcf"))

        assert header["sample_count"] == 1
        assert header["sample_names"] == ["SAMPLE1"]
        assert header["meta_line_count"] > 0

    def test_to_hgvs_list(self):
        loader = VCFLoader()
        variants = loader.load(str(FIXTURES / "sample.vcf"), max_variants=3)
        hgvs = loader.to_hgvs_list(variants)

        assert len(hgvs) == 3
        # First variant: chr1:12345 A>G
        assert hgvs[0] == "1:g.12345A>G"

    def test_indel_in_vcf(self):
        loader = VCFLoader()
        variants = loader.load(str(FIXTURES / "sample.vcf"))

        # chr2:22222 AT>A is an indel
        indels = [v for v in variants if len(v["ref"]) != len(v["alt"])]
        assert len(indels) >= 1

    def test_empty_vcf(self, tmp_path):
        empty_vcf = tmp_path / "empty.vcf"
        empty_vcf.write_text("##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n")
        loader = VCFLoader()
        variants = loader.load(str(empty_vcf))
        assert len(variants) == 0
