"""Tests for eLife XML client and JATS parser.

Tests the XML parsing logic with a minimal JATS fixture — no network calls.
Network integration tests are marked with @pytest.mark.integration.
"""

from __future__ import annotations

import pytest
from app.integrations.elife_xml import (
    ELifeXMLClient,
    _parse_jats_xml,
)

# ---------------------------------------------------------------------------
# Minimal JATS XML fixture (based on eLife actual structure)
# ---------------------------------------------------------------------------

_JATS_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <article-meta>
      <article-id pub-id-type="doi">10.7554/eLife.83069</article-id>
      <title-group>
        <article-title>GAS6 promotes macrophage efferocytosis in osteoarthritis</article-title>
      </title-group>
      <abstract>
        <p>We investigated the role of GAS6 in macrophage efferocytosis in osteoarthritis.</p>
        <p>GAS6 expression was reduced in osteoarthritic synovium.</p>
      </abstract>
      <pub-date pub-type="epub">
        <year>2023</year>
        <month>04</month>
        <day>15</day>
      </pub-date>
      <subj-group subj-group-type="heading">
        <subject>Immunology and Inflammation</subject>
      </subj-group>
      <contrib-group>
        <contrib contrib-type="author">
          <name>
            <surname>Smith</surname>
            <given-names>John A</given-names>
          </name>
        </contrib>
        <contrib contrib-type="author">
          <name>
            <surname>Doe</surname>
            <given-names>Jane B</given-names>
          </name>
        </contrib>
      </contrib-group>
    </article-meta>
  </front>
  <body>
    <sec sec-type="intro">
      <title>Introduction</title>
      <p>Osteoarthritis (OA) is a degenerative joint disease.</p>
      <p>Efferocytosis is the clearance of apoptotic cells by macrophages.</p>
    </sec>
    <sec sec-type="methods">
      <title>Materials and Methods</title>
      <p>C57BL/6 mice were fed a standard diet.</p>
      <p>ApoE-/- mice were fed a high-fat diet.</p>
    </sec>
    <sec sec-type="results">
      <title>Results</title>
      <p>GAS6 expression was significantly decreased in OA synovium (p&lt;0.01).</p>
    </sec>
  </body>
  <sub-article article-type="decision-letter">
    <body>
      <p>The reviewers found the study interesting but raised concerns.</p>
      <p>Major concern 1: The experimental groups are confounded by genotype and diet.</p>
      <p>Major concern 2: Figure 3C shows GAS6 increased, not decreased as claimed.</p>
    </body>
  </sub-article>
  <sub-article article-type="reply">
    <body>
      <p>We thank the reviewers for their thoughtful comments.</p>
      <p>Regarding concern 1: We acknowledge the confound and have added additional controls.</p>
    </body>
  </sub-article>
</article>
"""

_JATS_NO_DL = """<?xml version="1.0" encoding="UTF-8"?>
<article>
  <front>
    <article-meta>
      <article-id pub-id-type="doi">10.7554/eLife.99999</article-id>
      <title-group>
        <article-title>A paper without decision letter</article-title>
      </title-group>
    </article-meta>
  </front>
  <body>
    <sec sec-type="intro">
      <title>Introduction</title>
      <p>Some text.</p>
    </sec>
  </body>
</article>
"""

_JATS_MALFORMED = "this is not XML <<< broken"


# ---------------------------------------------------------------------------
# Parser tests (no network)
# ---------------------------------------------------------------------------


class TestJATSParser:
    def test_parses_doi(self):
        article = _parse_jats_xml("83069", _JATS_FIXTURE)
        assert article is not None
        assert article.doi == "10.7554/eLife.83069"

    def test_parses_title(self):
        article = _parse_jats_xml("83069", _JATS_FIXTURE)
        assert article is not None
        assert "GAS6" in article.title
        assert "efferocytosis" in article.title

    def test_parses_abstract(self):
        article = _parse_jats_xml("83069", _JATS_FIXTURE)
        assert article is not None
        assert "GAS6" in article.abstract
        assert len(article.abstract) > 20

    def test_parses_pub_date(self):
        article = _parse_jats_xml("83069", _JATS_FIXTURE)
        assert article is not None
        assert article.pub_date == "2023-04-15"

    def test_parses_subjects(self):
        article = _parse_jats_xml("83069", _JATS_FIXTURE)
        assert article is not None
        assert any("immunology" in s.lower() or "inflammation" in s.lower() for s in article.subjects)

    def test_parses_authors(self):
        article = _parse_jats_xml("83069", _JATS_FIXTURE)
        assert article is not None
        assert len(article.authors) == 2
        assert "John A Smith" in article.authors
        assert "Jane B Doe" in article.authors

    def test_parses_body_sections(self):
        article = _parse_jats_xml("83069", _JATS_FIXTURE)
        assert article is not None
        assert len(article.sections) == 3
        types = [s.section_type for s in article.sections]
        assert "intro" in types
        assert "methods" in types
        assert "results" in types

    def test_section_text_content(self):
        article = _parse_jats_xml("83069", _JATS_FIXTURE)
        assert article is not None
        intro_sec = next(s for s in article.sections if s.section_type == "intro")
        assert "Osteoarthritis" in intro_sec.text
        assert "Efferocytosis" in intro_sec.text

    def test_body_text_concatenation(self):
        article = _parse_jats_xml("83069", _JATS_FIXTURE)
        assert article is not None
        assert "Introduction" in article.body_text
        assert "Materials and Methods" in article.body_text
        assert "ApoE" in article.body_text

    def test_parses_decision_letter(self):
        article = _parse_jats_xml("83069", _JATS_FIXTURE)
        assert article is not None
        assert article.has_decision_letter is True
        assert "Major concern 1" in article.decision_letter
        assert "confounded by genotype" in article.decision_letter

    def test_parses_author_response(self):
        article = _parse_jats_xml("83069", _JATS_FIXTURE)
        assert article is not None
        assert article.has_author_response is True
        assert "thank the reviewers" in article.author_response

    def test_decision_letter_multi_paragraph(self):
        article = _parse_jats_xml("83069", _JATS_FIXTURE)
        assert article is not None
        # Both concerns should be in the text
        assert "Major concern 1" in article.decision_letter
        assert "Major concern 2" in article.decision_letter

    def test_no_decision_letter(self):
        article = _parse_jats_xml("99999", _JATS_NO_DL)
        assert article is not None
        assert article.has_decision_letter is False
        assert article.decision_letter == ""
        assert article.has_author_response is False

    def test_malformed_xml_returns_none(self):
        article = _parse_jats_xml("99999", _JATS_MALFORMED)
        assert article is None

    def test_has_peer_review_flag(self):
        article = _parse_jats_xml("83069", _JATS_FIXTURE)
        assert article is not None
        assert article.has_peer_review() is True

        no_dl = _parse_jats_xml("99999", _JATS_NO_DL)
        assert no_dl is not None
        assert no_dl.has_peer_review() is False


class TestELifeArticleConversions:
    def test_to_dict_excludes_raw_xml(self):
        article = _parse_jats_xml("83069", _JATS_FIXTURE)
        assert article is not None
        d = article.to_dict()
        assert "_raw_xml" not in d
        assert "title" in d
        assert "decision_letter" in d

    def test_to_w8_input_structure(self):
        article = _parse_jats_xml("83069", _JATS_FIXTURE)
        assert article is not None
        w8_input = article.to_w8_input()
        assert w8_input["source"] == "elife_xml"
        assert "body_text" in w8_input
        assert "sections" in w8_input
        # Sections should be list of dicts with type/title/text
        assert isinstance(w8_input["sections"], list)
        assert all("type" in s for s in w8_input["sections"])

    def test_to_ground_truth_structure(self):
        article = _parse_jats_xml("83069", _JATS_FIXTURE)
        assert article is not None
        gt = article.to_ground_truth()
        assert "decision_letter" in gt
        assert "author_response" in gt
        assert "article_id" in gt
        assert "_raw_xml" not in gt


class TestELifeXMLClientUnit:
    """Unit tests for ELifeXMLClient (no network calls)."""

    def test_client_instantiation(self):
        client = ELifeXMLClient(timeout=15, rate_limit_delay=0.5)
        assert client.timeout == 15
        assert client.rate_limit_delay == 0.5

    def test_xml_url_format(self):
        """Verify the URL format used to fetch articles."""
        client = ELifeXMLClient()
        article_id = "83069"
        expected = f"https://elifesciences.org/articles/{article_id}.xml"
        assert f"{client.XML_BASE}/{article_id}.xml" == expected

    def test_api_url_format(self):
        client = ELifeXMLClient()
        article_id = "83069"
        expected = f"https://api.elifesciences.org/articles/{article_id}"
        assert f"{client.API_BASE}/{article_id}" == expected


# ---------------------------------------------------------------------------
# Integration test (marked — only runs with network access)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_real_article_83069():
    """Fetch actual eLife article 83069 and verify peer review data."""
    async with ELifeXMLClient(rate_limit_delay=1.0) as client:
        article = await client.fetch_article("83069")

    assert article is not None, "Failed to fetch article 83069"
    assert article.article_id == "83069"
    assert article.doi.startswith("10.7554/eLife")
    assert len(article.title) > 10
    assert article.has_decision_letter, "Article 83069 should have a decision letter"
    assert len(article.decision_letter) > 200
    assert len(article.sections) >= 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_nonexistent_article():
    """Fetching a non-existent article ID returns None."""
    async with ELifeXMLClient() as client:
        # Use a very large ID unlikely to exist
        result = await client.fetch_article("9999999")

    assert result is None
