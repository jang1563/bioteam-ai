"""API Key authentication middleware.

Single-user Bearer token authentication. Token is read from BIOTEAM_API_KEY env var.
When no key is configured, authentication is disabled (development mode).

Supports two auth methods:
  1. Authorization: Bearer <token>  (standard REST endpoints)
  2. ?token=<token> query param     (SSE/EventSource — browsers can't set headers)

Exempt paths: /health, /docs, /openapi.json, /redoc, /
"""

from __future__ import annotations

import logging
import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

# Paths that don't require authentication
_EXEMPT_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc", "/"})

# Paths that accept query-param token (EventSource can't set headers)
_QUERY_PARAM_AUTH_PATHS = frozenset({"/api/v1/sse"})


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Validates Bearer token from Authorization header or query param.

    If BIOTEAM_API_KEY is empty, all requests are allowed (dev mode).
    """

    async def dispatch(self, request: Request, call_next):
        api_key = settings.bioteam_api_key

        # Dev mode: no key configured → skip auth
        if not api_key:
            return await call_next(request)

        # Exempt paths
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        # Extract token from header or query param
        token = self._extract_token(request)

        if token is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing authentication. Use Authorization: Bearer <key> or ?token=<key>"},
            )

        # Constant-time comparison to prevent timing attacks
        if not secrets.compare_digest(token, api_key):
            logger.warning(
                "Invalid API key attempt from %s on %s",
                request.client.host if request.client else "unknown",
                request.url.path,
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid API key."},
            )

        return await call_next(request)

    @staticmethod
    def _extract_token(request: Request) -> str | None:
        """Extract auth token from header or (for SSE) query param."""
        # 1. Standard Bearer header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]

        # 2. Query param for SSE paths only
        if request.url.path in _QUERY_PARAM_AUTH_PATHS:
            return request.query_params.get("token")

        return None
