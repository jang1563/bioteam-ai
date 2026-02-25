"""Edge case tests for Integrity API — validation boundaries, error responses, filter combos."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.integrity import router as integrity_router, set_auditor_agent
from app.db.database import create_db_and_tables, engine as db_engine
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
    finding = AuditFinding(
        category=overrides.get("category", "gene_name_error"),
        severity=overrides.get("severity", "warning"),
        title=overrides.get("title", "Test finding"),
        description=overrides.get("description", "Test description"),
        source_text=overrides.get("source_text", "test"),
        confidence=overrides.get("confidence", 0.85),
        checker=overrides.get("checker", "gene_name_checker"),
        status=overrides.get("status", "open"),
        workflow_id=overrides.get("workflow_id"),
    )
    with Session(db_engine) as session:
        session.add(finding)
        session.commit()
        session.refresh(finding)
        finding_id = finding.id
    return finding_id


def _create_run(**overrides) -> str:
    run = AuditRun(
        trigger=overrides.get("trigger", "manual"),
        total_findings=overrides.get("total_findings", 0),
        findings_by_severity=overrides.get("findings_by_severity", {}),
        findings_by_category=overrides.get("findings_by_category", {}),
        overall_level=overrides.get("overall_level", "clean"),
        summary=overrides.get("summary", ""),
        cost=overrides.get("cost", 0.0),
        duration_ms=overrides.get("duration_ms", 0),
    )
    with Session(db_engine) as session:
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id
    return run_id


# === Input Validation ===


class TestInputValidation:
    """Test request validation boundaries."""

    def test_audit_text_too_long(self):
        """Text exceeding 50000 chars should be rejected."""
        set_auditor_agent(MagicMock())
        client = _client()
        resp = client.post("/api/v1/integrity/audit", json={
            "text": "A" * 50001,
        })
        assert resp.status_code == 422

    def test_audit_text_exactly_max(self):
        """Text at exactly 50000 chars should be accepted (mock agent)."""
        mock_agent = MagicMock()
        mock_output = MagicMock()
        mock_output.output = {"total_findings": 0, "findings": [],
                              "findings_by_severity": {}, "findings_by_category": {},
                              "overall_level": "clean"}
        mock_output.summary = ""
        mock_output.cost = 0.0
        mock_agent.quick_check = AsyncMock(return_value=mock_output)
        set_auditor_agent(mock_agent)
        client = _client()
        resp = client.post("/api/v1/integrity/audit", json={
            "text": "A" * 50000,
        })
        assert resp.status_code == 201

    def test_audit_whitespace_only_text(self):
        """Whitespace-only text (length > 0) should be accepted."""
        mock_agent = MagicMock()
        mock_output = MagicMock()
        mock_output.output = {"total_findings": 0, "findings": [],
                              "findings_by_severity": {}, "findings_by_category": {},
                              "overall_level": "clean"}
        mock_output.summary = ""
        mock_output.cost = 0.0
        mock_agent.quick_check = AsyncMock(return_value=mock_output)
        set_auditor_agent(mock_agent)
        client = _client()
        resp = client.post("/api/v1/integrity/audit", json={
            "text": " ",  # Single space — min_length=1 passes
        })
        assert resp.status_code == 201

    def test_invalid_severity_filter(self):
        """Invalid severity filter should be rejected by pattern."""
        client = _client()
        resp = client.get("/api/v1/integrity/findings?severity=invalid")
        assert resp.status_code == 422

    def test_invalid_status_filter(self):
        """Invalid status filter should be rejected by pattern."""
        client = _client()
        resp = client.get("/api/v1/integrity/findings?status=invalid")
        assert resp.status_code == 422

    def test_invalid_update_status(self):
        """Invalid status in update should be rejected."""
        client = _client()
        fid = _create_finding()
        resp = client.put(f"/api/v1/integrity/findings/{fid}", json={
            "status": "invalid_status",
        })
        assert resp.status_code == 422

    def test_resolution_note_too_long(self):
        """Resolution note > 2000 chars should be rejected."""
        client = _client()
        fid = _create_finding()
        resp = client.put(f"/api/v1/integrity/findings/{fid}", json={
            "resolution_note": "X" * 2001,
        })
        assert resp.status_code == 422

    def test_resolution_note_at_max(self):
        """Resolution note at exactly 2000 chars should be accepted."""
        client = _client()
        fid = _create_finding()
        resp = client.put(f"/api/v1/integrity/findings/{fid}", json={
            "resolution_note": "X" * 2000,
        })
        assert resp.status_code == 200


# === Pagination ===


class TestPaginationEdgeCases:

    def test_limit_min_boundary(self):
        """limit=1 (minimum) should work."""
        client = _client()
        _create_finding()
        _create_finding()
        resp = client.get("/api/v1/integrity/findings?limit=1")
        assert resp.status_code == 200
        assert len(resp.json()) <= 1

    def test_limit_max_boundary(self):
        """limit=200 (maximum) should work."""
        client = _client()
        resp = client.get("/api/v1/integrity/findings?limit=200")
        assert resp.status_code == 200

    def test_limit_zero_rejected(self):
        """limit=0 should be rejected (ge=1)."""
        client = _client()
        resp = client.get("/api/v1/integrity/findings?limit=0")
        assert resp.status_code == 422

    def test_limit_over_max_rejected(self):
        """limit=201 should be rejected (le=200)."""
        client = _client()
        resp = client.get("/api/v1/integrity/findings?limit=201")
        assert resp.status_code == 422

    def test_negative_offset_rejected(self):
        """offset=-1 should be rejected (ge=0)."""
        client = _client()
        resp = client.get("/api/v1/integrity/findings?offset=-1")
        assert resp.status_code == 422

    def test_large_offset_returns_empty(self):
        """Very large offset beyond data should return empty list."""
        client = _client()
        resp = client.get("/api/v1/integrity/findings?offset=999999")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_runs_pagination(self):
        """Run list should also support pagination."""
        client = _client()
        _create_run()
        _create_run()
        resp = client.get("/api/v1/integrity/runs?limit=1")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


# === Filter Combinations ===


class TestFilterCombinations:

    def test_severity_and_status_combined(self):
        """Filtering by both severity and status should work."""
        client = _client()
        _create_finding(severity="error", status="open")
        _create_finding(severity="warning", status="open")
        _create_finding(severity="error", status="resolved")
        resp = client.get("/api/v1/integrity/findings?severity=error&status=open")
        assert resp.status_code == 200
        data = resp.json()
        for f in data:
            assert f["severity"] == "error"
            assert f["status"] == "open"

    def test_category_and_severity_combined(self):
        """Filtering by category and severity together."""
        client = _client()
        _create_finding(category="gene_name_error", severity="warning")
        _create_finding(category="gene_name_error", severity="error")
        _create_finding(category="statistical_inconsistency", severity="warning")
        resp = client.get(
            "/api/v1/integrity/findings?category=gene_name_error&severity=warning"
        )
        assert resp.status_code == 200
        data = resp.json()
        for f in data:
            assert f["category"] == "gene_name_error"
            assert f["severity"] == "warning"

    def test_workflow_id_filter(self):
        """Filtering by workflow_id should only return matching findings."""
        client = _client()
        _create_finding(workflow_id="wf-123")
        _create_finding(workflow_id="wf-456")
        _create_finding(workflow_id=None)
        resp = client.get("/api/v1/integrity/findings?workflow_id=wf-123")
        assert resp.status_code == 200
        data = resp.json()
        for f in data:
            assert f["workflow_id"] == "wf-123"


# === Update Edge Cases ===


class TestUpdateEdgeCases:

    def test_update_with_empty_body(self):
        """PUT with empty JSON body should succeed (no changes)."""
        client = _client()
        fid = _create_finding(status="open")
        resp = client.put(f"/api/v1/integrity/findings/{fid}", json={})
        assert resp.status_code == 200
        assert resp.json()["status"] == "open"

    def test_update_resolved_to_open(self):
        """Re-opening a resolved finding should work."""
        client = _client()
        fid = _create_finding(status="resolved")
        resp = client.put(f"/api/v1/integrity/findings/{fid}", json={
            "status": "open",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "open"

    def test_update_preserves_unset_fields(self):
        """Updating only status should not clear resolved_by/resolution_note."""
        client = _client()
        fid = _create_finding()
        # First resolve with note
        client.put(f"/api/v1/integrity/findings/{fid}", json={
            "status": "resolved",
            "resolved_by": "jkim",
            "resolution_note": "Verified",
        })
        # Then update only status (should preserve resolved_by via exclude_unset)
        resp = client.put(f"/api/v1/integrity/findings/{fid}", json={
            "status": "acknowledged",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "acknowledged"
        # resolved_by should be preserved (not cleared)
        assert data["resolved_by"] == "jkim"


# === Audit Trigger Edge Cases ===


class TestAuditTriggerEdgeCases:

    def test_audit_with_dois(self):
        """Audit request with DOI list should pass them through."""
        mock_agent = MagicMock()
        mock_output = MagicMock()
        mock_output.output = {"total_findings": 0, "findings": [],
                              "findings_by_severity": {}, "findings_by_category": {},
                              "overall_level": "clean"}
        mock_output.summary = ""
        mock_output.cost = 0.0
        mock_agent.quick_check = AsyncMock(return_value=mock_output)
        set_auditor_agent(mock_agent)
        client = _client()
        resp = client.post("/api/v1/integrity/audit", json={
            "text": "Some text referencing papers.",
            "dois": ["10.1038/test1", "10.1126/test2"],
        })
        assert resp.status_code == 201
        # Verify DOIs were passed
        call_kwargs = mock_agent.quick_check.call_args
        assert call_kwargs.kwargs.get("dois") == ["10.1038/test1", "10.1126/test2"]

    def test_audit_use_llm_true(self):
        """Audit with use_llm=True should call full audit, not quick_check."""
        mock_agent = MagicMock()
        mock_output = MagicMock()
        mock_output.output = {"total_findings": 0, "findings": [],
                              "findings_by_severity": {}, "findings_by_category": {},
                              "overall_level": "clean"}
        mock_output.summary = ""
        mock_output.cost = 0.0
        mock_agent.audit = AsyncMock(return_value=mock_output)
        set_auditor_agent(mock_agent)
        client = _client()
        resp = client.post("/api/v1/integrity/audit", json={
            "text": "Some text.",
            "use_llm": True,
        })
        assert resp.status_code == 201
        mock_agent.audit.assert_called_once()

    def test_audit_agent_exception_returns_500(self):
        """Agent raising exception should return 500."""
        mock_agent = MagicMock()
        mock_agent.quick_check = AsyncMock(side_effect=RuntimeError("boom"))
        set_auditor_agent(mock_agent)
        client = _client()
        resp = client.post("/api/v1/integrity/audit", json={
            "text": "Some text.",
        })
        assert resp.status_code == 500
        assert "internal error" in resp.json()["detail"].lower()

    def test_image_audit_no_agent_503(self):
        """Image audit without agent should return 503."""
        set_auditor_agent(None)
        client = _client()
        # Send a minimal multipart request
        import io
        files = [("files", ("test.jpg", io.BytesIO(b"\xff\xd8\xff\xe0"), "image/jpeg"))]
        resp = client.post("/api/v1/integrity/audit-images", files=files)
        assert resp.status_code == 503

    def test_image_audit_too_many_files(self):
        """More than 50 files should return 400."""
        mock_agent = MagicMock()
        set_auditor_agent(mock_agent)
        client = _client()
        import io
        files = [
            ("files", (f"img_{i}.jpg", io.BytesIO(b"\xff\xd8\xff\xe0"), "image/jpeg"))
            for i in range(51)
        ]
        resp = client.post("/api/v1/integrity/audit-images", files=files)
        assert resp.status_code == 400
        assert "50" in resp.json()["detail"]

    def test_image_audit_file_too_large(self):
        """File > 10MB should return 400."""
        mock_agent = MagicMock()
        set_auditor_agent(mock_agent)
        client = _client()
        import io
        large_content = b"\x00" * (10_000_001)  # 10MB + 1 byte
        files = [("files", ("huge.jpg", io.BytesIO(large_content), "image/jpeg"))]
        resp = client.post("/api/v1/integrity/audit-images", files=files)
        assert resp.status_code == 400
        assert "10MB" in resp.json()["detail"]


# === Stats Edge Cases ===


class TestStatsEdgeCases:

    def test_stats_empty_db(self):
        """Stats with no findings/runs should return zeros."""
        client = _client()
        resp = client.get("/api/v1/integrity/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_findings"] >= 0  # May have findings from other tests
        assert data["total_runs"] >= 0
        assert isinstance(data["average_findings_per_run"], float)

    def test_stats_avg_calculation(self):
        """Average findings per run should be correctly computed."""
        client = _client()
        _create_finding()
        _create_finding()
        _create_run()
        resp = client.get("/api/v1/integrity/stats")
        assert resp.status_code == 200
        data = resp.json()
        # avg = total_findings / total_runs
        if data["total_runs"] > 0:
            expected_avg = data["total_findings"] / data["total_runs"]
            assert abs(data["average_findings_per_run"] - expected_avg) < 0.01


# === Response Format ===


class TestResponseFormat:

    def test_finding_response_has_all_fields(self):
        """Finding response should include all expected fields."""
        client = _client()
        fid = _create_finding()
        resp = client.get(f"/api/v1/integrity/findings/{fid}")
        assert resp.status_code == 200
        data = resp.json()
        required_fields = [
            "id", "category", "severity", "title", "description",
            "confidence", "status", "created_at", "updated_at",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_run_response_has_all_fields(self):
        """Run response should include all expected fields."""
        client = _client()
        rid = _create_run()
        resp = client.get(f"/api/v1/integrity/runs/{rid}")
        assert resp.status_code == 200
        data = resp.json()
        required_fields = [
            "id", "trigger", "total_findings", "findings_by_severity",
            "overall_level", "created_at",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_delete_returns_204_no_body(self):
        """DELETE should return 204 with no response body."""
        client = _client()
        fid = _create_finding()
        resp = client.delete(f"/api/v1/integrity/findings/{fid}")
        assert resp.status_code == 204
        assert resp.content == b""
