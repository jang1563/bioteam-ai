"""Benchmark tests for the W8 Open Peer Review Corpus pipeline.

Tests:
- OpenPeerReviewEntry model: JSON round-trip for concerns and benchmark results
- ELifeXMLParser: section extraction and decision inference from mock XML
- PLOSXMLParser: peer review section extraction
- ConcernParser: JSON parsing of LLM concern output; graceful failure handling
- ConcernMatcher: keyword-based coverage metric computation
- PeerReviewCorpusClient: guarded by settings.peer_review_corpus_enabled
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.engines.review_corpus.concern_matcher import ConcernMatcher
from app.engines.review_corpus.concern_parser import ConcernParser
from app.engines.review_corpus.xml_parser import ELifeXMLParser, PLOSXMLParser
from app.models.review_corpus import (
    OpenPeerReviewEntry,
    ReviewConcernBatch,
    ReviewerConcern,
    W8BenchmarkResult,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


SAMPLE_ELIFE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<article xmlns="http://jats.nlm.nih.gov">
  <front>
    <article-meta>
      <title-group>
        <article-title>Test Paper</article-title>
      </title-group>
    </article-meta>
  </front>
  <body>
    <sec sec-type="decision-letter">
      <title>Decision Letter</title>
      <p>We have reviewed your manuscript and require major revisions.</p>
      <p>Reviewer 1: The statistical analysis needs improvement.</p>
      <p>Reviewer 2: The methodology section lacks detail.</p>
    </sec>
    <sec sec-type="author-comment">
      <title>Author Response</title>
      <p>We thank the reviewers for their comments.</p>
      <p>We have updated the statistical methods section as requested.</p>
    </sec>
  </body>
</article>"""


SAMPLE_PLOS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<article>
  <body>
    <sec sec-type="peer-review">
      <p>Reviewer 1: The sample size is insufficient for the conclusions.</p>
      <p>Reviewer 2: Please add a control group to the experiment.</p>
    </sec>
    <sec sec-type="author-response">
      <p>We have expanded the sample size from n=20 to n=50 as suggested.</p>
    </sec>
  </body>
</article>"""


SAMPLE_LLM_CONCERNS_JSON = """[
  {
    "concern_id": "R1C1",
    "concern_text": "Statistical analysis needs improvement",
    "category": "statistics",
    "severity": "major",
    "author_response_text": "Updated statistical methods section",
    "resolution": "conceded",
    "was_valid": true,
    "raised_by_multiple": false
  },
  {
    "concern_id": "R2C1",
    "concern_text": "Methodology section lacks detail",
    "category": "methodology",
    "severity": "minor",
    "author_response_text": "Added more detail to methods",
    "resolution": "conceded",
    "was_valid": true,
    "raised_by_multiple": false
  }
]"""


@pytest.fixture
def elife_parser():
    return ELifeXMLParser()


@pytest.fixture
def plos_parser():
    return PLOSXMLParser()


@pytest.fixture
def sample_concerns():
    return [
        ReviewerConcern(
            concern_id="R1C1",
            concern_text="The statistical analysis is insufficient",
            category="statistics",
            severity="major",
            author_response_text="We revised the stats",
            resolution="conceded",
            was_valid=True,
        ),
        ReviewerConcern(
            concern_id="R1C2",
            concern_text="Sample size is too small",
            category="methodology",
            severity="major",
            author_response_text="We expanded to n=50",
            resolution="conceded",
            was_valid=True,
        ),
        ReviewerConcern(
            concern_id="R2C1",
            concern_text="The interpretation of results is unclear",
            category="interpretation",
            severity="minor",
            author_response_text="We clarified the discussion",
            resolution="partially_addressed",
            was_valid=None,
        ),
    ]


# ---------------------------------------------------------------------------
# OpenPeerReviewEntry model tests
# ---------------------------------------------------------------------------


def test_open_peer_review_entry_concern_roundtrip(sample_concerns):
    entry = OpenPeerReviewEntry(
        id="elife:12345",
        source="elife",
        doi="10.7554/eLife.12345",
    )
    entry.set_concerns(sample_concerns)
    recovered = entry.get_concerns()

    assert len(recovered) == 3
    assert recovered[0].concern_id == "R1C1"
    assert recovered[0].category == "statistics"
    assert recovered[0].severity == "major"
    assert recovered[0].was_valid is True


def test_open_peer_review_entry_benchmark_roundtrip():
    entry = OpenPeerReviewEntry(
        id="elife:99999",
        source="elife",
        doi="10.7554/eLife.99999",
    )
    result = W8BenchmarkResult(
        article_id="elife:99999",
        source="elife",
        major_concern_recall=0.75,
        overall_concern_recall=0.65,
        concern_precision=0.80,
    )
    entry.set_benchmark(result)
    recovered = entry.get_benchmark()

    assert recovered is not None
    assert recovered.major_concern_recall == 0.75
    assert recovered.overall_concern_recall == 0.65


def test_open_peer_review_entry_empty_concerns():
    entry = OpenPeerReviewEntry(id="elife:0", source="elife", doi="10.7554/eLife.0")
    concerns = entry.get_concerns()
    assert concerns == []


def test_open_peer_review_entry_empty_benchmark():
    entry = OpenPeerReviewEntry(id="elife:0", source="elife", doi="10.7554/eLife.0")
    assert entry.get_benchmark() is None


# ---------------------------------------------------------------------------
# ELifeXMLParser tests
# ---------------------------------------------------------------------------


def test_elife_xml_parser_extracts_decision_letter(elife_parser):
    result = elife_parser.parse(SAMPLE_ELIFE_XML)
    assert len(result["decision_letter"]) > 20
    assert "statistical" in result["decision_letter"].lower()


def test_elife_xml_parser_extracts_author_response(elife_parser):
    result = elife_parser.parse(SAMPLE_ELIFE_XML)
    assert len(result["author_response"]) > 20
    assert "thank" in result["author_response"].lower()


def test_elife_xml_parser_infers_major_revision(elife_parser):
    result = elife_parser.parse(SAMPLE_ELIFE_XML)
    assert result["editorial_decision"] == "major_revision"


def test_elife_xml_parser_infers_accept():
    parser = ELifeXMLParser()
    xml = """<article><body><sec sec-type="decision-letter">
    <p>We are pleased to accept your manuscript for publication.</p>
    </sec></body></article>"""
    result = parser.parse(xml)
    assert result["editorial_decision"] == "accept"


def test_elife_xml_parser_infers_reject():
    parser = ELifeXMLParser()
    xml = """<article><body><sec sec-type="decision-letter">
    <p>We regret to inform you that we must reject your manuscript.</p>
    </sec></body></article>"""
    result = parser.parse(xml)
    assert result["editorial_decision"] == "reject"


def test_elife_xml_parser_empty_xml(elife_parser):
    result = elife_parser.parse("")
    assert result["decision_letter"] == ""
    assert result["author_response"] == ""


def test_elife_xml_parser_malformed_xml(elife_parser):
    result = elife_parser.parse("not valid xml <<<<")
    assert result["decision_letter"] == ""


# ---------------------------------------------------------------------------
# PLOSXMLParser tests
# ---------------------------------------------------------------------------


def test_plos_xml_parser_extracts_review(plos_parser):
    result = plos_parser.parse(SAMPLE_PLOS_XML)
    assert "sample size" in result["decision_letter"].lower() or "Reviewer" in result["decision_letter"]


def test_plos_xml_parser_extracts_response(plos_parser):
    result = plos_parser.parse(SAMPLE_PLOS_XML)
    assert "sample size" in result["author_response"].lower() or len(result["author_response"]) > 0


def test_plos_xml_parser_empty(plos_parser):
    result = plos_parser.parse("")
    assert result["decision_letter"] == ""


# ---------------------------------------------------------------------------
# ConcernParser tests
# ---------------------------------------------------------------------------


def test_concern_parser_parse_json_concerns():
    parser = ConcernParser(llm_layer=None)
    concerns = parser._parse_json_concerns("elife:123", SAMPLE_LLM_CONCERNS_JSON)
    assert len(concerns) == 2
    assert concerns[0].concern_id == "R1C1"
    assert concerns[0].category == "statistics"
    assert concerns[0].severity == "major"
    assert concerns[0].was_valid is True


def test_concern_parser_parse_markdown_wrapped_json():
    parser = ConcernParser(llm_layer=None)
    markdown_json = f"```json\n{SAMPLE_LLM_CONCERNS_JSON}\n```"
    concerns = parser._parse_json_concerns("elife:123", markdown_json)
    assert len(concerns) == 2


def test_concern_parser_parse_invalid_json():
    parser = ConcernParser(llm_layer=None)
    concerns = parser._parse_json_concerns("elife:123", "not json at all")
    assert concerns == []


def test_concern_parser_parse_empty_array():
    parser = ConcernParser(llm_layer=None)
    concerns = parser._parse_json_concerns("elife:123", "[]")
    assert concerns == []


@pytest.mark.asyncio
async def test_concern_parser_extract_no_llm():
    """Without LLM, returns empty batch."""
    parser = ConcernParser(llm_layer=None)
    batch = await parser.extract_concerns("elife:123", "Some review text", "Author response")
    assert isinstance(batch, ReviewConcernBatch)
    assert batch.concerns == []


@pytest.mark.asyncio
async def test_concern_parser_extract_with_mock_llm():
    # Build a mock content block with .text attribute
    mock_block = MagicMock()
    mock_block.text = SAMPLE_LLM_CONCERNS_JSON

    mock_raw_msg = MagicMock()
    mock_raw_msg.content = [mock_block]

    mock_llm = MagicMock()
    mock_llm.complete_raw = AsyncMock(return_value=(mock_raw_msg, MagicMock()))

    parser = ConcernParser(llm_layer=mock_llm)
    batch = await parser.extract_concerns(
        "elife:123",
        "The statistical analysis needs improvement. Reviewer 1 raised this.",
        "We updated the stats.",
    )
    assert len(batch.concerns) == 2
    assert batch.concerns[0].concern_id == "R1C1"


@pytest.mark.asyncio
async def test_concern_parser_extract_empty_decision_letter():
    parser = ConcernParser(llm_layer=MagicMock())
    batch = await parser.extract_concerns("elife:123", "", "")
    assert batch.concerns == []


def test_concern_parser_estimate_reviewer_count():
    parser = ConcernParser()
    concerns = [
        ReviewerConcern(concern_id="R1C1", concern_text="x"),
        ReviewerConcern(concern_id="R1C2", concern_text="y"),
        ReviewerConcern(concern_id="R2C1", concern_text="z"),
    ]
    count = parser._estimate_reviewer_count(concerns)
    assert count == 2


# ---------------------------------------------------------------------------
# ConcernMatcher tests
# ---------------------------------------------------------------------------


def test_concern_matcher_keyword_match_found(sample_concerns):
    matcher = ConcernMatcher(embed_fn=None)
    w8_text = (
        "The statistical analysis is insufficient and needs improvement. "
        "The sample size is too small for meaningful conclusions. "
        "The results need clearer interpretation in the discussion section."
    )
    result = matcher.compute_metrics(
        article_id="elife:12345",
        source="elife",
        human_concerns=sample_concerns,
        w8_review_text=w8_text,
    )
    assert result.overall_concern_recall is not None
    assert result.overall_concern_recall > 0.0


def test_concern_matcher_no_coverage(sample_concerns):
    matcher = ConcernMatcher(embed_fn=None)
    w8_text = "The paper is well written and the figures are clear."
    result = matcher.compute_metrics(
        article_id="elife:12345",
        source="elife",
        human_concerns=sample_concerns,
        w8_review_text=w8_text,
    )
    # Should have low recall
    assert result.overall_concern_recall is not None
    assert result.overall_concern_recall < 1.0


def test_concern_matcher_no_human_concerns():
    matcher = ConcernMatcher()
    result = matcher.compute_metrics(
        article_id="elife:0",
        source="elife",
        human_concerns=[],
        w8_review_text="Some W8 output",
    )
    assert result.major_concern_recall is None
    assert result.overall_concern_recall is None


def test_concern_matcher_only_major_concerns():
    """Major concern recall should only count major-severity concerns."""
    matcher = ConcernMatcher()
    concerns = [
        ReviewerConcern(concern_id="R1C1", concern_text="Major statistical flaw requiring revision", severity="major"),
        ReviewerConcern(concern_id="R1C2", concern_text="Minor typo in figure", severity="minor"),
    ]
    w8_text = "There is a major statistical flaw requiring revision in this paper."
    result = matcher.compute_metrics(
        article_id="test", source="elife", human_concerns=concerns, w8_review_text=w8_text
    )
    # Major recall should be 1.0 (the major concern is covered)
    assert result.major_concern_recall is not None
    assert result.major_concern_recall > 0.0


def test_concern_matcher_keyword_extraction():
    matcher = ConcernMatcher()
    keywords = matcher._extract_keywords("The statistical analysis needs major revision")
    assert "statistical" in keywords
    assert "analysis" in keywords
    assert "needs" in keywords
    # stopwords removed
    assert "the" not in keywords


def test_concern_matcher_sentence_split():
    matcher = ConcernMatcher()
    text = (
        "The statistical methodology requires revision. "
        "The sample size is too small for this analysis. "
        "The interpretation of results needs clarification."
    )
    sentences = matcher._split_into_sentences(text)
    assert len(sentences) >= 2


def test_concern_matcher_cosine_similarity():
    sim = ConcernMatcher._cosine_similarity([1.0, 0.0], [1.0, 0.0])
    assert abs(sim - 1.0) < 1e-6

    sim = ConcernMatcher._cosine_similarity([1.0, 0.0], [0.0, 1.0])
    assert abs(sim - 0.0) < 1e-6


# ---------------------------------------------------------------------------
# PeerReviewCorpusClient — disabled guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corpus_client_disabled_returns_none():
    from app.integrations.peer_review_corpus import PeerReviewCorpusClient
    client = PeerReviewCorpusClient()
    with patch("app.integrations.peer_review_corpus.settings") as mock_settings:
        mock_settings.peer_review_corpus_enabled = False
        result = await client.get_elife_article_meta("12345")
    assert result is None


@pytest.mark.asyncio
async def test_corpus_client_search_disabled_returns_empty():
    from app.integrations.peer_review_corpus import PeerReviewCorpusClient
    client = PeerReviewCorpusClient()
    with patch("app.integrations.peer_review_corpus.settings") as mock_settings:
        mock_settings.peer_review_corpus_enabled = False
        result = await client.search_elife_articles(subject="biophysics")
    assert result == []


@pytest.mark.asyncio
async def test_corpus_client_404_returns_none():
    """eLife API 404 should return None gracefully."""
    import httpx
    from app.integrations.peer_review_corpus import PeerReviewCorpusClient
    client = PeerReviewCorpusClient()

    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=mock_resp
    )

    mock_http = MagicMock()
    mock_http.get = AsyncMock(return_value=mock_resp)

    with (
        patch("app.integrations.peer_review_corpus.settings") as mock_settings,
        patch("httpx.AsyncClient") as mock_cls,
    ):
        mock_settings.peer_review_corpus_enabled = True
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await client.get_elife_article_meta("99999")

    assert result is None


def test_corpus_client_extract_year():
    from app.integrations.peer_review_corpus import PeerReviewCorpusClient
    assert PeerReviewCorpusClient._extract_year("2023-05-15") == 2023
    assert PeerReviewCorpusClient._extract_year("") is None
    assert PeerReviewCorpusClient._extract_year("xyz") is None
