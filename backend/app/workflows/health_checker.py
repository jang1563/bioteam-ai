"""HealthChecker — pre-flight API availability check for W9.

Runs lightweight probes before a long workflow starts so users know
immediately if required services are down rather than after 30 minutes
of compute.

Usage:
    issues = await HealthChecker.check_all([
        "ensembl_vep_api", "uniprot_api", "gprofiler", "ncbi_blast",
    ])
    # issues: list[HealthIssue] — empty = all good
"""

from __future__ import annotations

import importlib
import logging

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 8  # seconds per probe


class HealthIssue:
    """A single health check failure."""

    def __init__(self, service: str, message: str, severity: str = "warning") -> None:
        self.service = service
        self.message = message
        self.severity = severity  # "warning" | "error"

    def to_dict(self) -> dict:
        return {"service": self.service, "message": self.message, "severity": self.severity}

    def __repr__(self) -> str:
        return f"HealthIssue({self.service}: {self.message})"


class HealthChecker:
    """Static health-check registry for external services used by W9."""

    @classmethod
    async def check_all(cls, services: list[str]) -> list[HealthIssue]:
        """Run all requested health checks concurrently.

        Args:
            services: Names of services to check (see _CHECKS).

        Returns:
            List of HealthIssue objects. Empty = all healthy.
        """
        import asyncio

        tasks = []
        for svc in services:
            check_fn = cls._CHECKS.get(svc)
            if check_fn is None:
                logger.debug("No health check registered for: %s", svc)
                continue
            tasks.append(check_fn())

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        issues: list[HealthIssue] = []
        for r in results:
            if isinstance(r, HealthIssue):
                issues.append(r)
            elif isinstance(r, Exception):
                issues.append(HealthIssue("unknown", str(r), severity="error"))
        return issues

    @staticmethod
    async def _check_ensembl_vep() -> HealthIssue | None:
        """Probe Ensembl REST API /info/data endpoint."""
        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                resp = await client.get("https://rest.ensembl.org/info/data?content-type=application/json")
                if resp.status_code >= 400:
                    return HealthIssue("ensembl_vep_api", f"HTTP {resp.status_code}", severity="error")
        except httpx.TimeoutException:
            return HealthIssue("ensembl_vep_api", "Connection timeout", severity="warning")
        except Exception as e:
            return HealthIssue("ensembl_vep_api", str(e), severity="warning")
        return None

    @staticmethod
    async def _check_uniprot() -> HealthIssue | None:
        """Probe UniProt REST API with a known accession (P04637 = TP53)."""
        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                resp = await client.get(
                    "https://rest.uniprot.org/uniprotkb/P04637",
                    headers={"Accept": "application/json"},
                )
                if resp.status_code >= 400:
                    return HealthIssue("uniprot_api", f"HTTP {resp.status_code}", severity="error")
        except httpx.TimeoutException:
            return HealthIssue("uniprot_api", "Connection timeout", severity="warning")
        except Exception as e:
            return HealthIssue("uniprot_api", str(e), severity="warning")
        return None

    @staticmethod
    async def _check_gprofiler() -> HealthIssue | None:
        """Check if gprofiler-official is importable."""
        try:
            importlib.import_module("gprofiler")
        except ImportError:
            return HealthIssue(
                "gprofiler",
                "gprofiler-official not installed. Run: uv add gprofiler-official",
                severity="warning",
            )
        return None

    @staticmethod
    async def _check_ncbi_blast() -> HealthIssue | None:
        """Check if biopython BLAST module is importable."""
        try:
            importlib.import_module("Bio.Blast.NCBIWWW")
        except ImportError:
            return HealthIssue(
                "ncbi_blast",
                "biopython not installed. Run: uv add biopython",
                severity="warning",
            )
        return None

    @staticmethod
    async def _check_stringdb() -> HealthIssue | None:
        """Probe STRING DB API."""
        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                resp = await client.get(
                    "https://string-db.org/api/json/get_string_ids",
                    params={"identifiers": "TP53", "species": 9606, "limit": 1},
                )
                if resp.status_code >= 400:
                    return HealthIssue("stringdb", f"HTTP {resp.status_code}", severity="warning")
        except httpx.TimeoutException:
            return HealthIssue("stringdb", "Connection timeout", severity="warning")
        except Exception as e:
            return HealthIssue("stringdb", str(e), severity="warning")
        return None

    @staticmethod
    async def _check_data_files(file_paths: list[str] | None = None) -> HealthIssue | None:
        """Check that data manifest files exist on disk."""
        if not file_paths:
            return None
        from pathlib import Path
        missing = [p for p in file_paths if not Path(p).exists()]
        if missing:
            return HealthIssue(
                "data_files_exist",
                f"Missing files: {missing[:3]}{'...' if len(missing) > 3 else ''}",
                severity="error",
            )
        return None

    # Registry: service name → async check function
    _CHECKS: dict = {}


# Register checks after class definition
HealthChecker._CHECKS = {
    "ensembl_vep_api": HealthChecker._check_ensembl_vep,
    "uniprot_api": HealthChecker._check_uniprot,
    "gprofiler": HealthChecker._check_gprofiler,
    "ncbi_blast": HealthChecker._check_ncbi_blast,
    "stringdb": HealthChecker._check_stringdb,
}
