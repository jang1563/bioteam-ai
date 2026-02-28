"""Tests for email template rendering."""

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
            {"title": "AlphaFold3 Release", "source": "github", "description": "Open-source structure prediction", "url": "https://github.com/google-deepmind/alphafold3"},
            {"title": "CellFM Paper", "source": "biorxiv", "description": "100M cell foundation model"},
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
            authors=["Le Song"],
            abstract="Multiscale foundation models.",
            url="https://arxiv.org/abs/2412.06993",
            relevance_score=0.94,
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
        assert "BioTeam-AI Digest Report" in html

    def test_contains_topic_name(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "AI Biology" in html

    def test_contains_cost(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "$0.008" in html

    def test_contains_entry_links(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "https://arxiv.org/abs/2412.06993" in html

    def test_empty_entries(self):
        html = render_digest_email(_make_report(), _make_topic(), [])
        assert "BioTeam-AI Digest Report" in html

    def test_no_summary(self):
        report = _make_report()
        report.summary = ""
        html = render_digest_email(report, _make_topic(), _make_entries())
        assert "No summary generated" in html

    def test_trending_keywords_shown(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "Trending Topics" in html

    def test_dashboard_cta_present(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "View Full Report in Dashboard" in html

    def test_collapsible_abstract_present(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        assert "<details" in html
        assert "<summary" in html

    def test_numbered_entries(self):
        html = render_digest_email(_make_report(), _make_topic(), _make_entries())
        # Entries should be numbered (1. prefix)
        assert ">1.<" in html

    def test_xss_escaped_in_title(self):
        entries = _make_entries()
        entries[0].title = '<script>alert("xss")</script>'
        html = render_digest_email(_make_report(), _make_topic(), entries)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
