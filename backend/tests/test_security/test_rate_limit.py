"""Tests for rate limiting middleware."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.middleware.rate_limit import TokenBucket, RateLimitMiddleware


# === TokenBucket tests ===


def test_token_bucket_initial_capacity():
    """Bucket should start with full capacity."""
    bucket = TokenBucket(rate=1.0, capacity=10)
    # Should be able to consume capacity times
    for _ in range(10):
        assert bucket.consume() is True
    # 11th should fail
    assert bucket.consume() is False


def test_token_bucket_refill():
    """Bucket should refill over time."""
    import time
    bucket = TokenBucket(rate=100.0, capacity=5)  # 100 tokens/sec
    # Drain it
    for _ in range(5):
        bucket.consume()
    assert bucket.consume() is False

    # Wait for refill
    time.sleep(0.1)  # Should refill ~10 tokens, capped at 5
    assert bucket.consume() is True


def test_token_bucket_rate():
    """Bucket rate should control refill speed."""
    bucket = TokenBucket(rate=10.0, capacity=100)  # 10 tokens/sec
    # Drain
    for _ in range(100):
        bucket.consume()
    assert bucket.consume() is False


# === RateLimitMiddleware integration ===


def test_rate_limit_health_exempt():
    """Health endpoint should be exempt from rate limiting."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.database import create_db_and_tables

    create_db_and_tables()
    client = TestClient(app)

    # Hit health many times — should never be rate limited
    for _ in range(20):
        resp = client.get("/health")
        assert resp.status_code == 200


def test_rate_limit_returns_429():
    """Exceeding rate limit should return 429."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    test_app = FastAPI()
    test_app.add_middleware(RateLimitMiddleware, global_rpm=3, expensive_rpm=1)

    @test_app.get("/test")
    async def test_route():
        return {"ok": True}

    client = TestClient(test_app)

    # First 3 should succeed
    for _ in range(3):
        resp = client.get("/test")
        assert resp.status_code == 200

    # 4th should be rate limited
    resp = client.get("/test")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


if __name__ == "__main__":
    print("Testing Rate Limiting:")
    test_token_bucket_initial_capacity()
    test_token_bucket_refill()
    test_token_bucket_rate()
    test_rate_limit_health_exempt()
    test_rate_limit_returns_429()
    print("\nAll Rate Limiting tests passed!")
