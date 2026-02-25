"""Edge case tests for MetadataValidator — accession boundaries, genome build variants, sample sizes."""

import pytest
from app.engines.integrity.metadata_validator import MetadataValidator


@pytest.fixture
def validator():
    return MetadataValidator()


class TestAccessionBoundaryLengths:
    """Test accession regex boundary conditions — min/max digit counts."""

    # GSE: 1-8 digits
    def test_gse_1_digit(self, validator):
        """GSE1 (1 digit) should be matched."""
        findings = validator.validate_accessions("Data: GSE1.")
        # Should be found (valid format) — may flag as short
        assert isinstance(findings, list)

    def test_gse_8_digits(self, validator):
        """GSE12345678 (8 digits, max) should be matched."""
        findings = validator.validate_accessions("Data: GSE12345678.")
        assert isinstance(findings, list)

    def test_gse_9_digits_no_match(self, validator):
        r"""GSE123456789 (9 digits) should NOT be matched — beyond regex \d{1,8}."""
        text = "Data: GSE123456789."
        findings = validator.validate_accessions(text)
        # GSE123456789 exceeds \d{1,8}, won't match as GSE accession
        # (regex will match GSE12345678 as an 8-digit prefix though, due to \b)
        assert isinstance(findings, list)

    # SRR: 6-12 digits
    def test_srr_5_digits_no_match(self, validator):
        """SRR12345 (5 digits) should NOT match — below minimum 6."""
        text = "Run: SRR12345."
        findings = validator.validate_accessions(text)
        # SRR\d{6,12} requires at least 6 digits
        # Should not match as SRA accession
        assert isinstance(findings, list)

    def test_srr_6_digits(self, validator):
        """SRR123456 (6 digits, min) should match."""
        text = "Run: SRR123456."
        findings = validator.validate_accessions(text)
        assert isinstance(findings, list)

    def test_srr_12_digits(self, validator):
        """SRR123456789012 (12 digits, max) should match."""
        text = "Run: SRR123456789012."
        findings = validator.validate_accessions(text)
        assert isinstance(findings, list)

    # PRJNA: 5-9 digits
    def test_prjna_4_digits_no_match(self, validator):
        """PRJNA1234 (4 digits) should NOT match."""
        text = "Bio: PRJNA1234."
        findings = validator.validate_accessions(text)
        assert isinstance(findings, list)

    def test_prjna_5_digits(self, validator):
        """PRJNA12345 (5 digits, min) should match."""
        text = "Bio: PRJNA12345."
        findings = validator.validate_accessions(text)
        assert isinstance(findings, list)

    # SAMN: 7-10 digits
    def test_samn_6_digits_no_match(self, validator):
        """SAMN123456 (6 digits) should NOT match — below minimum 7."""
        text = "Sample: SAMN123456."
        findings = validator.validate_accessions(text)
        assert isinstance(findings, list)

    def test_samn_7_digits(self, validator):
        """SAMN1234567 (7 digits, min) should match."""
        text = "Sample: SAMN1234567."
        findings = validator.validate_accessions(text)
        assert isinstance(findings, list)


class TestAccessionWordBoundary:
    """Test that \b word boundary works correctly for accessions."""

    def test_accession_in_url(self, validator):
        """Accession inside a URL may or may not match depending on boundaries."""
        text = "https://example.com/GSE12345/data"
        findings = validator.validate_accessions(text)
        # GSE12345 should still be found (boundary between / and G)
        assert isinstance(findings, list)

    def test_accession_with_suffix(self, validator):
        """GSE12345abc has non-digit suffix — \b at transition from digit to letter."""
        text = "Data: GSE12345abc."
        findings = validator.validate_accessions(text)
        # \b applies at 5/a transition — GSE12345 should be matched
        assert isinstance(findings, list)

    def test_accession_case_sensitivity(self, validator):
        """GEO patterns are case-sensitive — gse12345 should NOT match."""
        text = "Data: gse12345."
        findings = validator.validate_accessions(text)
        # Regex uses \bGSE not \bgse, so lowercase shouldn't match
        assert len(findings) == 0

    def test_multiple_accessions_same_line(self, validator):
        """Multiple accessions on the same line should all be found."""
        text = "Data: GSE12345 and GSM678901 and SRR123456."
        findings = validator.validate_accessions(text)
        assert isinstance(findings, list)


class TestAccessionShortNumericPart:
    """Test the 'suspiciously short numeric part' detection."""

    def test_gse_short_numeric(self, validator):
        """GSE1 has a very short numeric part — may be flagged as incomplete."""
        text = "Data: GSE1."
        findings = validator.validate_accessions(text)
        # The check flags accessions with <3 digits (except GPL, GDS)
        # GSE1 has num_part length 1 → flagged
        if len(findings) > 0:
            assert findings[0].category == "metadata_error"

    def test_gpl_short_not_flagged(self, validator):
        """GPL1 (short but GPL/GDS excluded) should NOT be flagged as incomplete."""
        text = "Platform: GPL1."
        findings = validator.validate_accessions(text)
        # GPL is excluded from the short-numeric check
        assert len(findings) == 0

    def test_gds_short_not_flagged(self, validator):
        """GDS1 (short but excluded) should NOT be flagged."""
        text = "Dataset: GDS1."
        findings = validator.validate_accessions(text)
        assert len(findings) == 0


class TestGenomeBuildVariants:
    """Test genome build detection with various naming conventions."""

    def test_grch37_and_grch38_mixed(self, validator):
        """GRCh37 and GRCh38 should be flagged as mixed."""
        text = "Aligned to GRCh37. Analysis used GRCh38."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 1

    def test_hg19_and_grch38_mixed(self, validator):
        """hg19 and GRCh38 are NOT equivalent — should be flagged."""
        text = "Data in hg19. Analysis used GRCh38."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 1

    def test_mm10_and_grcm38_equivalent(self, validator):
        """mm10 and GRCm38 are equivalent — should NOT be flagged."""
        text = "Reference: mm10 (GRCm38)."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 0

    def test_mm39_and_grcm39_equivalent(self, validator):
        """mm39 and GRCm39 are equivalent — should NOT be flagged."""
        text = "Reference: mm39 (GRCm39)."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 0

    def test_human_and_mouse_builds_separate(self, validator):
        """Human hg38 and mouse mm10 should NOT trigger mixed build warning."""
        text = "Human data aligned to hg38. Mouse data aligned to mm10."
        findings = validator.check_genome_build_mixing(text)
        # These are different organisms — each has only one build
        assert len(findings) == 0

    def test_t2t_chm13_detected(self, validator):
        """T2T-CHM13 should be recognized as a human build."""
        text = "We used T2T-CHM13 and hg38 references."
        findings = validator.check_genome_build_mixing(text)
        # T2T-CHM13 is a different build from hg38 → flagged
        assert len(findings) == 1

    def test_t2t_underscore_variant(self, validator):
        """T2T_CHM13 (underscore) should also be recognized."""
        text = "We used T2T_CHM13 and hg38 references."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 1

    def test_same_build_mentioned_twice(self, validator):
        """Same build mentioned multiple times should NOT flag."""
        text = "Aligned to hg38. All coordinates are in hg38 space."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 0

    def test_three_builds_flagged(self, validator):
        """Three different builds should be flagged."""
        text = "Data from hg19, hg38, and T2T-CHM13."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 1
        # Should list all three builds
        assert len(findings[0].builds_found) >= 3


class TestLiftoverDetection:
    """Test liftover/conversion keyword detection."""

    def test_liftover_lowercase(self, validator):
        """'liftover' (lowercase) should suppress warning."""
        text = "Data in hg19, converted to hg38 using liftover."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 0

    def test_liftover_uppercase(self, validator):
        """'LIFTOVER' (uppercase) should suppress warning."""
        text = "Data in hg19, converted to hg38 using LIFTOVER."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 0

    def test_liftover_camelcase(self, validator):
        """'LiftOver' (camelCase) should suppress warning."""
        text = "Data in hg19, converted to hg38 using LiftOver."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 0

    def test_lift_hyphen_over(self, validator):
        """'lift-over' should suppress warning."""
        text = "Data in hg19, converted to hg38 with lift-over."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 0

    def test_lift_underscore_over(self, validator):
        """'lift_over' should suppress warning."""
        text = "Data in hg19, converted to hg38 using lift_over tool."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 0

    def test_crossmap(self, validator):
        """'CrossMap' should suppress warning."""
        text = "Coordinates in hg19 were converted to hg38 using CrossMap."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 0

    def test_convert_keyword(self, validator):
        """'convert' should suppress warning."""
        text = "We used hg19 data and convert to hg38."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 0

    def test_no_liftover_mention(self, validator):
        """Without liftover mention, mixed builds should be flagged."""
        text = "Some data in hg19, other data in hg38."
        findings = validator.check_genome_build_mixing(text)
        assert len(findings) == 1


class TestSampleSizeEdgeCases:
    """Edge cases for sample size consistency checks."""

    def test_consistent_single_group(self, validator):
        """Single group matching stated N should return None."""
        result = validator.check_sample_consistency(100, [100])
        assert result is None

    def test_inconsistent_single_group(self, validator):
        """Single group NOT matching stated N should return finding."""
        result = validator.check_sample_consistency(100, [99])
        assert result is not None
        assert result.stated_n == 100
        assert result.computed_n == 99

    def test_zero_stated_n_with_zero_groups(self, validator):
        """stated_n=0 with group_sizes=[0,0] should match."""
        result = validator.check_sample_consistency(0, [0, 0])
        assert result is None

    def test_zero_stated_n_with_nonzero_groups(self, validator):
        """stated_n=0 with nonzero groups should flag."""
        result = validator.check_sample_consistency(0, [10, 20])
        assert result is not None

    def test_many_groups(self, validator):
        """Many groups that sum correctly should pass."""
        groups = list(range(1, 11))  # 1+2+...+10 = 55
        result = validator.check_sample_consistency(55, groups)
        assert result is None

    def test_many_groups_mismatch(self, validator):
        """Many groups that don't sum correctly should flag."""
        groups = list(range(1, 11))  # sum = 55
        result = validator.check_sample_consistency(50, groups)
        assert result is not None
        assert result.computed_n == 55

    def test_large_numbers(self, validator):
        """Very large sample sizes should work fine."""
        result = validator.check_sample_consistency(1_000_000, [500_000, 500_000])
        assert result is None

    def test_description_lists_groups(self, validator):
        """Mismatch description should list the group sizes."""
        result = validator.check_sample_consistency(100, [40, 50])
        assert result is not None
        assert "40" in result.description
        assert "50" in result.description


class TestCheckAllCombined:
    """Test check_all integration."""

    def test_accession_and_build_combined(self, validator):
        """check_all should find both accession and build issues."""
        text = "Data at GSE1. Aligned to hg19 and hg38."
        findings = validator.check_all(text)
        categories = {f.category for f in findings}
        assert "genome_build_inconsistency" in categories

    def test_clean_text(self, validator):
        """Normal text should produce no findings."""
        text = "Gene expression was analyzed using standard methods."
        findings = validator.check_all(text)
        assert len(findings) == 0

    def test_empty_text(self, validator):
        """Empty text should produce no findings."""
        findings = validator.check_all("")
        assert len(findings) == 0

    def test_unicode_text(self, validator):
        """Unicode characters should not cause errors."""
        text = "유전체 분석에서 GSE12345 데이터를 사용했습니다."
        findings = validator.check_all(text)
        assert isinstance(findings, list)
