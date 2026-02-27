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

    async def _search_literature_mcp(self, context: ContextPackage) -> AgentOutput:
        """MCP-powered literature search via Anthropic healthcare connectors.

        Delegates to Claude + MCP tools instead of direct API clients.
        Falls back to traditional path on failure.
        """
        from app.config import settings as _settings
        from app.integrations.mcp_connector import MCPConnector

        mcp_sources = [
            s.strip() for s in _settings.mcp_preferred_sources.split(",") if s.strip()
        ]

        try:
            connector = MCPConnector(client=self.llm.raw_client)
            mcp_result = await connector.search(
                query=context.task_description,
                sources=mcp_sources,
                model_tier=self.model_tier,
                max_results=20,
            )

            # Build LLMResponse for cost tracking
            from app.llm.layer import LLMResponse

            meta = LLMResponse(
                model_version=mcp_result.model,
                input_tokens=mcp_result.input_tokens,
                output_tokens=mcp_result.output_tokens,
                cached_input_tokens=mcp_result.cached_input_tokens,
                cost=self.llm.estimate_cost(
                    self.model_tier,
                    mcp_result.input_tokens,
                    mcp_result.output_tokens,
                    mcp_result.cached_input_tokens,
                ),
            )

            search_result = LiteratureSearchResult(
                query=context.task_description,
                databases_searched=[f"MCP:{s}" for s in mcp_sources],
                total_found=len(mcp_result.papers),
                papers=mcp_result.papers,
                search_strategy=f"MCP connector: {', '.join(mcp_sources)}",
            )

            return self.build_output(
                output=search_result.model_dump(),
                output_type="LiteratureSearchResult",
                summary=f"MCP found {len(mcp_result.papers)} papers for: {context.task_description[:80]}",
                llm_response=meta,
            )

        except Exception as e:
            logger.warning("MCP search failed, falling back to traditional: %s", e)
            return await self.search_literature(context, _mcp_fallback=True)

    async def search_literature(
        self, context: ContextPackage, _mcp_fallback: bool = False
    ) -> AgentOutput:
        """Search external literature databases.

        Uses LLM to generate optimal search terms, then queries
        PubMed and Semantic Scholar. When mcp_enabled=True and
        _mcp_fallback=False, delegates to MCP connectors instead.
        """
        from app.config import settings as _settings

        if _settings.mcp_enabled and not _mcp_fallback:
            return await self._search_literature_mcp(context)

        class SearchTerms(BaseModel):
            pubmed_queries: list[str] = Field(
                min_length=1,
                max_length=3,
                description=(
                    "1-3 diverse PubMed queries. Strategy: "
                    "(1) Specific: key gene/protein names + technique, "
                    "(2) Broad: general topic + organism + MeSH terms, "
                    "(3) Alternative: synonyms, related pathways, or disease context"
                ),
            )
            semantic_scholar_queries: list[str] = Field(
                min_length=1,
                max_length=2,
                description=(
                    "1-2 Semantic Scholar queries. Strategy: "
                    "(1) Natural language: full research question rephrased, "
                    "(2) Key terms: biological entities + method"
                ),
            )
            keywords: list[str] = Field(default_factory=list)

            @property
            def pubmed_query(self) -> str:
                """Backward compatibility: return first PubMed query."""
                return self.pubmed_queries[0] if self.pubmed_queries else ""

            @property
            def semantic_scholar_query(self) -> str:
                """Backward compatibility: return first S2 query."""
                return self.semantic_scholar_queries[0] if self.semantic_scholar_queries else ""

        messages = [
            {
                "role": "user",
                "content": (
                    f"Generate diverse search queries for this research topic:\n\n"
                    f"{context.task_description}\n\n"
                    f"Create 3 PubMed queries using different strategies:\n"
                    f"1. Specific: key gene/protein names, techniques, organism\n"
                    f"2. Broad: general topic with MeSH terms\n"
                    f"3. Alternative: synonyms, related pathways, or disease context\n\n"
                    f"Also create 2 Semantic Scholar queries:\n"
                    f"1. Natural language rephrasing of the research question\n"
                    f"2. Key biological entities and methods only"
                ),
            }
        ]

        terms, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=SearchTerms,
            system=self.system_prompt_cached,
        )
        # Guard against malformed/empty model outputs from mocks or provider drift.
        pubmed_queries = [q.strip() for q in terms.pubmed_queries if isinstance(q, str) and q.strip()]
        if not pubmed_queries:
            pubmed_queries = [context.task_description]
        semantic_queries = [
            q.strip() for q in terms.semantic_scholar_queries if isinstance(q, str) and q.strip()
        ]
        if not semantic_queries:
            semantic_queries = [context.task_description]

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

        # PubMed search: parallel multi-query (blocking I/O → thread pool)
        if has_pubmed:
            pubmed = self._pubmed or PubMedClient()
            per_query_limit = max(5, 20 // len(pubmed_queries))

            async def _run_pm_query(q: str) -> list:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    return await asyncio.wait_for(
                        loop.run_in_executor(pool, lambda: pubmed.search(q, max_results=per_query_limit)),
                        timeout=15.0,
                    )

            pm_tasks = [_run_pm_query(q) for q in pubmed_queries]
            pm_results = await asyncio.gather(*pm_tasks, return_exceptions=True)

            pm_total = 0
            for i, result in enumerate(pm_results):
                if isinstance(result, BaseException):
                    logger.warning("PubMed query %d failed: %s", i, result)
                    continue
                for p in result:
                    papers.append(p.to_dict())
                pm_total += len(result)

            databases_searched.append(f"PubMed ({len(pubmed_queries)} queries)")
            logger.info("PubMed returned %d papers from %d queries", pm_total, len(pubmed_queries))
        else:
            databases_searched.append("PubMed")
            logger.debug("PubMed skipped (no NCBI_EMAIL configured)")

        # Semantic Scholar search: parallel multi-query (blocking I/O → thread pool)
        if has_s2:
            s2 = self._s2 or SemanticScholarClient()
            per_s2_limit = max(5, 10 // len(semantic_queries))

            async def _run_s2_query(q: str) -> list:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    return await asyncio.wait_for(
                        loop.run_in_executor(pool, lambda: s2.search(q, limit=per_s2_limit)),
                        timeout=15.0,
                    )

            s2_tasks = [_run_s2_query(q) for q in semantic_queries]
            s2_results = await asyncio.gather(*s2_tasks, return_exceptions=True)

            s2_total = 0
            for i, result in enumerate(s2_results):
                if isinstance(result, BaseException):
                    logger.warning("S2 query %d failed: %s", i, result)
                    continue
                for p in result:
                    papers.append(p.to_dict())
                s2_total += len(result)

            databases_searched.append(f"Semantic Scholar ({len(semantic_queries)} queries)")
            logger.info("S2 returned %d papers from %d queries", s2_total, len(semantic_queries))
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
            search_strategy=(
                f"PubMed ({len(terms.pubmed_queries)}): "
                + " | ".join(terms.pubmed_queries)
                + f" ; S2 ({len(terms.semantic_scholar_queries)}): "
                + " | ".join(terms.semantic_scholar_queries)
            ),
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
