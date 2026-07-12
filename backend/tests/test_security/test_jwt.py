"""Tests for JWT creation, verification, login endpoint, and middleware integration."""

from __future__ import annotations

import pytest
from app.security.jwt import create_jwt, verify_jwt

TEST_KEY = "test-secret-key-for-jwt"


class TestJWTCreation:
    def test_create_returns_three_part_token(self):
        token = create_jwt(api_key=TEST_KEY)
        assert token.count(".") == 2

    def test_create_with_custom_ttl(self):
        token = create_jwt(api_key=TEST_KEY, ttl_seconds=60, now=1000)
        payload = verify_jwt(token=token, api_key=TEST_KEY, now=1000)
        assert payload is not None
        assert payload["exp"] == 1060

    def test_create_sets_admin_subject(self):
        token = create_jwt(api_key=TEST_KEY, now=1000)
        payload = verify_jwt(token=token, api_key=TEST_KEY, now=1000)
        assert payload is not None
        assert payload["sub"] == "admin"


class TestJWTVerification:
    def test_valid_token(self):
        token = create_jwt(api_key=TEST_KEY, now=1000)
        payload = verify_jwt(token=token, api_key=TEST_KEY, now=1000)
        assert payload is not None
        assert payload["sub"] == "admin"

    def test_expired_token(self):
        token = create_jwt(api_key=TEST_KEY, ttl_seconds=10, now=1000)
        payload = verify_jwt(token=token, api_key=TEST_KEY, now=1011)
        assert payload is None

    def test_wrong_key(self):
        token = create_jwt(api_key=TEST_KEY)
        payload = verify_jwt(token=token, api_key="wrong-key")
        assert payload is None

    def test_tampered_payload(self):
        token = create_jwt(api_key=TEST_KEY)
        parts = token.split(".")
        # Tamper with the payload
        parts[1] = parts[1] + "x"
        tampered = ".".join(parts)
        assert verify_jwt(token=tampered, api_key=TEST_KEY) is None

    def test_missing_parts(self):
        assert verify_jwt(token="only.two", api_key=TEST_KEY) is None
        assert verify_jwt(token="single", api_key=TEST_KEY) is None
        assert verify_jwt(token="", api_key=TEST_KEY) is None

    def test_garbage_token(self):
        assert verify_jwt(token="a.b.c", api_key=TEST_KEY) is None

    def test_not_yet_expired_boundary(self):
        token = create_jwt(api_key=TEST_KEY, ttl_seconds=10, now=1000)
        # Exactly at expiration time — should still be valid
        assert verify_jwt(token=token, api_key=TEST_KEY, now=1010) is not None
        # One second after — expired
        assert verify_jwt(token=token, api_key=TEST_KEY, now=1011) is None


@pytest.mark.asyncio
class TestLoginEndpoint:
    """Test POST /api/v1/auth/login."""

    @pytest.fixture()
    def client(self, monkeypatch):
        monkeypatch.setenv("BIOTEAM_API_KEY", TEST_KEY)
        # Re-import to pick up env change
        from app.config import Settings
        monkeypatch.setattr("app.config.settings", Settings())
        monkeypatch.setattr("app.api.v1.auth.settings", Settings())

        from app.api.v1.auth import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    async def test_login_valid_key(self, client):
        resp = client.post("/api/v1/auth/login", json={"api_key": TEST_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 86400
        # Token should be verifiable
        payload = verify_jwt(token=data["access_token"], api_key=TEST_KEY)
        assert payload is not None
        assert payload["sub"] == "admin"

    async def test_login_invalid_key(self, client):
        resp = client.post("/api/v1/auth/login", json={"api_key": "wrong"})
        assert resp.status_code == 403

    async def test_login_empty_key(self, client):
        resp = client.post("/api/v1/auth/login", json={"api_key": ""})
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestVerifyEndpoint:
    """Test POST /api/v1/auth/verify."""

    @pytest.fixture()
    def client(self, monkeypatch):
        monkeypatch.setenv("BIOTEAM_API_KEY", TEST_KEY)
        from app.config import Settings
        monkeypatch.setattr("app.config.settings", Settings())
        monkeypatch.setattr("app.api.v1.auth.settings", Settings())

        from app.api.v1.auth import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    async def test_verify_raw_key(self, client):
        resp = client.post(
            "/api/v1/auth/verify",
            headers={"Authorization": f"Bearer {TEST_KEY}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["subject"] == "admin"
        assert data["expires_at"] is None

    async def test_verify_jwt_token(self, client):
        token = create_jwt(api_key=TEST_KEY)
        resp = client.post(
            "/api/v1/auth/verify",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["subject"] == "admin"
        assert data["expires_at"] is not None

    async def test_verify_invalid_token(self, client):
        resp = client.post(
            "/api/v1/auth/verify",
            headers={"Authorization": "Bearer invalid"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False

    async def test_verify_no_header(self, client):
        resp = client.post("/api/v1/auth/verify")
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False


class TestMiddlewareJWTAcceptance:
    """Test that the auth middleware accepts JWT tokens."""

    def test_middleware_accepts_jwt(self, monkeypatch):
        monkeypatch.setenv("BIOTEAM_API_KEY", TEST_KEY)
        from app.config import Settings
        monkeypatch.setattr("app.config.settings", Settings())

        from app.middleware.auth import APIKeyAuthMiddleware
        token = create_jwt(api_key=TEST_KEY)
        assert APIKeyAuthMiddleware._is_authenticated(
            token=token, source="header", api_key=TEST_KEY, path="/api/v1/agents"
        ) is True

    def test_middleware_rejects_expired_jwt(self, monkeypatch):
        monkeypatch.setenv("BIOTEAM_API_KEY", TEST_KEY)
        from app.config import Settings
        monkeypatch.setattr("app.config.settings", Settings())

        from app.middleware.auth import APIKeyAuthMiddleware
        token = create_jwt(api_key=TEST_KEY, ttl_seconds=1, now=1000)
        assert APIKeyAuthMiddleware._is_authenticated(
            token=token, source="header", api_key=TEST_KEY, path="/api/v1/agents"
        ) is False

    def test_middleware_still_accepts_raw_key(self, monkeypatch):
        monkeypatch.setenv("BIOTEAM_API_KEY", TEST_KEY)
        from app.config import Settings
        monkeypatch.setattr("app.config.settings", Settings())

        from app.middleware.auth import APIKeyAuthMiddleware
        assert APIKeyAuthMiddleware._is_authenticated(
            token=TEST_KEY, source="header", api_key=TEST_KEY, path="/api/v1/agents"
        ) is True
