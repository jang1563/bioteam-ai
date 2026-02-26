#!/usr/bin/env python3
"""Digest Pipeline Validation — Real Data Execution.

Runs the DigestPipeline with REAL API calls (PubMed, bioRxiv, arXiv,
GitHub, HuggingFace, Semantic Scholar) to validate end-to-end functionality.

Usage:
    cd backend
    uv run python -m scripts.run_digest_validation
    uv run python -m scripts.run_digest_validation --topic "CRISPR gene therapy"

Requires: ANTHROPIC_API_KEY env var. Recommended: NCBI_EMAIL.
Estimated cost: ~$0.02 per run (1 Sonnet call for summarization).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# Ensure backend is importable and .env is found
BACKEND_DIR = Path(__file__).parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

if (PROJECT_ROOT / ".env").exists() and not Path(".env").exists():
    os.chdir(PROJECT_ROOT)

# Initialize DB tables before model imports
from app.db.database import create_db_and_tables
create_db_and_tables()

from app.agents.base import BaseAgent
from app.agents.digest_agent import DigestAgent
from app.config import settings
from app.digest.pipeline import DigestPipeline
from app.llm.layer import LLMLayer
from app.models.digest import TopicProfile

logger = logging.getLogger("digest_validation")

DEFAULT_TOPIC = "spaceflight genomics"
DEFAULT_QUERIES = [
    "spaceflight gene expression",
    "microgravity transcriptomics",
    "astronaut omics ISS",
]


def check_env() -> list[str]:
    """Check required environment variables."""
    warnings = []
    if not settings.anthropic_api_key:
        print("  ERROR: ANTHROPIC_API_KEY is not set. Add it to .env file.")
        sys.exit(1)
    if not settings.ncbi_email and not os.environ.get("NCBI_EMAIL"):
        warnings.append("NCBI_EMAIL not set -- PubMed search may be limited")
    return warnings


def create_test_topic(name: str, queries: list[str]) -> TopicProfile:
    """Create a temporary TopicProfile for validation."""
    return TopicProfile(
        name=name,
        queries=queries,
        sources=["pubmed", "biorxiv", "arxiv", "github", "huggingface", "semantic_scholar"],
        categories=["genomics", "transcriptomics", "bioinformatics"],
        schedule="manual",
    )


async def run_validation(topic_name: str, queries: list[str]) -> None:
    """Run the digest pipeline and print results."""
    print()
    print("=" * 70)
    print("  DIGEST PIPELINE VALIDATION -- REAL DATA")
    print("=" * 70)

    warnings = check_env()
    for w in warnings:
        print(f"  WARNING: {w}")

    # Create test topic
    topic = create_test_topic(topic_name, queries)
    print(f"\n  Topic: {topic.name}")
    print(f"  Queries: {', '.join(topic.queries)}")
    print(f"  Sources: {', '.join(topic.sources)}")

    # Initialize pipeline with real DigestAgent
    llm = LLMLayer()
    digest_spec = BaseAgent.load_spec("digest_agent")
    digest_agent = DigestAgent(spec=digest_spec, llm=llm)
    pipeline = DigestPipeline(digest_agent=digest_agent)

    print("\n  Running pipeline...")
    t0 = time.time()
    try:
        report = await pipeline.run(topic, days=7)
    except Exception as e:
        print(f"\n  PIPELINE CRASHED: {type(e).__name__}: {e}")
        logger.exception("Pipeline crashed")
        return
    elapsed = time.time() - t0

    # === Source Report ===
    print("\n" + "=" * 70)
    print("  SOURCE REPORT")
    print("=" * 70)

    source_counts: dict[str, int] = {}
    if hasattr(report, "entries_by_source"):
        source_counts = report.entries_by_source or {}
    else:
        # Count from entries if available
        from app.db.database import engine as db_engine
        from app.models.digest import DigestEntry
        from sqlmodel import Session, select, func

        with Session(db_engine) as session:
            rows = session.exec(
                select(DigestEntry.source, func.count(DigestEntry.id))
                .where(DigestEntry.topic_id == topic.id)
                .group_by(DigestEntry.source)
            ).all()
            source_counts = {row[0]: row[1] for row in rows}

    total_entries = sum(source_counts.values())
    for source, count in sorted(source_counts.items()):
        status = "ok" if count > 0 else "EMPTY"
        print(f"  {source:<20} {count:>4} entries  [{status}]")
    print(f"  {'TOTAL':<20} {total_entries:>4} entries")

    # === Dedup Report ===
    print("\n" + "=" * 70)
    print("  DEDUP & SCORING")
    print("=" * 70)
    print(f"  Total after dedup: {report.total_entries}")
    if hasattr(report, "duplicates_removed"):
        print(f"  Duplicates removed: {report.duplicates_removed}")

    # === Summary Report ===
    print("\n" + "=" * 70)
    print("  SUMMARY (DigestAgent output)")
    print("=" * 70)
    if report.summary:
        print(f"  {report.summary[:500]}")
    else:
        print("  (No summary generated)")

    if report.highlights:
        print(f"\n  Highlights ({len(report.highlights)}):")
        for h in report.highlights[:5]:
            if isinstance(h, dict):
                print(f"    - {h.get('title', '?')[:80]}")
            else:
                print(f"    - {str(h)[:80]}")

    # === Cost Report ===
    print("\n" + "=" * 70)
    print("  METRICS")
    print("=" * 70)
    print(f"  Duration: {elapsed:.1f}s")
    if hasattr(report, "cost"):
        print(f"  LLM cost: ${report.cost:.4f}")

    print(f"\n  STATUS: {'COMPLETED' if total_entries > 0 else 'NO ENTRIES FOUND'}")


def main():
    parser = argparse.ArgumentParser(description="Digest Pipeline Validation")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help="Topic name")
    parser.add_argument("--queries", nargs="+", default=DEFAULT_QUERIES, help="Search queries")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)-30s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)

    asyncio.run(run_validation(args.topic, args.queries))


if __name__ == "__main__":
    main()
