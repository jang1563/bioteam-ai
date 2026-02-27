"""Paper Parser — extract structured sections from scientific papers.

Supports PDF (via PyMuPDF/fitz) and DOCX (via python-docx).
Splits into sections based on common scientific paper heading patterns.
No LLM calls — purely deterministic.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Common scientific paper section headings (case-insensitive)
_HEADING_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\s*(?:\d+\.?\s+)?(Abstract)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*(?:\d+\.?\s+)?(Introduction)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*(?:\d+\.?\s+)?(Background)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*(?:\d+\.?\s+)?(Materials?\s+and\s+Methods?|Methods?|Experimental\s+(?:Section|Procedures?))\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*(?:\d+\.?\s+)?(Results?)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*(?:\d+\.?\s+)?(Results?\s+and\s+Discussion)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*(?:\d+\.?\s+)?(Discussion)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*(?:\d+\.?\s+)?(Conclusion|Conclusions|Concluding\s+Remarks?)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*(?:\d+\.?\s+)?(Supplementar[yi]\s+(?:Materials?|Information|Data))\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*(?:\d+\.?\s+)?(Acknowledgm?ents?)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*(?:\d+\.?\s+)?(References?|Bibliography|Literature\s+Cited)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*(?:\d+\.?\s+)?(Author\s+Contributions?|Data\s+Availability)\s*$", re.IGNORECASE | re.MULTILINE),
]

# Figure/table caption patterns
_FIGURE_CAPTION_RE = re.compile(
    r"^((?:Fig(?:ure)?|Table|Supplementar[yi]\s+(?:Fig(?:ure)?|Table))\s*\.?\s*\d+[.:]\s*.+)$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class ParsedSection:
    """A single section of a parsed scientific paper."""

    heading: str
    text: str
    page_range: tuple[int, int] = (0, 0)
    figures: list[str] = field(default_factory=list)


@dataclass
class ParsedPaper:
    """Complete parsed paper with sections."""

    title: str
    sections: list[ParsedSection]
    full_text: str
    page_count: int
    references_raw: str = ""


class PaperParser:
    """Extract structured sections from scientific papers (PDF or DOCX)."""

    def parse(self, pdf_bytes: bytes) -> ParsedPaper:
        """Parse a PDF into structured sections.

        Args:
            pdf_bytes: Raw PDF file content.

        Returns:
            ParsedPaper with extracted sections.

        Raises:
            ValueError: If pdf_bytes is empty or not valid PDF.
            ImportError: If PyMuPDF is not installed.
        """
        if not pdf_bytes:
            raise ValueError("Empty PDF bytes provided")

        full_text, page_count, page_texts = self._extract_text(pdf_bytes)
        if not full_text.strip():
            raise ValueError("No text extracted from PDF — possibly image-only")

        title = self._extract_title(page_texts[0] if page_texts else full_text[:500])
        sections = self._split_sections(full_text)
        references_raw = self._extract_references(sections)

        return ParsedPaper(
            title=title,
            sections=sections,
            full_text=full_text,
            page_count=page_count,
            references_raw=references_raw,
        )

    def parse_file(self, file_path: str | Path) -> ParsedPaper:
        """Parse a PDF or DOCX file from disk.

        Args:
            file_path: Path to the PDF or DOCX file.

        Returns:
            ParsedPaper with extracted sections.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self.parse(path.read_bytes())
        elif suffix in (".docx", ".doc"):
            return self.parse_docx(path)
        else:
            raise ValueError(f"Unsupported file type: {suffix} (expected .pdf or .docx)")

    def parse_docx(self, docx_path: str | Path) -> ParsedPaper:
        """Parse a DOCX file into structured sections.

        Uses python-docx to extract paragraph text with style-based
        heading detection for better section splitting than raw text.

        Args:
            docx_path: Path to the DOCX file.

        Returns:
            ParsedPaper with extracted sections.
        """
        full_text, heading_paragraphs = self._extract_text_docx(docx_path)
        if not full_text.strip():
            raise ValueError("No text extracted from DOCX")

        # Use heading_paragraphs for section splitting if available
        if heading_paragraphs:
            sections = self._split_sections_from_headings(full_text, heading_paragraphs)
        else:
            sections = self._split_sections(full_text)

        title = self._extract_title(full_text[:1000])
        references_raw = self._extract_references(sections)

        return ParsedPaper(
            title=title,
            sections=sections,
            full_text=full_text,
            page_count=0,  # DOCX doesn't have fixed page count
            references_raw=references_raw,
        )

    def _extract_text(self, pdf_bytes: bytes) -> tuple[str, int, list[str]]:
        """Extract text from all pages.

        Returns:
            Tuple of (full_text, page_count, per_page_texts).
        """
        import fitz  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_texts: list[str] = []
        for page in doc:
            page_texts.append(page.get_text("text"))
        doc.close()

        full_text = "\n\n".join(page_texts)
        return full_text, len(page_texts), page_texts

    def _extract_title(self, first_page_text: str) -> str:
        """Extract paper title from first page text.

        Heuristic: title is typically the first non-empty line(s) before
        the author block. We take lines before common patterns like
        author affiliations or 'Abstract'.
        """
        lines = first_page_text.strip().split("\n")
        title_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if title_lines:
                    break
                continue
            # Stop at common non-title patterns
            lower = stripped.lower()
            if any(kw in lower for kw in ["abstract", "@", "university", "department", "institute", "corresponding"]):
                break
            # Stop at very short lines (likely headers/footers)
            if len(stripped) < 5 and title_lines:
                break
            title_lines.append(stripped)
            # Titles rarely exceed 3 lines
            if len(title_lines) >= 3:
                break

        title = " ".join(title_lines).strip()
        return title if title else "Untitled Paper"

    def _split_sections(self, full_text: str) -> list[ParsedSection]:
        """Split full text into sections by heading patterns."""
        # Find all heading positions
        headings: list[tuple[int, str]] = []
        for pattern in _HEADING_PATTERNS:
            for match in pattern.finditer(full_text):
                heading_text = match.group(1).strip()
                headings.append((match.start(), heading_text))

        # Sort by position
        headings.sort(key=lambda x: x[0])

        if not headings:
            # No headings found — return entire text as single section
            figures = _FIGURE_CAPTION_RE.findall(full_text)
            return [ParsedSection(
                heading="Full Text",
                text=full_text.strip(),
                figures=figures,
            )]

        sections: list[ParsedSection] = []

        # Text before first heading (title block, author info)
        pre_heading_text = full_text[: headings[0][0]].strip()
        if pre_heading_text:
            sections.append(ParsedSection(
                heading="Preamble",
                text=pre_heading_text,
            ))

        # Each heading to next heading
        for i, (pos, heading) in enumerate(headings):
            if i + 1 < len(headings):
                next_pos = headings[i + 1][0]
            else:
                next_pos = len(full_text)

            section_text = full_text[pos:next_pos]
            # Remove the heading line itself from the text
            lines = section_text.split("\n", 1)
            body = lines[1].strip() if len(lines) > 1 else ""

            figures = _FIGURE_CAPTION_RE.findall(body)
            sections.append(ParsedSection(
                heading=heading,
                text=body,
                figures=figures,
            ))

        return sections

    def _extract_references(self, sections: list[ParsedSection]) -> str:
        """Extract the references section text."""
        for section in sections:
            lower = section.heading.lower()
            if lower in ("references", "bibliography", "literature cited"):
                return section.text
        return ""

    def _extract_text_docx(self, docx_path: str | Path) -> tuple[str, list[tuple[int, str]]]:
        """Extract text and heading positions from a DOCX file.

        Returns:
            Tuple of (full_text, list of (char_offset, heading_text)).
        """
        from docx import Document

        doc = Document(str(docx_path))
        text_parts: list[str] = []
        heading_paragraphs: list[tuple[int, str]] = []
        current_offset = 0

        for para in doc.paragraphs:
            para_text = para.text.strip()
            if not para_text:
                text_parts.append("")
                current_offset += 1  # newline
                continue

            # Detect headings by Word style
            style_name = (para.style.name or "").lower() if para.style else ""
            is_heading = "heading" in style_name and "toc" not in style_name

            # Also check if text matches our heading patterns
            if not is_heading:
                for pattern in _HEADING_PATTERNS:
                    if pattern.match(para_text):
                        is_heading = True
                        break

            # Filter out false headings: body text with heading styles
            # Real section headings are short (< 150 chars)
            if is_heading and len(para_text) > 150:
                is_heading = False

            if is_heading:
                heading_paragraphs.append((current_offset, para_text))

            text_parts.append(para_text)
            current_offset += len(para_text) + 1  # +1 for newline

        full_text = "\n".join(text_parts)
        return full_text, heading_paragraphs

    def _split_sections_from_headings(
        self, full_text: str, headings: list[tuple[int, str]]
    ) -> list[ParsedSection]:
        """Split text using pre-identified heading positions (from DOCX styles)."""
        if not headings:
            return self._split_sections(full_text)

        sections: list[ParsedSection] = []

        # Text before first heading
        pre_heading_text = full_text[: headings[0][0]].strip()
        if pre_heading_text:
            sections.append(ParsedSection(heading="Preamble", text=pre_heading_text))

        for i, (pos, heading_text) in enumerate(headings):
            if i + 1 < len(headings):
                next_pos = headings[i + 1][0]
            else:
                next_pos = len(full_text)

            body = full_text[pos + len(heading_text):next_pos].strip()
            figures = _FIGURE_CAPTION_RE.findall(body)
            sections.append(ParsedSection(
                heading=heading_text,
                text=body,
                figures=figures,
            ))

        return sections
