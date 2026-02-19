"""Live integration tests for Cold Start — uses real PubMed and Semantic Scholar APIs.

Tests are skipped when API keys are missing or APIs are unreachable.
Run explicitly with: pytest tests/test_integration/test_cold_start_live.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import asyncio
import tempfile

import pytest

from app.cold_start.seeder import ColdStartSeeder
from app.cold_start.smoke_test import SmokeTest
from app.memory.semantic import SemanticMemory
from app.agents.registry import create_registry
from app.llm.mock_layer import MockLLMLayer


# === Skip conditions ===

SKIP_NO_NCBI_EMAIL = pytest.mark.skipif(
    not os.environ.get("NCBI_EMAIL"),
    reason="NCBI_EMAIL not set — skipping live PubMed tests",
)

SKIP_NO_S2_KEY = pytest.mark.skipif(
    not os.environ.get("S2_API_KEY"),
    reason="S2_API_KEY not set — skipping live S2 tests",
)


# === Fixtures ===


@pytest.fixture
def live_memory():
    """Fresh ChromaDB in temp directory for live tests."""
    tmpdir = tempfile.mkdtemp()
    return SemanticMemory(persist_dir=tmpdir)


@pytest.fixture
def seeder(live_memory):
    return ColdStartSeeder(memory=live_memory)


# === PubMed Live Tests ===


@SKIP_NO_NCBI_EMAIL
def test_seed_from_pubmed_live(seeder, live_memory):
    """Seed from real PubMed API — verify papers are stored."""
    try:
        result = seeder.seed_from_pubmed("spaceflight anemia", max_results=5)
    except Exception as e:
        pytest.skip(f"PubMed API unreachable: {e}")

    assert result.source == "pubmed"
    assert result.papers_fetched > 0, "Should fetch at least 1 paper"
    assert result.papers_stored > 0, "Should store at least 1 paper"
    assert len(result.errors) == 0, f"Errors: {result.errors}"

    # Verify in ChromaDB
    count = live_memory.count("literature")
    assert count == result.papers_stored


@SKIP_NO_NCBI_EMAIL
def test_papers_searchable_after_pubmed_seed(seeder, live_memory):
    """After seeding, papers should be searchable by semantic similarity."""
    try:
        seeder.seed_from_pubmed("spaceflight anemia", max_results=5)
    except Exception as e:
        pytest.skip(f"PubMed API unreachable: {e}")

    results = live_memory.search("literature", "spaceflight")
    assert len(results) > 0, "Should find papers by semantic search"
    # Check metadata structure
    first = results[0]
    assert "id" in first
    assert "text" in first
    assert "metadata" in first
    assert first["metadata"].get("source") == "pubmed"


@SKIP_NO_NCBI_EMAIL
def test_seed_deduplication(seeder, live_memory):
    """Seeding twice with same query should not duplicate papers."""
    try:
        r1 = seeder.seed_from_pubmed("spaceflight anemia", max_results=3)
        count_after_first = live_memory.count("literature")

        r2 = seeder.seed_from_pubmed("spaceflight anemia", max_results=3)
        count_after_second = live_memory.count("literature")
    except Exception as e:
        pytest.skip(f"PubMed API unreachable: {e}")

    # Second seed should store 0 new papers (all duplicates)
    assert count_after_second == count_after_first
    assert r2.papers_skipped >= r2.papers_fetched - r2.papers_stored


# === Semantic Scholar Live Tests ===


@SKIP_NO_S2_KEY
def test_seed_from_s2_live(seeder, live_memory):
    """Seed from real Semantic Scholar API."""
    try:
        result = seeder.seed_from_semantic_scholar("spaceflight anemia", limit=5)
    except Exception as e:
        pytest.skip(f"S2 API unreachable: {e}")

    assert result.source == "semantic_scholar"
    assert result.papers_fetched > 0
    assert result.papers_stored > 0
    assert len(result.errors) == 0


@SKIP_NO_S2_KEY
@SKIP_NO_NCBI_EMAIL
def test_seed_status_multi_source(seeder, live_memory):
    """Seeding from both sources should show combined counts."""
    try:
        seeder.seed_from_pubmed("spaceflight anemia", max_results=3)
        seeder.seed_from_semantic_scholar("spaceflight anemia", limit=3)
    except Exception as e:
        pytest.skip(f"API unreachable: {e}")

    status = seeder.get_seed_status()
    assert "literature" in status
    assert status["literature"] > 0


# === Smoke Test with Real Registry ===


def test_smoke_test_with_real_registry():
    """SmokeTest should pass with mock LLM but real registry (no API keys needed)."""
    from app.agents.research_director import QueryClassification

    classification = QueryClassification(
        type="simple_query",
        reasoning="Smoke test",
        target_agent="t02_transcriptomics",
    )
    mock = MockLLMLayer({"sonnet:QueryClassification": classification})
    registry = create_registry(mock)

    smoke = SmokeTest(registry=registry)
    result = asyncio.run(smoke.run())

    assert result.passed, f"Smoke test failed: {result.checks}"
    assert result.checks["registry"]["passed"]
    assert result.checks["critical_health"]["passed"]
    assert result.checks["direct_query"]["passed"]


if __name__ == "__main__":
    print("Running Cold Start Live Integration Tests:")
    test_smoke_test_with_real_registry()
    print("\nCompleted!")
