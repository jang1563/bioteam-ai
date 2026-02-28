"""Tests for circuit breaker and retry logic in LLM layer."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import asyncio
import time

from app.llm.layer import CircuitBreaker, CircuitBreakerOpenError, _retry_with_backoff

# === CircuitBreaker unit tests ===


def test_circuit_breaker_starts_closed():
    """Circuit breaker should start in CLOSED state."""
    cb = CircuitBreaker(failure_threshold=3)
    assert cb.state == "closed"
    assert cb.allow_request() is True


def test_circuit_breaker_opens_after_threshold():
    """Circuit breaker should open after N consecutive failures."""
    cb = CircuitBreaker(failure_threshold=3, reset_timeout=60.0)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "closed"
    cb.record_failure()
    assert cb.state == "open"
    assert cb.allow_request() is False


def test_circuit_breaker_success_resets():
    """A success should reset the failure count."""
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb.state == "closed"
    # Need 3 more failures to open
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "closed"


def test_circuit_breaker_half_open_after_timeout():
    """Circuit breaker should transition to HALF_OPEN after reset_timeout."""
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.1)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "open"

    time.sleep(0.15)
    assert cb.state == "half_open"
    assert cb.allow_request() is True
    # Only one probe is allowed until success/failure closes/reopens the circuit.
    assert cb.allow_request() is False


def test_circuit_breaker_half_open_success_closes():
    """A success in HALF_OPEN state should close the circuit."""
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.1)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.15)
    assert cb.state == "half_open"

    cb.record_success()
    assert cb.state == "closed"


def test_circuit_breaker_half_open_failure_reopens():
    """A failure in HALF_OPEN state should reopen the circuit."""
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.1)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.15)
    assert cb.state == "half_open"

    cb.record_failure()
    assert cb.state == "open"


# === _retry_with_backoff tests ===


def test_retry_succeeds_first_try():
    """Should return result on first successful call."""
    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = asyncio.run(_retry_with_backoff(factory, max_retries=3, base_delay=0.01))
    assert result == "ok"
    assert call_count == 1


def test_retry_with_open_circuit_breaker():
    """Should raise CircuitBreakerOpenError when circuit is open."""
    cb = CircuitBreaker(failure_threshold=1)
    cb.record_failure()  # Opens the circuit

    async def factory():
        return "should not reach here"

    try:
        asyncio.run(_retry_with_backoff(factory, circuit_breaker=cb))
        assert False, "Should have raised CircuitBreakerOpenError"
    except CircuitBreakerOpenError:
        pass


# === Backup label sanitization test ===


def test_backup_label_sanitization():
    """Backup label should be sanitized to prevent path traversal."""
    from app.backup.manager import BackupManager

    # Path traversal attempts
    assert BackupManager._sanitize_label("../../etc/passwd") == "etcpasswd"
    assert BackupManager._sanitize_label("label/with/slashes") == "labelwithslashes"
    assert BackupManager._sanitize_label("normal-label_v2") == "normal-label_v2"
    assert BackupManager._sanitize_label("") == ""
    assert BackupManager._sanitize_label("a" * 100) == "a" * 64  # Truncated


# === SSE subscriber cap test ===


def test_sse_hub_max_subscribers():
    """SSE hub should cap subscribers and evict oldest."""
    from app.api.v1.sse import SSEHub

    hub = SSEHub()
    hub.MAX_SUBSCRIBERS = 3  # Small cap for testing

    q1 = hub.subscribe()
    hub.subscribe()
    hub.subscribe()
    assert hub.subscriber_count == 3

    # 4th subscriber should evict oldest (q1)
    hub.subscribe()
    assert hub.subscriber_count == 3
    assert q1 not in hub._subscribers
    # q1 should have received None terminator
    assert q1.get_nowait() is None


if __name__ == "__main__":
    print("Testing Circuit Breaker & Security:")
    test_circuit_breaker_starts_closed()
    test_circuit_breaker_opens_after_threshold()
    test_circuit_breaker_success_resets()
    test_circuit_breaker_half_open_after_timeout()
    test_circuit_breaker_half_open_success_closes()
    test_circuit_breaker_half_open_failure_reopens()
    test_retry_succeeds_first_try()
    test_retry_with_open_circuit_breaker()
    test_backup_label_sanitization()
    test_sse_hub_max_subscribers()
    print("\nAll Circuit Breaker & Security tests passed!")
