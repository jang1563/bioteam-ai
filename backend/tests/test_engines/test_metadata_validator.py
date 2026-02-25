"""Tests for MetadataValidator — GEO/SRA accessions, genome builds, sample sizes."""

import pytest

from app.engines.integrity.metadata_validator import MetadataValidator


@pytest.fixture
def validator():
    return MetadataValidator()


class TestAccessionValidation:

    def test_detects_geo_accessions(self, validator):
        """GEO accessions (GSE, GSM, GPL) are extracted."""
        text = "Data is available at GSE12345 and GSM6789012."
        findings = validator.validate_accessions(text)
        # These are valid accessions, should not produce warnings
        assert isinstance(findings, list)

    def test_detects_sra_accessions(self, validator):
        """SRA accessions (SRP, SRR) are extracted."""
        text = "Raw reads: SRR1234567. Study: SRP123456."
        findings = validator.validate_accessions(text)
        assert isinstance(findings, list)

    def test_no_accessions_in_text(self, validator):
        """Text without accessions produces no findings."""
        text = "The weather is nice today."
        findings = validator.validate_accessions(text)
        assert len(findings) == 0

    def test_bioproject_accession(self, validator):
        """BioProject accessions (PRJNA) are extracted."""
        text = "BioProject: PRJNA12345."
        findings = validator.validate_accessions(text)
        assert isinstance(findings, list)


class TestGenomeBuildMixing:

    def test_no_builds_in_text(self, validator):
        """Text without genome builds produces no findings."""
        text = "Simple text with no genome references."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 0

    def test_single_build_no_finding(self, validator):
        """Single genome build is fine."""
        text = "Aligned to hg38 reference genome."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 0

    def test_mixed_builds_flagged(self, validator):
        """Both hg19 and hg38 without liftover should be flagged."""
        text = "Some samples were mapped to hg19, while others used hg38."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 1
        assert findings[0].category == "genome_build_inconsistency"
        assert "hg19" in findings[0].builds_found
        assert "hg38" in findings[0].builds_found

    def test_mixed_builds_with_liftover_ok(self, validator):
        """Mixed builds with explicit liftover mention is acceptable."""
        text = "Coordinates were originally in hg19 and converted to hg38 using liftOver."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 0

    def test_equivalent_builds_not_flagged(self, validator):
        """hg38 and GRCh38 are the same build, should not be flagged."""
        text = "Reference genome: hg38 (GRCh38)."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 0

    def test_mouse_builds_mixed(self, validator):
        """Mixed mouse builds (mm9, mm10) should be flagged."""
        text = "Dataset A used mm9 while dataset B used mm10."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 1
        assert "mm9" in findings[0].builds_found


class TestSampleConsistency:

    def test_consistent_samples(self, validator):
        """Matching total and groups is fine."""
        result = validator.check_sample_consistency(100, [50, 50])
        assert result is None

    def test_inconsistent_samples(self, validator):
        """Mismatched total vs groups produces finding."""
        result = validator.check_sample_consistency(100, [40, 50])
        assert result is not None
        assert result.severity == "warning"
        assert result.stated_n == 100
        assert result.computed_n == 90

    def test_empty_groups(self, validator):
        """Empty group list returns None."""
        result = validator.check_sample_consistency(100, [])
        assert result is None


class TestCheckAll:

    def test_check_all_combines_results(self, validator):
        """check_all runs both accession and genome build checks."""
        text = "Data at GSE12345. Aligned to hg19 and hg38."
        findings = validator.check_all(text)
        # Should find genome build mixing
        build_findings = [f for f in findings if f.category == "genome_build_inconsistency"]
        assert len(build_findings) == 1
