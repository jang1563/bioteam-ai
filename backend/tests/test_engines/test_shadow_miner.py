"""Tests for ShadowMiner engine."""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.engines.negative_results.shadow_miner import (
    NegativeResultClassification,
    ShadowMiner,
)
from app.integrations.pubmed import PubMedPaper
from app.models.negative_result import NegativeResult  # noqa: F401


def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _make_miner(llm_mock=None):
    engine = _make_engine()
    session = Session(engine)
    llm = llm_mock or MagicMock()
    miner = ShadowMiner(llm_layer=llm, session=session)
    return miner, session


def _mock_llm(is_negative=True, confidence=0.85):
    llm = MagicMock()
    classification = NegativeResultClassification(
        is_negative=is_negative,
        confidence=confidence,
        claim="Drug X does not inhibit VEGF signaling",
        outcome="No significant reduction in tumor vascularity",
        organism="mouse",
        failure_category="statistical",
        reasoning="p=0.42 across all dosing regimens",
    )
    llm.complete_structured = AsyncMock(return_value=classification)
    return llm


def _make_paper(pmid="12345", title="Test paper", abstract="Test abstract", doi="10.1234/test"):
    return PubMedPaper(pmid=pmid, title=title, abstract=abstract, doi=doi, journal="Nature", year="2023")


# ── Query augmentation ────────────────────────────────────────────────────────


class TestQueryAugmentation:
    def test_topic_included_in_query(self):
        miner, _ = _make_miner()
        q = miner._augment_query("CRISPR off-target")
        assert "CRISPR off-target" in q

    def test_negative_vocab_included(self):
        miner, _ = _make_miner()
        q = miner._augment_query("CRISPR off-target")
        assert "no significant" in q or "null result" in q

    def test_query_has_both_parts(self):
        miner, _ = _make_miner()
        q = miner._augment_query("spaceflight anemia")
        assert q.startswith("(spaceflight anemia)")


# ── classify_abstract ─────────────────────────────────────────────────────────


class TestClassifyAbstract:
    @pytest.mark.asyncio
    async def test_returns_classification_for_abstract(self):
        llm = _mock_llm(is_negative=True, confidence=0.9)
        miner, _ = _make_miner(llm)
        paper = _make_paper()
        result = await miner.classify_abstract(paper)
        assert result is not None
        assert result.is_negative is True
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_abstract(self):
        miner, _ = _make_miner()
        paper = _make_paper(abstract="")
        result = await miner.classify_abstract(paper)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_llm_error(self):
        llm = MagicMock()
        llm.complete_structured = AsyncMock(side_effect=RuntimeError("LLM timeout"))
        miner, _ = _make_miner(llm)
        paper = _make_paper()
        result = await miner.classify_abstract(paper)
        assert result is None

    @pytest.mark.asyncio
    async def test_calls_llm_with_haiku_model(self):
        llm = _mock_llm()
        miner, _ = _make_miner(llm)
        paper = _make_paper()
        await miner.classify_abstract(paper)
        call_kwargs = llm.complete_structured.call_args
        assert call_kwargs.kwargs.get("model") == "haiku"


# ── run() ─────────────────────────────────────────────────────────────────────


class TestMinerRun:
    @pytest.mark.asyncio
    async def test_stores_negative_result_in_db(self):
        llm = _mock_llm(is_negative=True, confidence=0.9)
        miner, session = _make_miner(llm)

        papers = [_make_paper(pmid="111")]
        with patch.object(miner.pubmed, "search", return_value=papers):
            result = await miner.run("cancer therapy", max_papers=5)

        assert result.entries_created == 1
        assert result.negatives_found == 1
        stored = session.exec(
            __import__("sqlmodel", fromlist=["select"]).select(NegativeResult)
        ).all()
        assert len(stored) == 1
        assert stored[0].created_by == "shadow_miner"

    @pytest.mark.asyncio
    async def test_skips_low_confidence(self):
        llm = _mock_llm(is_negative=True, confidence=0.4)
        miner, session = _make_miner(llm)

        papers = [_make_paper(pmid="222")]
        with patch.object(miner.pubmed, "search", return_value=papers):
            result = await miner.run("cancer therapy", min_confidence=0.6)

        assert result.entries_created == 0
        assert result.negatives_found == 0

    @pytest.mark.asyncio
    async def test_skips_positive_results(self):
        llm = _mock_llm(is_negative=False, confidence=0.95)
        miner, session = _make_miner(llm)

        papers = [_make_paper(pmid="333")]
        with patch.object(miner.pubmed, "search", return_value=papers):
            result = await miner.run("cancer therapy")

        assert result.entries_created == 0

    @pytest.mark.asyncio
    async def test_returns_run_statistics(self):
        llm = _mock_llm(is_negative=True, confidence=0.9)
        miner, _ = _make_miner(llm)

        papers = [_make_paper(pmid=str(i)) for i in range(3)]
        with patch.object(miner.pubmed, "search", return_value=papers):
            result = await miner.run("BRCA1 mutations", max_papers=3)

        assert result.query == "BRCA1 mutations"
        assert result.papers_fetched == 3
        assert result.papers_classified == 3
        assert result.negatives_found == 3
        assert result.entries_created == 3
        assert len(result.pmids_processed) == 3

    @pytest.mark.asyncio
    async def test_handles_pubmed_failure_gracefully(self):
        miner, _ = _make_miner()
        with patch.object(miner.pubmed, "search", side_effect=RuntimeError("Network error")):
            result = await miner.run("test query")

        assert result.papers_fetched == 0
        assert len(result.errors) > 0
        assert "Network error" in result.errors[0]

    @pytest.mark.asyncio
    async def test_uses_doi_as_source_when_available(self):
        llm = _mock_llm(is_negative=True, confidence=0.9)
        miner, session = _make_miner(llm)

        papers = [_make_paper(pmid="444", doi="10.1234/xyz")]
        with patch.object(miner.pubmed, "search", return_value=papers):
            await miner.run("test topic")

        stored = session.exec(
            __import__("sqlmodel", fromlist=["select"]).select(NegativeResult)
        ).all()
        assert stored[0].source == "doi:10.1234/xyz"

    @pytest.mark.asyncio
    async def test_uses_pmid_source_when_no_doi(self):
        llm = _mock_llm(is_negative=True, confidence=0.9)
        miner, session = _make_miner(llm)

        paper = _make_paper(pmid="555", doi="")
        with patch.object(miner.pubmed, "search", return_value=[paper]):
            await miner.run("test topic")

        stored = session.exec(
            __import__("sqlmodel", fromlist=["select"]).select(NegativeResult)
        ).all()
        assert stored[0].source == "pubmed:555"
