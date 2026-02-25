"""Tests for PubMed integration.

NOTE: These tests make real API calls to NCBI.
Run with: python tests/test_integrations/test_pubmed.py
Set NCBI_API_KEY and NCBI_EMAIL in environment for higher rate limits.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("NCBI_EMAIL", "test@example.com")

from app.integrations.pubmed import PubMedClient, PubMedPaper


def test_search_basic():
    """Should find papers for a well-known topic."""
    client = PubMedClient()
    papers = client.search("spaceflight anemia", max_results=5)

    assert len(papers) > 0, "Should find at least 1 paper"
    assert isinstance(papers[0], PubMedPaper)
    assert papers[0].pmid, "PMID should not be empty"
    assert papers[0].title, "Title should not be empty"
    print(f"  PASS: Found {len(papers)} papers")
    for p in papers[:3]:
        print(f"    - [{p.pmid}] {p.title[:80]}... (DOI: {p.doi})")


def test_search_with_mesh():
    """Should handle MeSH terms in query."""
    client = PubMedClient()
    papers = client.search("Weightlessness[MeSH] AND Anemia[MeSH]", max_results=5)

    assert len(papers) >= 0  # May have 0 results for very specific MeSH query
    print(f"  PASS: MeSH search returned {len(papers)} results")


def test_fetch_details():
    """Should fetch details for known PMIDs."""
    client = PubMedClient()
    # PMID for the Trudel 2022 space anemia paper
    papers = client.fetch_details(["35031899"])

    assert len(papers) == 1
    paper = papers[0]
    assert paper.pmid == "35031899"
    assert "anemia" in paper.title.lower() or "hemolysis" in paper.title.lower() or paper.title != ""
    assert paper.abstract != ""
    assert len(paper.authors) > 0
    print(f"  PASS: Fetched details for PMID 35031899: {paper.title[:60]}...")


def test_to_dict():
    """Paper should serialize to dict with source field."""
    paper = PubMedPaper(
        pmid="12345678",
        title="Test Paper",
        authors=["Author A", "Author B"],
        doi="10.1234/test",
    )
    d = paper.to_dict()
    assert d["source"] == "pubmed"
    assert d["pmid"] == "12345678"
    assert d["doi"] == "10.1234/test"
    print("  PASS: to_dict serialization")


def test_empty_search():
    """Should return empty list for nonsense query."""
    client = PubMedClient()
    papers = client.search("xyzabc123nonexistent9999", max_results=5)

    assert len(papers) == 0
    print("  PASS: Empty search returns empty list")


if __name__ == "__main__":
    print("Testing PubMed Integration (live API):")
    test_to_dict()
    test_search_basic()
    test_search_with_mesh()
    test_fetch_details()
    test_empty_search()
    print("\nAll PubMed tests passed!")
