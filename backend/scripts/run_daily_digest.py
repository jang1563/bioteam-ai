#!/usr/bin/env python3
"""Daily Digest Runner — standalone script for GitHub Actions cron.

Runs the DigestPipeline for all active daily topics, generates Gemini
summaries, and sends email reports.  Designed to run without a persistent
server (creates its own DB, seeds topics if needed).

Usage:
    cd backend
    uv run python -m scripts.run_daily_digest

Environment variables (set via GitHub Secrets):
    GOOGLE_API_KEY          — Gemini API key (required for free summarization)
    SMTP_USER               — Gmail address
    SMTP_PASSWORD           — Gmail App Password
    DIGEST_RECIPIENTS       — Comma-separated email addresses
    NCBI_EMAIL              — For PubMed polite access (recommended)
    ANTHROPIC_API_KEY       — Fallback LLM (optional, Gemini preferred)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Path setup ──────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

# Ensure CWD is backend/ so sqlite:///data/bioteam.db resolves correctly
os.chdir(BACKEND_DIR)

# Create data/ directory if it doesn't exist (fresh CI environment)
(BACKEND_DIR / "data").mkdir(exist_ok=True)

# ── Logging ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-30s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
# Suppress noisy loggers
for name in ("httpx", "httpcore", "chromadb", "anthropic", "urllib3"):
    logging.getLogger(name).setLevel(logging.WARNING)

logger = logging.getLogger("daily_digest")

# ── DB & model imports (after path setup) ───────────────────────────
from app.db.database import create_db_and_tables  # noqa: E402
from app.db.database import engine as db_engine
from app.models.digest import DigestEntry, DigestReport, TopicProfile  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

create_db_and_tables()

from app.agents.base import BaseAgent  # noqa: E402
from app.agents.digest_agent import DigestAgent  # noqa: E402
from app.config import settings  # noqa: E402
from app.digest.pipeline import DigestPipeline  # noqa: E402
from app.email.sender import is_email_configured, send_digest_email  # noqa: E402
from app.llm.layer import LLMLayer  # noqa: E402

# ── Topic definitions (same as seed_digest_topics.py) ───────────────
TOPICS: list[dict] = [
    {
        "name": "AI in Science",
        "queries": [
            "AI scientist automated research",
            "LLM scientific discovery",
            "autonomous lab agent",
            "machine learning hypothesis generation",
            "AI-driven experiment design",
        ],
        "sources": ["pubmed", "biorxiv", "arxiv", "semantic_scholar", "github", "huggingface"],
        "categories": {"arxiv": ["cs.AI", "cs.LG", "cs.CL", "cs.MA"]},
        "schedule": "daily",
    },
    {
        "name": "AI biology and medicine",
        "queries": [
            "artificial intelligence biology",
            "deep learning genomics",
            "machine learning drug discovery",
            "foundation model protein structure",
            "large language model biomedical",
        ],
        "sources": ["pubmed", "biorxiv", "arxiv", "semantic_scholar", "github", "huggingface"],
        "categories": {"arxiv": ["q-bio", "cs.AI", "cs.LG", "cs.CL"]},
        "schedule": "daily",
    },
    {
        "name": "Space Biology and Biomedicine",
        "queries": [
            "space biology spaceflight",
            "microgravity cell biology",
            "space radiation biology",
            "astronaut health biomedicine",
            "spaceflight omics gene expression",
        ],
        "sources": ["pubmed", "biorxiv", "arxiv", "semantic_scholar"],
        "categories": {"domain": "space biology", "organisms": ["human", "mouse", "cell lines"]},
        "schedule": "daily",
    },
]


def ensure_topics() -> list[TopicProfile]:
    """Seed topics if DB is empty, then return all active daily topics."""
    with Session(db_engine) as session:
        existing = session.exec(select(TopicProfile)).all()
        if not existing:
            logger.info("No topics found — seeding defaults")
            for defn in TOPICS:
                topic = TopicProfile(
                    name=defn["name"],
                    queries=defn["queries"],
                    sources=defn["sources"],
                    categories=defn["categories"],
                    schedule=defn["schedule"],
                )
                session.add(topic)
            session.commit()
            existing = session.exec(select(TopicProfile)).all()

        # Return only active daily topics
        active = [t for t in existing if t.is_active and t.schedule == "daily"]
        for t in active:
            session.expunge(t)
        return active


def _already_emailed_today(topic: TopicProfile) -> bool:
    """Return True if a digest report was already created for this topic in the last 12 hours.

    Prevents duplicate emails when GitHub Actions fires multiple times or overlaps
    with a running server scheduler that also generates reports.
    """
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=12)
    with Session(db_engine) as session:
        latest = session.exec(
            select(DigestReport)
            .where(DigestReport.topic_id == topic.id)
            .order_by(DigestReport.created_at.desc())
            .limit(1)
        ).first()
    if latest is None:
        return False
    created_at = latest.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at > cutoff


async def run_digest_for_topic(
    pipeline: DigestPipeline, topic: TopicProfile
) -> bool:
    """Run pipeline + send email for a single topic. Returns True on success."""
    logger.info("━━━ Processing: %s ━━━", topic.name)

    # Guard: skip if a report was already created in the last 12h (prevents duplicate
    # emails when the server scheduler overlaps with this CI script on a persistent DB).
    if _already_emailed_today(topic):
        logger.info("Skipping '%s' — report already created in last 12h", topic.name)
        return True

    try:
        report = await pipeline.run(topic, days=7)
    except Exception as e:
        logger.error("Pipeline failed for '%s': %s", topic.name, e)
        return False

    logger.info(
        "Report: %d entries, summary=%d chars, cost=$%.4f",
        report.entry_count,
        len(report.summary or ""),
        report.cost,
    )

    # Send email
    if not is_email_configured():
        logger.warning("Email not configured — skipping send")
        return True

    try:
        with Session(db_engine) as session:
            entries = session.exec(
                select(DigestEntry)
                .where(DigestEntry.topic_id == topic.id)
                .order_by(DigestEntry.relevance_score.desc())
                .limit(10)
            ).all()
            for entry in entries:
                session.expunge(entry)

        sent = await send_digest_email(report, topic, list(entries))
        if sent:
            logger.info("Email sent for '%s'", topic.name)
        else:
            logger.warning("Email send returned False for '%s'", topic.name)
        return sent
    except Exception as e:
        logger.error("Email failed for '%s': %s", topic.name, e)
        return False


async def main() -> None:
    """Run daily digest for all active topics."""
    logger.info("=" * 60)
    logger.info("  BioTeam-AI Daily Digest Runner")
    logger.info("=" * 60)
    logger.info("  Gemini model: %s", settings.gemini_model)
    logger.info("  LLM provider: %s", settings.digest_llm_provider)
    logger.info("  Email configured: %s", is_email_configured())
    logger.info("  Recipients: %s", settings.digest_recipients or "(none)")

    # Ensure topics exist
    topics = ensure_topics()
    if not topics:
        logger.warning("No active daily topics found — nothing to do")
        return

    logger.info("  Active daily topics: %d", len(topics))
    for t in topics:
        logger.info("    - %s", t.name)

    # Initialize pipeline
    llm = LLMLayer()
    digest_spec = BaseAgent.load_spec("digest_agent")
    digest_agent = DigestAgent(spec=digest_spec, llm=llm)
    pipeline = DigestPipeline(digest_agent=digest_agent)

    # Run for each topic sequentially (avoid overwhelming APIs)
    success = 0
    for topic in topics:
        ok = await run_digest_for_topic(pipeline, topic)
        if ok:
            success += 1

    pipeline.shutdown()

    logger.info("=" * 60)
    logger.info("  Done: %d/%d topics processed successfully", success, len(topics))
    logger.info("=" * 60)

    if success < len(topics):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
