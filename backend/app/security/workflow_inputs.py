"""Validation helpers for user-supplied workflow file paths.

The workflow API accepts file references for W8/W9 runs. To avoid treating the
server filesystem as an implicit upload API, these paths are restricted to a
small allowlist of roots that operators can configure explicitly.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Literal

from app.config import _PROJECT_ROOT, settings

WorkflowInputKind = Literal["w8", "w9"]

_W8_SUFFIXES = {".pdf", ".docx", ".doc"}
_W9_SUFFIXES = {".json", ".tsv", ".csv", ".txt", ".xlsx", ".vcf"}


def _configured_roots() -> list[Path]:
    roots: list[Path] = []
    raw_roots = [entry.strip() for entry in settings.workflow_input_roots.split(",") if entry.strip()]
    for raw_root in raw_roots:
        root = Path(raw_root).expanduser()
        if not root.is_absolute():
            root = (_PROJECT_ROOT / root)
        roots.append(root.resolve(strict=False))

    temp_root = Path(tempfile.gettempdir()).resolve(strict=False)
    if temp_root not in roots:
        roots.append(temp_root)
    legacy_tmp = Path("/tmp").resolve(strict=False)
    if legacy_tmp not in roots:
        roots.append(legacy_tmp)

    return roots


def allowed_workflow_input_roots() -> list[Path]:
    """Return the canonical allowlist of roots for workflow file inputs."""
    return list(_configured_roots())


def _is_supported_suffix(path: Path, kind: WorkflowInputKind) -> bool:
    if kind == "w8":
        return path.suffix.lower() in _W8_SUFFIXES

    suffix = path.suffix.lower()
    return suffix in _W9_SUFFIXES or str(path).lower().endswith(".vcf.gz")


def _is_within_roots(path: Path, roots: list[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def normalize_workflow_input_path(raw_path: str, *, kind: WorkflowInputKind) -> str:
    """Normalize and validate a workflow input path.

    Relative paths are resolved against the repository root. The returned string
    is always an absolute, canonical path suitable for storage.
    """
    if "://" in raw_path:
        raise ValueError("Workflow file paths must be local filesystem paths, not URLs")

    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = _PROJECT_ROOT / candidate

    normalized = candidate.resolve(strict=False)
    roots = allowed_workflow_input_roots()

    if not _is_supported_suffix(normalized, kind):
        if kind == "w8":
            raise ValueError("W8 inputs must be .pdf, .docx, or .doc files")
        raise ValueError("W9 inputs must be .json, .tsv, .csv, .txt, .xlsx, .vcf, or .vcf.gz files")

    if not _is_within_roots(normalized, roots):
        allowed = ", ".join(str(root) for root in roots)
        raise ValueError(f"Workflow file path must be under an allowed root: {allowed}")

    return str(normalized)
