"""Benchmark: Retraction Checker — mock-based validation of retraction/correction detection.

Tests RetractionChecker against known retraction patterns from Retraction Watch
and PubPeer. Uses mock clients for offline, deterministic testing.

Severity mapping (verified from retraction_checker.py):
  - is_retracted=True  → category="retracted_reference", severity="critical"
  - is_corrected=True  → category="corrected_reference", severity="warning"
  - has_expression_of_concern=True → category="retracted_reference", severity="error"
  - PubPeer has_comments=True → category="pubpeer_flagged", severity="info"

References:
- Retraction Watch database (retractionwatch.com)
- PubPeer (pubpeer.com)
"""

import os

import pytest

from app.engines.integrity.finding_models import PubPeerStatus, RetractionStatus
from app.engines.integrity.retraction_checker import RetractionChecker


# ── Mock clients ──


class MockCrossrefClient:
    """Mock that returns preset RetractionStatus for known DOIs."""

    def __init__(self, status_map: dict[str, RetractionStatus] | None = None):
        self._map = status_map or {}

    async def check_retraction(self, doi: str) -> RetractionStatus:
        return self._map.get(doi, RetractionStatus(doi=doi))


class MockPubPeerClient:
    """Mock that returns preset PubPeerStatus for known DOIs."""

    def __init__(self, status_map: dict[str, PubPeerStatus] | None = None):
        self._map = status_map or {}

    async def check_doi(self, doi: str) -> PubPeerStatus:
        return self._map.get(doi, PubPeerStatus(doi=doi))


# ── Test data ──

# Famous retracted papers (DOIs are real, but we mock the responses)
RETRACTED_DOIS = {
    "10.1016/S0140-6736(97)11096-0": "Wakefield MMR-autism (retracted 2010)",
    "10.1126/science.aaa8415": "Lacour political canvassing (retracted 2015)",
    "10.1038/nature10145": "Obokata STAP cells (retracted 2014)",
}

CORRECTED_DOIS = {
    "10.1038/s41586-020-2012-7": "Zhou et al. bat coronavirus (corrected)",
    "10.1016/j.cell.2020.02.058": "Wrapp et al. spike protein (corrected)",
}

EOC_DOIS = {
    "10.1234/eoc-example": "Example expression of concern",
}

PUBPEER_FLAGGED_DOIS = {
    "10.1234/pubpeer-1": (5, "https://pubpeer.com/publications/ABC123"),
    "10.1234/pubpeer-2": (12, "https://pubpeer.com/publications/DEF456"),
}

CLEAN_DOIS = [
    "10.1038/s41591-022-01696-6",
    "10.1126/science.abc1234",
    "10.1016/j.cell.2021.01.001",
    "10.1371/journal.pone.0000001",
]


def _make_crossref_map() -> dict[str, RetractionStatus]:
    """Build mock crossref status map."""
    m: dict[str, RetractionStatus] = {}
    for doi in RETRACTED_DOIS:
        m[doi] = RetractionStatus(doi=doi, is_retracted=True)
    for doi in CORRECTED_DOIS:
        m[doi] = RetractionStatus(doi=doi, is_corrected=True)
    for doi in EOC_DOIS:
        m[doi] = RetractionStatus(doi=doi, has_expression_of_concern=True)
    return m


def _make_pubpeer_map() -> dict[str, PubPeerStatus]:
    """Build mock pubpeer status map."""
    m: dict[str, PubPeerStatus] = {}
    for doi, (count, url) in PUBPEER_FLAGGED_DOIS.items():
        m[doi] = PubPeerStatus(doi=doi, has_comments=True, comment_count=count, url=url)
    return m


def _make_checker() -> RetractionChecker:
    """Create checker with both mock clients."""
    return RetractionChecker(
        crossref_client=MockCrossrefClient(_make_crossref_map()),
        pubpeer_client=MockPubPeerClient(_make_pubpeer_map()),
    )


# ══════════════════════════════════════════════════════════════════
# 1. Retraction detection
# ══════════════════════════════════════════════════════════════════


class TestRetractionDetection:
    """Retracted DOIs should produce critical findings."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("doi, desc", list(RETRACTED_DOIS.items()))
    async def test_retracted_doi(self, doi: str, desc: str):
        checker = _make_checker()
        findings = await checker.check_doi(doi)
        retracted = [f for f in findings if f.severity == "critical"]
        assert len(retracted) >= 1, f"Should detect retraction for {doi} ({desc})"
        assert retracted[0].category == "retracted_reference"
        assert retracted[0].confidence >= 0.99


# ══════════════════════════════════════════════════════════════════
# 2. Correction detection
# ══════════════════════════════════════════════════════════════════


class TestCorrectionDetection:
    """Corrected DOIs should produce warning findings."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("doi, desc", list(CORRECTED_DOIS.items()))
    async def test_corrected_doi(self, doi: str, desc: str):
        checker = _make_checker()
        findings = await checker.check_doi(doi)
        corrected = [f for f in findings if f.severity == "warning"]
        assert len(corrected) >= 1, f"Should detect correction for {doi} ({desc})"
        assert corrected[0].category == "corrected_reference"


# ══════════════════════════════════════════════════════════════════
# 3. Expression of concern
# ══════════════════════════════════════════════════════════════════


class TestExpressionOfConcern:
    """EOC DOIs should produce error findings (category=retracted_reference)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("doi, desc", list(EOC_DOIS.items()))
    async def test_eoc_doi(self, doi: str, desc: str):
        checker = _make_checker()
        findings = await checker.check_doi(doi)
        eoc = [f for f in findings if f.severity == "error"]
        assert len(eoc) >= 1, f"Should detect EOC for {doi} ({desc})"
        # EOC uses same category as retracted (verified from source)
        assert eoc[0].category == "retracted_reference"


# ══════════════════════════════════════════════════════════════════
# 4. PubPeer detection
# ══════════════════════════════════════════════════════════════════


class TestPubPeerDetection:
    """PubPeer-flagged DOIs should produce info findings."""

    @pytest.mark.parametrize(
        "doi, count_url",
        list(PUBPEER_FLAGGED_DOIS.items()),
        ids=list(PUBPEER_FLAGGED_DOIS.keys()),
    )
    @pytest.mark.asyncio
    async def test_pubpeer_flagged(self, doi: str, count_url: tuple):
        checker = _make_checker()
        findings = await checker.check_doi(doi)
        pp = [f for f in findings if f.category == "pubpeer_flagged"]
        assert len(pp) >= 1, f"Should detect PubPeer comments for {doi}"
        assert pp[0].severity == "info"


# ══════════════════════════════════════════════════════════════════
# 5. Clean DOIs
# ══════════════════════════════════════════════════════════════════


class TestCleanDOIs:
    """Clean DOIs should produce zero findings."""

    @pytest.mark.parametrize("doi", CLEAN_DOIS)
    @pytest.mark.asyncio
    async def test_clean_doi(self, doi: str):
        checker = _make_checker()
        findings = await checker.check_doi(doi)
        assert len(findings) == 0, f"False positive for clean DOI {doi}: {findings}"


# ══════════════════════════════════════════════════════════════════
# 6. Combined scenarios
# ══════════════════════════════════════════════════════════════════


class TestCombinedScenarios:
    """Edge cases and combination scenarios."""

    @pytest.mark.asyncio
    async def test_no_clients(self):
        """Checker with no clients should return empty list."""
        checker = RetractionChecker(crossref_client=None, pubpeer_client=None)
        findings = await checker.check_doi("10.1234/anything")
        assert len(findings) == 0

    @pytest.mark.asyncio
    async def test_batch_mixed(self):
        """Batch check with mixed retracted + clean DOIs."""
        checker = _make_checker()
        dois = [
            list(RETRACTED_DOIS.keys())[0],  # retracted
            CLEAN_DOIS[0],                     # clean
            list(CORRECTED_DOIS.keys())[0],    # corrected
        ]
        findings = await checker.check_batch(dois)
        assert len(findings) == 2  # 1 retracted + 1 corrected

    @pytest.mark.asyncio
    async def test_retracted_plus_pubpeer(self):
        """Same DOI flagged by both Crossref and PubPeer."""
        doi = "10.1234/both-flagged"
        crossref_map = {doi: RetractionStatus(doi=doi, is_retracted=True)}
        pubpeer_map = {doi: PubPeerStatus(doi=doi, has_comments=True, comment_count=3, url="https://pubpeer.com/test")}
        checker = RetractionChecker(
            crossref_client=MockCrossrefClient(crossref_map),
            pubpeer_client=MockPubPeerClient(pubpeer_map),
        )
        findings = await checker.check_doi(doi)
        assert len(findings) == 2  # 1 retraction + 1 pubpeer
        categories = {f.category for f in findings}
        assert "retracted_reference" in categories
        assert "pubpeer_flagged" in categories

    @pytest.mark.asyncio
    async def test_retracted_and_corrected(self):
        """DOI that is both retracted AND corrected → 2 findings."""
        doi = "10.1234/retracted-corrected"
        crossref_map = {doi: RetractionStatus(doi=doi, is_retracted=True, is_corrected=True)}
        checker = RetractionChecker(
            crossref_client=MockCrossrefClient(crossref_map),
            pubpeer_client=None,
        )
        findings = await checker.check_doi(doi)
        assert len(findings) == 2
        severities = {f.severity for f in findings}
        assert "critical" in severities  # retracted
        assert "warning" in severities   # corrected


# ══════════════════════════════════════════════════════════════════
# 7. Scorecard
# ══════════════════════════════════════════════════════════════════


class TestRetractionScorecard:
    """Aggregate precision/recall across all ground truth."""

    @pytest.mark.asyncio
    async def test_retraction_metrics(self):
        checker = _make_checker()
        tp = fp = fn = tn = 0

        # True positives: retracted, corrected, EOC, pubpeer
        positive_dois = (
            list(RETRACTED_DOIS.keys())
            + list(CORRECTED_DOIS.keys())
            + list(EOC_DOIS.keys())
            + list(PUBPEER_FLAGGED_DOIS.keys())
        )
        for doi in positive_dois:
            findings = await checker.check_doi(doi)
            if len(findings) >= 1:
                tp += 1
            else:
                fn += 1

        # True negatives: clean DOIs
        for doi in CLEAN_DOIS:
            findings = await checker.check_doi(doi)
            if len(findings) == 0:
                tn += 1
            else:
                fp += 1

        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        print(f"\n=== Retraction Scorecard ===")
        print(f"TP={tp} FP={fp} FN={fn} TN={tn}")
        print(f"Precision: {precision:.3f}")
        print(f"Recall:    {recall:.3f}")
        print(f"F1 Score:  {f1:.3f}")

        assert recall >= 0.85, f"Retraction recall {recall:.3f} below 0.85"
        assert precision >= 0.85, f"Retraction precision {precision:.3f} below 0.85"


# ══════════════════════════════════════════════════════════════════
# 8. Optional live test
# ══════════════════════════════════════════════════════════════════


class TestLiveCrossref:
    """Optional: test against real Crossref API. Requires CROSSREF_EMAIL env var."""

    @pytest.mark.skipif(
        not os.environ.get("CROSSREF_EMAIL"),
        reason="CROSSREF_EMAIL not set — skipping live Crossref test",
    )
    @pytest.mark.asyncio
    async def test_wakefield_retraction_live(self):
        """Wakefield 1998 MMR-autism paper — retracted by The Lancet in 2010."""
        from app.integrations.crossref import CrossrefClient

        client = CrossrefClient(email=os.environ["CROSSREF_EMAIL"])
        checker = RetractionChecker(crossref_client=client)
        findings = await checker.check_doi("10.1016/S0140-6736(97)11096-0")
        # Informational: print what we find
        print(f"\n=== Live Crossref: Wakefield ===")
        print(f"Findings: {len(findings)}")
        for f in findings:
            print(f"  {f.category} ({f.severity}): {f.title}")
