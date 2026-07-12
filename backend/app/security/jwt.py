"""Minimal JWT implementation for single-user auth.

Uses HMAC-SHA256 with the API key as secret. No external dependencies.
Follows the same pattern as stream_token.py — stdlib only.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

_JWT_VERSION = "v1"
_DEFAULT_TTL = 86400  # 24 hours


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_jwt(*, api_key: str, ttl_seconds: int = _DEFAULT_TTL, now: int | None = None) -> str:
    """Create a signed JWT token.

    Returns a compact JWT string: header.payload.signature
    """
    issued_at = int(now if now is not None else time.time())
    expires_at = issued_at + max(1, ttl_seconds)

    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT", "v": _JWT_VERSION}).encode())
    payload = _b64url_encode(json.dumps({
        "sub": "admin",
        "iat": issued_at,
        "exp": expires_at,
    }).encode())

    signing_input = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(api_key.encode("utf-8"), signing_input, hashlib.sha256).digest()

    return f"{header}.{payload}.{_b64url_encode(signature)}"


def verify_jwt(*, token: str, api_key: str, now: int | None = None) -> dict | None:
    """Verify JWT signature and expiration.

    Returns the payload dict on success, None on any failure.
    """
    parts = token.split(".")
    if len(parts) != 3:
        return None

    header_b64, payload_b64, sig_b64 = parts

    try:
        signature = _b64url_decode(sig_b64)
    except Exception:
        return None

    # Verify signature
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(api_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        return None

    # Decode and validate payload
    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        return None

    if header.get("v") != _JWT_VERSION:
        return None

    current = int(now if now is not None else time.time())
    if current > payload.get("exp", 0):
        return None

    return payload
