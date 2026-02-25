"""Tests for API Key authentication middleware."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from unittest.mock import patch

from app.db.database import create_db_and_tables
from app.main import app
from fastapi.testclient import TestClient


def _client():
    create_db_and_tables()
    return TestClient(app)


# === Auth disabled (no BIOTEAM_API_KEY) ===


def test_no_key_configured_allows_all():
    """When BIOTEAM_API_KEY is empty, all requests should pass."""
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.bioteam_api_key = ""
        client = _client()
        resp = client.get("/health")
        assert resp.status_code == 200


# === Auth enabled ===


def test_missing_auth_header_returns_401():
    """Request without Authorization header should get 401."""
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.bioteam_api_key = "test-secret-key"
        client = _client()
        resp = client.get("/api/v1/agents")
        assert resp.status_code == 401
        assert "Authorization" in resp.json()["detail"]


def test_invalid_token_returns_403():
    """Request with wrong token should get 403."""
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.bioteam_api_key = "correct-key"
        client = _client()
        resp = client.get("/api/v1/agents", headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 403


def test_valid_token_passes():
    """Request with correct token should succeed."""
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.bioteam_api_key = "my-secret"
        client = _client()
        # Wire up registry first
        from app.agents.registry import create_registry
        from app.api.v1.agents import set_registry
        from app.llm.mock_layer import MockLLMLayer
        set_registry(create_registry(MockLLMLayer()))
        resp = client.get("/api/v1/agents", headers={"Authorization": "Bearer my-secret"})
        assert resp.status_code == 200


def test_health_exempt_from_auth():
    """Health endpoint should work even with auth enabled and no token."""
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.bioteam_api_key = "secret-key"
        client = _client()
        resp = client.get("/health")
        assert resp.status_code == 200


def test_root_exempt_from_auth():
    """Root endpoint should work without auth."""
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.bioteam_api_key = "secret-key"
        client = _client()
        resp = client.get("/")
        assert resp.status_code == 200


def test_bearer_prefix_required():
    """Auth header without 'Bearer ' prefix should fail."""
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.bioteam_api_key = "key123"
        client = _client()
        resp = client.get("/api/v1/agents", headers={"Authorization": "key123"})
        assert resp.status_code == 401


# === SSE query-param auth ===
# SSE returns a blocking StreamingResponse, so we test middleware logic
# using a standalone app with a simple response at the SSE path.


def _sse_auth_client():
    """Create a test app with auth middleware and a simple /api/v1/sse endpoint."""
    from app.middleware.auth import APIKeyAuthMiddleware
    from fastapi import FastAPI

    test_app = FastAPI()
    test_app.add_middleware(APIKeyAuthMiddleware)

    @test_app.get("/api/v1/sse")
    async def fake_sse():
        return {"status": "sse_ok"}

    @test_app.get("/api/v1/agents")
    async def fake_agents():
        return {"status": "agents_ok"}

    return TestClient(test_app)


def test_sse_query_param_auth_valid():
    """SSE endpoint should accept ?token= query param."""
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.bioteam_api_key = "sse-secret"
        client = _sse_auth_client()
        resp = client.get("/api/v1/sse?token=sse-secret")
        assert resp.status_code == 200
        assert resp.json()["status"] == "sse_ok"


def test_sse_query_param_auth_invalid():
    """SSE endpoint with wrong query param token should get 403."""
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.bioteam_api_key = "sse-secret"
        client = _sse_auth_client()
        resp = client.get("/api/v1/sse?token=wrong-token")
        assert resp.status_code == 403


def test_sse_no_auth_returns_401():
    """SSE endpoint without any auth should get 401."""
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.bioteam_api_key = "sse-secret"
        client = _sse_auth_client()
        resp = client.get("/api/v1/sse")
        assert resp.status_code == 401


def test_sse_bearer_header_also_works():
    """SSE endpoint should also accept standard Bearer header."""
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.bioteam_api_key = "sse-secret"
        client = _sse_auth_client()
        resp = client.get(
            "/api/v1/sse",
            headers={"Authorization": "Bearer sse-secret"},
        )
        assert resp.status_code == 200


def test_non_sse_query_param_rejected():
    """Non-SSE endpoints should NOT accept query param auth."""
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.bioteam_api_key = "my-key"
        client = _sse_auth_client()
        resp = client.get("/api/v1/agents?token=my-key")
        assert resp.status_code == 401


if __name__ == "__main__":
    print("Testing Auth Middleware:")
    test_no_key_configured_allows_all()
    test_missing_auth_header_returns_401()
    test_invalid_token_returns_403()
    test_valid_token_passes()
    test_health_exempt_from_auth()
    test_root_exempt_from_auth()
    test_bearer_prefix_required()
    test_sse_query_param_auth_valid()
    test_sse_query_param_auth_invalid()
    test_sse_no_auth_returns_401()
    test_sse_bearer_header_also_works()
    test_non_sse_query_param_rejected()
    print("\nAll Auth Middleware tests passed!")
