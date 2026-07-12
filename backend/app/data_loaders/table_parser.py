"""Table parser for bioinformatics data files (TSV/CSV/Excel).

Auto-detects column names from common tools (DESeq2, edgeR, limma)
and normalizes them to a standard schema.

Usage:
    parser = TableParser()
    table = parser.parse("/data/degs.tsv")
    degs = table.to_deg_list()
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Column name aliases → standard name
_GENE_ALIASES = {"gene", "symbol", "gene_symbol", "gene_name", "geneid", "gene_id", "ensembl_id", "feature"}
_LOGFC_ALIASES = {"log2foldchange", "logfc", "log2fc", "lfc", "log_fc", "fc"}
_PADJ_ALIASES = {"padj", "fdr", "adj.p.val", "p.adjust", "q_value", "qvalue", "adj_pval", "adjusted_pvalue"}
_PVALUE_ALIASES = {"pvalue", "p_value", "pval", "p.value", "rawp"}
_BASEMEAN_ALIASES = {"basemean", "aveexpr", "logcpm", "mean_expression", "avgexpr"}


def _normalize_col(name: str) -> str | None:
    """Map a raw column name to a standard field name."""
    lower = name.strip().lower().replace(" ", "_").replace("-", "_")
    if lower in _GENE_ALIASES:
        return "gene"
    if lower in _LOGFC_ALIASES:
        return "log2FC"
    if lower in _PADJ_ALIASES:
        return "padj"
    if lower in _PVALUE_ALIASES:
        return "pvalue"
    if lower in _BASEMEAN_ALIASES:
        return "baseMean"
    return None


@dataclass
class ParsedTable:
    """Result of parsing a bioinformatics table file."""

    columns: list[str]                   # Original column names
    normalized_columns: dict[str, str]   # original_name → standard_name
    rows: list[dict[str, Any]]           # List of row dicts (original keys)
    file_path: str = ""
    detected_format: str = ""            # "deseq2", "edger", "limma", "generic"
    warnings: list[str] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def has_gene_column(self) -> bool:
        return "gene" in self.normalized_columns.values()

    @property
    def has_logfc_column(self) -> bool:
        return "log2FC" in self.normalized_columns.values()

    @property
    def has_padj_column(self) -> bool:
        return "padj" in self.normalized_columns.values()

    def _get_col(self, standard_name: str) -> str | None:
        """Get the original column name for a standard field."""
        for orig, norm in self.normalized_columns.items():
            if norm == standard_name:
                return orig
        return None

    def to_deg_list(self, padj_threshold: float = 0.05, logfc_threshold: float = 0.0) -> list[dict]:
        """Convert to DEG list format: [{gene, log2FC, padj, direction}, ...]."""
        gene_col = self._get_col("gene")
        logfc_col = self._get_col("log2FC")
        padj_col = self._get_col("padj")

        if not gene_col:
            return []

        degs = []
        for row in self.rows:
            gene = row.get(gene_col, "")
            if not gene:
                continue

            logfc = _safe_float(row.get(logfc_col)) if logfc_col else None
            padj = _safe_float(row.get(padj_col)) if padj_col else None

            # Apply thresholds
            if padj is not None and padj > padj_threshold:
                continue
            if logfc is not None and abs(logfc) < logfc_threshold:
                continue

            direction = "up" if (logfc is not None and logfc > 0) else "down" if (logfc is not None and logfc < 0) else "unknown"

            deg = {"gene": str(gene), "direction": direction}
            if logfc is not None:
                deg["log2FC"] = logfc
            if padj is not None:
                deg["padj"] = padj
            degs.append(deg)

        return degs

    def get_gene_list(self) -> list[str]:
        """Extract just the gene names/symbols."""
        gene_col = self._get_col("gene")
        if not gene_col:
            return []
        return [str(row[gene_col]) for row in self.rows if row.get(gene_col)]


def _safe_float(val: Any) -> float | None:
    if val is None or val == "" or val == "NA" or val == "nan":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _detect_format(normalized: dict[str, str], all_columns: list[str] | None = None) -> str:
    """Heuristic format detection based on column names.

    Checks original column names first to distinguish tools that
    normalize to the same standard fields (e.g. logCPM vs baseMean).
    """
    norms = set(normalized.values())
    orig_lower = {k.lower() for k in normalized.keys()}
    # Also include non-normalized columns for disambiguation
    if all_columns:
        orig_lower |= {c.lower() for c in all_columns}

    # Check tool-specific columns FIRST (before baseMean aggregation)
    if "log2FC" in norms and "padj" in norms:
        if "logcpm" in orig_lower:
            return "edger"
        if "aveexpr" in orig_lower or "adj.p.val" in orig_lower:
            return "limma"
        if "basemean" in orig_lower or "log2foldchange" in orig_lower:
            return "deseq2"
        return "generic_deg"
    if "gene" in norms:
        return "gene_list"
    return "generic"


class TableParser:
    """Auto-detecting bioinformatics table parser."""

    def parse(self, file_path: str, max_rows: int = 100_000) -> ParsedTable:
        """Parse a TSV/CSV file with auto-detected columns.

        Args:
            file_path: Path to TSV, CSV, or TXT file.
            max_rows: Maximum rows to load (default 100K).

        Returns:
            ParsedTable with normalized columns and data.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = path.suffix.lower()
        if suffix in (".xlsx", ".xls"):
            return self._parse_excel(path, max_rows)

        # TSV/CSV/TXT — auto-detect delimiter
        return self._parse_delimited(path, max_rows)

    def _parse_delimited(self, path: Path, max_rows: int) -> ParsedTable:
        """Parse TSV or CSV with auto-detected delimiter."""
        warnings: list[str] = []

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            # Sniff delimiter
            sample = f.read(4096)
            f.seek(0)

            try:
                dialect = csv.Sniffer().sniff(sample, delimiters="\t,;")
                delimiter = dialect.delimiter
            except csv.Error:
                delimiter = "\t"  # Default to TSV

            reader = csv.DictReader(f, delimiter=delimiter)
            columns = list(reader.fieldnames or [])

            if not columns:
                return ParsedTable(columns=[], normalized_columns={}, rows=[],
                                   file_path=str(path), warnings=["Empty file or no header"])

            # Normalize columns
            normalized = {}
            for col in columns:
                std = _normalize_col(col)
                if std:
                    normalized[col] = std

            # Read rows
            rows = []
            for i, row in enumerate(reader):
                if i >= max_rows:
                    warnings.append(f"Truncated at {max_rows} rows")
                    break
                rows.append(dict(row))

        if not rows:
            warnings.append("No data rows found")

        fmt = _detect_format(normalized, columns)

        return ParsedTable(
            columns=columns,
            normalized_columns=normalized,
            rows=rows,
            file_path=str(path),
            detected_format=fmt,
            warnings=warnings,
        )

    def _parse_excel(self, path: Path, max_rows: int) -> ParsedTable:
        """Parse Excel files (requires openpyxl)."""
        try:
            import openpyxl
        except ImportError:
            return ParsedTable(
                columns=[], normalized_columns={}, rows=[],
                file_path=str(path),
                warnings=["openpyxl not installed — cannot parse Excel files"],
            )

        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            return ParsedTable(columns=[], normalized_columns={}, rows=[],
                               file_path=str(path), warnings=["No active sheet"])

        rows_iter = ws.iter_rows(values_only=True)
        header = next(rows_iter, None)
        if not header:
            return ParsedTable(columns=[], normalized_columns={}, rows=[],
                               file_path=str(path), warnings=["Empty Excel file"])

        columns = [str(c) if c else f"col_{i}" for i, c in enumerate(header)]
        normalized = {}
        for col in columns:
            std = _normalize_col(col)
            if std:
                normalized[col] = std

        rows = []
        warnings = []
        for i, row_vals in enumerate(rows_iter):
            if i >= max_rows:
                warnings.append(f"Truncated at {max_rows} rows")
                break
            row = {columns[j]: v for j, v in enumerate(row_vals) if j < len(columns)}
            rows.append(row)

        wb.close()
        fmt = _detect_format(normalized, columns)

        return ParsedTable(
            columns=columns,
            normalized_columns=normalized,
            rows=rows,
            file_path=str(path),
            detected_format=fmt,
            warnings=warnings,
        )
