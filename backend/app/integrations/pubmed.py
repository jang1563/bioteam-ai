"""PubMed integration via Biopython (Bio.Entrez).

Provides structured access to PubMed literature search and abstract retrieval.
Rate-limited to respect NCBI guidelines (10 req/sec with API key, 3 without).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from Bio import Entrez, Medline


def _configure_entrez() -> None:
    """Configure Entrez at call time (not import time) to pick up env vars."""
    if not Entrez.email:
        Entrez.email = os.environ.get("NCBI_EMAIL", "")
    api_key = os.environ.get("NCBI_API_KEY", "")
    if api_key:
        Entrez.api_key = api_key


@dataclass
class PubMedPaper:
    """Structured representation of a PubMed result."""

    pmid: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    journal: str = ""
    year: str = ""
    abstract: str = ""
    doi: str = ""
    mesh_terms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "pmid": self.pmid,
            "title": self.title,
            "authors": self.authors,
            "journal": self.journal,
            "year": self.year,
            "abstract": self.abstract,
            "doi": self.doi,
            "mesh_terms": self.mesh_terms,
            "source": "pubmed",
        }


class PubMedClient:
    """Client for PubMed search and retrieval via Biopython.

    Usage:
        client = PubMedClient()
        papers = client.search("spaceflight anemia", max_results=20)
        for paper in papers:
            print(paper.title, paper.doi)
    """

    def search(
        self,
        query: str,
        max_results: int = 20,
        sort: str = "relevance",
    ) -> list[PubMedPaper]:
        """Search PubMed and return structured results.

        Args:
            query: PubMed search query (supports MeSH terms, Boolean operators).
            max_results: Maximum number of results to return.
            sort: Sort order ("relevance" or "date").

        Returns:
            List of PubMedPaper objects with metadata and abstracts.
        """
        _configure_entrez()

        # Step 1: Search for PMIDs
        handle = Entrez.esearch(
            db="pubmed",
            term=query,
            retmax=max_results,
            sort=sort,
        )
        search_results = Entrez.read(handle)
        handle.close()

        pmids = search_results.get("IdList", [])
        if not pmids:
            return []

        # Step 2: Fetch details for all PMIDs
        return self.fetch_details(pmids)

    def fetch_details(self, pmids: list[str]) -> list[PubMedPaper]:
        """Fetch full details for a list of PMIDs.

        Args:
            pmids: List of PubMed IDs to fetch.

        Returns:
            List of PubMedPaper objects with full metadata.
        """
        _configure_entrez()

        handle = Entrez.efetch(
            db="pubmed",
            id=",".join(pmids),
            rettype="medline",
            retmode="text",
        )
        records = Medline.parse(handle)

        papers = []
        for record in records:
            paper = PubMedPaper(
                pmid=record.get("PMID", ""),
                title=record.get("TI", ""),
                authors=record.get("AU", []),
                journal=record.get("JT", "") or record.get("TA", ""),
                year=self._extract_year(record),
                abstract=record.get("AB", ""),
                doi=self._extract_doi(record),
                mesh_terms=record.get("MH", []),
            )
            papers.append(paper)

        handle.close()
        return papers

    @staticmethod
    def _extract_year(record: dict) -> str:
        """Extract publication year from record."""
        dp = record.get("DP", "")
        if dp and len(dp) >= 4:
            return dp[:4]
        return ""

    @staticmethod
    def _extract_doi(record: dict) -> str:
        """Extract DOI from article identifiers."""
        aids = record.get("AID", [])
        for aid in aids:
            if aid.endswith("[doi]"):
                return aid.replace(" [doi]", "")
        lid = record.get("LID", "")
        if "[doi]" in lid:
            return lid.replace(" [doi]", "")
        return ""
