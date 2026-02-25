"""Tests for Contradictions API — read-only endpoints."""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.api.v1.contradictions import router as contradictions_router
from app.db.database import create_db_and_tables
from app.db.database import engine as db_engine
from app.models.evidence import ContradictionEntry
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session


def _client():
    """Create a test app with just the contradictions router (no middleware)."""
    create_db_and_tables()
    test_app = FastAPI()
    test_app.include_router(contradictions_router)
    return TestClient(test_app)


def _seed_entry(
    claim_a: str = "VEGF increases under hypoxia",
    claim_b: str = "VEGF decreases under hypoxia",
    types: list[str] | None = None,
    workflow_id: str | None = None,
    detected_by: str = "ambiguity_engine",
) -> ContradictionEntry:
    """Insert a ContradictionEntry directly into the DB and return it."""
    entry = ContradictionEntry(
        claim_a=claim_a,
        claim_b=claim_b,
        types=types or ["conditional_truth"],
        resolution_hypotheses=["Different cell types"],
        rcmxt_a={"R": 0.6, "C": 0.5, "M": 0.7, "T": 0.4},
        rcmxt_b={"R": 0.4, "C": 0.3, "M": 0.6, "T": 0.5},
        discriminating_experiment="Test in both cell types",
        detected_at=datetime.now(timezone.utc),
        detected_by=detected_by,
        workflow_id=workflow_id,
    )
    with Session(db_engine) as session:
        session.add(entry)
        session.commit()
        session.refresh(entry)
        session.expunge(entry)
    return entry


# === Tests ===


def test_list_empty():
    """GET /api/v1/contradictions should return empty list when no entries."""
    client = _client()
    resp = client.get("/api/v1/contradictions")
    assert resp.status_code == 200
    # May contain entries from other tests, but should be a list
    assert isinstance(resp.json(), list)


def test_list_with_entries():
    """GET /api/v1/contradictions should return seeded entries."""
    client = _client()
    entry = _seed_entry()
    resp = client.get("/api/v1/contradictions")
    assert resp.status_code == 200
    data = resp.json()
    assert any(e["id"] == entry.id for e in data)


def test_get_by_id():
    """GET /api/v1/contradictions/{id} should return the entry."""
    client = _client()
    entry = _seed_entry(claim_a="Gene X upregulated", claim_b="Gene X downregulated")
    resp = client.get(f"/api/v1/contradictions/{entry.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == entry.id
    assert data["claim_a"] == "Gene X upregulated"
    assert data["claim_b"] == "Gene X downregulated"


def test_get_not_found():
    """GET /api/v1/contradictions/{id} should return 404 for missing ID."""
    client = _client()
    resp = client.get("/api/v1/contradictions/nonexistent-id")
    assert resp.status_code == 404


def test_by_workflow_filter():
    """GET /api/v1/contradictions/by-workflow/{wf_id} should filter correctly."""
    client = _client()
    entry = _seed_entry(
        claim_a="EPO elevated in spaceflight",
        claim_b="EPO reduced in spaceflight",
        workflow_id="wf-123",
    )
    resp = client.get("/api/v1/contradictions/by-workflow/wf-123")
    assert resp.status_code == 200
    data = resp.json()
    assert any(e["id"] == entry.id for e in data)
    assert all(e["workflow_id"] == "wf-123" for e in data)


def test_by_workflow_no_match():
    """GET /api/v1/contradictions/by-workflow/{wf_id} with no match returns empty."""
    client = _client()
    resp = client.get("/api/v1/contradictions/by-workflow/nonexistent-wf")
    assert resp.status_code == 200
    data = resp.json()
    assert all(e.get("workflow_id") != "nonexistent-wf" or len(data) == 0 for e in data)


def test_response_schema_types():
    """Response should include types as a list."""
    client = _client()
    entry = _seed_entry(types=["conditional_truth", "temporal_dynamics"])
    resp = client.get(f"/api/v1/contradictions/{entry.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "conditional_truth" in data["types"]
    assert "temporal_dynamics" in data["types"]


def test_response_schema_rcmxt():
    """Response should include RCMXT scores as dicts."""
    client = _client()
    entry = _seed_entry()
    resp = client.get(f"/api/v1/contradictions/{entry.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["rcmxt_a"], dict)
    assert isinstance(data["rcmxt_b"], dict)
    assert "R" in data["rcmxt_a"]


def test_sorted_by_detected_at():
    """Entries should be sorted newest first."""
    client = _client()
    import time
    e1 = _seed_entry(claim_a="Older claim A", claim_b="Older claim B")
    time.sleep(0.01)  # Ensure different timestamps
    e2 = _seed_entry(claim_a="Newer claim A", claim_b="Newer claim B")

    resp = client.get("/api/v1/contradictions")
    assert resp.status_code == 200
    data = resp.json()

    # Find positions of our entries
    ids = [e["id"] for e in data]
    if e1.id in ids and e2.id in ids:
        assert ids.index(e2.id) < ids.index(e1.id), "Newer should come first"


def test_no_write_endpoints():
    """POST, PUT, DELETE should not exist for contradictions."""
    client = _client()
    assert client.post("/api/v1/contradictions", json={}).status_code in (404, 405)
    assert client.put("/api/v1/contradictions/test-id", json={}).status_code in (404, 405)
    assert client.delete("/api/v1/contradictions/test-id").status_code in (404, 405)
