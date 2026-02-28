"""Digest Pipeline — FETCH → DEDUP → SUMMARIZE → STORE.

Standalone pipeline that fetches papers from multiple sources,
deduplicates, computes relevance, generates a summary via DigestAgent,
and persists everything to the database.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.db.database import engine as db_engine
from app.integrations.arxiv_client import ArxivClient
from app.integrations.biorxiv import BiorxivClient
from app.integrations.github_trending import GithubTrendingClient
from app.integrations.huggingface import HuggingFaceClient
from app.integrations.pubmed import PubMedClient
from app.integrations.semantic_scholar import SemanticScholarClient
from app.models.digest import DigestEntry, DigestReport, TopicProfile
from app.models.messages import ContextPackage
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

# Source name constants
SOURCE_PUBMED = "pubmed"
SOURCE_BIORXIV = "biorxiv"
SOURCE_ARXIV = "arxiv"
SOURCE_GITHUB = "github"
SOURCE_HUGGINGFACE = "huggingface"
SOURCE_S2 = "semantic_scholar"


class DigestPipeline:
    """Multi-source research digest pipeline.

    Usage:
        pipeline = DigestPipeline()
        report = await pipeline.run(topic)
    """

    def __init__(self, digest_agent=None) -> None:
        self._digest_agent = digest_agent
        self._executor = ThreadPoolExecutor(max_workers=3)
        self._clients = {
            SOURCE_PUBMED: PubMedClient(),
            SOURCE_S2: SemanticScholarClient(),
            SOURCE_BIORXIV: BiorxivClient(),
            SOURCE_ARXIV: ArxivClient(),
            SOURCE_GITHUB: GithubTrendingClient(token=getattr(settings, "github_token", "")),
            SOURCE_HUGGINGFACE: HuggingFaceClient(),
        }

    def shutdown(self) -> None:
        """Shut down the ThreadPoolExecutor. Call during app teardown."""
        self._executor.shutdown(wait=False)

    async def run(self, topic: TopicProfile, days: int = 7) -> DigestReport:
        """Full pipeline: FETCH → DEDUP → SCORE → STORE → SUMMARIZE → REPORT.

        Args:
            topic: TopicProfile with queries, sources, and categories.
            days: Look-back period in days.

        Returns:
            DigestReport with summary and highlights.
        """
        logger.info("Starting digest pipeline for topic '%s'", topic.name)

        # 1. Fetch from all enabled sources in parallel
        raw_entries = await self._fetch_all_sources(topic, days=days)
        logger.info("Fetched %d raw entries from %d sources", len(raw_entries), len(topic.sources))

        # 2. Deduplicate
        unique_entries = self._deduplicate(raw_entries)
        logger.info("After dedup: %d unique entries", len(unique_entries))

        # 3. Compute relevance scores
        scored_entries = self._compute_relevance(unique_entries, topic.queries)

        # 4. Sort by relevance and take top entries
        scored_entries.sort(key=lambda e: e.get("relevance_score", 0), reverse=True)
        top_entries = scored_entries[:100]

        # 5. Persist entries to DB
        persisted = self._persist_entries(top_entries, topic.id)
        logger.info("Persisted %d entries", len(persisted))

        # 6. Summarize with DigestAgent (if available)
        report = await self._summarize(persisted, topic, days=days)
        logger.info("Digest report generated: %d entries, cost=%.4f", report.entry_count, report.cost)

        return report

    async def _fetch_all_sources(self, topic: TopicProfile, days: int = 7) -> list[dict]:
        """Fetch from all enabled sources in parallel."""
        tasks = []
        loop = asyncio.get_running_loop()

        for source in topic.sources:
            if source not in self._clients:
                continue
            tasks.append(self._fetch_single_source(source, topic, days, loop))

        # Track source names in same order as tasks for error attribution
        source_names = [s for s in topic.sources if s in self._clients]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_entries: list[dict] = []
        for source_name, result in zip(source_names, results):
            if isinstance(result, Exception):
                logger.warning("Source '%s' fetch failed: %s", source_name, result)
                continue
            logger.debug("Source '%s' returned %d entries", source_name, len(result))
            all_entries.extend(result)

        return all_entries

    async def _fetch_single_source(
        self, source: str, topic: TopicProfile, days: int, loop
    ) -> list[dict]:
        """Fetch from a single source with timeout."""
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(
                    self._executor,
                    self._fetch_sync,
                    source,
                    topic,
                    days,
                ),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Source %s timed out", source)
            return []
        except Exception as e:
            logger.warning("Source %s error: %s", source, e)
            return []

    def _fetch_sync(self, source: str, topic: TopicProfile, days: int) -> list[dict]:
        """Synchronous fetch for a single source (runs in ThreadPoolExecutor)."""
        query = " ".join(topic.queries[:3])  # Use first 3 queries combined
        categories = topic.categories.get(source, []) if topic.categories else []

        if source == SOURCE_PUBMED:
            papers = self._clients[SOURCE_PUBMED].search(query, max_results=30, sort="date")
            return [p.to_dict() for p in papers]

        elif source == SOURCE_S2:
            papers = self._clients[SOURCE_S2].search(query, limit=20)
            return [p.to_dict() for p in papers]

        elif source == SOURCE_BIORXIV:
            papers = self._clients[SOURCE_BIORXIV].search_by_topic(query, days=days, max_results=30)
            return [p.to_dict() for p in papers]

        elif source == SOURCE_ARXIV:
            cats = categories or ArxivClient.BIO_AI_CATEGORIES
            papers = self._clients[SOURCE_ARXIV].search(query, max_results=30, categories=cats)
            return [p.to_dict() for p in papers]

        elif source == SOURCE_GITHUB:
            repos = self._clients[SOURCE_GITHUB].trending_ai_bio(
                query=query, days=days, max_results=20
            )
            return [r.to_dict() for r in repos]

        elif source == SOURCE_HUGGINGFACE:
            papers = self._clients[SOURCE_HUGGINGFACE].search_papers(query, max_results=30)
            return [p.to_dict() for p in papers]

        return []

    def _deduplicate(self, entries: list[dict]) -> list[dict]:
        """Cross-source dedup by DOI, arXiv ID, or title."""
        seen_ids: set[str] = set()
        seen_titles: set[str] = set()
        unique: list[dict] = []

        for entry in entries:
            # Check by DOI
            doi = entry.get("doi", "")
            if doi and doi in seen_ids:
                continue

            # Check by arXiv ID
            arxiv_id = entry.get("arxiv_id", "") or entry.get("paper_id", "")
            if arxiv_id and arxiv_id in seen_ids:
                continue

            # Check by repo full_name
            full_name = entry.get("full_name", "")
            if full_name and full_name in seen_ids:
                continue

            # Check by normalized title
            title = entry.get("title", "").strip().lower()
            if title and title in seen_titles:
                continue

            # Mark as seen
            if doi:
                seen_ids.add(doi)
            if arxiv_id:
                seen_ids.add(arxiv_id)
            if full_name:
                seen_ids.add(full_name)
            if title:
                seen_titles.add(title)

            unique.append(entry)

        return unique

    def _compute_relevance(self, entries: list[dict], queries: list[str]) -> list[dict]:
        """Deterministic keyword-based relevance scoring with word boundary matching."""
        # Extract keywords: keep quoted phrases intact, split remainder
        keywords: list[str] = []
        for q in queries:
            quoted = re.findall(r'"([^"]+)"', q)
            keywords.extend(phrase.lower() for phrase in quoted)
            remainder = re.sub(r'"[^"]*"', '', q)
            keywords.extend(w.lower() for w in remainder.split() if len(w) > 2)

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_keywords: list[str] = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        # Pre-compile regex patterns for word boundary matching
        patterns: list[re.Pattern] = []
        for kw in unique_keywords:
            try:
                patterns.append(re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE))
            except re.error:
                continue

        for entry in entries:
            text = f"{entry.get('title', '')} {entry.get('abstract', '')} {entry.get('summary', '')} {entry.get('description', '')}"
            if not text.strip():
                entry["relevance_score"] = 0.0
                continue

            matched = sum(1 for pat in patterns if pat.search(text))
            score = min(matched / max(len(patterns), 1), 1.0)
            entry["relevance_score"] = round(score, 3)

        return entries

    def _persist_entries(self, entries: list[dict], topic_id: str) -> list[DigestEntry]:
        """Store entries in SQLite, skipping duplicates."""
        persisted: list[DigestEntry] = []

        with Session(db_engine) as session:
            for entry_data in entries:
                external_id = self._extract_external_id(entry_data)
                if not external_id:
                    continue

                # Check if already exists for this topic
                existing = session.exec(
                    select(DigestEntry).where(
                        DigestEntry.topic_id == topic_id,
                        DigestEntry.external_id == external_id,
                    )
                ).first()
                if existing:
                    continue

                db_entry = DigestEntry(
                    topic_id=topic_id,
                    source=entry_data.get("source", "unknown"),
                    external_id=external_id,
                    title=entry_data.get("title", ""),
                    authors=entry_data.get("authors", []),
                    abstract=entry_data.get("abstract", "") or entry_data.get("summary", "") or entry_data.get("description", ""),
                    url=self._resolve_url(entry_data),
                    metadata_extra={
                        k: str(v) if not isinstance(v, (str, int, float, bool, list, dict, type(None))) else v
                        for k, v in entry_data.items()
                        if k not in ("title", "authors", "abstract", "summary", "description", "source", "url", "pdf_url", "source_url")
                    },
                    relevance_score=entry_data.get("relevance_score", 0.0),
                    published_at=self._normalize_date(entry_data),
                )
                session.add(db_entry)
                persisted.append(db_entry)

            session.commit()
            for p in persisted:
                session.refresh(p)
                session.expunge(p)

        return persisted

    async def _summarize(self, entries: list[DigestEntry], topic: TopicProfile, days: int = 7) -> DigestReport:
        """Generate a summary report using DigestAgent."""
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=days)

        # Build source breakdown
        source_breakdown: dict[str, int] = {}
        for e in entries:
            source_breakdown[e.source] = source_breakdown.get(e.source, 0) + 1

        summary_text = ""
        highlights: list[dict] = []
        cost = 0.0

        if self._digest_agent and entries:
            # Prepare entries for the agent
            entries_for_llm = [
                {
                    "title": e.title,
                    "source": e.source,
                    "abstract": e.abstract[:500] if e.abstract else "",
                    "authors": e.authors[:3],
                    "url": e.url,
                    "published_at": e.published_at,
                    "relevance_score": e.relevance_score,
                }
                for e in entries[:30]  # Cap at 30 entries for LLM
            ]

            task_desc = json.dumps({
                "topic_name": topic.name,
                "period": f"Last {days} days",
                "entries": entries_for_llm,
                "instructions": (
                    "Only report facts present in the provided data. "
                    "Do not infer or fabricate information not explicitly stated. "
                    "Include the URL when referencing specific papers."
                ),
            }, ensure_ascii=False)

            context = ContextPackage(task_description=task_desc)
            try:
                output = await self._digest_agent.run(context)
                if output.output and not output.error:
                    summary_text = output.output.get("executive_summary", "")
                    highlights = output.output.get("highlights", [])
                    cost = output.cost
            except Exception as e:
                logger.warning("DigestAgent summarization failed: %s", e)

        # Create report
        report = DigestReport(
            topic_id=topic.id,
            period_start=period_start,
            period_end=now,
            entry_count=len(entries),
            summary=summary_text,
            highlights=highlights,
            source_breakdown=source_breakdown,
            cost=cost,
        )

        with Session(db_engine) as session:
            session.add(report)
            session.commit()
            session.refresh(report)
            session.expunge(report)

        return report

    @staticmethod
    def _resolve_url(entry_data: dict) -> str:
        """Resolve the best URL for an entry, with source-specific fallbacks."""
        url = (
            entry_data.get("url", "")
            or entry_data.get("pdf_url", "")
            or entry_data.get("source_url", "")
        )
        if url:
            return url

        source = entry_data.get("source", "")
        doi = entry_data.get("doi", "")

        if source == "biorxiv" and doi:
            return f"https://www.biorxiv.org/content/{doi}"
        if source == "arxiv":
            arxiv_id = entry_data.get("arxiv_id", "")
            if arxiv_id:
                return f"https://arxiv.org/abs/{arxiv_id}"
        if source == "pubmed":
            pmid = entry_data.get("pmid", "")
            if pmid:
                return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        if doi:
            return f"https://doi.org/{doi}"

        return ""

    @staticmethod
    def _normalize_date(entry_data: dict) -> str:
        """Parse various date formats and normalize to YYYY-MM-DD."""
        raw = (
            entry_data.get("date", "")
            or entry_data.get("published", "")
            or entry_data.get("published_at", "")
            or entry_data.get("year", "")
        )
        if not raw:
            return ""

        raw = str(raw).strip()

        if re.match(r'^\d{4}-\d{2}-\d{2}$', raw):
            return raw
        if re.match(r'^\d{4}$', raw):
            return raw

        for fmt in (
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y/%m/%d",
        ):
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # Handle timezone-aware ISO strings (e.g., 2024-01-15T10:30:00+00:00)
        try:
            if "T" in raw:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass

        return raw

    @staticmethod
    def _extract_external_id(entry: dict) -> str:
        """Extract the best unique external identifier for an entry."""
        # Priority: DOI > arXiv ID > paper_id > pmid > full_name
        for key in ("doi", "arxiv_id", "paper_id", "pmid", "full_name"):
            val = entry.get(key, "")
            if val:
                return str(val)
        return ""
