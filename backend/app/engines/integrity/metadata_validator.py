"""Metadata Validator — validates GEO/SRA accessions, genome builds, sample sizes.

Deterministic engine: no LLM calls. Uses regex patterns and heuristic
rules to detect metadata errors in biological datasets.
"""

from __future__ import annotations

import logging
import re

from app.engines.integrity.finding_models import (
    AccessionFinding,
    GenomeBuildFinding,
    IntegrityFinding,
    SampleSizeFinding,
)

logger = logging.getLogger(__name__)

# GEO accession patterns
_GEO_PATTERNS = {
    "GSE": re.compile(r"\bGSE\d{1,8}\b"),       # Series
    "GSM": re.compile(r"\bGSM\d{1,8}\b"),       # Sample
    "GPL": re.compile(r"\bGPL\d{1,6}\b"),        # Platform
    "GDS": re.compile(r"\bGDS\d{1,6}\b"),        # Dataset
}

# SRA accession patterns
_SRA_PATTERNS = {
    "SRP": re.compile(r"\bSRP\d{6,9}\b"),        # Study
    "SRR": re.compile(r"\bSRR\d{6,12}\b"),       # Run
    "SRX": re.compile(r"\bSRX\d{6,9}\b"),        # Experiment
    "SRS": re.compile(r"\bSRS\d{6,9}\b"),        # Sample
    "PRJNA": re.compile(r"\bPRJNA\d{5,9}\b"),    # BioProject
    "SAMN": re.compile(r"\bSAMN\d{7,10}\b"),     # BioSample
}

# Genome build references
_GENOME_BUILDS = {
    "human": {
        "hg19": re.compile(r"\bhg19\b", re.IGNORECASE),
        "hg38": re.compile(r"\bhg38\b", re.IGNORECASE),
        "GRCh37": re.compile(r"\bGRCh37\b", re.IGNORECASE),
        "GRCh38": re.compile(r"\bGRCh38\b", re.IGNORECASE),
        "T2T-CHM13": re.compile(r"\bT2T[-_]?CHM13\b", re.IGNORECASE),
    },
    "mouse": {
        "mm9": re.compile(r"\bmm9\b", re.IGNORECASE),
        "mm10": re.compile(r"\bmm10\b", re.IGNORECASE),
        "mm39": re.compile(r"\bmm39\b", re.IGNORECASE),
        "GRCm38": re.compile(r"\bGRCm38\b", re.IGNORECASE),
        "GRCm39": re.compile(r"\bGRCm39\b", re.IGNORECASE),
    },
}

# Equivalent builds (for cross-referencing)
_EQUIVALENT_BUILDS: dict[str, str] = {
    "hg19": "GRCh37",
    "GRCh37": "hg19",
    "hg38": "GRCh38",
    "GRCh38": "hg38",
    "mm10": "GRCm38",
    "GRCm38": "mm10",
    "mm39": "GRCm39",
    "GRCm39": "mm39",
}


class MetadataValidator:
    """Validates data repository metadata and cross-references.

    Checks:
    1. GEO/SRA accession format validity
    2. Genome build consistency (no hg19/hg38 mixing)
    3. Sample size plausibility
    """

    def validate_accessions(self, text: str) -> list[IntegrityFinding]:
        """Extract and validate GEO/SRA accessions from text.

        Currently checks format validity only (not whether accessions
        actually exist in the database — that would require API calls).
        """
        findings: list[IntegrityFinding] = []
        found_accessions: list[dict] = []

        # Extract GEO accessions
        for acc_type, pattern in _GEO_PATTERNS.items():
            for match in pattern.finditer(text):
                found_accessions.append({
                    "accession": match.group(0),
                    "type": "GEO",
                    "prefix": acc_type,
                })

        # Extract SRA accessions
        for acc_type, pattern in _SRA_PATTERNS.items():
            for match in pattern.finditer(text):
                found_accessions.append({
                    "accession": match.group(0),
                    "type": "SRA",
                    "prefix": acc_type,
                })

        # Check for suspicious patterns
        # e.g., GSE followed by too few digits might be incomplete
        for acc in found_accessions:
            accession = acc["accession"]
            # Very short numeric part might be incomplete
            num_part = accession.lstrip("GSEMLPDSRXNPRJNA")
            if len(num_part) < 3 and acc["prefix"] not in ("GPL", "GDS"):
                findings.append(
                    AccessionFinding(
                        severity="info",
                        title=f"Possibly incomplete accession: {accession}",
                        description=f"Accession {accession} has a very short numeric part.",
                        source_text=accession,
                        suggestion="Verify the full accession number.",
                        confidence=0.5,
                        checker="metadata_validator",
                        accession=accession,
                        accession_type=acc["type"],
                    )
                )

        return findings

    def check_genome_build_mixing(self, text: str) -> list[IntegrityFinding]:
        """Check for inconsistent genome build references in text.

        Flags when both hg19 and hg38 (or mm9 and mm10) are mentioned
        without explicit liftover/conversion context.
        """
        findings: list[IntegrityFinding] = []

        for organism, builds in _GENOME_BUILDS.items():
            found_builds: list[str] = []
            for build_name, pattern in builds.items():
                if pattern.search(text):
                    found_builds.append(build_name)

            if len(found_builds) < 2:
                continue

            # Filter out equivalent names (hg38 and GRCh38 are the same)
            unique_builds: set[str] = set()
            for b in found_builds:
                canonical = min(b, _EQUIVALENT_BUILDS.get(b, b))
                unique_builds.add(canonical)

            if len(unique_builds) >= 2:
                # Check if "liftover" or "crossmap" is mentioned (explicit conversion)
                has_liftover = bool(
                    re.search(r"\b(liftover|lift[-_]?over|crossmap|convert)\b", text, re.IGNORECASE)
                )

                if not has_liftover:
                    findings.append(
                        GenomeBuildFinding(
                            severity="warning",
                            title=f"Mixed genome builds: {', '.join(found_builds)}",
                            description=(
                                f"Multiple {organism} genome builds referenced: {', '.join(found_builds)}. "
                                f"No liftover/conversion mention found. This may indicate "
                                f"coordinate system inconsistency."
                            ),
                            source_text=", ".join(found_builds),
                            suggestion=(
                                "Ensure all genomic coordinates use the same reference build, "
                                "or explicitly document liftover steps."
                            ),
                            confidence=0.7,
                            checker="metadata_validator",
                            builds_found=found_builds,
                        )
                    )

        return findings

    def check_sample_consistency(
        self,
        stated_n: int,
        group_sizes: list[int],
    ) -> SampleSizeFinding | None:
        """Check if stated total sample size matches sum of group sizes.

        Returns a finding if there's a mismatch, None otherwise.
        """
        if not group_sizes:
            return None

        computed_n = sum(group_sizes)
        if computed_n == stated_n:
            return None

        return SampleSizeFinding(
            severity="warning",
            title=f"Sample size mismatch: stated N={stated_n}, computed N={computed_n}",
            description=(
                f"Stated total sample size is {stated_n}, but the sum of group sizes "
                f"({' + '.join(str(g) for g in group_sizes)}) = {computed_n}."
            ),
            source_text=f"N={stated_n}",
            suggestion="Verify the total sample size against individual group sizes.",
            confidence=0.9,
            checker="metadata_validator",
            stated_n=stated_n,
            computed_n=computed_n,
        )

    def check_all(self, text: str) -> list[IntegrityFinding]:
        """Run all metadata validation checks on text."""
        findings: list[IntegrityFinding] = []
        findings.extend(self.validate_accessions(text))
        findings.extend(self.check_genome_build_mixing(text))
        return findings
