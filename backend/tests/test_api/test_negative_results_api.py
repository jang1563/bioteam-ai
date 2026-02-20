"""Tests for Negative Results (Lab KB) CRUD API endpoints."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.negative_results import router as nr_router
from app.db.database import create_db_and_tables


def _client():
    """Create a test app with just the NR router (no middleware)."""
    create_db_and_tables()
    test_app = FastAPI()
    test_app.include_router(nr_router)
    return TestClient(test_app)


def _create_entry(client, **overrides):
    """Helper to create a negative result entry."""
    payload = {
        "claim": "Drug X inhibits target Y",
        "outcome": "No inhibition observed at 10uM",
        "source": "internal",
        "confidence": 0.7,
        "failure_category": "protocol",
        **overrides,
    }
    resp = client.post("/api/v1/negative-results", json=payload)
    assert resp.status_code == 201
    return resp.json()


def test_create_negative_result():
    """POST /api/v1/negative-results should create a new entry."""
    client = _client()
    data = _create_entry(client)
    assert data["claim"] == "Drug X inhibits target Y"
    assert data["outcome"] == "No inhibition observed at 10uM"
    assert data["source"] == "internal"
    assert data["confidence"] == 0.7
    assert data["failure_category"] == "protocol"
    assert data["created_by"] == "human"
    assert data["verification_status"] == "unverified"
    assert "id" in data


def test_get_negative_result():
    """GET /api/v1/negative-results/{id} should return the entry."""
    client = _client()
    created = _create_entry(client)
    resp = client.get(f"/api/v1/negative-results/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]
    assert resp.json()["claim"] == created["claim"]


def test_get_negative_result_not_found():
    """GET /api/v1/negative-results/nonexistent should return 404."""
    client = _client()
    resp = client.get("/api/v1/negative-results/nonexistent-id")
    assert resp.status_code == 404


def test_list_negative_results():
    """GET /api/v1/negative-results should list all entries."""
    client = _client()
    _create_entry(client, claim="Claim A")
    _create_entry(client, claim="Claim B")
    resp = client.get("/api/v1/negative-results")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2


def test_list_negative_results_filter_by_source():
    """GET /api/v1/negative-results?source=internal should filter."""
    client = _client()
    _create_entry(client, source="internal", claim="Internal claim")
    _create_entry(client, source="clinical_trial", claim="Trial claim")
    resp = client.get("/api/v1/negative-results?source=internal")
    assert resp.status_code == 200
    data = resp.json()
    assert all(r["source"] == "internal" for r in data)


def test_update_negative_result():
    """PUT /api/v1/negative-results/{id} should update fields."""
    client = _client()
    created = _create_entry(client)
    resp = client.put(f"/api/v1/negative-results/{created['id']}", json={
        "confidence": 0.9,
        "verification_status": "confirmed",
        "verified_by": "jkim",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["confidence"] == 0.9
    assert data["verification_status"] == "confirmed"
    assert data["verified_by"] == "jkim"
    # Unchanged fields preserved
    assert data["claim"] == created["claim"]


def test_update_negative_result_not_found():
    """PUT /api/v1/negative-results/nonexistent should return 404."""
    client = _client()
    resp = client.put("/api/v1/negative-results/nonexistent-id", json={
        "confidence": 0.9,
    })
    assert resp.status_code == 404


def test_delete_negative_result():
    """DELETE /api/v1/negative-results/{id} should remove the entry."""
    client = _client()
    created = _create_entry(client)
    resp = client.delete(f"/api/v1/negative-results/{created['id']}")
    assert resp.status_code == 204

    # Verify it's gone
    resp = client.get(f"/api/v1/negative-results/{created['id']}")
    assert resp.status_code == 404


def test_delete_negative_result_not_found():
    """DELETE /api/v1/negative-results/nonexistent should return 404."""
    client = _client()
    resp = client.delete("/api/v1/negative-results/nonexistent-id")
    assert resp.status_code == 404


def test_create_validation_invalid_source():
    """POST with invalid source should return 422."""
    client = _client()
    resp = client.post("/api/v1/negative-results", json={
        "claim": "test",
        "outcome": "test",
        "source": "INVALID",
    })
    assert resp.status_code == 422


def test_create_with_all_fields():
    """POST with all optional fields should work."""
    client = _client()
    resp = client.post("/api/v1/negative-results", json={
        "claim": "Compound Z activates pathway W",
        "outcome": "No activation detected",
        "source": "clinical_trial",
        "confidence": 0.85,
        "failure_category": "biological",
        "conditions": {"temperature": "37C", "cell_line": "HeLa"},
        "implications": ["Pathway may require cofactor", "Consider alternative compound"],
        "organism": "Homo sapiens",
        "source_id": "NCT12345678",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["conditions"] == {"temperature": "37C", "cell_line": "HeLa"}
    assert len(data["implications"]) == 2
    assert data["organism"] == "Homo sapiens"
    assert data["source_id"] == "NCT12345678"


if __name__ == "__main__":
    print("Testing Negative Results API:")
    test_create_negative_result()
    test_get_negative_result()
    test_get_negative_result_not_found()
    test_list_negative_results()
    test_list_negative_results_filter_by_source()
    test_update_negative_result()
    test_update_negative_result_not_found()
    test_delete_negative_result()
    test_delete_negative_result_not_found()
    test_create_validation_invalid_source()
    test_create_with_all_fields()
    print("\nAll Negative Results API tests passed!")
