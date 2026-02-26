"""Citation Validator — deterministic post-processing for claim-source fidelity.

v4.2: Addresses researcher trust concern (CRITICAL).
Cross-references every citation in agent-generated synthesis against
the actual search results retrieved during the workflow.

No LLM calls — purely deterministic string matching and DOI/PMID lookup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class CitationIssue:
    """A single citation validation issue."""

    citation_ref: str               # DOI, PMID, or inline reference
    issue_type: str                 # "not_in_search_results" | "doi_mismatch" | "hallucinated" | "unverifiable"
    context: str = ""               # Surrounding text where citation appears
    suggestion: str = ""            # Suggested fix


@dataclass
class CitationReport:
    """Result of citation validation for a synthesis output."""

    total_citations: int = 0
    verified: int = 0
    issues: list[CitationIssue] = field(default_factory=list)

    @property
    def unverified_count(self) -> int:
        return self.total_citations - self.verified

    @property
    def verification_rate(self) -> float:
        if self.total_citations == 0:
            return 1.0
        return self.verified / self.total_citations

    @property
    def is_clean(self) -> bool:
        return len(self.issues) == 0


class CitationValidator:
    """Validates citations in agent-generated text against known sources.

    Usage:
        validator = CitationValidator()
        validator.register_sources(search_results)  # From W1 SEARCH step
        report = validator.validate(synthesis_text)
        if not report.is_clean:
            # Flag for human review or re-run
    """

    def __init__(self) -> None:
        self._known_dois: set[str] = set()
        self._known_pmids: set[str] = set()
        self._known_titles: set[str] = set()        # Lowercase, stripped
        self._known_authors: set[str] = set()        # Lowercase last names

    def register_sources(self, sources: list[dict]) -> None:
        """Register papers retrieved during the workflow search step.

        Args:
            sources: List of paper metadata dicts. Expected keys:
                     doi, pmid, title, authors (list of str).
        """
        for s in sources:
            if doi := s.get("doi"):
                self._known_dois.add(self._normalize_doi(doi))
            if pmid := s.get("pmid"):
                self._known_pmids.add(str(pmid).strip())
            if title := s.get("title"):
                self._known_titles.add(title.strip().lower())
            for author in s.get("authors", []):
                if author:
                    # Extract last name (simple heuristic: last space-separated token)
                    parts = author.strip().split()
                    if parts:
                        self._known_authors.add(parts[-1].lower())

    def validate(self, text: str, inline_refs: list[dict] | None = None) -> CitationReport:
        """Validate citations in synthesized text.

        Args:
            text: The synthesis text containing citations.
            inline_refs: Optional structured citation list. Each dict has:
                         doi, pmid, title, first_author.

        Returns:
            CitationReport with verification results and issues.
        """
        report = CitationReport()

        if inline_refs:
            report.total_citations = len(inline_refs)
            for ref in inline_refs:
                verified = self._verify_ref(ref)
                if verified:
                    report.verified += 1
                else:
                    issue = CitationIssue(
                        citation_ref=ref.get("doi") or ref.get("pmid") or ref.get("title", "unknown"),
                        issue_type="not_in_search_results",
                        context=ref.get("title", ""),
                        suggestion="Verify this citation was in the original search results.",
                    )
                    report.issues.append(issue)
        else:
            # Extract DOIs from text and validate
            dois = self._extract_dois(text)
            pmids = self._extract_pmids(text)
            all_refs = [(d, "doi") for d in dois] + [(p, "pmid") for p in pmids]
            report.total_citations = len(all_refs)

            for ref_id, ref_type in all_refs:
                if ref_type == "doi" and self._normalize_doi(ref_id) in self._known_dois:
                    report.verified += 1
                elif ref_type == "pmid" and ref_id in self._known_pmids:
                    report.verified += 1
                else:
                    report.issues.append(CitationIssue(
                        citation_ref=ref_id,
                        issue_type="not_in_search_results",
                        suggestion=f"This {ref_type.upper()} was not found in search results.",
                    ))

        return report

    def _verify_ref(self, ref: dict) -> bool:
        """Check if a structured reference matches any known source."""
        if doi := ref.get("doi"):
            if self._normalize_doi(doi) in self._known_dois:
                return True
        if pmid := ref.get("pmid"):
            if str(pmid).strip() in self._known_pmids:
                return True
        if title := ref.get("title"):
            if title.strip().lower() in self._known_titles:
                return True
        if first_author := ref.get("first_author"):
            if first_author.strip().lower() in self._known_authors:
                return True
        return False

    @staticmethod
    def _normalize_doi(doi: str) -> str:
        """Normalize DOI to lowercase, strip URL prefix."""
        doi = doi.strip().lower()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if doi.startswith(prefix):
                doi = doi[len(prefix):]
        return doi

    @staticmethod
    def _extract_dois(text: str) -> list[str]:
        """Extract DOI patterns from text."""
        # Match DOI patterns: 10.XXXX/... (standard DOI format)
        pattern = r'10\.\d{4,9}/[^\s,;)\]}>]+'
        return re.findall(pattern, text)

    @staticmethod
    def _extract_pmids(text: str) -> list[str]:
        """Extract PMID patterns from text."""
        # Match "PMID: 12345678" or "PMID:12345678" (7-9 digits; modern PMIDs can be 9 digits)
        pattern = r'PMID:\s*(\d{7,9})'
        return re.findall(pattern, text, re.IGNORECASE)
