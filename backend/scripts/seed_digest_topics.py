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
    {
        "name": "Cancer Genomics and Precision Oncology",
        "queries": [
            "cancer genomics somatic mutation",
            "precision oncology targeted therapy biomarker",
            "tumor microenvironment immunotherapy",
            "CRISPR cancer functional genomics",
            "liquid biopsy circulating tumor DNA",
            "single cell RNA cancer heterogeneity",
        ],
        "sources": ["pubmed", "biorxiv", "semantic_scholar"],
        "categories": {
            "domain": "cancer genomics",
            "organisms": ["human", "mouse", "cell lines"],
        },
        "schedule": "daily",
    },
    {
        "name": "AI and Machine Learning in Biology",
        "queries": [
            "large language model biology protein",
            "foundation model genomics transcriptomics",
            "AlphaFold protein structure prediction",
            "deep learning drug discovery",
            "graph neural network biological network",
            "multi-omics integration machine learning",
        ],
        "sources": ["biorxiv", "arxiv", "huggingface", "github", "semantic_scholar"],
        "categories": {
            "domain": "AI biology",
            "organisms": ["computational", "human"],
        },
        "schedule": "daily",
    },
    {
        "name": "Neuroscience and Neurodegeneration",
        "queries": [
            "Alzheimer's disease neurodegeneration amyloid tau",
            "neuroinflammation microglia brain",
            "adult neurogenesis hippocampus",
            "Parkinson's disease alpha-synuclein",
            "synaptic plasticity long-term potentiation",
            "single cell atlas brain transcriptomics",
        ],
        "sources": ["pubmed", "biorxiv", "semantic_scholar"],
        "categories": {
            "domain": "neuroscience",
            "organisms": ["human", "mouse", "rat"],
        },
        "schedule": "weekly",
    },
    {
        "name": "Gene Therapy and CRISPR",
        "queries": [
            "CRISPR Cas9 gene editing therapeutic",
            "base editing prime editing in vivo",
            "AAV gene therapy clinical trial",
            "RNA therapeutics siRNA antisense oligonucleotide",
            "CRISPR off-target safety delivery",
        ],
        "sources": ["pubmed", "biorxiv", "semantic_scholar"],
        "categories": {
            "domain": "gene therapy",
            "organisms": ["human", "mouse", "cell lines"],
        },
        "schedule": "weekly",
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
