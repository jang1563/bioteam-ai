"""Tests for Digest Pipeline."""

import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.db.database import engine as db_engine, create_db_and_tables
from app.digest.pipeline import DigestPipeline
from app.models.digest import TopicProfile, DigestEntry, DigestReport


def setup_module():
    create_db_and_tables()


def _make_topic(
    name: str = "Test Topic",
    queries: list[str] | None = None,
    sources: list[str] | None = None,
) -> TopicProfile:
    topic = TopicProfile(
        name=name,
        queries=queries or ["AI biology"],
        sources=sources or ["pubmed", "arxiv"],
    )
    with Session(db_engine) as session:
        session.add(topic)
        session.commit()
        session.refresh(topic)
        session.expunge(topic)
    return topic


def _mock_pubmed_papers():
    """Create mock PubMed papers."""
    from app.integrations.pubmed import PubMedPaper
    return [
        PubMedPaper(pmid="111", title="AI Genomics Paper", authors=["Kim J"], abstract="AI for genomics.", doi="10.1234/a1"),
        PubMedPaper(pmid="222", title="ML Drug Discovery", authors=["Lee H"], abstract="ML for drugs.", doi="10.1234/a2"),
    ]


def _mock_arxiv_papers():
    """Create mock arXiv papers."""
    from app.integrations.arxiv_client import ArxivPaper
    return [
        ArxivPaper(arxiv_id="2502.11111", title="AI Genomics Paper", authors=["Kim J"], abstract="AI for genomics.", doi="10.1234/a1"),
        ArxivPaper(arxiv_id="2502.22222", title="New Transformer Model", authors=["Park S"], abstract="Novel architecture."),
    ]


# === Deduplication Tests ===


def test_deduplicate_by_doi():
    """Should remove duplicate DOIs across sources."""
    pipeline = DigestPipeline()
    entries = [
        {"doi": "10.1234/test", "title": "Paper A", "source": "pubmed"},
        {"doi": "10.1234/test", "title": "Paper A", "source": "arxiv"},
        {"doi": "10.5678/other", "title": "Paper B", "source": "pubmed"},
    ]
    result = pipeline._deduplicate(entries)
    assert len(result) == 2


def test_deduplicate_by_arxiv_id():
    """Should remove duplicate arXiv IDs."""
    pipeline = DigestPipeline()
    entries = [
        {"arxiv_id": "2502.11111", "title": "Paper A", "source": "arxiv"},
        {"paper_id": "2502.11111", "title": "Paper A", "source": "huggingface"},
    ]
    result = pipeline._deduplicate(entries)
    assert len(result) == 1


def test_deduplicate_by_title():
    """Should remove entries with identical titles."""
    pipeline = DigestPipeline()
    entries = [
        {"title": "Exact Same Title", "source": "pubmed", "pmid": "111"},
        {"title": "Exact Same Title", "source": "biorxiv", "doi": "10.1101/x"},
    ]
    result = pipeline._deduplicate(entries)
    assert len(result) == 1


def test_deduplicate_empty():
    """Empty input should return empty output."""
    pipeline = DigestPipeline()
    assert pipeline._deduplicate([]) == []


# === Relevance Scoring Tests ===


def test_relevance_scoring():
    """Should score entries by keyword match."""
    pipeline = DigestPipeline()
    entries = [
        {"title": "AI in biology and genomics", "abstract": "Machine learning for genes"},
        {"title": "Unrelated cooking recipe", "abstract": "How to cook pasta"},
    ]
    scored = pipeline._compute_relevance(entries, ["AI biology genomics"])
    assert scored[0]["relevance_score"] > scored[1]["relevance_score"]


def test_relevance_scoring_empty_queries():
    """Empty queries should give 0 scores."""
    pipeline = DigestPipeline()
    entries = [{"title": "Test", "abstract": "Something"}]
    scored = pipeline._compute_relevance(entries, [])
    assert scored[0]["relevance_score"] == 0.0


# === Entry Persistence Tests ===


def test_persist_entries():
    """Should persist entries to database."""
    pipeline = DigestPipeline()
    topic = _make_topic(name="Persist Test")
    entries = [
        {"doi": "10.9999/persist1", "title": "Persist Paper", "source": "pubmed", "authors": ["A"], "abstract": "Test"},
    ]
    persisted = pipeline._persist_entries(entries, topic.id)
    assert len(persisted) == 1
    assert persisted[0].external_id == "10.9999/persist1"


def test_persist_entries_dedup():
    """Should not duplicate existing entries for same topic."""
    pipeline = DigestPipeline()
    topic = _make_topic(name="Dedup Persist Test")
    entries = [{"doi": "10.9999/dup1", "title": "Dup Paper", "source": "arxiv", "authors": []}]

    first = pipeline._persist_entries(entries, topic.id)
    assert len(first) == 1

    second = pipeline._persist_entries(entries, topic.id)
    assert len(second) == 0  # Already exists


# === External ID Extraction ===


def test_extract_external_id():
    """Should extract the best external ID."""
    assert DigestPipeline._extract_external_id({"doi": "10.1234/x"}) == "10.1234/x"
    assert DigestPipeline._extract_external_id({"arxiv_id": "2502.1"}) == "2502.1"
    assert DigestPipeline._extract_external_id({"full_name": "user/repo"}) == "user/repo"
    assert DigestPipeline._extract_external_id({}) == ""


# === Full Pipeline (Mocked) ===


def test_full_pipeline_mocked():
    """Full pipeline should work with mocked clients."""
    pipeline = DigestPipeline()
    topic = _make_topic(name="Full Pipeline Test", sources=["pubmed", "arxiv"])

    # Mock the fetch methods
    mock_pubmed = _mock_pubmed_papers()
    mock_arxiv = _mock_arxiv_papers()

    with patch.object(pipeline._clients["pubmed"], "search", return_value=mock_pubmed), \
         patch.object(pipeline._clients["arxiv"], "search", return_value=mock_arxiv):
        report = asyncio.run(pipeline.run(topic, days=7))

    assert isinstance(report, DigestReport)
    assert report.topic_id == topic.id
    assert report.entry_count > 0
    # One paper appears in both sources (same DOI), so dedup should reduce count
    assert report.source_breakdown.get("pubmed", 0) > 0 or report.source_breakdown.get("arxiv", 0) > 0
