"""API Key authentication middleware.

Single-user Bearer token authentication. Token is read from BIOTEAM_API_KEY env var.
When no key is configured, authentication is disabled (development mode).

Exempt paths: /health, /docs, /openapi.json, /redoc
"""

from __future__ import annotations

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

# Paths that don't require authentication
_EXEMPT_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc", "/"})


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Validates Bearer token from Authorization header.

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

        # SSE endpoint needs auth too but check is the same
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header. Use: Bearer <api_key>"},
            )

        token = auth_header[7:]  # Strip "Bearer "
        if token != api_key:
            logger.warning("Invalid API key attempt from %s", request.client.host if request.client else "unknown")
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid API key."},
            )

        return await call_next(request)
