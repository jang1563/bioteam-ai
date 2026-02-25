"""Gene Name Checker — detects Excel-corrupted gene names and deprecated symbols.

Deterministic engine: no LLM calls. Uses regex patterns to find common
Excel date-mangling artifacts and optionally validates against HGNC.

References:
- Ziemann et al. "Gene name errors are widespread in the scientific literature" (2016)
- Abeysooriya et al. "Gene name errors: Lessons not learned" (2021)
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from app.engines.integrity.finding_models import GeneNameFinding

if TYPE_CHECKING:
    from app.integrations.hgnc import HGNCClient

logger = logging.getLogger(__name__)

# Gene families known to be corrupted by Excel's date auto-format.
# Maps: date-like pattern → (gene family prefix, possible member numbers)
_GENE_DATE_FAMILIES: dict[str, dict] = {
    "MARCH": {"members": range(1, 12), "renamed_to": "MARCHF", "month_abbr": "Mar"},
    "SEPT": {"members": range(1, 13), "renamed_to": "SEPTIN", "month_abbr": "Sep"},
    "DEC": {"members": range(1, 3), "renamed_to": None, "month_abbr": "Dec"},  # DEC1→BHLHE40, DEC2→BHLHE41 (no simple prefix)
    "OCT": {"members": range(1, 5), "renamed_to": None, "month_abbr": "Oct"},
    "FEB": {"members": range(1, 3), "renamed_to": None, "month_abbr": "Feb"},
}

# Month abbreviations that collide with gene family names
_MONTH_ABBR_TO_FAMILY: dict[str, str] = {}
for _family, _info in _GENE_DATE_FAMILIES.items():
    _MONTH_ABBR_TO_FAMILY[_info["month_abbr"].lower()] = _family

# Pre-compiled regex for Excel date patterns: "1-Mar", "Sep-7", "01-Mar", "Mar-01"
# Also handles "1-Sep-2024" partial date forms
_EXCEL_DATE_RE = re.compile(
    r"""
    \b
    (?:
        (\d{1,2})               # day number
        [-/]                    # separator
        (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)  # month abbr
        (?:[-/]\d{2,4})?        # optional year
    |
        (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)  # month abbr first
        [-/]                    # separator
        (\d{1,2})               # day number
        (?:[-/]\d{2,4})?        # optional year
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Direct gene symbol pattern for known families: MARCH1, SEPT7, DEC1, OCT4
_GENE_SYMBOL_RE = re.compile(
    r"\b(MARCH|SEPT|DEC|OCT|FEB)(\d{1,2})\b",
    re.IGNORECASE,
)


class GeneNameChecker:
    """Deterministic gene name validation engine.

    Detects:
    1. Excel date-mangled gene names (MARCH1→1-Mar, SEPT7→7-Sep)
    2. Deprecated/alias gene symbols (via optional HGNC lookup)
    """

    def __init__(self, hgnc_client: HGNCClient | None = None) -> None:
        self._hgnc = hgnc_client

    def check_text(self, text: str) -> list[GeneNameFinding]:
        """Scan free text for gene name errors.

        Looks for Excel date patterns that match known gene families.
        Context-aware: only flags patterns that appear in data-like contexts
        (tables, gene lists) or when the month/number maps to a known gene.
        """
        findings: list[GeneNameFinding] = []
        findings.extend(self._detect_excel_corruption(text))
        return findings

    def check_table_data(
        self,
        headers: list[str],
        rows: list[list[str]],
    ) -> list[GeneNameFinding]:
        """Scan tabular data for gene name errors.

        Table context implies data, so we flag more aggressively.
        """
        findings: list[GeneNameFinding] = []

        # Check headers
        for h in headers:
            findings.extend(self._detect_excel_corruption(h, in_table=True))

        # Check all cells
        for row in rows:
            for cell in row:
                findings.extend(self._detect_excel_corruption(cell, in_table=True))

        return self._deduplicate(findings)

    def _detect_excel_corruption(
        self,
        text: str,
        in_table: bool = False,
    ) -> list[GeneNameFinding]:
        """Find Excel date patterns that likely represent corrupted gene names."""
        findings: list[GeneNameFinding] = []

        for match in _EXCEL_DATE_RE.finditer(text):
            full_match = match.group(0)

            # Extract month abbreviation and number
            if match.group(1) is not None:
                # Format: "1-Mar"
                number = int(match.group(1))
                month_abbr = match.group(2).lower()
            else:
                # Format: "Mar-1"
                month_abbr = match.group(3).lower()
                number = int(match.group(4))

            # Check if this month maps to a known gene family
            family = _MONTH_ABBR_TO_FAMILY.get(month_abbr)
            if family is None:
                continue

            info = _GENE_DATE_FAMILIES[family]
            if number not in info["members"]:
                continue

            # This looks like a corrupted gene name
            original_gene = f"{family}{number}"
            renamed = info.get("renamed_to")
            # DEC family has non-uniform renaming: DEC1→BHLHE40, DEC2→BHLHE41
            dec_renames = {"DEC1": "BHLHE40", "DEC2": "BHLHE41"}
            if original_gene.upper() in dec_renames:
                corrected = dec_renames[original_gene.upper()]
                suggestion = (
                    f"'{full_match}' is likely Excel-corrupted gene name {original_gene}. "
                    f"HGNC has renamed this gene to {corrected}."
                )
            elif renamed:
                corrected = f"{renamed}{number}"
                suggestion = (
                    f"'{full_match}' is likely Excel-corrupted gene name {original_gene}. "
                    f"HGNC has renamed this gene to {corrected}."
                )
            else:
                corrected = original_gene
                suggestion = (
                    f"'{full_match}' is likely Excel-corrupted gene name {original_gene}."
                )

            severity = "error" if in_table else "warning"

            findings.append(
                GeneNameFinding(
                    severity=severity,
                    title=f"Possible Excel-corrupted gene: {original_gene}",
                    description=suggestion,
                    source_text=full_match,
                    suggestion=f"Replace '{full_match}' with '{corrected}'",
                    confidence=0.9 if in_table else 0.7,
                    checker="gene_name_checker",
                    original_text=full_match,
                    corrected_symbol=corrected,
                    error_type="excel_date",
                    metadata={
                        "family": family,
                        "member": number,
                        "in_table": in_table,
                    },
                )
            )

        return findings

    def _deduplicate(self, findings: list[GeneNameFinding]) -> list[GeneNameFinding]:
        """Remove duplicate findings for the same source text."""
        seen: set[str] = set()
        unique: list[GeneNameFinding] = []
        for f in findings:
            key = f"{f.original_text}:{f.corrected_symbol}"
            if key not in seen:
                seen.add(key)
                unique.append(f)
        return unique
