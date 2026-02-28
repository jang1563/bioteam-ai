"""eLife XML integration for open peer review corpus collection.

Fetches full JATS XML from eLife articles, extracts paper body sections,
decision letter, and author response for W8 benchmarking.

eLife articles with open peer review:
    Full XML: GET https://elifesciences.org/articles/{article_id}.xml
    JSON API:  GET https://api.elifesciences.org/articles/{article_id}

Rate limit: 1 req/sec recommended (no published limit, but be respectful).
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Iterator
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

# JATS namespace used in eLife XMLs
_NS = {
    "jats": "https://jats.nlm.nih.gov/ns/archiving/1.0/",
    "ali": "http://www.niso.org/schemas/ali/1.0/",
    "mml": "http://www.w3.org/1998/Math/MathML",
    "xlink": "http://www.w3.org/1999/xlink",
}

# Section tags we want to keep for W8 analysis
_BODY_SECTION_TYPES = {
    "intro",
    "methods",
    "results",
    "discussion",
    "conclusions",
    "materials|methods",
}


@dataclass
class ELifeSection:
    """A single JATS <sec> element parsed into structured text."""

    section_type: str  # e.g., "intro", "methods", "results"
    title: str
    text: str  # concatenated paragraph text


@dataclass
class ELifeArticle:
    """Structured representation of an eLife article with peer review data."""

    article_id: str
    doi: str = ""
    title: str = ""
    abstract: str = ""
    subjects: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    pub_date: str = ""  # YYYY-MM-DD
    # Full body as plain text (concatenated sections)
    body_text: str = ""
    # Structured sections for targeted analysis
    sections: list[ELifeSection] = field(default_factory=list)
    # Open peer review content
    decision_letter: str = ""
    author_response: str = ""
    # Convenience flags
    has_decision_letter: bool = False
    has_author_response: bool = False
    # Raw XML (optional, not serialized by default)
    _raw_xml: str = field(default="", repr=False, compare=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("_raw_xml", None)
        return d

    def has_peer_review(self) -> bool:
        return self.has_decision_letter

    def to_w8_input(self) -> dict:
        """Format for W8 INGEST step (provides text without PDF)."""
        return {
            "article_id": self.article_id,
            "doi": self.doi,
            "title": self.title,
            "abstract": self.abstract,
            "subjects": self.subjects,
            "authors": self.authors,
            "pub_date": self.pub_date,
            "body_text": self.body_text,
            "sections": [
                {"type": s.section_type, "title": s.title, "text": s.text}
                for s in self.sections
            ],
            "source": "elife_xml",
        }

    def to_ground_truth(self) -> dict:
        """Format for W8 evaluation ground truth."""
        return {
            "article_id": self.article_id,
            "doi": self.doi,
            "title": self.title,
            "subjects": self.subjects,
            "decision_letter": self.decision_letter,
            "author_response": self.author_response,
        }


class ELifeXMLClient:
    """Client for eLife articles with JATS XML parsing and peer review extraction.

    Usage (single article)::

        async with ELifeXMLClient() as client:
            article = await client.fetch_article("83069")
            print(article.title)
            print(article.decision_letter[:500])

    Usage (bulk collection)::

        async with ELifeXMLClient() as client:
            articles = await client.fetch_reviewed_articles(
                subject="immunology",
                max_articles=50,
            )
    """

    XML_BASE = "https://elifesciences.org/articles"
    API_BASE = "https://api.elifesciences.org/articles"
    # eLife article IDs are up to 6 digits; recent ones are ~100000
    RATE_LIMIT_DELAY = 1.0  # seconds between requests

    def __init__(self, timeout: int = 30, rate_limit_delay: float = RATE_LIMIT_DELAY) -> None:
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self._client: httpx.AsyncClient | None = None
        self._last_request_time: float = 0.0

    async def __aenter__(self) -> "ELifeXMLClient":
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": "BioTeam-AI/1.0 (research; contact via GitHub)"},
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _get(self, url: str) -> httpx.Response:
        """Rate-limited GET request."""
        assert self._client is not None, "Use async context manager"
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            import asyncio
            await asyncio.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.monotonic()
        return await self._client.get(url)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_article(
        self,
        article_id: str,
        meta: dict | None = None,
    ) -> ELifeArticle | None:
        """Fetch and parse a single eLife article by its numeric ID.

        Resolves the correct CDN XML URL from the API metadata (to avoid 406
        errors from the legacy elifesciences.org/articles/{id}.xml redirect).

        Args:
            article_id: eLife article numeric ID (string or int).
            meta: Pre-fetched API metadata dict. If None, fetches it now.

        Returns:
            Parsed ELifeArticle, or None if not found / XML unavailable.
        """
        article_id = str(article_id).lstrip("0") or "0"

        # Resolve correct XML URL via API metadata
        if meta is None:
            meta = await self.fetch_article_metadata(article_id)

        # Prefer the versioned CDN URL from the API (avoids legacy redirect 406s)
        xml_url = meta.get("xml") if meta else None
        if not xml_url:
            # Fallback: try the classic URL pattern
            xml_url = f"{self.XML_BASE}/{article_id}.xml"

        try:
            resp = await self._get(xml_url)
        except httpx.HTTPError as e:
            logger.warning("HTTP error fetching %s: %s", xml_url, e)
            return None

        if resp.status_code == 404:
            logger.debug("Article %s not found", article_id)
            return None
        if resp.status_code != 200:
            logger.warning("Unexpected status %d for %s", resp.status_code, xml_url)
            return None

        return _parse_jats_xml(article_id, resp.text)

    async def fetch_article_metadata(self, article_id: str) -> dict:
        """Fetch JSON metadata from eLife API (faster than XML for filtering).

        Returns empty dict on error.
        """
        url = f"{self.API_BASE}/{article_id}"
        try:
            resp = await self._get(url)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.debug("Metadata fetch failed for %s: %s", article_id, e)
        return {}

    async def fetch_article_list_page(
        self,
        page: int = 1,
        per_page: int = 100,
        subject: str | None = None,
        order: str = "desc",
    ) -> tuple[list[str], int]:
        """Fetch a page of article IDs from the eLife API list endpoint.

        Returns (article_ids, total_count).
        Uses GET /articles?page=N&per-page=M&order=desc&type=research-article
        """
        params = f"page={page}&per-page={per_page}&order={order}&type[]=research-article&type[]=short-report&type[]=research-advance"
        if subject:
            params += f"&subject[]={subject}"
        url = f"{self.API_BASE}?{params}"

        try:
            resp = await self._get(url)
            if resp.status_code != 200:
                logger.warning("List API returned %d for page %d", resp.status_code, page)
                return [], 0
            data = resp.json()
            items = data.get("items", [])
            total = data.get("total", 0)
            ids = [str(item["id"]) for item in items if "id" in item]
            return ids, total
        except Exception as e:
            logger.warning("List API error on page %d: %s", page, e)
            return [], 0

    async def fetch_reviewed_articles(
        self,
        subject: str | None = None,
        max_articles: int = 50,
        start_id: int = 1,
        end_id: int = 110000,
        require_author_response: bool = False,
    ) -> list[ELifeArticle]:
        """Bulk-collect eLife articles that have decision letters.

        Uses the eLife API paginated list endpoint (efficient — no sequential
        ID scanning). Fetches pages of 100 article IDs, then downloads XML only
        for qualifying articles.

        Args:
            subject: Filter by subject area (e.g., "immunology-inflammation").
            max_articles: Stop after this many qualifying articles.
            start_id: Minimum article ID filter (applied after fetching).
            end_id: Maximum article ID filter (applied after fetching).
            require_author_response: Also require author response text.

        Returns:
            List of ELifeArticle with decision letters (and optionally author responses).
        """
        results: list[ELifeArticle] = []
        page = 1
        per_page = 100

        logger.info(
            "Fetching eLife articles via API list (subject=%s, target=%d)",
            subject or "all",
            max_articles,
        )

        while len(results) < max_articles:
            ids, total = await self.fetch_article_list_page(
                page=page, per_page=per_page, subject=subject
            )

            if not ids:
                logger.info("No more articles on page %d (total=%d)", page, total)
                break

            logger.info("Page %d: got %d article IDs (total available: %d)", page, len(ids), total)

            for article_id in ids:
                if len(results) >= max_articles:
                    break

                # Apply ID range filter if specified
                try:
                    id_int = int(article_id)
                    if id_int < start_id or id_int > end_id:
                        continue
                except ValueError:
                    pass

                # Fast pre-filter via JSON API: check for decision letter presence
                # and get the correct CDN XML URL in one call.
                meta = await self.fetch_article_metadata(article_id)
                if not meta:
                    continue

                # Re-check article type (list endpoint may include mixed types)
                if meta.get("type", "") not in ("research-article", "short-report", "research-advance"):
                    continue

                # Skip if API indicates no decision letter exists
                if "decisionLetter" not in meta:
                    continue
                if require_author_response and "authorResponse" not in meta:
                    continue

                # Subject filter (re-check from metadata if specified)
                if subject:
                    meta_subjects = [s.get("id", "").lower() for s in meta.get("subjects", [])]
                    if not any(subject.lower() in s for s in meta_subjects):
                        continue

                # Fetch full XML — pass meta so fetch_article uses the correct CDN URL
                article = await self.fetch_article(article_id, meta=meta)
                if article is None:
                    continue

                if not article.has_decision_letter:
                    continue
                if require_author_response and not article.has_author_response:
                    continue

                results.append(article)
                logger.info(
                    "[%d/%d] Collected: %s — %s (DL: %d chars, AR: %d chars)",
                    len(results),
                    max_articles,
                    article_id,
                    article.title[:60],
                    len(article.decision_letter),
                    len(article.author_response),
                )

            # Check if we've exhausted all available pages
            if page * per_page >= total:
                logger.info("Exhausted all %d available articles after page %d", total, page)
                break

            page += 1

        logger.info("Collected %d reviewed eLife articles", len(results))
        return results

    async def fetch_articles_by_ids(self, article_ids: list[str]) -> list[ELifeArticle]:
        """Fetch specific articles by their IDs.

        Used when you already have a curated list of article IDs.
        """
        results: list[ELifeArticle] = []
        for article_id in article_ids:
            article = await self.fetch_article(article_id)
            if article is not None:
                results.append(article)
                logger.debug(
                    "Fetched %s: DL=%s AR=%s",
                    article_id,
                    article.has_decision_letter,
                    article.has_author_response,
                )
        return results


# ------------------------------------------------------------------
# JATS XML parser (stateless functions)
# ------------------------------------------------------------------

def _iter_text(element: ET.Element) -> Iterator[str]:
    """Yield all text content from an element and its descendants."""
    if element.text:
        yield element.text.strip()
    for child in element:
        yield from _iter_text(child)
        if child.tail:
            yield child.tail.strip()


def _element_text(element: ET.Element, sep: str = " ") -> str:
    """Get concatenated text from element, collapsing whitespace."""
    parts = [t for t in _iter_text(element) if t]
    return sep.join(parts).strip()


def _parse_section(sec: ET.Element) -> ELifeSection:
    """Parse a JATS <sec> element into an ELifeSection."""
    sec_type = sec.get("sec-type", "").lower()
    # Try to classify by sec-type attribute
    for key in _BODY_SECTION_TYPES:
        if key in sec_type:
            break
    else:
        sec_type = sec_type or "other"

    # Get title from first <title> child
    title_el = sec.find("title")
    title = _element_text(title_el) if title_el is not None else ""

    # Gather paragraph text
    paragraphs: list[str] = []
    for p in sec.iter("p"):
        text = _element_text(p)
        if text:
            paragraphs.append(text)

    return ELifeSection(
        section_type=sec_type,
        title=title,
        text="\n\n".join(paragraphs),
    )


def _parse_jats_xml(article_id: str, xml_text: str) -> ELifeArticle | None:
    """Parse JATS XML string into an ELifeArticle.

    eLife JATS structure:
        <article>
          <front>
            <article-meta>
              <title-group><article-title>...</article-title></title-group>
              <abstract>...</abstract>
              <pub-date>...</pub-date>
              <subj-group>...</subj-group>
              <contrib-group>...</contrib-group>
            </article-meta>
          </front>
          <body>
            <sec sec-type="intro">...</sec>
            <sec sec-type="methods">...</sec>
            ...
          </body>
          <sub-article article-type="decision-letter">
            <body>...</body>
          </sub-article>
          <sub-article article-type="reply">
            <body>...</body>
          </sub-article>
        </article>
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning("XML parse error for article %s: %s", article_id, e)
        return None

    article = ELifeArticle(article_id=article_id, _raw_xml=xml_text)

    # --- DOI ---
    for article_id_el in root.iter("article-id"):
        if article_id_el.get("pub-id-type") == "doi":
            article.doi = (article_id_el.text or "").strip()
            break

    # --- Title ---
    title_el = root.find(".//article-title")
    if title_el is not None:
        article.title = _element_text(title_el)

    # --- Abstract ---
    abstract_el = root.find(".//abstract")
    if abstract_el is not None:
        article.abstract = _element_text(abstract_el)

    # --- Publication date ---
    for pub_date in root.iter("pub-date"):
        if pub_date.get("pub-type") in ("epub", "pub", "collection", None):
            year = getattr(pub_date.find("year"), "text", "") or ""
            month = getattr(pub_date.find("month"), "text", "01") or "01"
            day = getattr(pub_date.find("day"), "text", "01") or "01"
            if year:
                article.pub_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                break

    # --- Subjects ---
    for subj_group in root.iter("subj-group"):
        if subj_group.get("subj-group-type") in ("heading", "display-channel", None):
            for subj in subj_group.iter("subject"):
                text = (subj.text or "").strip()
                if text:
                    article.subjects.append(text)

    # --- Authors ---
    for contrib in root.iter("contrib"):
        if contrib.get("contrib-type") == "author":
            surname = getattr(contrib.find(".//surname"), "text", "") or ""
            given = getattr(contrib.find(".//given-names"), "text", "") or ""
            name = f"{given} {surname}".strip()
            if name:
                article.authors.append(name)

    # --- Body sections ---
    body = root.find("body")
    if body is not None:
        sections: list[ELifeSection] = []
        all_body_text: list[str] = []

        for sec in body:
            if sec.tag == "sec":
                parsed_sec = _parse_section(sec)
                sections.append(parsed_sec)
                if parsed_sec.text:
                    all_body_text.append(f"## {parsed_sec.title}\n{parsed_sec.text}")

        article.sections = sections
        article.body_text = "\n\n".join(all_body_text)

    # --- Sub-articles (decision letter + author reply) ---
    for sub_article in root.findall("sub-article"):
        sub_type = sub_article.get("article-type", "")

        sub_body = sub_article.find("body")
        if sub_body is None:
            continue

        # Collect all paragraph text from sub-article body
        paragraphs: list[str] = []
        for p in sub_body.iter("p"):
            text = _element_text(p)
            if text:
                paragraphs.append(text)

        text_content = "\n\n".join(paragraphs)

        if sub_type == "decision-letter":
            article.decision_letter = text_content
            article.has_decision_letter = bool(text_content.strip())
        elif sub_type == "reply":
            article.author_response = text_content
            article.has_author_response = bool(text_content.strip())

    return article


# ------------------------------------------------------------------
# Convenience sync wrapper for scripts
# ------------------------------------------------------------------

def fetch_article_sync(article_id: str, timeout: int = 30) -> ELifeArticle | None:
    """Synchronous wrapper for single-article fetch (for scripts/tests)."""
    import asyncio

    async def _run():
        async with ELifeXMLClient(timeout=timeout) as client:
            return await client.fetch_article(article_id)

    return asyncio.run(_run())
