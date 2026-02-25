"""Tests for Knowledge Manager agent."""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.knowledge_manager import (
    KnowledgeManagerAgent,
    NoveltyAssessment,
)
from app.llm.mock_layer import MockLLMLayer
from app.memory.semantic import SemanticMemory
from app.models.messages import ContextPackage


def make_agent(
    mock_responses: dict | None = None,
    memory: SemanticMemory | None = None,
) -> KnowledgeManagerAgent:
    """Create a KnowledgeManagerAgent with MockLLMLayer + temp ChromaDB."""
    spec = BaseAgent.load_spec("knowledge_manager")
    mock = MockLLMLayer(mock_responses or {})
    if memory is None:
        tmpdir = tempfile.mkdtemp()
        memory = SemanticMemory(persist_dir=tmpdir)
    return KnowledgeManagerAgent(spec=spec, llm=mock, memory=memory)


def test_store_and_retrieve():
    """KM should store evidence and retrieve it by semantic search."""
    tmpdir = tempfile.mkdtemp()
    memory = SemanticMemory(persist_dir=tmpdir)
    agent = make_agent(memory=memory)

    # Store some evidence
    stored = agent.store_evidence(
        doc_id="doi:10.1038/s41591-022-01696-6",
        text="Space anemia is caused by splenic hemolysis in microgravity. "
             "Red blood cell destruction increases by 54% during spaceflight.",
        collection="literature",
        metadata={"doi": "10.1038/s41591-022-01696-6", "year": "2022"},
    )
    assert stored is True, "Should store new evidence"

    # Try to store duplicate
    stored_again = agent.store_evidence(
        doc_id="doi:10.1038/s41591-022-01696-6",
        text="Duplicate text",
        collection="literature",
    )
    assert stored_again is False, "Should skip duplicate"

    # Retrieve
    context = ContextPackage(task_description="spaceflight anemia red blood cell destruction")
    output = asyncio.run(agent.retrieve_memory(context))

    assert output.is_success, f"Failed: {output.error}"
    assert output.output["total_found"] >= 1
    assert any("hemolysis" in r.get("text", "").lower() or "anemia" in r.get("text", "").lower()
               for r in output.output["results"])
    print("  PASS: store and retrieve evidence")


def test_dedup_by_id():
    """ChromaDB deduplication should work via DOI/PMID-based IDs."""
    tmpdir = tempfile.mkdtemp()
    memory = SemanticMemory(persist_dir=tmpdir)
    agent = make_agent(memory=memory)

    agent.store_evidence("pmid:12345678", "Paper 1 text")
    agent.store_evidence("pmid:12345678", "Different text same PMID")

    count = memory.count("literature")
    assert count == 1, f"Expected 1 document, got {count}"
    print("  PASS: dedup by ID")


def test_search_literature_method():
    """search_literature should use only literature collection."""
    tmpdir = tempfile.mkdtemp()
    memory = SemanticMemory(persist_dir=tmpdir)
    agent = make_agent(memory=memory)

    # Add to literature
    agent.store_evidence("doi:lit1", "Space anemia study", collection="literature")
    # Add to synthesis (should NOT appear in search_literature)
    memory.add("synthesis", "synth1", "Agent synthesis about space anemia")

    results = memory.search_literature("space anemia", n_results=5)
    assert len(results) >= 1
    # synthesis result should not be in search_literature results
    result_ids = [r["id"] for r in results]
    assert "synth1" not in result_ids, "synthesis results should not appear in search_literature"
    print("  PASS: search_literature excludes synthesis")


def test_search_all_collections():
    """search_all should merge results from multiple collections."""
    tmpdir = tempfile.mkdtemp()
    memory = SemanticMemory(persist_dir=tmpdir)
    make_agent(memory=memory)

    memory.add("literature", "lit1", "Space anemia paper")
    memory.add("synthesis", "synth1", "Agent synthesis about anemia")
    memory.add("lab_kb", "kb1", "Lab note: EPO experiment failed")

    results = memory.search_all("anemia", n_results=5)
    assert len(results) >= 2  # Should find items from multiple collections
    collections_found = set(r.get("collection") for r in results)
    assert len(collections_found) >= 2, f"Expected results from >=2 collections, got {collections_found}"
    print("  PASS: search_all merges collections")


def test_llm_search_terms():
    """KM should use LLM to generate optimized search terms and call real APIs."""
    from app.integrations.pubmed import PubMedPaper
    from app.integrations.semantic_scholar import S2Paper
    from pydantic import BaseModel, Field

    class SearchTerms(BaseModel):
        pubmed_queries: list[str] = Field(default_factory=lambda: ["spaceflight[MeSH] AND anemia[MeSH]"])
        semantic_scholar_queries: list[str] = Field(default_factory=lambda: ["spaceflight induced anemia mechanisms"])
        keywords: list[str] = Field(default_factory=lambda: ["spaceflight", "anemia"])

    # Create mock integration clients so tests don't hit real APIs
    class MockPubMed:
        def search(self, query, max_results=20):
            return [
                PubMedPaper(pmid="12345678", title="Space anemia study", authors=["Kim J"],
                            journal="Nature Medicine", year="2022",
                            abstract="Spaceflight hemolysis.", doi="10.1038/test1"),
            ]

    class MockS2:
        def search(self, query, limit=10):
            return [
                S2Paper(paper_id="abc123", title="Microgravity erythropoiesis",
                        authors=["Lee S"], year=2023,
                        abstract="Red blood cell dynamics.", doi="10.1234/test2"),
            ]

    agent = make_agent({"sonnet:SearchTerms": SearchTerms()})
    agent._pubmed = MockPubMed()
    agent._s2 = MockS2()

    context = ContextPackage(task_description="spaceflight anemia mechanisms")
    output = asyncio.run(agent.search_literature(context))

    assert output.is_success
    assert output.output_type == "LiteratureSearchResult"
    assert any("PubMed" in db for db in output.output["databases_searched"])
    assert any("Semantic Scholar" in db for db in output.output["databases_searched"])
    assert output.output["total_found"] == 2
    assert len(output.output["papers"]) == 2
    assert output.output["papers"][0]["source"] == "pubmed"
    assert output.output["papers"][1]["source"] == "semantic_scholar"
    print("  PASS: LLM search term generation + API calls")


def test_novelty_assessment():
    """KM should assess novelty of findings."""
    assessment = NoveltyAssessment(
        finding="EPO receptor expression in splenic macrophages",
        is_novel=True,
        novelty_score=0.85,
        reasoning="No prior studies examined EPO receptor on splenic macrophages in microgravity.",
    )
    agent = make_agent({"sonnet:NoveltyAssessment": assessment})

    context = ContextPackage(
        task_description="EPO receptor expression in splenic macrophages during spaceflight"
    )
    output = asyncio.run(agent.assess_novelty(context))

    assert output.is_success
    assert output.output["is_novel"] is True
    assert output.output["novelty_score"] > 0.5
    print("  PASS: novelty assessment")


if __name__ == "__main__":
    print("Testing Knowledge Manager Agent:")
    test_store_and_retrieve()
    test_dedup_by_id()
    test_search_literature_method()
    test_search_all_collections()
    test_llm_search_terms()
    test_novelty_assessment()
    print("\nAll Knowledge Manager tests passed!")
