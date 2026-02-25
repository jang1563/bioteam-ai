"""Rate limiting middleware using in-memory token bucket.

No external dependencies (no Redis needed for Phase 1).
Limits are configurable via Settings.

Default limits:
- Global: 60 requests/minute
- Expensive endpoints (/direct-query, /workflows POST): 10 requests/minute
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Endpoints with lower rate limits (expensive LLM calls)
_EXPENSIVE_ENDPOINTS = frozenset({
    "/api/v1/direct-query",
    "/api/v1/workflows",
})

# Exempt from rate limiting
_EXEMPT_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc", "/"})


class TokenBucket:
    """Simple token bucket rate limiter."""

    def __init__(self, rate: float, capacity: int) -> None:
        self.rate = rate  # tokens per second
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def consume(self) -> bool:
        """Try to consume a token. Returns True if allowed."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory rate limiter per client IP.

    Args:
        global_rpm: Global requests per minute per client.
        expensive_rpm: Requests per minute for expensive endpoints.
    """

    def __init__(self, app, global_rpm: int = 60, expensive_rpm: int = 10) -> None:
        super().__init__(app)
        self.global_rpm = global_rpm
        self.expensive_rpm = expensive_rpm
        # Per-client buckets: {client_ip: TokenBucket}
        self._global_buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(rate=global_rpm / 60.0, capacity=global_rpm)
        )
        self._expensive_buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(rate=expensive_rpm / 60.0, capacity=expensive_rpm)
        )

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip exempt paths
        if path in _EXEMPT_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        # Global rate check
        if not self._global_buckets[client_ip].consume():
            logger.warning("Rate limit exceeded for %s on %s", client_ip, path)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please retry later."},
                headers={"Retry-After": "60"},
            )

        # Expensive endpoint rate check
        if path in _EXPENSIVE_ENDPOINTS and request.method == "POST":
            if not self._expensive_buckets[client_ip].consume():
                logger.warning("Expensive endpoint rate limit exceeded for %s on %s", client_ip, path)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded for this endpoint. Please retry later."},
                    headers={"Retry-After": "60"},
                )

        return await call_next(request)
