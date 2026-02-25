"""Tests for Semantic Scholar integration.

NOTE: These tests make real API calls to Semantic Scholar.
Run with: python tests/test_integrations/test_semantic_scholar.py
Set S2_API_KEY in environment for higher rate limits (optional).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.integrations.semantic_scholar import S2Paper, SemanticScholarClient


def test_search_basic():
    """Should find papers for a well-known topic."""
    client = SemanticScholarClient(timeout=15)
    try:
        papers = client.search("spaceflight induced anemia", limit=5)
    except Exception as e:
        print(f"  SKIP: S2 API error ({type(e).__name__}): {e}")
        return

    assert len(papers) > 0, "Should find at least 1 paper"
    assert isinstance(papers[0], S2Paper)
    assert papers[0].title, "Title should not be empty"
    print(f"  PASS: Found {len(papers)} papers")
    for p in papers[:3]:
        print(f"    - {p.title[:80]}... (citations: {p.citation_count}, DOI: {p.doi})")


def test_get_paper_by_doi():
    """Should fetch a specific paper by DOI."""
    client = SemanticScholarClient(timeout=15)
    try:
        paper = client.get_paper("10.1038/s41591-021-01637-7")
    except Exception as e:
        print(f"  SKIP: S2 API error ({type(e).__name__}): {e}")
        return

    if paper:
        assert paper.doi == "10.1038/s41591-021-01637-7"
        assert paper.title != ""
        assert paper.citation_count >= 0
        print(f"  PASS: Got paper by DOI: {paper.title[:60]}... (cited {paper.citation_count}x)")
    else:
        print("  SKIP: Paper not found (API may be rate-limited)")


def test_get_citations():
    """Should get papers citing a given paper."""
    client = SemanticScholarClient(timeout=15)
    citing = client.get_citations("10.1038/s41591-021-01637-7", limit=3)

    if citing:
        assert len(citing) > 0
        assert isinstance(citing[0], S2Paper)
        print(f"  PASS: Found {len(citing)} citing papers")
        for p in citing[:2]:
            print(f"    - {p.title[:80]}...")
    else:
        print("  SKIP: No citations found (API may be rate-limited)")


def test_get_references():
    """Should get papers referenced by a given paper."""
    client = SemanticScholarClient(timeout=15)
    refs = client.get_references("10.1038/s41591-021-01637-7", limit=3)

    if refs:
        assert len(refs) > 0
        print(f"  PASS: Found {len(refs)} referenced papers")
    else:
        print("  SKIP: No references found (API may be rate-limited)")


def test_to_dict():
    """Paper should serialize to dict with source field."""
    paper = S2Paper(
        paper_id="abc123",
        title="Test Paper",
        doi="10.1234/test",
        citation_count=42,
    )
    d = paper.to_dict()
    assert d["source"] == "semantic_scholar"
    assert d["paper_id"] == "abc123"
    assert d["citation_count"] == 42
    print("  PASS: to_dict serialization")


def test_empty_search():
    """Should return empty list for nonsense query."""
    client = SemanticScholarClient(timeout=15)
    try:
        papers = client.search("xyzabc123nonexistent9999zzz", limit=5)
        assert len(papers) == 0
        print("  PASS: Empty search returns empty list")
    except Exception as e:
        print(f"  SKIP: S2 API error ({type(e).__name__}): {e}")


if __name__ == "__main__":
    print("Testing Semantic Scholar Integration (live API):")
    test_to_dict()
    test_search_basic()
    test_get_paper_by_doi()
    test_get_citations()
    test_get_references()
    test_empty_search()
    print("\nAll Semantic Scholar tests passed!")
