"""Tests for magazine-style email template rendering."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from datetime import datetime, timezone

from app.email.templates.digest_report import render_digest_email
from app.models.digest import DigestEntry, DigestReport, TopicProfile


def _make_report() -> DigestReport:
    return DigestReport(
        topic_id="t1",
        period_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        period_end=datetime(2024, 1, 7, tzinfo=timezone.utc),
        entry_count=5,
        summary="Notable advances in AI+Biology this week.",
        highlights=[
            {
                "title": "AlphaFold3 Release",
                "source": "github",
                "one_liner": "Open-source structure prediction",
                "why_important": "Enables drug discovery at scale",
                "url": "https://github.com/google-deepmind/alphafold3",
            },
            {
                "title": "CellFM Paper",
                "source": "biorxiv",
                "one_liner": "100M cell foundation model",
                "why_important": "",
                "url": "",
            },
        ],
        source_breakdown={"arxiv": 3, "pubmed": 2, "github": 1},
        cost=0.008,
    )


def _make_topic() -> TopicProfile:
    return TopicProfile(
        name="AI Biology",
        queries=["AI biology"],
        sources=["arxiv", "pubmed", "github"],
    )


def _make_entries() -> list[DigestEntry]:
    return [
        DigestEntry(
            topic_id="t1",
            source="arxiv",
            external_id="2412.06993",
            title="AI-Driven Digital Organism",
            authors=["Le Song", "Jane Doe", "Bob Smith", "Alice Lee"],
            abstract="Multiscale foundation models for digital organisms in biology.",
            url="https://arxiv.org/abs/2412.06993",
            relevance_score=0.94,
            published_at="2024-12-09",
        ),
        DigestEntry(
            topic_id="t1",
            source="pubmed",
            external_id="39858535",
            title="PPI Prediction",
            authors=["Kiouri DP"],
            abstract="Structure-based approaches.",
            url="https://pubmed.ncbi.nlm.nih.gov/39858535/",
            relevance_score=0.92,
        ),
    ]


class TestRenderDigestEmail:
    def test_contains_summary(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "Notable advances in AI+Biology" in html

    def test_contains_highlights(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "AlphaFold3 Release" in html
        assert "CellFM Paper" in html

    def test_contains_source_breakdown(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "arxiv" in html
        assert "pubmed" in html

    def test_contains_top_entries(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "AI-Driven Digital Organism" in html
        assert "PPI Prediction" in html

    def test_html_structure_valid(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert "BIOTEAM-AI" in html

    def test_contains_topic_name(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "AI Biology" in html

    def test_contains_cost(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "0.008" in html

    def test_contains_entry_links(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "https://arxiv.org/abs/2412.06993" in html

    def test_empty_entries(self):
        html = render_digest_email(_make_report(), _make_topic(), [])
        assert "BIOTEAM-AI" in html

    def test_no_summary(self):
        report = _make_report()
        report.summary = ""
        html = render_digest_email(report, _make_topic(), _make_entries())
        assert "No summary available" in html

    def test_trending_keywords_shown(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "TRENDING" in html

    def test_dashboard_cta_present(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "Explore Full Report" in html

    def test_xss_escaped_in_title(self):
        entries = _make_entries()
        entries[0].title = '<script>alert("xss")</script>'
        html = render_digest_email(_make_report(), _make_topic(), entries)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    # --- Accent color tests ---

    def test_topic_accent_blue(self):
        topic = TopicProfile(name="AI in Science", queries=["test"], sources=["arxiv"])
        html = render_digest_email(_make_report(), topic, _make_entries())
        assert "#2563eb" in html  # Blue primary

    def test_topic_accent_green(self):
        topic = TopicProfile(name="AI biology and medicine", queries=["test"], sources=["arxiv"])
        html = render_digest_email(_make_report(), topic, _make_entries())
        assert "#059669" in html  # Green primary

    def test_topic_accent_violet(self):
        topic = TopicProfile(name="Space Biology and Biomedicine", queries=["test"], sources=["arxiv"])
        html = render_digest_email(_make_report(), topic, _make_entries())
        assert "#7c3aed" in html  # Violet primary

    def test_fallback_accent(self):
        """Unknown topic name should use default indigo accent."""
        topic = TopicProfile(name="Unknown Topic", queries=["test"], sources=["arxiv"])
        html = render_digest_email(_make_report(), topic, _make_entries())
        assert "#6366f1" in html  # Indigo fallback

    # --- Hero / highlights tests ---

    def test_hero_section_uses_first_highlight(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "FEATURED" in html
        assert "AlphaFold3 Release" in html

    def test_why_important_rendered(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "Enables drug discovery at scale" in html

    def test_empty_highlights_no_hero(self):
        report = _make_report()
        report.highlights = []
        html = render_digest_email(report, _make_topic(), _make_entries())
        assert "FEATURED" not in html

    # --- Deep reads tests ---

    def test_author_display(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "Le Song" in html
        assert "et al." in html  # 4 authors, show 3 + et al.

    def test_author_single(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "Kiouri DP" in html

    def test_published_date_formatted(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "Dec 09, 2024" in html

    def test_abstract_in_deep_reads(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "Multiscale foundation models" in html

    def test_read_paper_link(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "Read paper" in html

    def test_source_stats_section(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "SOURCES" in html

    def test_light_theme_background(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "#f8fafc" in html  # Light page background

    def test_overview_label(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "OVERVIEW" in html
