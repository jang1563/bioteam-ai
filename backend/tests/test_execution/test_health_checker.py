"""Tests for HealthChecker."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.workflows.health_checker import HealthChecker, HealthIssue


@pytest.mark.asyncio
async def test_no_services_returns_empty():
    issues = await HealthChecker.check_all([])
    assert issues == []


@pytest.mark.asyncio
async def test_unknown_service_skipped():
    issues = await HealthChecker.check_all(["unknown_service_xyz"])
    assert issues == []


@pytest.mark.asyncio
async def test_ensembl_healthy():
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        issues = await HealthChecker.check_all(["ensembl_vep_api"])
    assert issues == []


@pytest.mark.asyncio
async def test_ensembl_timeout():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client_cls.return_value = mock_client

        issues = await HealthChecker.check_all(["ensembl_vep_api"])
    assert len(issues) == 1
    assert issues[0].service == "ensembl_vep_api"
    assert issues[0].severity == "warning"


@pytest.mark.asyncio
async def test_uniprot_healthy():
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        issues = await HealthChecker.check_all(["uniprot_api"])
    assert issues == []


@pytest.mark.asyncio
async def test_gprofiler_not_installed():
    with patch("importlib.import_module", side_effect=ImportError("No module gprofiler")):
        issue = await HealthChecker._check_gprofiler()
    assert issue is not None
    assert issue.service == "gprofiler"
    assert "gprofiler-official" in issue.message


@pytest.mark.asyncio
async def test_ncbi_blast_not_installed():
    with patch("importlib.import_module", side_effect=ImportError("No module biopython")):
        issue = await HealthChecker._check_ncbi_blast()
    assert issue is not None
    assert issue.service == "ncbi_blast"


def test_health_issue_to_dict():
    issue = HealthIssue("test_service", "Something failed", severity="error")
    d = issue.to_dict()
    assert d["service"] == "test_service"
    assert d["severity"] == "error"
    assert d["message"] == "Something failed"


@pytest.mark.asyncio
async def test_multiple_checks_some_fail():
    mock_resp_ok = MagicMock()
    mock_resp_ok.status_code = 200
    mock_resp_fail = MagicMock()
    mock_resp_fail.status_code = 503

    call_count = {"n": 0}

    async def mock_get(url, **kwargs):
        call_count["n"] += 1
        if "ensembl" in url:
            return mock_resp_ok
        return mock_resp_fail

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = mock_get
        mock_client_cls.return_value = mock_client

        issues = await HealthChecker.check_all(["ensembl_vep_api", "uniprot_api"])

    # uniprot returned 503 → warning
    assert any(i.service == "uniprot_api" for i in issues)
