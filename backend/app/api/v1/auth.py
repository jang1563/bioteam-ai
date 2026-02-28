"""Authentication helper endpoints."""

from __future__ import annotations

from app.config import settings
from app.security.stream_token import issue_stream_token
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_STREAM_AUTH_PATHS = frozenset({
    "/api/v1/sse",
    "/api/v1/direct-query/stream",
})
_STREAM_TOKEN_TTL_SECONDS = 120


class StreamTokenRequest(BaseModel):
    path: str = "/api/v1/direct-query/stream"


class StreamTokenResponse(BaseModel):
    token: str
    expires_in_seconds: int
    path: str


@router.post("/stream-token", response_model=StreamTokenResponse)
async def create_stream_token(req: StreamTokenRequest) -> StreamTokenResponse:
    """Issue short-lived path-bound stream token for EventSource auth."""
    if req.path not in _STREAM_AUTH_PATHS:
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

