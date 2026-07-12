#!/usr/bin/env python3
"""Seed digest topics into the database.

Usage:
    cd backend
    uv run python -m scripts.seed_digest_topics
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

# Ensure CWD is backend/ so sqlite:///data/bioteam.db resolves correctly
os.chdir(BACKEND_DIR)

from app.db.database import create_db_and_tables, engine  # noqa: E402
from app.models.digest import TopicProfile  # noqa: E402

create_db_and_tables()

from sqlmodel import Session, select  # noqa: E402

# ── Topic definitions ──────────────────────────────────────────────
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
        "categories": {
            "arxiv": ["cs.AI", "cs.LG", "cs.CL", "cs.MA"],
        },
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
        "categories": {
            "arxiv": ["q-bio", "cs.AI", "cs.LG", "cs.CL"],
        },
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
        "categories": {
            "domain": "space biology",
            "organisms": ["human", "mouse", "cell lines"],
        },
        "schedule": "daily",
    },
]


def seed_topics() -> None:
    """Insert topics that don't already exist (matched by name)."""
    with Session(engine) as session:
        for defn in TOPICS:
            existing = session.exec(
                select(TopicProfile).where(TopicProfile.name == defn["name"])
            ).first()
            if existing:
                print(f"  SKIP (already exists): {defn['name']}  [id={existing.id}]")
                continue

            topic = TopicProfile(
                name=defn["name"],
                queries=defn["queries"],
                sources=defn["sources"],
                categories=defn["categories"],
                schedule=defn["schedule"],
            )
            session.add(topic)
            session.commit()
            session.refresh(topic)
            print(f"  CREATED: {topic.name}  [id={topic.id}]")


if __name__ == "__main__":
    print("Seeding digest topics...")
    seed_topics()
    print("Done.")
