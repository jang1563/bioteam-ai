"""Tests for Data Integrity Audit API endpoints.

Tests covering:
- List/get/update/delete findings (CRUD)
- Trigger ad-hoc audit
- List audit runs
- Aggregate stats
- Filter by severity, category, status
- Pagination
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from unittest.mock import AsyncMock, MagicMock

from app.api.v1.integrity import router as integrity_router
from app.api.v1.integrity import set_auditor_agent
from app.db.database import create_db_and_tables
from app.db.database import engine as db_engine
from app.models.integrity import AuditFinding, AuditRun
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session


def _client():
    """Create a test app with just the integrity router (no middleware)."""
    create_db_and_tables()
    test_app = FastAPI()
    test_app.include_router(integrity_router)
    return TestClient(test_app)


def _create_finding(**overrides) -> str:
    """Create a finding directly in DB, return its ID."""
    finding = AuditFinding(
        category=overrides.get("category", "gene_name_error"),
        severity=overrides.get("severity", "warning"),
        title=overrides.get("title", "Possible Excel corruption"),
        description=overrides.get("description", "1-Mar detected in table context"),
        source_text=overrides.get("source_text", "Gene 1-Mar was upregulated"),
        suggestion=overrides.get("suggestion", "Verify gene name; may be MARCH1"),
        confidence=overrides.get("confidence", 0.85),
        checker=overrides.get("checker", "gene_name_checker"),
        workflow_id=overrides.get("workflow_id"),
        paper_doi=overrides.get("paper_doi"),
        status=overrides.get("status", "open"),
    )
    with Session(db_engine) as session:
        session.add(finding)
        session.commit()
        session.refresh(finding)
        finding_id = finding.id
    return finding_id


def _create_run(**overrides) -> str:
    """Create an audit run directly in DB, return its ID."""
    run = AuditRun(
        trigger=overrides.get("trigger", "manual"),
        total_findings=overrides.get("total_findings", 3),
        findings_by_severity=overrides.get("findings_by_severity", {"warning": 2, "error": 1}),
        findings_by_category=overrides.get("findings_by_category", {"gene_name_error": 2, "statistical_inconsistency": 1}),
        overall_level=overrides.get("overall_level", "minor_issues"),
        summary=overrides.get("summary", "Found 3 issues"),
        cost=overrides.get("cost", 0.0),
        duration_ms=overrides.get("duration_ms", 150),
    )
    with Session(db_engine) as session:
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id
    return run_id


# === Findings CRUD ===


def test_list_findings_empty():
    """GET /findings should return empty list when no findings exist."""
    client = _client()
    resp = client.get("/api/v1/integrity/findings")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_findings():
    """GET /findings should return all findings."""
    client = _client()
    _create_finding(title="Finding A")
    _create_finding(title="Finding B")
    resp = client.get("/api/v1/integrity/findings")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


def test_list_findings_filter_severity():
    """GET /findings?severity=error should filter by severity."""
    client = _client()
    _create_finding(severity="warning", title="Warn")
    _create_finding(severity="error", title="Err")
    resp = client.get("/api/v1/integrity/findings?severity=error")
    assert resp.status_code == 200
    data = resp.json()
    assert all(f["severity"] == "error" for f in data)


def test_list_findings_filter_category():
    """GET /findings?category=gene_name_error should filter by category."""
    client = _client()
    _create_finding(category="gene_name_error")
    _create_finding(category="statistical_inconsistency")
    resp = client.get("/api/v1/integrity/findings?category=gene_name_error")
    assert resp.status_code == 200
    data = resp.json()
    assert all(f["category"] == "gene_name_error" for f in data)


def test_list_findings_filter_status():
    """GET /findings?status=open should filter by status."""
    client = _client()
    _create_finding(status="open")
    _create_finding(status="resolved")
    resp = client.get("/api/v1/integrity/findings?status=open")
    assert resp.status_code == 200
    data = resp.json()
    assert all(f["status"] == "open" for f in data)


def test_list_findings_pagination():
    """GET /findings?limit=1&offset=0 should paginate."""
    client = _client()
    _create_finding(title="A")
    _create_finding(title="B")
    resp = client.get("/api/v1/integrity/findings?limit=1&offset=0")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_finding():
    """GET /findings/{id} should return the finding."""
    client = _client()
    fid = _create_finding()
    resp = client.get(f"/api/v1/integrity/findings/{fid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == fid


def test_get_finding_not_found():
    """GET /findings/nonexistent should return 404."""
    client = _client()
    resp = client.get("/api/v1/integrity/findings/nonexistent-id")
    assert resp.status_code == 404


def test_update_finding_status():
    """PUT /findings/{id} should update status fields."""
    client = _client()
    fid = _create_finding()
    resp = client.put(f"/api/v1/integrity/findings/{fid}", json={
        "status": "acknowledged",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "acknowledged"
    # Title should be preserved
    assert data["title"] == "Possible Excel corruption"


def test_update_finding_resolve():
    """PUT /findings/{id} should support full resolution."""
    client = _client()
    fid = _create_finding()
    resp = client.put(f"/api/v1/integrity/findings/{fid}", json={
        "status": "resolved",
        "resolved_by": "jkim",
        "resolution_note": "Verified: this is MARCH1 correctly named",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "resolved"
    assert data["resolved_by"] == "jkim"
    assert "Verified" in data["resolution_note"]


def test_update_finding_false_positive():
    """PUT /findings/{id} with false_positive status."""
    client = _client()
    fid = _create_finding()
    resp = client.put(f"/api/v1/integrity/findings/{fid}", json={
        "status": "false_positive",
        "resolution_note": "This is a date, not a gene name",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "false_positive"


def test_update_finding_not_found():
    """PUT /findings/nonexistent should return 404."""
    client = _client()
    resp = client.put("/api/v1/integrity/findings/nonexistent-id", json={
        "status": "acknowledged",
    })
    assert resp.status_code == 404


def test_delete_finding():
    """DELETE /findings/{id} should remove the finding."""
    client = _client()
    fid = _create_finding()
    resp = client.delete(f"/api/v1/integrity/findings/{fid}")
    assert resp.status_code == 204

    # Verify gone
    resp = client.get(f"/api/v1/integrity/findings/{fid}")
    assert resp.status_code == 404


def test_delete_finding_not_found():
    """DELETE /findings/nonexistent should return 404."""
    client = _client()
    resp = client.delete("/api/v1/integrity/findings/nonexistent-id")
    assert resp.status_code == 404


# === Audit Trigger ===


def test_trigger_audit_no_agent():
    """POST /audit without agent wired should return 503."""
    client = _client()
    set_auditor_agent(None)
    resp = client.post("/api/v1/integrity/audit", json={
        "text": "Gene 1-Mar was upregulated in the experiment.",
    })
    assert resp.status_code == 503


def test_trigger_audit_quick_check():
    """POST /audit with use_llm=false should run quick_check."""
    # Mock the auditor agent
    mock_agent = MagicMock()
    mock_output = MagicMock()
    mock_output.output = {
        "total_findings": 1,
        "findings": [
            {
                "category": "gene_name_error",
                "severity": "warning",
                "title": "Excel date corruption",
                "description": "1-Mar detected",
                "source_text": "1-Mar",
                "suggestion": "Verify: may be MARCH1",
                "confidence": 0.85,
                "checker": "gene_name_checker",
                "metadata": {},
            }
        ],
        "findings_by_severity": {"warning": 1},
        "findings_by_category": {"gene_name_error": 1},
        "overall_level": "minor_issues",
    }
    mock_output.summary = "1 integrity finding"
    mock_output.cost = 0.0
    mock_agent.quick_check = AsyncMock(return_value=mock_output)

    set_auditor_agent(mock_agent)
    client = _client()
    resp = client.post("/api/v1/integrity/audit", json={
        "text": "Gene 1-Mar was upregulated.",
        "use_llm": False,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["total_findings"] == 1
    assert data["overall_level"] == "minor_issues"
    assert data["trigger"] == "manual"
    mock_agent.quick_check.assert_called_once()


def test_trigger_audit_validation():
    """POST /audit with empty text should return 422."""
    set_auditor_agent(MagicMock())
    client = _client()
    resp = client.post("/api/v1/integrity/audit", json={
        "text": "",
    })
    assert resp.status_code == 422


# === Audit Runs ===


def test_list_runs():
    """GET /runs should list audit runs."""
    client = _client()
    _create_run()
    resp = client.get("/api/v1/integrity/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["trigger"] == "manual"


def test_get_run():
    """GET /runs/{id} should return a single run."""
    client = _client()
    rid = _create_run()
    resp = client.get(f"/api/v1/integrity/runs/{rid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == rid


def test_get_run_not_found():
    """GET /runs/nonexistent should return 404."""
    client = _client()
    resp = client.get("/api/v1/integrity/runs/nonexistent-id")
    assert resp.status_code == 404


# === Stats ===


def test_stats():
    """GET /stats should return aggregate statistics."""
    client = _client()
    _create_finding(severity="warning", category="gene_name_error", status="open")
    _create_finding(severity="error", category="statistical_inconsistency", status="resolved")
    _create_run()
    resp = client.get("/api/v1/integrity/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_findings"] >= 2
    assert data["total_runs"] >= 1
    assert "findings_by_severity" in data
    assert "findings_by_category" in data
    assert "findings_by_status" in data


if __name__ == "__main__":
    print("Testing Integrity API:")
    test_list_findings_empty()
    test_list_findings()
    test_list_findings_filter_severity()
    test_list_findings_filter_category()
    test_list_findings_filter_status()
    test_list_findings_pagination()
    test_get_finding()
    test_get_finding_not_found()
    test_update_finding_status()
    test_update_finding_resolve()
    test_update_finding_false_positive()
    test_update_finding_not_found()
    test_delete_finding()
    test_delete_finding_not_found()
    test_trigger_audit_no_agent()
    test_trigger_audit_quick_check()
    test_trigger_audit_validation()
    test_list_runs()
    test_get_run()
    test_get_run_not_found()
    test_stats()
    print("\nAll Integrity API tests passed!")
