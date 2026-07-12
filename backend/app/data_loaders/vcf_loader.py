"""VCF file loader for genomic variants.

Parses standard VCF 4.x files without external dependencies.
For large VCF files, consider installing pysam for indexed access.

Usage:
    loader = VCFLoader()
    variants = loader.load("/data/variants.vcf")
    # [{chrom, pos, id, ref, alt, qual, filter, info_str}, ...]
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VCFLoader:
    """Lightweight VCF parser (no pysam dependency required)."""

    def load(
        self,
        vcf_path: str,
        max_variants: int = 10_000,
        filter_pass_only: bool = True,
        min_qual: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Parse a VCF file and return variant records.

        Args:
            vcf_path: Path to .vcf or .vcf.gz file.
            max_variants: Maximum variants to return.
            filter_pass_only: If True, only return FILTER=PASS or FILTER=. variants.
            min_qual: Minimum QUAL score (0 = no filter).

        Returns:
            List of variant dicts with chrom, pos, id, ref, alt, qual, filter, info_str.
        """
        path = Path(vcf_path)
        if not path.exists():
            raise FileNotFoundError(f"VCF file not found: {vcf_path}")

        variants = []
        open_fn = self._get_open_fn(path)

        with open_fn(str(path), "rt") as f:
            for line in f:
                if line.startswith("#"):
                    continue

                parts = line.strip().split("\t")
                if len(parts) < 8:
                    continue

                chrom, pos, var_id, ref, alt, qual_str, filt, info = parts[:8]

                # QUAL filter
                try:
                    qual = float(qual_str) if qual_str != "." else 0.0
                except ValueError:
                    qual = 0.0

                if min_qual > 0 and qual < min_qual:
                    continue

                # FILTER
                if filter_pass_only and filt not in ("PASS", "."):
                    continue

                try:
                    pos_int = int(pos)
                except ValueError:
                    continue  # skip malformed POS

                variants.append({
                    "chrom": chrom,
                    "pos": pos_int,
                    "id": var_id if var_id != "." else None,
                    "ref": ref,
                    "alt": alt,
                    "qual": qual,
                    "filter": filt,
                    "info_str": info,
                })

                if len(variants) >= max_variants:
                    logger.info("VCF truncated at %d variants", max_variants)
                    break

        return variants

    def get_header(self, vcf_path: str) -> dict[str, Any]:
        """Extract VCF header metadata."""
        path = Path(vcf_path)
        if not path.exists():
            raise FileNotFoundError(f"VCF file not found: {vcf_path}")

        meta_lines = []
        sample_names = []
        open_fn = self._get_open_fn(path)

        with open_fn(str(path), "rt") as f:
            for line in f:
                if line.startswith("##"):
                    meta_lines.append(line.strip())
                elif line.startswith("#CHROM"):
                    parts = line.strip().split("\t")
                    if len(parts) > 9:
                        sample_names = parts[9:]
                    break
                else:
                    break

        return {
            "meta_line_count": len(meta_lines),
            "sample_names": sample_names,
            "sample_count": len(sample_names),
        }

    @staticmethod
    def _get_open_fn(path: Path):
        """Return appropriate open function for .vcf vs .vcf.gz."""
        if path.suffix == ".gz" or str(path).endswith(".vcf.gz"):
            import gzip
            return gzip.open
        return open

    def to_hgvs_list(self, variants: list[dict], assembly: str = "GRCh38") -> list[str]:
        """Convert variant dicts to HGVS notation for VEP queries.

        Args:
            variants: List of variant dicts from load().
            assembly: Genome assembly (default GRCh38).

        Returns:
            List of HGVS strings (e.g., "9:g.107545939A>T").
        """
        hgvs_list = []
        for v in variants:
            chrom = v["chrom"].replace("chr", "")
            pos = v["pos"]
            ref = v["ref"]
            alt = v["alt"]

            # Simple SNV
            if len(ref) == 1 and len(alt) == 1:
                hgvs_list.append(f"{chrom}:g.{pos}{ref}>{alt}")
            else:
                # For indels, use region format
                hgvs_list.append(f"{chrom}:g.{pos}_{pos + len(ref) - 1}del{ref}ins{alt}")

        return hgvs_list
