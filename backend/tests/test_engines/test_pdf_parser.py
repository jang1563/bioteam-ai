"""Tests for PDF parser engine."""

from __future__ import annotations

import pytest

from app.engines.pdf.parser import PaperParser, ParsedPaper, ParsedSection


class TestPaperParser:
    """Tests for PaperParser."""

    def setup_method(self):
        self.parser = PaperParser()

    def test_parse_raises_on_empty_bytes(self):
        with pytest.raises(ValueError, match="Empty PDF"):
            self.parser.parse(b"")

    def test_parse_raises_on_invalid_pdf(self):
        with pytest.raises(Exception):
            self.parser.parse(b"not a pdf file")

    def test_parse_file_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            self.parser.parse_file("/nonexistent/path/paper.pdf")

    def test_parse_file_raises_on_non_pdf(self, tmp_path):
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello")
        with pytest.raises(ValueError, match="Unsupported file type"):
            self.parser.parse_file(str(txt_file))


class TestExtractTitle:
    """Tests for title extraction heuristic."""

    def setup_method(self):
        self.parser = PaperParser()

    def test_extracts_simple_title(self):
        text = "Effects of Spaceflight on Gene Expression\n\nJohn Smith, Jane Doe\nUniversity of Space"
        title = self.parser._extract_title(text)
        assert "Effects of Spaceflight" in title

    def test_returns_untitled_for_empty(self):
        title = self.parser._extract_title("")
        assert title == "Untitled Paper"

    def test_stops_at_abstract(self):
        text = "My Paper Title\n\nAbstract\nThis is the abstract."
        title = self.parser._extract_title(text)
        assert "Abstract" not in title
        assert "My Paper Title" in title

    def test_stops_at_email(self):
        text = "My Paper Title\nAuthor Name\nauthor@university.edu"
        title = self.parser._extract_title(text)
        assert "@" not in title


class TestSplitSections:
    """Tests for section splitting."""

    def setup_method(self):
        self.parser = PaperParser()

    def test_splits_standard_sections(self):
        text = (
            "Paper Title\n\n"
            "Abstract\nThis is the abstract text.\n\n"
            "Introduction\nThis introduces the topic.\n\n"
            "Methods\nWe used RNA-seq analysis.\n\n"
            "Results\nWe found significant changes.\n\n"
            "Discussion\nOur findings suggest that.\n\n"
            "References\n1. Smith et al. 2020\n"
        )
        sections = self.parser._split_sections(text)
        headings = [s.heading for s in sections]
        assert "Abstract" in headings
        assert "Introduction" in headings
        assert "Methods" in headings
        assert "Results" in headings
        assert "Discussion" in headings
        assert "References" in headings

    def test_returns_full_text_when_no_headings(self):
        text = "This is just a blob of text with no standard section headings."
        sections = self.parser._split_sections(text)
        assert len(sections) == 1
        assert sections[0].heading == "Full Text"

    def test_handles_numbered_headings(self):
        text = (
            "1. Introduction\nSome intro text.\n\n"
            "2. Methods\nSome methods.\n"
        )
        sections = self.parser._split_sections(text)
        headings = [s.heading for s in sections]
        assert "Introduction" in headings
        assert "Methods" in headings

    def test_extracts_figure_captions(self):
        text = (
            "Results\n"
            "We observed changes.\n"
            "Figure 1: Expression levels of key genes.\n"
            "Table 1: Sample demographics.\n\n"
            "Discussion\nWe discuss the results.\n"
        )
        sections = self.parser._split_sections(text)
        results_section = next(s for s in sections if s.heading == "Results")
        assert len(results_section.figures) >= 1


class TestExtractReferences:
    """Tests for references extraction."""

    def setup_method(self):
        self.parser = PaperParser()

    def test_extracts_references_section(self):
        sections = [
            ParsedSection(heading="Introduction", text="Some intro"),
            ParsedSection(heading="References", text="1. Smith 2020\n2. Doe 2021"),
        ]
        refs = self.parser._extract_references(sections)
        assert "Smith 2020" in refs
        assert "Doe 2021" in refs

    def test_returns_empty_when_no_references(self):
        sections = [
            ParsedSection(heading="Introduction", text="Some intro"),
        ]
        refs = self.parser._extract_references(sections)
        assert refs == ""


class TestParsedPaperDataclass:
    """Tests for dataclass structure."""

    def test_parsed_section_defaults(self):
        section = ParsedSection(heading="Test", text="content")
        assert section.page_range == (0, 0)
        assert section.figures == []

    def test_parsed_paper_structure(self):
        paper = ParsedPaper(
            title="Test Paper",
            sections=[ParsedSection(heading="Abstract", text="test")],
            full_text="test text",
            page_count=5,
        )
        assert paper.title == "Test Paper"
        assert paper.page_count == 5
        assert paper.references_raw == ""
        assert len(paper.sections) == 1
