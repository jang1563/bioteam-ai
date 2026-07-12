"""JATS XML parser for eLife decision letters and author responses.

eLife's decision letter XML structure:
  <article>
    <front>...</front>
    <body>
      <sec sec-type="decision-letter">...</sec>
      <sec sec-type="author-comment">...</sec>
    </body>
  </article>

Extracts plain text from these sections without requiring full PDF parsing.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


class ELifeXMLParser:
    """Parse eLife decision letter XML into structured text sections."""

    # JATS namespaces used in eLife XML
    _NS = {
        "jats": "http://jats.nlm.nih.gov",
        "mml": "http://www.w3.org/1998/Math/MathML",
        "xlink": "http://www.w3.org/1999/xlink",
    }

    def parse(self, xml_text: str) -> dict[str, str]:
        """Parse eLife decision letter XML.

        Returns:
            dict with keys: decision_letter, author_response, editorial_decision
        """
        result = {
            "decision_letter": "",
            "author_response": "",
            "editorial_decision": "",
        }
        if not xml_text or not xml_text.strip():
            return result

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning("eLife XML parse error: %s", e)
            return result

        # Try JATS sec-type based extraction first
        # Use wildcard namespace to handle both plain and JATS-namespaced tags
        body_elem = root.find(".//{*}body")
        search_root = body_elem if body_elem is not None else root

        for sec in search_root.iter():
            if sec.tag.endswith("sec"):
                sec_type = sec.get("sec-type", "")
                text = self._extract_text(sec)
                if sec_type in ("decision-letter", "decision_letter"):
                    result["decision_letter"] = text
                elif sec_type in ("author-comment", "author_comment", "author-response", "author_response"):
                    result["author_response"] = text

        # Fallback: look for boxed-text or sub-article elements
        if not result["decision_letter"]:
            for elem in root.iter():
                if elem.tag.endswith("sub-article"):
                    article_type = elem.get("article-type", "")
                    text = self._extract_text(elem)
                    if "decision" in article_type.lower():
                        result["decision_letter"] = text
                    elif "reply" in article_type.lower() or "response" in article_type.lower():
                        result["author_response"] = text

        # Infer editorial decision from decision letter text
        result["editorial_decision"] = self._infer_decision(result["decision_letter"])

        return result

    def _extract_text(self, element: ET.Element) -> str:
        """Recursively extract all text content from an XML element."""
        parts: list[str] = []
        for node in element.iter():
            if node.text and node.text.strip():
                parts.append(node.text.strip())
            if node.tail and node.tail.strip():
                parts.append(node.tail.strip())
        text = " ".join(parts)
        # Collapse multiple spaces/newlines
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _infer_decision(self, decision_text: str) -> str:
        """Infer editorial decision from decision letter text."""
        if not decision_text:
            return ""
        text_lower = decision_text.lower()

        # Order matters — check most specific first
        if "accept" in text_lower and "major" not in text_lower[:200]:
            return "accept"
        if "major revision" in text_lower or "major revisions" in text_lower:
            return "major_revision"
        if "minor revision" in text_lower or "minor revisions" in text_lower:
            return "minor_revision"
        if "reject" in text_lower:
            return "reject"
        if "accept" in text_lower:
            return "accept"
        return "unknown"


class PLOSXMLParser(ELifeXMLParser):
    """Parse PLOS JATS XML which embeds peer review in <sec sec-type="peer-review">."""

    def parse(self, xml_text: str) -> dict[str, str]:
        result = {
            "decision_letter": "",
            "author_response": "",
            "editorial_decision": "",
        }
        if not xml_text or not xml_text.strip():
            return result

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning("PLOS XML parse error: %s", e)
            return result

        for sec in root.iter():
            if not sec.tag.endswith("sec"):
                continue
            sec_type = sec.get("sec-type", "").lower()
            text = self._extract_text(sec)
            if "peer-review" in sec_type or "reviewer" in sec_type:
                result["decision_letter"] += " " + text
            elif "author-response" in sec_type or "rebuttal" in sec_type:
                result["author_response"] += " " + text

        result["decision_letter"] = result["decision_letter"].strip()
        result["author_response"] = result["author_response"].strip()
        result["editorial_decision"] = self._infer_decision(result["decision_letter"])
        return result
