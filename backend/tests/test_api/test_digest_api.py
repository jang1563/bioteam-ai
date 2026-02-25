"""Tests for Research Digest API endpoints."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.api.v1.digest import router as digest_router
from app.db.database import create_db_and_tables
from app.db.database import engine as db_engine
from app.models.digest import DigestEntry, DigestReport, TopicProfile
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session


def _client():
    """Create a test app with just the digest router (no middleware)."""
    create_db_and_tables()
    test_app = FastAPI()
    test_app.include_router(digest_router)
    return TestClient(test_app)


def _seed_topic(name: str = "AI Biology", queries: list[str] | None = None) -> TopicProfile:
    topic = TopicProfile(
        name=name,
        queries=queries or ["AI biology research"],
        sources=["pubmed", "arxiv"],
    )
    with Session(db_engine) as session:
        session.add(topic)
        session.commit()
        session.refresh(topic)
        session.expunge(topic)
    return topic


def _seed_entry(topic_id: str, source: str = "arxiv", title: str = "Test Paper") -> DigestEntry:
    entry = DigestEntry(
        topic_id=topic_id,
        source=source,
        external_id=f"10.1234/{title.replace(' ', '_').lower()}",
        title=title,
        authors=["Author A"],
        abstract="Test abstract.",
        relevance_score=0.8,
    )
    with Session(db_engine) as session:
        session.add(entry)
        session.commit()
        session.refresh(entry)
        session.expunge(entry)
    return entry


def _seed_report(topic_id: str) -> DigestReport:
    report = DigestReport(
        topic_id=topic_id,
        entry_count=5,
        summary="This week's digest.",
        highlights=[{"title": "Paper A", "one_liner": "Important"}],
        source_breakdown={"arxiv": 3, "pubmed": 2},
        cost=0.01,
    )
    with Session(db_engine) as session:
        session.add(report)
        session.commit()
        session.refresh(report)
        session.expunge(report)
    return report


# === Topic CRUD Tests ===


def test_create_topic():
    """POST /digest/topics should create a new topic."""
    client = _client()
    resp = client.post("/api/v1/digest/topics", json={
        "name": "Test Topic Create",
        "queries": ["test query"],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Topic Create"
    assert data["queries"] == ["test query"]
    assert data["schedule"] == "daily"
    assert data["is_active"] is True


def test_list_topics():
    """GET /digest/topics should return all topics."""
    client = _client()
    _seed_topic("List Test Topic")
    resp = client.get("/api/v1/digest/topics")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_topic():
    """GET /digest/topics/{id} should return the topic."""
    client = _client()
    topic = _seed_topic("Get Test Topic")
    resp = client.get(f"/api/v1/digest/topics/{topic.id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Get Test Topic"


def test_get_topic_not_found():
    """GET /digest/topics/{id} should return 404 for missing ID."""
    client = _client()
    resp = client.get("/api/v1/digest/topics/nonexistent")
    assert resp.status_code == 404


def test_update_topic():
    """PUT /digest/topics/{id} should update the topic."""
    client = _client()
    topic = _seed_topic("Update Test Topic")
    resp = client.put(f"/api/v1/digest/topics/{topic.id}", json={
        "name": "Updated Name",
        "schedule": "weekly",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Updated Name"
    assert data["schedule"] == "weekly"


def test_delete_topic():
    """DELETE /digest/topics/{id} should delete the topic."""
    client = _client()
    topic = _seed_topic("Delete Test Topic")
    resp = client.delete(f"/api/v1/digest/topics/{topic.id}")
    assert resp.status_code == 204
    # Verify deleted
    resp2 = client.get(f"/api/v1/digest/topics/{topic.id}")
    assert resp2.status_code == 404


# === Entry Tests ===


def test_list_entries():
    """GET /digest/entries should return entries."""
    client = _client()
    topic = _seed_topic("Entry List Topic")
    _seed_entry(topic.id, title="Entry List Paper")
    resp = client.get("/api/v1/digest/entries", params={"topic_id": topic.id})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_get_entry():
    """GET /digest/entries/{id} should return the entry."""
    client = _client()
    topic = _seed_topic("Entry Get Topic")
    entry = _seed_entry(topic.id, title="Entry Get Paper")
    resp = client.get(f"/api/v1/digest/entries/{entry.id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Entry Get Paper"


def test_get_entry_not_found():
    """GET /digest/entries/{id} should return 404."""
    client = _client()
    resp = client.get("/api/v1/digest/entries/nonexistent")
    assert resp.status_code == 404


# === Report Tests ===


def test_list_reports():
    """GET /digest/reports should return reports."""
    client = _client()
    topic = _seed_topic("Report List Topic")
    _seed_report(topic.id)
    resp = client.get("/api/v1/digest/reports", params={"topic_id": topic.id})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_get_report():
    """GET /digest/reports/{id} should return the report."""
    client = _client()
    topic = _seed_topic("Report Get Topic")
    report = _seed_report(topic.id)
    resp = client.get(f"/api/v1/digest/reports/{report.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entry_count"] == 5
    assert data["source_breakdown"]["arxiv"] == 3


# === Stats Tests ===


def test_stats():
    """GET /digest/stats should return aggregate stats."""
    client = _client()
    resp = client.get("/api/v1/digest/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_topics" in data
    assert "total_entries" in data
    assert "entries_by_source" in data


# === Validation Tests ===


def test_create_topic_validation():
    """POST /digest/topics should reject invalid data."""
    client = _client()
    # Empty name
    resp = client.post("/api/v1/digest/topics", json={"name": "", "queries": ["test"]})
    assert resp.status_code == 422

    # No queries
    resp = client.post("/api/v1/digest/topics", json={"name": "Test", "queries": []})
    assert resp.status_code == 422

    # Invalid schedule
    resp = client.post("/api/v1/digest/topics", json={
        "name": "Test", "queries": ["q"], "schedule": "hourly",
    })
    assert resp.status_code == 422


def test_create_topic_invalid_source():
    """POST /digest/topics should reject invalid source names."""
    client = _client()
    resp = client.post("/api/v1/digest/topics", json={
        "name": "Bad Source Topic",
        "queries": ["test"],
        "sources": ["pubmed", "invalid_source"],
    })
    assert resp.status_code == 422


def test_entries_sort_by_date():
    """GET /digest/entries?sort_by=date should accept date sort."""
    client = _client()
    topic = _seed_topic("Sort Date Topic")
    _seed_entry(topic.id, title="Sort Date Paper")
    resp = client.get("/api/v1/digest/entries", params={
        "topic_id": topic.id,
        "sort_by": "date",
    })
    assert resp.status_code == 200


def test_entries_sort_by_invalid():
    """GET /digest/entries?sort_by=invalid should return 422."""
    client = _client()
    resp = client.get("/api/v1/digest/entries", params={"sort_by": "invalid"})
    assert resp.status_code == 422


def test_stats_returns_aggregates():
    """GET /digest/stats should return proper aggregate structure."""
    client = _client()
    resp = client.get("/api/v1/digest/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["total_topics"], int)
    assert isinstance(data["total_entries"], int)
    assert isinstance(data["total_reports"], int)
    assert isinstance(data["entries_by_source"], dict)
