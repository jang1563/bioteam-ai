"""Tests for email sender."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from app.email.sender import get_recipients, is_email_configured, send_digest_email
from app.models.digest import DigestEntry, DigestReport, TopicProfile


def _make_report() -> DigestReport:
    return DigestReport(
        topic_id="t1",
        period_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        period_end=datetime(2024, 1, 7, tzinfo=timezone.utc),
        entry_count=5,
        summary="Test summary",
        highlights=[{"title": "Paper 1", "source": "arxiv", "description": "Desc"}],
        source_breakdown={"arxiv": 3, "pubmed": 2},
        cost=0.005,
    )


def _make_topic() -> TopicProfile:
    return TopicProfile(
        name="AI Biology",
        queries=["AI biology"],
        sources=["arxiv", "pubmed"],
    )


def _make_entries() -> list[DigestEntry]:
    return [
        DigestEntry(
            topic_id="t1",
            source="arxiv",
            external_id="2412.06993",
            title="Test Paper",
            authors=["Author A"],
            abstract="Abstract here",
            url="https://arxiv.org/abs/2412.06993",
            relevance_score=0.95,
        ),
    ]


class TestIsEmailConfigured:
    def test_not_configured_when_empty(self):
        with patch("app.email.sender.settings") as mock_settings:
            mock_settings.smtp_user = ""
            mock_settings.smtp_password = ""
            assert is_email_configured() is False

    def test_not_configured_when_password_missing(self):
        with patch("app.email.sender.settings") as mock_settings:
            mock_settings.smtp_user = "user@gmail.com"
            mock_settings.smtp_password = ""
            assert is_email_configured() is False

    def test_configured_when_both_set(self):
        with patch("app.email.sender.settings") as mock_settings:
            mock_settings.smtp_user = "user@gmail.com"
            mock_settings.smtp_password = "app-password"
            assert is_email_configured() is True


class TestGetRecipients:
    def test_empty_returns_empty_list(self):
        with patch("app.email.sender.settings") as mock_settings:
            mock_settings.digest_recipients = ""
            assert get_recipients() == []

    def test_single_recipient(self):
        with patch("app.email.sender.settings") as mock_settings:
            mock_settings.digest_recipients = "user@example.com"
            assert get_recipients() == ["user@example.com"]

    def test_multiple_recipients(self):
        with patch("app.email.sender.settings") as mock_settings:
            mock_settings.digest_recipients = "a@x.com, b@x.com, c@x.com"
            assert get_recipients() == ["a@x.com", "b@x.com", "c@x.com"]


class TestSendDigestEmail:
    @pytest.mark.asyncio
    async def test_skips_when_not_configured(self):
        with patch("app.email.sender.settings") as mock_settings:
            mock_settings.smtp_user = ""
            mock_settings.smtp_password = ""
            result = await send_digest_email(
                _make_report(), _make_topic(), _make_entries()
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_skips_when_no_recipients(self):
        with patch("app.email.sender.settings") as mock_settings:
            mock_settings.smtp_user = "user@gmail.com"
            mock_settings.smtp_password = "pass"
            mock_settings.digest_recipients = ""
            result = await send_digest_email(
                _make_report(), _make_topic(), _make_entries(), recipients=[]
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_sends_successfully(self):
        with patch("app.email.sender.settings") as mock_settings, \
             patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            mock_settings.smtp_user = "user@gmail.com"
            mock_settings.smtp_password = "pass"
            mock_settings.smtp_host = "smtp.gmail.com"
            mock_settings.smtp_port = 587
            mock_settings.digest_recipients = "a@x.com"

            result = await send_digest_email(
                _make_report(), _make_topic(), _make_entries(),
                recipients=["a@x.com"],
            )
            assert result is True
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_on_smtp_error(self):
        with patch("app.email.sender.settings") as mock_settings, \
             patch("aiosmtplib.send", new_callable=AsyncMock, side_effect=Exception("SMTP error")):
            mock_settings.smtp_user = "user@gmail.com"
            mock_settings.smtp_password = "pass"
            mock_settings.smtp_host = "smtp.gmail.com"
            mock_settings.smtp_port = 587
            mock_settings.digest_recipients = "a@x.com"

            result = await send_digest_email(
                _make_report(), _make_topic(), _make_entries(),
                recipients=["a@x.com"],
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_email_subject_format(self):
        with patch("app.email.sender.settings") as mock_settings, \
             patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            mock_settings.smtp_user = "user@gmail.com"
            mock_settings.smtp_password = "pass"
            mock_settings.smtp_host = "smtp.gmail.com"
            mock_settings.smtp_port = 587

            report = _make_report()
            topic = _make_topic()

            await send_digest_email(report, topic, _make_entries(), recipients=["a@x.com"])

            # Extract the message from the call
            msg = mock_send.call_args[0][0]
            assert "[BioTeam-AI]" in msg["Subject"]
            assert "AI Biology" in msg["Subject"]
