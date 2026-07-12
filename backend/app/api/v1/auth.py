"""Authentication helper endpoints."""

from __future__ import annotations

import secrets

from app.config import settings
from app.security.jwt import create_jwt, verify_jwt
from app.security.stream_token import issue_stream_token
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_STREAM_AUTH_PATHS = frozenset({
    "/api/v1/sse",
    "/api/v1/direct-query/stream",
})
_STREAM_TOKEN_TTL_SECONDS = 120
_JWT_TTL_SECONDS = 86400  # 24 hours


def _is_stream_auth_path(path: str) -> bool:
    """Allow stream token issuance for supported SSE endpoints."""
    return path in _STREAM_AUTH_PATHS or path.startswith("/api/v1/sse/workflow/")


# ---------------------------------------------------------------------------
# Stream token (existing)
# ---------------------------------------------------------------------------


class StreamTokenRequest(BaseModel):
    path: str = "/api/v1/direct-query/stream"


class StreamTokenResponse(BaseModel):
    token: str
    expires_in_seconds: int
    path: str


@router.post("/stream-token", response_model=StreamTokenResponse)
async def create_stream_token(req: StreamTokenRequest) -> StreamTokenResponse:
    """Issue short-lived path-bound stream token for EventSource auth."""
    if not _is_stream_auth_path(req.path):
        raise HTTPException(status_code=400, detail="Unsupported stream path.")
    if not settings.bioteam_api_key:
        raise HTTPException(status_code=400, detail="API key auth is disabled.")

    token = issue_stream_token(
        api_key=settings.bioteam_api_key,
        path=req.path,
        ttl_seconds=_STREAM_TOKEN_TTL_SECONDS,
    )
    return StreamTokenResponse(
        token=token,
        expires_in_seconds=_STREAM_TOKEN_TTL_SECONDS,
        path=req.path,
    )


# ---------------------------------------------------------------------------
# JWT login / verify (new)
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    api_key: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class VerifyResponse(BaseModel):
    valid: bool
    subject: str | None = None
    expires_at: int | None = None


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest) -> LoginResponse:
    """Exchange API key for a JWT access token."""
    if not settings.bioteam_api_key:
        raise HTTPException(
            status_code=400,
            detail="Auth is disabled (no API key configured). No login needed.",
        )

    if not secrets.compare_digest(req.api_key, settings.bioteam_api_key):
        raise HTTPException(status_code=403, detail="Invalid API key.")

    token = create_jwt(api_key=settings.bioteam_api_key, ttl_seconds=_JWT_TTL_SECONDS)
    return LoginResponse(access_token=token, expires_in=_JWT_TTL_SECONDS)


@router.post("/verify", response_model=VerifyResponse)
async def verify_token(request: Request) -> VerifyResponse:
    """Check whether the current Bearer token is valid."""
    api_key = settings.bioteam_api_key
    if not api_key:
        return VerifyResponse(valid=True, subject="dev")

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return VerifyResponse(valid=False)

    token = auth_header[7:]

    # Check raw API key first
    if secrets.compare_digest(token, api_key):
        return VerifyResponse(valid=True, subject="admin", expires_at=None)

    # Check JWT
    payload = verify_jwt(token=token, api_key=api_key)
    if payload:
        return VerifyResponse(
            valid=True,
            subject=payload.get("sub"),
            expires_at=payload.get("exp"),
        )

    return VerifyResponse(valid=False)
