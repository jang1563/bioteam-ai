"""Tests for RetractionChecker — unified retraction/correction checking."""

from unittest.mock import AsyncMock

import pytest
from app.engines.integrity.finding_models import PubPeerStatus, RetractionStatus
from app.engines.integrity.retraction_checker import RetractionChecker


@pytest.fixture
def mock_crossref():
    """Mock CrossrefClient."""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_pubpeer():
    """Mock PubPeerClient."""
    client = AsyncMock()
    return client


class TestRetractionChecker:

    @pytest.mark.asyncio
    async def test_retracted_doi(self, mock_crossref):
        """Retracted DOI produces critical finding."""
        mock_crossref.check_retraction.return_value = RetractionStatus(
            doi="10.1234/retracted",
            is_retracted=True,
            retraction_doi="10.1234/retraction-notice",
        )

        checker = RetractionChecker(crossref_client=mock_crossref)
        findings = await checker.check_doi("10.1234/retracted")

        assert len(findings) == 1
        assert findings[0].severity == "critical"
        assert findings[0].category == "retracted_reference"

    @pytest.mark.asyncio
    async def test_corrected_doi(self, mock_crossref):
        """Corrected DOI produces warning finding."""
        mock_crossref.check_retraction.return_value = RetractionStatus(
            doi="10.1234/corrected",
            is_corrected=True,
            correction_doi="10.1234/erratum",
        )

        checker = RetractionChecker(crossref_client=mock_crossref)
        findings = await checker.check_doi("10.1234/corrected")

        assert len(findings) == 1
        assert findings[0].severity == "warning"
        assert findings[0].category == "corrected_reference"

    @pytest.mark.asyncio
    async def test_expression_of_concern(self, mock_crossref):
        """Expression of concern produces error finding."""
        mock_crossref.check_retraction.return_value = RetractionStatus(
            doi="10.1234/eoc",
            has_expression_of_concern=True,
        )

        checker = RetractionChecker(crossref_client=mock_crossref)
        findings = await checker.check_doi("10.1234/eoc")

        assert len(findings) == 1
        assert findings[0].severity == "error"

    @pytest.mark.asyncio
    async def test_clean_doi(self, mock_crossref):
        """Clean DOI produces no findings."""
        mock_crossref.check_retraction.return_value = RetractionStatus(
            doi="10.1234/clean",
        )

        checker = RetractionChecker(crossref_client=mock_crossref)
        findings = await checker.check_doi("10.1234/clean")

        assert len(findings) == 0

    @pytest.mark.asyncio
    async def test_pubpeer_comments(self, mock_crossref, mock_pubpeer):
        """PubPeer commentary produces info finding."""
        mock_crossref.check_retraction.return_value = RetractionStatus(doi="10.1234/flagged")
        mock_pubpeer.check_doi.return_value = PubPeerStatus(
            doi="10.1234/flagged",
            comment_count=3,
            has_comments=True,
            url="https://pubpeer.com/publications/12345",
        )

        checker = RetractionChecker(crossref_client=mock_crossref, pubpeer_client=mock_pubpeer)
        findings = await checker.check_doi("10.1234/flagged")

        assert len(findings) == 1
        assert findings[0].category == "pubpeer_flagged"
        assert findings[0].severity == "info"

    @pytest.mark.asyncio
    async def test_batch_check(self, mock_crossref):
        """Batch check processes multiple DOIs."""
        mock_crossref.check_retraction.side_effect = [
            RetractionStatus(doi="10.1/a", is_retracted=True),
            RetractionStatus(doi="10.1/b"),
        ]

        checker = RetractionChecker(crossref_client=mock_crossref)
        findings = await checker.check_batch(["10.1/a", "10.1/b"])

        assert len(findings) == 1  # Only retracted DOI produces a finding

    @pytest.mark.asyncio
    async def test_no_clients(self):
        """Checker without any clients produces no findings."""
        checker = RetractionChecker()
        findings = await checker.check_doi("10.1234/test")
        assert findings == []

    @pytest.mark.asyncio
    async def test_retracted_and_pubpeer(self, mock_crossref, mock_pubpeer):
        """Both retraction and PubPeer findings for same DOI."""
        mock_crossref.check_retraction.return_value = RetractionStatus(
            doi="10.1234/bad",
            is_retracted=True,
        )
        mock_pubpeer.check_doi.return_value = PubPeerStatus(
            doi="10.1234/bad",
            comment_count=5,
            has_comments=True,
            url="https://pubpeer.com/bad",
        )

        checker = RetractionChecker(crossref_client=mock_crossref, pubpeer_client=mock_pubpeer)
        findings = await checker.check_doi("10.1234/bad")

        assert len(findings) == 2
        categories = {f.category for f in findings}
        assert "retracted_reference" in categories
        assert "pubpeer_flagged" in categories
