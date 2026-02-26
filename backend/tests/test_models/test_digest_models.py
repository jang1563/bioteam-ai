"""Tests for digest data models."""

import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")


from app.db.database import create_db_and_tables
from app.db.database import engine as db_engine
from app.models.digest import DigestEntry, DigestReport, TopicProfile
from sqlmodel import Session


def _uid() -> str:
    """Generate a unique suffix to avoid UNIQUE constraint collisions across runs."""
    return uuid.uuid4().hex[:8]


def setup_module():
    create_db_and_tables()


# === TopicProfile Tests ===


def test_topic_profile_create():
    """Should create a TopicProfile with defaults."""
    topic = TopicProfile(
        name="AI in Biology",
        queries=["AI biology research", "machine learning genomics"],
    )
    with Session(db_engine) as session:
        session.add(topic)
        session.commit()
        session.refresh(topic)
        tid = topic.id

    with Session(db_engine) as session:
        loaded = session.get(TopicProfile, tid)
        assert loaded is not None
        assert loaded.name == "AI in Biology"
        assert loaded.queries == ["AI biology research", "machine learning genomics"]
        assert loaded.schedule == "daily"
        assert loaded.is_active is True


def test_topic_profile_sources_default():
    """Default sources should include all 6 sources."""
    topic = TopicProfile(name="Test", queries=["test"])
    assert "pubmed" in topic.sources
    assert "arxiv" in topic.sources
    assert "huggingface" in topic.sources


def test_topic_profile_categories_json():
    """Categories should serialize as JSON."""
    topic = TopicProfile(
        name="Categorized",
        queries=["test"],
        categories={"arxiv": ["cs.AI", "q-bio"], "biorxiv": []},
    )
    with Session(db_engine) as session:
        session.add(topic)
        session.commit()
        session.refresh(topic)
        tid = topic.id

    with Session(db_engine) as session:
        loaded = session.get(TopicProfile, tid)
        assert loaded.categories["arxiv"] == ["cs.AI", "q-bio"]


# === DigestEntry Tests ===


def test_digest_entry_create():
    """Should create a DigestEntry."""
    ext_id = f"2502.{_uid()}"
    entry = DigestEntry(
        topic_id="topic-1",
        source="arxiv",
        external_id=ext_id,
        title="Test Paper",
        authors=["Author A", "Author B"],
        abstract="Test abstract",
        relevance_score=0.85,
    )
    with Session(db_engine) as session:
        session.add(entry)
        session.commit()
        session.refresh(entry)
        eid = entry.id

    with Session(db_engine) as session:
        loaded = session.get(DigestEntry, eid)
        assert loaded is not None
        assert loaded.source == "arxiv"
        assert loaded.authors == ["Author A", "Author B"]
        assert loaded.relevance_score == 0.85


def test_digest_entry_metadata_json():
    """metadata_extra should serialize as JSON."""
    entry = DigestEntry(
        topic_id="topic-1",
        source="github",
        external_id=f"user/repo-{_uid()}",
        title="Cool Repo",
        metadata_extra={"stars": 500, "language": "Python"},
    )
    with Session(db_engine) as session:
        session.add(entry)
        session.commit()
        session.refresh(entry)
        eid = entry.id

    with Session(db_engine) as session:
        loaded = session.get(DigestEntry, eid)
        assert loaded.metadata_extra["stars"] == 500


# === DigestReport Tests ===


def test_digest_report_create():
    """Should create a DigestReport."""
    report = DigestReport(
        topic_id="topic-1",
        entry_count=15,
        summary="This week's highlights in AI biology research.",
        highlights=[{"title": "Paper A", "one_liner": "Novel approach"}],
        source_breakdown={"arxiv": 8, "pubmed": 5, "github": 2},
        cost=0.01,
    )
    with Session(db_engine) as session:
        session.add(report)
        session.commit()
        session.refresh(report)
        rid = report.id

    with Session(db_engine) as session:
        loaded = session.get(DigestReport, rid)
        assert loaded is not None
        assert loaded.entry_count == 15
        assert loaded.source_breakdown["arxiv"] == 8
        assert loaded.cost == 0.01


def test_digest_report_highlights_json():
    """Highlights should round-trip through JSON."""
    highlights = [
        {"title": "Paper A", "source": "arxiv", "one_liner": "Novel method"},
        {"title": "Paper B", "source": "pubmed", "one_liner": "Important finding"},
    ]
    report = DigestReport(
        topic_id="topic-1",
        entry_count=2,
        highlights=highlights,
    )
    with Session(db_engine) as session:
        session.add(report)
        session.commit()
        session.refresh(report)
        rid = report.id

    with Session(db_engine) as session:
        loaded = session.get(DigestReport, rid)
        assert len(loaded.highlights) == 2
        assert loaded.highlights[0]["title"] == "Paper A"


def test_digest_report_defaults():
    """Default values should be set correctly."""
    report = DigestReport(topic_id="topic-1")
    assert report.entry_count == 0
    assert report.summary == ""
    assert report.highlights == []
    assert report.source_breakdown == {}
    assert report.cost == 0.0
