"""Tests for health endpoint and main app."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import asyncio

from app.api.health import HealthStatus, health_check

# === HealthStatus Model Tests ===


def test_health_status_model():
    from datetime import datetime, timezone
    status = HealthStatus(
        status="healthy",
        version="0.5.0",
        checks={"llm_api": {"status": "ok", "detail": "test"}},
        dependencies={"llm_api": "ok"},
        timestamp=datetime.now(timezone.utc),
    )
    assert status.status == "healthy"
    assert status.version == "0.5.0"
    assert "llm_api" in status.checks
    assert status.dependencies["llm_api"] == "ok"
    print("  PASS: health_status_model")


# === Health Endpoint Tests ===


def test_health_check_returns_status():
    """health_check should return a HealthStatus with checks."""
    result = asyncio.run(health_check())
    assert isinstance(result, HealthStatus)
    assert result.status in ("healthy", "degraded", "unhealthy")
    assert result.version == "0.8.0"
    assert "llm_api" in result.checks
    assert "database" in result.checks
    assert "chromadb" in result.checks
    assert "pubmed" in result.checks
    assert "cost_tracker" in result.checks
    assert result.timestamp is not None
    # dependencies should mirror checks
    assert len(result.dependencies) == len(result.checks)
    for name in result.checks:
        assert name in result.dependencies
    print("  PASS: health_check_returns_status")


def test_health_check_has_all_checks():
    """All 5 dependency checks should be present."""
    result = asyncio.run(health_check())
    expected_checks = ["llm_api", "database", "chromadb", "pubmed", "cost_tracker"]
    for check in expected_checks:
        assert check in result.checks, f"Missing check: {check}"
        assert "status" in result.checks[check], f"Check {check} missing status"
    print("  PASS: health_check_has_all_checks")


# === Main App Tests ===


def test_root_endpoint():
    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "BioTeam-AI"
    assert data["version"] == "0.1.0"
    assert data["status"] == "running"
    print("  PASS: root_endpoint")


def test_health_endpoint_via_app():
    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded", "unhealthy")
    assert "checks" in data
    assert "dependencies" in data
    assert "version" in data
    assert "timestamp" in data
    print("  PASS: health_endpoint_via_app")


def test_cors_headers():
    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.options(
        "/",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    # CORS should allow localhost:3000
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    print("  PASS: cors_headers")


if __name__ == "__main__":
    print("Testing Health & Main:")
    test_health_status_model()
    test_health_check_returns_status()
    test_health_check_has_all_checks()
    test_root_endpoint()
    test_health_endpoint_via_app()
    test_cors_headers()
    print("\nAll Health & Main tests passed!")
