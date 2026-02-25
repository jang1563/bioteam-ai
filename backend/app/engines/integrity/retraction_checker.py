"""Retraction Checker — checks retraction/correction status of referenced papers.

Wraps CrossrefClient and PubPeerClient into a unified checker interface
that produces IntegrityFinding objects.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.engines.integrity.finding_models import (
    IntegrityFinding,
    PubPeerStatus,
    RetractionFinding,
    RetractionStatus,
)

if TYPE_CHECKING:
    from app.integrations.crossref import CrossrefClient
    from app.integrations.pubpeer import PubPeerClient

logger = logging.getLogger(__name__)


class RetractionChecker:
    """Checks referenced DOIs for retraction/correction status and PubPeer commentary.

    Produces IntegrityFinding objects for:
    - Retracted papers (critical severity)
    - Corrected papers (warning severity)
    - Expression of concern (error severity)
    - PubPeer-flagged papers (info severity)
    """

    def __init__(
        self,
        crossref_client: CrossrefClient | None = None,
        pubpeer_client: PubPeerClient | None = None,
    ) -> None:
        self._crossref = crossref_client
        self._pubpeer = pubpeer_client

    async def check_doi(self, doi: str) -> list[IntegrityFinding]:
        """Check a single DOI and return any integrity findings."""
        findings: list[IntegrityFinding] = []

        # Crossref check
        if self._crossref:
            status = await self._crossref.check_retraction(doi)
            findings.extend(self._crossref_to_findings(status))

        # PubPeer check
        if self._pubpeer:
            pp_status = await self._pubpeer.check_doi(doi)
            finding = self._pubpeer_to_finding(pp_status)
            if finding:
                findings.append(finding)

        return findings

    async def check_batch(self, dois: list[str]) -> list[IntegrityFinding]:
        """Check multiple DOIs and return all findings."""
        all_findings: list[IntegrityFinding] = []
        for doi in dois:
            findings = await self.check_doi(doi)
            all_findings.extend(findings)
        return all_findings

    def _crossref_to_findings(self, status: RetractionStatus) -> list[IntegrityFinding]:
        """Convert a RetractionStatus to IntegrityFinding objects."""
        findings: list[IntegrityFinding] = []

        if status.is_retracted:
            findings.append(
                RetractionFinding(
                    category="retracted_reference",
                    severity="critical",
                    title=f"Retracted paper: {status.doi}",
                    description=(
                        f"DOI {status.doi} has been retracted."
                        + (f" Retraction notice: {status.retraction_doi}" if status.retraction_doi else "")
                    ),
                    source_text=status.doi,
                    suggestion="Remove or flag this reference as retracted.",
                    confidence=0.99,
                    checker="retraction_checker",
                    doi=status.doi,
                    retraction_status=status,
                )
            )

        if status.is_corrected:
            findings.append(
                RetractionFinding(
                    category="corrected_reference",
                    severity="warning",
                    title=f"Corrected paper: {status.doi}",
                    description=(
                        f"DOI {status.doi} has a published correction."
                        + (f" Correction: {status.correction_doi}" if status.correction_doi else "")
                    ),
                    source_text=status.doi,
                    suggestion="Check the correction notice for impact on cited conclusions.",
                    confidence=0.95,
                    checker="retraction_checker",
                    doi=status.doi,
                    retraction_status=status,
                )
            )

        if status.has_expression_of_concern:
            findings.append(
                RetractionFinding(
                    category="retracted_reference",
                    severity="error",
                    title=f"Expression of concern: {status.doi}",
                    description=f"DOI {status.doi} has an expression of concern from the publisher.",
                    source_text=status.doi,
                    suggestion="Review the expression of concern before relying on this paper.",
                    confidence=0.95,
                    checker="retraction_checker",
                    doi=status.doi,
                    retraction_status=status,
                )
            )

        return findings

    def _pubpeer_to_finding(self, status: PubPeerStatus) -> IntegrityFinding | None:
        """Convert PubPeer status to an IntegrityFinding if there are comments."""
        if not status.has_comments:
            return None

        return IntegrityFinding(
            category="pubpeer_flagged",
            severity="info",
            title=f"PubPeer commentary: {status.doi}",
            description=(
                f"DOI {status.doi} has {status.comment_count} PubPeer comment(s). "
                f"See: {status.url}"
            ),
            source_text=status.doi,
            suggestion="Review PubPeer comments for potential integrity concerns.",
            confidence=0.6,
            checker="retraction_checker",
            metadata={"pubpeer_url": status.url, "comment_count": status.comment_count},
        )
