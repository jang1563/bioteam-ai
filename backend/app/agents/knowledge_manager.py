"""Knowledge Manager Agent — manages memory, literature, and novelty detection.

Responsibilities:
1. Literature search (PubMed, Semantic Scholar, bioRxiv/medRxiv)
2. Semantic memory management (ChromaDB with 3 provenance-separated collections)
3. Novelty detection (compare new findings against existing knowledge)
4. Citation tracking with DOI/PMID deduplication
"""

from __future__ import annotations

import logging

from app.agents.base import BaseAgent
from app.integrations.pubmed import PubMedClient
from app.integrations.semantic_scholar import SemanticScholarClient
from app.memory.semantic import SemanticMemory
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# === Output Models ===


class LiteratureSearchResult(BaseModel):
    """Result of a literature search across databases."""

    query: str
    databases_searched: list[str] = Field(default_factory=list)
    total_found: int = 0
    screened: int = 0
    included: int = 0
    papers: list[dict] = Field(default_factory=list)  # {doi, pmid, title, authors, year, abstract, relevance}
    search_strategy: str = ""


class MemoryRetrievalResult(BaseModel):
    """Result of retrieving relevant memory for a query."""

    query: str
    results: list[dict] = Field(default_factory=list)  # {id, text, source, relevance_score, metadata}
    total_found: int = 0
    collections_searched: list[str] = Field(default_factory=list)


class NoveltyAssessment(BaseModel):
    """Assessment of whether a finding is novel."""

    finding: str
    is_novel: bool = False
    novelty_score: float = 0.5  # 0.0 = well-known, 1.0 = completely novel
    similar_existing: list[str] = Field(default_factory=list)  # IDs of similar existing evidence
    reasoning: str = ""


# === Agent Implementation ===


class KnowledgeManagerAgent(BaseAgent):
    """Manages the system's collective memory and literature access.

    Uses ChromaDB for semantic memory (3 collections: literature, synthesis, lab_kb).
    Uses PubMed + Semantic Scholar for external literature search.
    """

    def __init__(
        self,
        spec,
        llm,
        memory: SemanticMemory | None = None,
        pubmed_client: PubMedClient | None = None,
        s2_client: SemanticScholarClient | None = None,
    ) -> None:
        super().__init__(spec, llm)
        self.memory = memory or SemanticMemory()
        self._pubmed = pubmed_client
        self._s2 = s2_client

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Retrieve relevant memory for the given context."""
        return await self.retrieve_memory(context)

    async def retrieve_memory(self, context: ContextPackage) -> AgentOutput:
        """Search semantic memory for context relevant to the task."""
        query = context.task_description

        # Search literature collection (primary sources only)
        literature_results = self.memory.search_literature(
            query=query,
            n_results=10,
        )

        # Search lab_kb for relevant internal knowledge
        lab_results = self.memory.search(
            collection="lab_kb",
            query=query,
            n_results=5,
        )

        all_results = []
        for r in literature_results:
            r["source"] = "literature"
            all_results.append(r)
        for r in lab_results:
            r["source"] = "lab_kb"
            all_results.append(r)

        result = MemoryRetrievalResult(
            query=query,
            results=all_results,
            total_found=len(all_results),
            collections_searched=["literature", "lab_kb"],
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="MemoryRetrievalResult",
            summary=f"Found {len(all_results)} relevant items for: {query[:80]}",
        )

    async def search_literature(self, context: ContextPackage) -> AgentOutput:
        """Search external literature databases.

        Uses LLM to generate optimal search terms, then queries
        PubMed and Semantic Scholar.
        """

        class SearchTerms(BaseModel):
            pubmed_query: str = Field(description="Optimized PubMed search query with MeSH terms")
            semantic_scholar_query: str = Field(description="Natural language query for Semantic Scholar")
            keywords: list[str] = Field(default_factory=list)

        messages = [
            {
                "role": "user",
                "content": (
                    f"Generate optimized search queries for this research topic:\n\n"
                    f"{context.task_description}\n\n"
                    f"Create a PubMed query (use MeSH terms when appropriate) "
                    f"and a Semantic Scholar query."
                ),
            }
        ]

        terms, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=SearchTerms,
            system=self.system_prompt_cached,
        )

        # Execute actual API searches
        # Only calls real APIs if clients were injected or NCBI_EMAIL is configured.
        # This avoids blocking network calls in test environments.
        import asyncio
        import os
        from concurrent.futures import ThreadPoolExecutor

        papers: list[dict] = []
        databases_searched: list[str] = []

        has_pubmed = self._pubmed is not None or bool(os.environ.get("NCBI_EMAIL"))
        has_s2 = self._s2 is not None

        if has_pubmed or has_s2:
            loop = asyncio.get_event_loop()

        # PubMed search (blocking I/O → thread pool with 15s timeout)
        if has_pubmed:
            try:
                pubmed = self._pubmed or PubMedClient()
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pubmed_papers = await asyncio.wait_for(
                        loop.run_in_executor(pool, lambda: pubmed.search(terms.pubmed_query, max_results=20)),
                        timeout=15.0,
                    )
                for p in pubmed_papers:
                    papers.append(p.to_dict())
                databases_searched.append("PubMed")
                logger.info("PubMed returned %d papers for: %s", len(pubmed_papers), terms.pubmed_query)
            except asyncio.TimeoutError:
                logger.warning("PubMed search timed out after 15s")
                databases_searched.append("PubMed (timeout)")
            except Exception as e:
                logger.warning("PubMed search failed (continuing): %s", e)
                databases_searched.append("PubMed (failed)")
        else:
            databases_searched.append("PubMed")
            logger.debug("PubMed skipped (no NCBI_EMAIL configured)")

        # Semantic Scholar search (blocking I/O → thread pool with 15s timeout)
        if has_s2:
            try:
                s2 = self._s2 or SemanticScholarClient()
                with ThreadPoolExecutor(max_workers=1) as pool:
                    s2_papers = await asyncio.wait_for(
                        loop.run_in_executor(pool, lambda: s2.search(terms.semantic_scholar_query, limit=10)),
                        timeout=15.0,
                    )
                for p in s2_papers:
                    papers.append(p.to_dict())
                databases_searched.append("Semantic Scholar")
                logger.info("S2 returned %d papers for: %s", len(s2_papers), terms.semantic_scholar_query)
            except asyncio.TimeoutError:
                logger.warning("Semantic Scholar search timed out after 15s")
                databases_searched.append("Semantic Scholar (timeout)")
            except Exception as e:
                logger.warning("Semantic Scholar search failed (continuing): %s", e)
                databases_searched.append("Semantic Scholar (failed)")
        else:
            databases_searched.append("Semantic Scholar")
            logger.debug("Semantic Scholar skipped (no client configured)")

        # Deduplicate by DOI
        seen_dois: set[str] = set()
        unique_papers: list[dict] = []
        for p in papers:
            doi = p.get("doi", "")
            if doi and doi in seen_dois:
                continue
            if doi:
                seen_dois.add(doi)
            unique_papers.append(p)

        result = LiteratureSearchResult(
            query=context.task_description,
            databases_searched=databases_searched,
            total_found=len(unique_papers),
            papers=unique_papers,
            search_strategy=f"PubMed: {terms.pubmed_query} | S2: {terms.semantic_scholar_query}",
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="LiteratureSearchResult",
            summary=f"Found {len(unique_papers)} papers for: {context.task_description[:80]}",
            llm_response=meta,
        )

    async def assess_novelty(self, context: ContextPackage) -> AgentOutput:
        """Assess whether a finding is novel compared to existing knowledge."""
        finding = context.task_description

        # Check existing knowledge
        existing = self.memory.search_literature(query=finding, n_results=5)

        messages = [
            {
                "role": "user",
                "content": (
                    f"Assess the novelty of this finding:\n\n"
                    f"{finding}\n\n"
                    f"Existing related knowledge:\n"
                    f"{[r.get('text', '')[:200] for r in existing]}\n\n"
                    f"Is this finding genuinely novel or already known?"
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=NoveltyAssessment,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="NoveltyAssessment",
            summary=f"Novelty: {'Novel' if result.is_novel else 'Known'} ({result.novelty_score:.2f})",
            llm_response=meta,
        )

    def store_evidence(
        self,
        doc_id: str,
        text: str,
        collection: str = "literature",
        metadata: dict | None = None,
    ) -> bool:
        """Store evidence in ChromaDB with deduplication.

        Returns True if stored, False if already exists (dedup).
        """
        existing = self.memory.collections[collection].get(ids=[doc_id])
        if existing["ids"]:
            return False  # Already exists
        self.memory.add(
            collection=collection,
            doc_id=doc_id,
            text=text,
            metadata=metadata,
        )
        return True
