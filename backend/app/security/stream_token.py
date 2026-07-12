"""Short-lived signed tokens for SSE query-param authentication."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

_TOKEN_VERSION = "v1"


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def issue_stream_token(*, api_key: str, path: str, ttl_seconds: int = 120, now: int | None = None) -> str:
    """Issue a path-bound signed token with short expiration."""
    issued_at = int(now if now is not None else time.time())
    expires_at = issued_at + max(1, ttl_seconds)
    payload = f"{_TOKEN_VERSION}:{path}:{expires_at}".encode("utf-8")
    signature = hmac.new(api_key.encode("utf-8"), payload, hashlib.sha256).digest()
    return f"{_b64url_encode(payload)}.{_b64url_encode(signature)}"


def verify_stream_token(*, token: str, api_key: str, path: str, now: int | None = None) -> bool:
    """Verify signed stream token integrity, path binding, and expiration."""
    if "." not in token:
        return False

    payload_b64, sig_b64 = token.split(".", 1)
    try:
        payload = _b64url_decode(payload_b64)
        signature = _b64url_decode(sig_b64)
    except Exception:
        return False

    expected_sig = hmac.new(api_key.encode("utf-8"), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_sig):
        return False

    try:
        version, token_path, expires_at_raw = payload.decode("utf-8").split(":", 2)
        expires_at = int(expires_at_raw)
    except Exception:
        return False

    if version != _TOKEN_VERSION:
        return False
    if token_path != path:
        return False

    current = int(now if now is not None else time.time())
    return current <= expires_at

