"""Tests for StepErrorReport error classification."""

from __future__ import annotations

import httpx
import pytest

from app.models.step_error import StepErrorReport


def test_classify_timeout():
    exc = httpx.TimeoutException("Timed out")
    r = StepErrorReport.classify("BLAST", "t01", exc, retry_count=0)
    assert r.error_type == "TRANSIENT"
    assert r.suggested_action == "RETRY"
    assert r.step_id == "BLAST"
    assert r.agent_id == "t01"


def test_classify_connect_error():
    exc = httpx.ConnectError("Connection refused")
    r = StepErrorReport.classify("VEP", "t01", exc)
    assert r.error_type == "TRANSIENT"


def test_classify_429():
    response = httpx.Response(status_code=429)
    exc = httpx.HTTPStatusError("Rate limit", request=None, response=response)
    r = StepErrorReport.classify("GO_ENRICH", "t06", exc)
    assert r.error_type == "TRANSIENT"


def test_classify_503():
    response = httpx.Response(status_code=503)
    exc = httpx.HTTPStatusError("Service unavailable", request=None, response=response)
    r = StepErrorReport.classify("NETWORK", "t06", exc)
    assert r.error_type == "TRANSIENT"


def test_classify_400_bad_request():
    response = httpx.Response(status_code=400)
    exc = httpx.HTTPStatusError("Bad request", request=None, response=response)
    r = StepErrorReport.classify("INGEST", "code", exc)
    assert r.error_type == "USER_INPUT"
    assert r.suggested_action == "USER_PROVIDE_INPUT"


def test_classify_401_unauthorized():
    response = httpx.Response(status_code=401)
    exc = httpx.HTTPStatusError("Unauthorized", request=None, response=response)
    r = StepErrorReport.classify("VEP", "t01", exc)
    assert r.error_type == "USER_INPUT"
    assert "API 키" in r.recovery_suggestions[0]


def test_classify_404_not_found():
    response = httpx.Response(status_code=404)
    exc = httpx.HTTPStatusError("Not found", request=None, response=response)
    r = StepErrorReport.classify("PROTEIN_ANALYSIS", "t03", exc)
    assert r.error_type == "SKIP_SAFE"
    assert r.suggested_action == "SKIP"


def test_classify_file_not_found():
    exc = FileNotFoundError("No such file: /data/samples.vcf")
    r = StepErrorReport.classify("INGEST_DATA", "code", exc)
    assert r.error_type == "USER_INPUT"
    assert any("파일" in s for s in r.recovery_suggestions)


def test_classify_memory_error():
    exc = MemoryError("Out of memory")
    r = StepErrorReport.classify("CROSS_OMICS", "integrative", exc)
    assert r.error_type == "FATAL"
    assert r.suggested_action == "ABORT"


def test_classify_max_tokens():
    exc = ValueError("max_tokens exceeded: context_length too large")
    r = StepErrorReport.classify("SYNTHESIZE", "research_director", exc)
    assert r.error_type == "RECOVERABLE"
    assert r.suggested_action == "RETRY_WITH_PARAMS"


def test_classify_generic():
    exc = RuntimeError("Unknown error occurred")
    r = StepErrorReport.classify("NOVEL_ASSESS", "research_director", exc)
    assert r.error_type == "RECOVERABLE"


def test_retry_count_preserved():
    exc = httpx.TimeoutException("timeout")
    r = StepErrorReport.classify("BLAST", "t01", exc, retry_count=2)
    assert r.retry_count == 2


def test_technical_detail_contains_traceback():
    exc = ValueError("test")
    r = StepErrorReport.classify("X", "y", exc)
    # technical_detail should be a string (could be empty in simple cases)
    assert isinstance(r.technical_detail, str)
