"""Tests for ColdStartSeeder — seed_from_pubmed, seed_from_semantic_scholar, get_seed_status."""

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.cold_start.seeder import ColdStartSeeder, SeedResult
from app.memory.semantic import SemanticMemory


def _make_seeder() -> ColdStartSeeder:
    """Create a ColdStartSeeder with temp ChromaDB."""
    tmpdir = tempfile.mkdtemp()
    memory = SemanticMemory(persist_dir=tmpdir)
    return ColdStartSeeder(memory=memory)


def _mock_pubmed_papers():
    """Create mock PubMed papers."""
    from app.integrations.pubmed import PubMedPaper
    return [
        PubMedPaper(
            pmid="12345678",
            title="Spaceflight-induced hemolysis in astronauts",
            abstract="We observed a 54% increase in red blood cell destruction.",
            doi="10.1038/test1",
            year="2022",
            journal="Nature Medicine",
        ),
        PubMedPaper(
            pmid="87654321",
            title="Erythropoiesis regulation in microgravity",
            abstract="EPO levels and reticulocyte counts were measured during ISS missions.",
            doi="10.1038/test2",
            year="2023",
            journal="Blood",
        ),
        PubMedPaper(
            pmid="11111111",
            title="",  # Empty title — should still store with abstract
            abstract="A study with no title but valid abstract content.",
            doi="",
            year="2024",
            journal="",
        ),
    ]


def _mock_s2_papers():
    """Create mock Semantic Scholar papers."""
    from app.integrations.semantic_scholar import S2Paper
    return [
        S2Paper(
            paper_id="abc123",
            title="Cell-free RNA biomarkers for spaceflight monitoring",
            abstract="cfRNA signatures can detect tissue damage in spaceflight.",
            doi="10.1234/s2test1",
            year=2024,
            citation_count=42,
        ),
        S2Paper(
            paper_id="def456",
            title="Mouse models of spaceflight anemia",
            abstract="We used hindlimb unloading to simulate microgravity effects on erythrocytes.",
            doi="10.1234/s2test2",
            year=2023,
            citation_count=15,
        ),
    ]


def test_seed_from_pubmed():
    """seed_from_pubmed should store papers in ChromaDB."""
    seeder = _make_seeder()

    with patch("app.integrations.pubmed.PubMedClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.search.return_value = _mock_pubmed_papers()
        MockClient.return_value = mock_instance

        result = seeder.seed_from_pubmed("spaceflight anemia", max_results=10)

    assert isinstance(result, SeedResult)
    assert result.source == "pubmed"
    assert result.papers_fetched == 3
    assert result.papers_stored == 3  # All 3 have content
    assert result.errors == []

    # Verify stored in ChromaDB
    status = seeder.get_seed_status()
    assert status["literature"] == 3
    print("  PASS: seed_from_pubmed")


def test_seed_from_semantic_scholar():
    """seed_from_semantic_scholar should store papers in ChromaDB."""
    seeder = _make_seeder()

    with patch("app.integrations.semantic_scholar.SemanticScholarClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.search.return_value = _mock_s2_papers()
        MockClient.return_value = mock_instance

        result = seeder.seed_from_semantic_scholar("spaceflight anemia", limit=10)

    assert isinstance(result, SeedResult)
    assert result.source == "semantic_scholar"
    assert result.papers_fetched == 2
    assert result.papers_stored == 2
    assert result.errors == []

    status = seeder.get_seed_status()
    assert status["literature"] == 2
    print("  PASS: seed_from_semantic_scholar")


def test_get_seed_status_empty():
    """get_seed_status on fresh memory should return all zeros."""
    seeder = _make_seeder()
    status = seeder.get_seed_status()
    assert status["literature"] == 0
    assert status["synthesis"] == 0
    assert status["lab_kb"] == 0
    print("  PASS: get_seed_status_empty")


if __name__ == "__main__":
    print("Testing Cold Start Seeder:")
    test_seed_from_pubmed()
    test_seed_from_semantic_scholar()
    test_get_seed_status_empty()
    print("\nAll Cold Start Seeder tests passed!")
