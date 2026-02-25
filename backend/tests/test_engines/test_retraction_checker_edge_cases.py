"""Edge case tests for RetractionChecker — multi-flag DOIs, empty batches, client errors."""

from unittest.mock import AsyncMock

import pytest

from app.engines.integrity.finding_models import PubPeerStatus, RetractionStatus
from app.engines.integrity.retraction_checker import RetractionChecker


@pytest.fixture
def mock_crossref():
    return AsyncMock()


@pytest.fixture
def mock_pubpeer():
    return AsyncMock()


class TestMultipleFlagsPerDOI:
    """Test DOIs that have multiple issues simultaneously."""

    @pytest.mark.asyncio
    async def test_retracted_and_corrected_and_eoc(self, mock_crossref):
        """DOI with all three flags should produce three findings."""
        mock_crossref.check_retraction.return_value = RetractionStatus(
            doi="10.1234/allflag",
            is_retracted=True,
            is_corrected=True,
            has_expression_of_concern=True,
            retraction_doi="10.1234/retract",
            correction_doi="10.1234/erratum",
        )
        checker = RetractionChecker(crossref_client=mock_crossref)
        findings = await checker.check_doi("10.1234/allflag")
        assert len(findings) == 3
        severities = {f.severity for f in findings}
        assert severities == {"critical", "warning", "error"}

    @pytest.mark.asyncio
    async def test_retracted_without_retraction_doi(self, mock_crossref):
        """Retracted but no retraction_doi should still produce finding without crashing."""
        mock_crossref.check_retraction.return_value = RetractionStatus(
            doi="10.1234/nonotice",
            is_retracted=True,
            retraction_doi=None,
        )
        checker = RetractionChecker(crossref_client=mock_crossref)
        findings = await checker.check_doi("10.1234/nonotice")
        assert len(findings) == 1
        assert findings[0].severity == "critical"
        # Description should not contain "None"
        assert "None" not in findings[0].description

    @pytest.mark.asyncio
    async def test_corrected_without_correction_doi(self, mock_crossref):
        """Corrected but no correction_doi should work."""
        mock_crossref.check_retraction.return_value = RetractionStatus(
            doi="10.1234/corrnoref",
            is_corrected=True,
            correction_doi=None,
        )
        checker = RetractionChecker(crossref_client=mock_crossref)
        findings = await checker.check_doi("10.1234/corrnoref")
        assert len(findings) == 1
        assert findings[0].severity == "warning"


class TestPubPeerEdgeCases:
    """Test PubPeer-specific edge cases."""

    @pytest.mark.asyncio
    async def test_pubpeer_no_comments(self, mock_pubpeer):
        """PubPeer with has_comments=False should produce no finding."""
        mock_pubpeer.check_doi.return_value = PubPeerStatus(
            doi="10.1234/clean",
            comment_count=0,
            has_comments=False,
        )
        checker = RetractionChecker(pubpeer_client=mock_pubpeer)
        findings = await checker.check_doi("10.1234/clean")
        assert len(findings) == 0

    @pytest.mark.asyncio
    async def test_pubpeer_one_comment(self, mock_pubpeer):
        """Single PubPeer comment should produce info finding."""
        mock_pubpeer.check_doi.return_value = PubPeerStatus(
            doi="10.1234/onecomment",
            comment_count=1,
            has_comments=True,
            url="https://pubpeer.com/1",
        )
        checker = RetractionChecker(pubpeer_client=mock_pubpeer)
        findings = await checker.check_doi("10.1234/onecomment")
        assert len(findings) == 1
        assert findings[0].severity == "info"
        assert "1" in findings[0].description

    @pytest.mark.asyncio
    async def test_pubpeer_many_comments(self, mock_pubpeer):
        """Many PubPeer comments should still produce info-level finding."""
        mock_pubpeer.check_doi.return_value = PubPeerStatus(
            doi="10.1234/many",
            comment_count=100,
            has_comments=True,
            url="https://pubpeer.com/many",
        )
        checker = RetractionChecker(pubpeer_client=mock_pubpeer)
        findings = await checker.check_doi("10.1234/many")
        assert len(findings) == 1
        assert findings[0].severity == "info"
        assert "100" in findings[0].description

    @pytest.mark.asyncio
    async def test_pubpeer_empty_url(self, mock_pubpeer):
        """PubPeer with empty URL should still work."""
        mock_pubpeer.check_doi.return_value = PubPeerStatus(
            doi="10.1234/nourl",
            comment_count=2,
            has_comments=True,
            url="",
        )
        checker = RetractionChecker(pubpeer_client=mock_pubpeer)
        findings = await checker.check_doi("10.1234/nourl")
        assert len(findings) == 1


class TestBatchEdgeCases:
    """Test batch checking edge cases."""

    @pytest.mark.asyncio
    async def test_empty_batch(self, mock_crossref):
        """Empty DOI list should return empty findings."""
        checker = RetractionChecker(crossref_client=mock_crossref)
        findings = await checker.check_batch([])
        assert findings == []

    @pytest.mark.asyncio
    async def test_single_doi_batch(self, mock_crossref):
        """Single DOI batch should work like single check."""
        mock_crossref.check_retraction.return_value = RetractionStatus(
            doi="10.1234/single",
            is_retracted=True,
        )
        checker = RetractionChecker(crossref_client=mock_crossref)
        findings = await checker.check_batch(["10.1234/single"])
        assert len(findings) == 1

    @pytest.mark.asyncio
    async def test_mixed_batch(self, mock_crossref):
        """Batch with some retracted and some clean."""
        mock_crossref.check_retraction.side_effect = [
            RetractionStatus(doi="10.1/a", is_retracted=True),
            RetractionStatus(doi="10.1/b"),
            RetractionStatus(doi="10.1/c", is_corrected=True),
        ]
        checker = RetractionChecker(crossref_client=mock_crossref)
        findings = await checker.check_batch(["10.1/a", "10.1/b", "10.1/c"])
        assert len(findings) == 2  # retracted + corrected

    @pytest.mark.asyncio
    async def test_duplicate_dois_in_batch(self, mock_crossref):
        """Duplicate DOIs in batch should each be checked (no dedup at this level)."""
        mock_crossref.check_retraction.return_value = RetractionStatus(
            doi="10.1/dup",
            is_retracted=True,
        )
        checker = RetractionChecker(crossref_client=mock_crossref)
        findings = await checker.check_batch(["10.1/dup", "10.1/dup"])
        assert len(findings) == 2  # Each call produces a finding


class TestNoClientsScenarios:
    """Test behavior when clients are None."""

    @pytest.mark.asyncio
    async def test_no_crossref_no_pubpeer(self):
        """No clients at all should return empty findings."""
        checker = RetractionChecker()
        findings = await checker.check_doi("10.1234/test")
        assert findings == []

    @pytest.mark.asyncio
    async def test_only_crossref(self, mock_crossref):
        """Only Crossref client (no PubPeer) should work."""
        mock_crossref.check_retraction.return_value = RetractionStatus(
            doi="10.1234/xref",
            is_retracted=True,
        )
        checker = RetractionChecker(crossref_client=mock_crossref, pubpeer_client=None)
        findings = await checker.check_doi("10.1234/xref")
        assert len(findings) == 1

    @pytest.mark.asyncio
    async def test_only_pubpeer(self, mock_pubpeer):
        """Only PubPeer client (no Crossref) should work."""
        mock_pubpeer.check_doi.return_value = PubPeerStatus(
            doi="10.1234/pp",
            comment_count=3,
            has_comments=True,
            url="https://pubpeer.com/pp",
        )
        checker = RetractionChecker(crossref_client=None, pubpeer_client=mock_pubpeer)
        findings = await checker.check_doi("10.1234/pp")
        assert len(findings) == 1


class TestFindingConfidenceAndMetadata:
    """Test confidence values and metadata population."""

    @pytest.mark.asyncio
    async def test_retracted_confidence(self, mock_crossref):
        """Retracted finding should have 0.99 confidence."""
        mock_crossref.check_retraction.return_value = RetractionStatus(
            doi="10.1234/r",
            is_retracted=True,
        )
        checker = RetractionChecker(crossref_client=mock_crossref)
        findings = await checker.check_doi("10.1234/r")
        assert findings[0].confidence == 0.99

    @pytest.mark.asyncio
    async def test_corrected_confidence(self, mock_crossref):
        """Corrected finding should have 0.95 confidence."""
        mock_crossref.check_retraction.return_value = RetractionStatus(
            doi="10.1234/c",
            is_corrected=True,
        )
        checker = RetractionChecker(crossref_client=mock_crossref)
        findings = await checker.check_doi("10.1234/c")
        assert findings[0].confidence == 0.95

    @pytest.mark.asyncio
    async def test_pubpeer_confidence(self, mock_pubpeer):
        """PubPeer finding should have 0.6 confidence."""
        mock_pubpeer.check_doi.return_value = PubPeerStatus(
            doi="10.1234/pp",
            comment_count=5,
            has_comments=True,
            url="https://pubpeer.com/pp",
        )
        checker = RetractionChecker(pubpeer_client=mock_pubpeer)
        findings = await checker.check_doi("10.1234/pp")
        assert findings[0].confidence == 0.6

    @pytest.mark.asyncio
    async def test_pubpeer_metadata_populated(self, mock_pubpeer):
        """PubPeer finding metadata should include URL and count."""
        mock_pubpeer.check_doi.return_value = PubPeerStatus(
            doi="10.1234/meta",
            comment_count=7,
            has_comments=True,
            url="https://pubpeer.com/meta",
        )
        checker = RetractionChecker(pubpeer_client=mock_pubpeer)
        findings = await checker.check_doi("10.1234/meta")
        assert findings[0].metadata["pubpeer_url"] == "https://pubpeer.com/meta"
        assert findings[0].metadata["comment_count"] == 7

    @pytest.mark.asyncio
    async def test_retraction_finding_has_doi(self, mock_crossref):
        """Retraction finding should store the DOI."""
        mock_crossref.check_retraction.return_value = RetractionStatus(
            doi="10.1234/stored",
            is_retracted=True,
        )
        checker = RetractionChecker(crossref_client=mock_crossref)
        findings = await checker.check_doi("10.1234/stored")
        assert findings[0].doi == "10.1234/stored"
        assert findings[0].source_text == "10.1234/stored"
