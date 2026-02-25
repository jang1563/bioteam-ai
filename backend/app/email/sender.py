"""Async email sender for digest report delivery.

Uses aiosmtplib for non-blocking SMTP (Gmail SMTP with STARTTLS).
Designed as fire-and-forget — errors are logged but never fail the pipeline.
"""

from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings
from app.email.templates.digest_report import render_digest_email
from app.models.digest import DigestEntry, DigestReport, TopicProfile

logger = logging.getLogger(__name__)


def is_email_configured() -> bool:
    """Check if SMTP credentials are set."""
    return bool(settings.smtp_user and settings.smtp_password)


def get_recipients() -> list[str]:
    """Parse comma-separated recipients from settings."""
    raw = settings.digest_recipients.strip()
    if not raw:
        return []
    return [addr.strip() for addr in raw.split(",") if addr.strip()]


async def send_digest_email(
    report: DigestReport,
    topic: TopicProfile,
    entries: list[DigestEntry],
    recipients: list[str] | None = None,
) -> bool:
    """Send a digest report via email.

    Args:
        report: The digest report to send.
        topic: The topic profile for context.
        entries: Top entries to include in the email.
        recipients: Override recipient list. If None, uses settings.

    Returns:
        True if email was sent successfully, False otherwise.
    """
    if not is_email_configured():
        logger.debug("Email not configured, skipping send")
        return False

    to_addrs = recipients or get_recipients()
    if not to_addrs:
        logger.debug("No recipients configured, skipping send")
        return False

    try:
        import aiosmtplib
    except ImportError:
        logger.warning("aiosmtplib not installed, skipping email send")
        return False

    # Build email
    subject = f"[BioTeam-AI] {topic.name} — Digest Report"
    if report.period_end:
        subject += f" ({report.period_end.strftime('%Y-%m-%d')})"

    html_body = render_digest_email(report, topic, entries)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            start_tls=True,
            username=settings.smtp_user,
            password=settings.smtp_password,
        )
        logger.info("Digest email sent to %s", ", ".join(to_addrs))
        return True
    except Exception as e:
        logger.warning("Failed to send digest email: %s", e)
        return False
