"""Tests for CitationValidator — deterministic citation verification."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.engines.citation_validator import CitationReport, CitationValidator

# === DOI Normalization Tests ===


def test_normalize_doi_plain():
    assert CitationValidator._normalize_doi("10.1038/s41586-020-2521-4") == "10.1038/s41586-020-2521-4"
    print("  PASS: normalize_doi_plain")


def test_normalize_doi_https():
    assert CitationValidator._normalize_doi("https://doi.org/10.1038/s41586-020-2521-4") == "10.1038/s41586-020-2521-4"
    print("  PASS: normalize_doi_https")


def test_normalize_doi_http():
    assert CitationValidator._normalize_doi("http://doi.org/10.1234/test") == "10.1234/test"
    print("  PASS: normalize_doi_http")


def test_normalize_doi_prefix():
    assert CitationValidator._normalize_doi("doi:10.1234/test") == "10.1234/test"
    print("  PASS: normalize_doi_prefix")


def test_normalize_doi_uppercase():
    assert CitationValidator._normalize_doi("10.1038/S41586-020-2521-4") == "10.1038/s41586-020-2521-4"
    print("  PASS: normalize_doi_uppercase")


# === DOI Extraction Tests ===


def test_extract_dois_basic():
    text = "We referenced 10.1038/s41586-020-2521-4 in our analysis."
    dois = CitationValidator._extract_dois(text)
    assert len(dois) == 1
    assert "10.1038/s41586-020-2521-4" in dois
    print("  PASS: extract_dois_basic")


def test_extract_dois_multiple():
    text = "Studies 10.1038/s41586-020-2521-4 and 10.1126/science.abc1234 confirm this."
    dois = CitationValidator._extract_dois(text)
    assert len(dois) == 2
    print("  PASS: extract_dois_multiple")


def test_extract_dois_none():
    text = "No DOIs in this text."
    dois = CitationValidator._extract_dois(text)
    assert len(dois) == 0
    print("  PASS: extract_dois_none")


# === PMID Extraction Tests ===


def test_extract_pmids_with_space():
    text = "See PMID: 12345678 for details."
    pmids = CitationValidator._extract_pmids(text)
    assert len(pmids) == 1
    assert "12345678" in pmids
    print("  PASS: extract_pmids_with_space")


def test_extract_pmids_no_space():
    text = "See PMID:87654321 for details."
    pmids = CitationValidator._extract_pmids(text)
    assert len(pmids) == 1
    assert "87654321" in pmids
    print("  PASS: extract_pmids_no_space")


def test_extract_pmids_case_insensitive():
    text = "See pmid: 12345678 for details."
    pmids = CitationValidator._extract_pmids(text)
    assert len(pmids) == 1
    print("  PASS: extract_pmids_case_insensitive")


def test_extract_pmids_none():
    text = "No PMIDs here."
    pmids = CitationValidator._extract_pmids(text)
    assert len(pmids) == 0
    print("  PASS: extract_pmids_none")


# === Source Registration Tests ===


def test_register_sources():
    v = CitationValidator()
    v.register_sources([
        {"doi": "10.1038/s41586-020-2521-4", "pmid": "32699394", "title": "Spaceflight Study", "authors": ["John Smith"]},
        {"doi": "10.1126/science.abc1234", "title": "Another Study", "authors": ["Jane Doe", "Bob Lee"]},
    ])
    assert "10.1038/s41586-020-2521-4" in v._known_dois
    assert "10.1126/science.abc1234" in v._known_dois
    assert "32699394" in v._known_pmids
    assert "spaceflight study" in v._known_titles
    assert "smith" in v._known_authors
    assert "doe" in v._known_authors
    assert "lee" in v._known_authors
    print("  PASS: register_sources")


def test_register_sources_with_url_doi():
    v = CitationValidator()
    v.register_sources([
        {"doi": "https://doi.org/10.1038/s41586-020-2521-4"},
    ])
    assert "10.1038/s41586-020-2521-4" in v._known_dois
    print("  PASS: register_sources_with_url_doi")


def test_register_empty_fields():
    """Should handle missing/empty fields gracefully."""
    v = CitationValidator()
    v.register_sources([
        {"doi": None, "pmid": None, "title": None, "authors": []},
        {},
    ])
    assert len(v._known_dois) == 0
    assert len(v._known_pmids) == 0
    assert len(v._known_titles) == 0
    print("  PASS: register_empty_fields")


# === Validation with Inline Refs ===


def test_validate_inline_all_verified():
    v = CitationValidator()
    v.register_sources([
        {"doi": "10.1038/s41586-020-2521-4", "title": "Spaceflight Study"},
        {"doi": "10.1126/science.abc1234", "title": "Another Study"},
    ])
    report = v.validate("", inline_refs=[
        {"doi": "10.1038/s41586-020-2521-4", "title": "Spaceflight Study"},
        {"doi": "10.1126/science.abc1234"},
    ])
    assert report.total_citations == 2
    assert report.verified == 2
    assert report.is_clean
    assert report.verification_rate == 1.0
    print("  PASS: validate_inline_all_verified")


def test_validate_inline_some_unverified():
    v = CitationValidator()
    v.register_sources([
        {"doi": "10.1038/s41586-020-2521-4"},
    ])
    report = v.validate("", inline_refs=[
        {"doi": "10.1038/s41586-020-2521-4"},
        {"doi": "10.9999/hallucinated.doi"},
    ])
    assert report.total_citations == 2
    assert report.verified == 1
    assert len(report.issues) == 1
    assert report.issues[0].issue_type == "not_in_search_results"
    assert not report.is_clean
    print("  PASS: validate_inline_some_unverified")


def test_validate_inline_by_title():
    """Should verify by title match when DOI/PMID is missing."""
    v = CitationValidator()
    v.register_sources([
        {"title": "Spaceflight-Induced Anemia Mechanisms"},
    ])
    report = v.validate("", inline_refs=[
        {"title": "Spaceflight-Induced Anemia Mechanisms"},
    ])
    assert report.verified == 1
    assert report.is_clean
    print("  PASS: validate_inline_by_title")


def test_validate_inline_by_pmid():
    v = CitationValidator()
    v.register_sources([
        {"pmid": "32699394"},
    ])
    report = v.validate("", inline_refs=[
        {"pmid": "32699394"},
    ])
    assert report.verified == 1
    assert report.is_clean
    print("  PASS: validate_inline_by_pmid")


# === Validation with Text Extraction ===


def test_validate_text_dois():
    v = CitationValidator()
    v.register_sources([
        {"doi": "10.1038/s41586-020-2521-4"},
    ])
    text = "As shown by 10.1038/s41586-020-2521-4, the mechanism is clear."
    report = v.validate(text)
    assert report.total_citations == 1
    assert report.verified == 1
    assert report.is_clean
    print("  PASS: validate_text_dois")


def test_validate_text_pmids():
    v = CitationValidator()
    v.register_sources([
        {"pmid": "32699394"},
    ])
    text = "See PMID: 32699394 for the full dataset."
    report = v.validate(text)
    assert report.total_citations == 1
    assert report.verified == 1
    assert report.is_clean
    print("  PASS: validate_text_pmids")


def test_validate_text_unverified():
    v = CitationValidator()
    v.register_sources([])
    text = "The study 10.9999/fake.doi showed interesting results (PMID: 99999999)."
    report = v.validate(text)
    assert report.total_citations == 2
    assert report.verified == 0
    assert len(report.issues) == 2
    print("  PASS: validate_text_unverified")


def test_validate_empty_text():
    v = CitationValidator()
    report = v.validate("")
    assert report.total_citations == 0
    assert report.verified == 0
    assert report.is_clean
    assert report.verification_rate == 1.0
    print("  PASS: validate_empty_text")


# === CitationReport Properties ===


def test_report_unverified_count():
    report = CitationReport(total_citations=5, verified=3)
    assert report.unverified_count == 2
    print("  PASS: report_unverified_count")


def test_report_verification_rate():
    report = CitationReport(total_citations=4, verified=3)
    assert report.verification_rate == 0.75
    print("  PASS: report_verification_rate")


def test_report_verification_rate_zero():
    report = CitationReport(total_citations=0, verified=0)
    assert report.verification_rate == 1.0
    print("  PASS: report_verification_rate_zero")


if __name__ == "__main__":
    print("Testing CitationValidator:")
    # DOI normalization
    test_normalize_doi_plain()
    test_normalize_doi_https()
    test_normalize_doi_http()
    test_normalize_doi_prefix()
    test_normalize_doi_uppercase()
    # DOI extraction
    test_extract_dois_basic()
    test_extract_dois_multiple()
    test_extract_dois_none()
    # PMID extraction
    test_extract_pmids_with_space()
    test_extract_pmids_no_space()
    test_extract_pmids_case_insensitive()
    test_extract_pmids_none()
    # Registration
    test_register_sources()
    test_register_sources_with_url_doi()
    test_register_empty_fields()
    # Inline validation
    test_validate_inline_all_verified()
    test_validate_inline_some_unverified()
    test_validate_inline_by_title()
    test_validate_inline_by_pmid()
    # Text validation
    test_validate_text_dois()
    test_validate_text_pmids()
    test_validate_text_unverified()
    test_validate_empty_text()
    # Report properties
    test_report_unverified_count()
    test_report_verification_rate()
    test_report_verification_rate_zero()
    print("\nAll CitationValidator tests passed!")
