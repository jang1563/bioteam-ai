"""Tests for API Key authentication middleware."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import create_db_and_tables


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
        from app.llm.mock_layer import MockLLMLayer
        from app.api.v1.agents import set_registry
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


if __name__ == "__main__":
    print("Testing Auth Middleware:")
    test_no_key_configured_allows_all()
    test_missing_auth_header_returns_401()
    test_invalid_token_returns_403()
    test_valid_token_passes()
    test_health_exempt_from_auth()
    test_root_exempt_from_auth()
    test_bearer_prefix_required()
    print("\nAll Auth Middleware tests passed!")
