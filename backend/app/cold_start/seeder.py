"""Cold Start Seeder — populate ChromaDB with initial knowledge.

Seeds the literature collection from PubMed and Semantic Scholar
so that the system has baseline knowledge before the first workflow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.memory.semantic import SemanticMemory

logger = logging.getLogger(__name__)


@dataclass
class SeedResult:
    """Result of a seeding operation."""

    source: str
    papers_fetched: int = 0
    papers_stored: int = 0
    papers_skipped: int = 0  # Already in DB (dedup)
    errors: list[str] = field(default_factory=list)


class ColdStartSeeder:
    """Seeds ChromaDB with initial literature from external sources.

    Usage:
        seeder = ColdStartSeeder(memory=memory)
        result = seeder.seed_from_pubmed("spaceflight anemia", max_results=50)
        status = seeder.get_seed_status()
    """

    def __init__(self, memory: SemanticMemory) -> None:
        self.memory = memory

    def seed_from_pubmed(
        self,
        query: str,
        max_results: int = 50,
    ) -> SeedResult:
        """Fetch papers from PubMed and store in ChromaDB literature collection.

        Args:
            query: PubMed search query.
            max_results: Maximum papers to fetch.

        Returns:
            SeedResult with counts and any errors.
        """
        from app.integrations.pubmed import PubMedClient

        result = SeedResult(source="pubmed")

        try:
            client = PubMedClient()
            papers = client.search(query, max_results=max_results)
            result.papers_fetched = len(papers)

            for paper in papers:
                doc_id = f"pmid:{paper.pmid}" if paper.pmid else f"pubmed:{paper.title[:50]}"
                text = f"{paper.title}. {paper.abstract}"

                if not text.strip() or text.strip() == ".":
                    result.papers_skipped += 1
                    continue

                metadata = {
                    "source": "pubmed",
                    "pmid": paper.pmid,
                    "doi": paper.doi,
                    "year": paper.year,
                    "journal": paper.journal,
                }

                try:
                    self.memory.add("literature", doc_id, text, metadata=metadata)
                    result.papers_stored += 1
                except Exception as e:
                    result.papers_skipped += 1
                    result.errors.append(f"Failed to store {doc_id}: {e}")

        except Exception as e:
            result.errors.append(f"PubMed search failed: {e}")
            logger.error("PubMed seeding failed: %s", e)

        return result

    def seed_from_semantic_scholar(
        self,
        query: str,
        limit: int = 50,
    ) -> SeedResult:
        """Fetch papers from Semantic Scholar and store in ChromaDB.

        Args:
            query: Natural language search query.
            limit: Maximum papers to fetch.

        Returns:
            SeedResult with counts and any errors.
        """
        from app.integrations.semantic_scholar import SemanticScholarClient

        result = SeedResult(source="semantic_scholar")

        try:
            client = SemanticScholarClient()
            papers = client.search(query, limit=limit)
            result.papers_fetched = len(papers)

            for paper in papers:
                doc_id = f"doi:{paper.doi}" if paper.doi else f"s2:{paper.paper_id}"
                text = f"{paper.title}. {paper.abstract}"

                if not text.strip() or text.strip() == ".":
                    result.papers_skipped += 1
                    continue

                metadata = {
                    "source": "semantic_scholar",
                    "s2_id": paper.paper_id,
                    "doi": paper.doi,
                    "year": paper.year or 0,
                    "citations": paper.citation_count,
                }

                try:
                    self.memory.add("literature", doc_id, text, metadata=metadata)
                    result.papers_stored += 1
                except Exception as e:
                    result.papers_skipped += 1
                    result.errors.append(f"Failed to store {doc_id}: {e}")

        except Exception as e:
            result.errors.append(f"Semantic Scholar search failed: {e}")
            logger.error("S2 seeding failed: %s", e)

        return result

    def get_seed_status(self) -> dict[str, int]:
        """Get current document counts per collection."""
        return {
            name: self.memory.count(name)
            for name in self.memory.collections
        }
