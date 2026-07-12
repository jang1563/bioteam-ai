"""Magazine-style HTML email template for digest reports.

Clean, editorial design inspired by Nature Briefing / Morning Brew.
Topic-specific accent colors, table-based layout for Outlook compatibility,
inline CSS only for email client support.
"""

from __future__ import annotations

import html
import re
from datetime import datetime

from app.config import settings
from app.models.digest import DigestEntry, DigestReport, TopicProfile

# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------
BG_PAGE = "#f8fafc"
BG_CARD = "#ffffff"
TEXT_PRIMARY = "#1e293b"
TEXT_SECONDARY = "#64748b"
TEXT_MUTED = "#94a3b8"
BORDER = "#e2e8f0"
FONT_STACK = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
MAX_WIDTH = "640"

# Topic-specific accent palettes (case-insensitive keys)
TOPIC_ACCENTS: dict[str, dict[str, str]] = {
    "ai in science": {
        "primary": "#2563eb",
        "primary_light": "#dbeafe",
        "primary_dark": "#1e40af",
    },
    "ai biology and medicine": {
        "primary": "#059669",
        "primary_light": "#d1fae5",
        "primary_dark": "#065f46",
    },
    "space biology and biomedicine": {
        "primary": "#7c3aed",
        "primary_light": "#ede9fe",
        "primary_dark": "#5b21b6",
    },
}
DEFAULT_ACCENT = {"primary": "#6366f1", "primary_light": "#e0e7ff", "primary_dark": "#4338ca"}

# Source badge colors (matching frontend)
SOURCE_COLORS: dict[str, str] = {
    "pubmed": "#3b82f6",
    "biorxiv": "#f97316",
    "arxiv": "#ef4444",
    "github": "#a855f7",
    "huggingface": "#eab308",
    "semantic_scholar": "#22c55e",
}

# Outlook-safe explicit light backgrounds (no hex-alpha)
SOURCE_BG_COLORS: dict[str, str] = {
    "pubmed": "#eff6ff",
    "biorxiv": "#fff7ed",
    "arxiv": "#fef2f2",
    "github": "#faf5ff",
    "huggingface": "#fefce8",
    "semantic_scholar": "#f0fdf4",
}

# Stop-words to filter from keyword extraction
_STOPWORDS = frozenset(
    "a an the of in on at to for with by from and or but is are was were "
    "be been being have has had do does did will would could should may might "
    "this that these those it its we our you your they their their study "
    "analysis results findings new using via based data paper study research "
    "review evidence effect effects role function expression human cell cells "
    "patients model models approach method methods".split()
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_accent(topic_name: str) -> dict[str, str]:
    """Get topic-specific accent colors with fallback."""
    return TOPIC_ACCENTS.get(topic_name.strip().lower(), DEFAULT_ACCENT)


def _extract_keywords(entries: list[DigestEntry], top_n: int = 8) -> list[str]:
    """Extract trending keywords from entry titles (simple word-count approach)."""
    counts: dict[str, int] = {}
    for e in entries:
        words = re.findall(r"[a-zA-Z]{4,}", e.title.lower())
        for w in words:
            if w not in _STOPWORDS:
                counts[w] = counts.get(w, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda x: -x[1])[:top_n]]


def _format_authors(authors: list[str], max_show: int = 3) -> str:
    """Format author list with et al. truncation."""
    if not authors:
        return ""
    safe = [html.escape(a) for a in authors[:max_show]]
    result = ", ".join(safe)
    if len(authors) > max_show:
        result += " et al."
    return result


def _format_published_date(date_str: str) -> str:
    """Format a date string for display. Handles YYYY-MM-DD, YYYY, or empty."""
    if not date_str:
        return ""
    date_str = date_str.strip()
    # Try YYYY-MM-DD
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date_str)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%b %d, %Y")
        except ValueError:
            return date_str
    return date_str


def _source_badge(source: str) -> str:
    """Render an inline source badge."""
    color = SOURCE_COLORS.get(source, "#888")
    bg = SOURCE_BG_COLORS.get(source, "#f1f5f9")
    safe_source = html.escape(source)
    return (
        f'<span style="display:inline-block;padding:1px 7px;border-radius:10px;'
        f'background:{bg};color:{color};font-size:10px;font-weight:600;'
        f'text-transform:uppercase;">{safe_source}</span>'
    )


def _section_label(text: str, accent: dict[str, str]) -> str:
    """Render a section label with accent underline."""
    return (
        f'<div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;'
        f'color:{accent["primary"]};font-weight:700;margin:0 0 8px 0;">{html.escape(text)}</div>'
        f'<div style="width:40px;height:2px;background:{accent["primary"]};margin-bottom:16px;"></div>'
    )


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------
def _build_masthead(topic_name: str, accent: dict[str, str], period_end: datetime | None, entry_count: int) -> str:
    """Masthead: accent bar + brand + topic title + date/count."""
    safe_name = html.escape(topic_name)
    date_str = period_end.strftime("%B %d, %Y") if period_end else ""
    count_str = f"{entry_count} papers scanned" if entry_count else ""
    meta_parts = [p for p in [date_str, count_str] if p]
    meta_line = "  |  ".join(meta_parts)

    return (
        f'<tr><td style="padding:0;">'
        # Accent bar
        f'<div style="height:4px;background:{accent["primary"]};'
        f'border-radius:8px 8px 0 0;"></div>'
        # Card
        f'<div style="background:{BG_CARD};border:1px solid {BORDER};border-top:none;'
        f'border-radius:0 0 8px 8px;padding:24px 28px;">'
        f'<div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;'
        f'color:{TEXT_SECONDARY};font-weight:700;margin-bottom:8px;">BIOTEAM-AI</div>'
        f'<div style="font-size:24px;line-height:1.3;font-weight:700;'
        f'color:{TEXT_PRIMARY};margin:0 0 6px 0;">{safe_name}</div>'
        f'<div style="font-size:13px;color:{TEXT_SECONDARY};margin:0;">{meta_line}</div>'
        f'</div>'
        f'</td></tr>'
    )


def _build_hero(highlight: dict, accent: dict[str, str], entry_url_map: dict[str, str]) -> str:
    """Hero: featured paper (highlight #1) with accent background."""
    title = html.escape(highlight.get("title", ""))
    source = highlight.get("source", "")
    desc = html.escape(highlight.get("one_liner", "") or highlight.get("description", ""))
    why = html.escape(highlight.get("why_important", ""))
    raw_url = highlight.get("url", "") or entry_url_map.get(highlight.get("title", "").strip().lower(), "")
    url = html.escape(raw_url)

    title_html = (
        f'<a href="{url}" style="color:#ffffff;text-decoration:none;">{title}</a>'
        if url else title
    )

    source_html = (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
        f'background:rgba(255,255,255,0.15);color:#ffffff;font-size:11px;'
        f'text-transform:uppercase;">{html.escape(source)}</span>'
    ) if source else ""

    why_html = (
        f'<div style="font-size:13px;font-style:italic;color:rgba(255,255,255,0.75);'
        f'margin:8px 0 0 0;">{why}</div>'
    ) if why else ""

    cta_html = (
        f'<a href="{url}" style="display:inline-block;margin-top:16px;padding:8px 20px;'
        f'background:#ffffff;color:{accent["primary_dark"]};font-size:13px;font-weight:600;'
        f'border-radius:4px;text-decoration:none;">Read paper &#8594;</a>'
    ) if url else ""

    return (
        f'<tr><td style="padding:12px 0 0 0;">'
        f'<div style="background:{accent["primary_dark"]};border-radius:8px;padding:28px;">'
        f'<div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;'
        f'color:rgba(255,255,255,0.6);margin-bottom:12px;">FEATURED</div>'
        f'<div style="font-size:20px;line-height:1.35;font-weight:700;'
        f'color:#ffffff;margin:0 0 10px 0;">{title_html}</div>'
        f'{source_html}'
        f'<div style="font-size:14px;line-height:1.6;color:rgba(255,255,255,0.9);'
        f'margin:10px 0 0 0;">{desc}</div>'
        f'{why_html}'
        f'{cta_html}'
        f'</div>'
        f'</td></tr>'
    )


def _build_summary(summary: str, accent: dict[str, str]) -> str:
    """Executive summary section."""
    if not summary:
        text = f'<span style="color:{TEXT_SECONDARY};font-style:italic;">No summary available for this period.</span>'
    else:
        text = html.escape(summary).replace("\n", "<br>\n")

    return (
        f'<tr><td style="padding:12px 0 0 0;">'
        f'<div style="background:{BG_CARD};border:1px solid {BORDER};'
        f'border-radius:8px;padding:24px 28px;">'
        f'{_section_label("OVERVIEW", accent)}'
        f'<div style="font-size:14px;line-height:1.7;color:{TEXT_PRIMARY};margin:0;">'
        f'{text}</div>'
        f'</div>'
        f'</td></tr>'
    )


def _build_highlights(highlights: list[dict], accent: dict[str, str], entry_url_map: dict[str, str]) -> str:
    """Top picks: highlights #2-6 with numbering."""
    if not highlights:
        return ""

    items = []
    for i, h in enumerate(highlights, 2):  # Start at 2 (hero was #1)
        title = html.escape(h.get("title", ""))
        source = h.get("source", "")
        desc = html.escape(h.get("one_liner", "") or h.get("description", ""))
        why = html.escape(h.get("why_important", ""))
        raw_url = h.get("url", "") or entry_url_map.get(h.get("title", "").strip().lower(), "")
        url = html.escape(raw_url)

        title_html = (
            f'<a href="{url}" style="color:{TEXT_PRIMARY};text-decoration:none;'
            f'font-weight:600;">{title}</a>'
            if url else f'<span style="font-weight:600;">{title}</span>'
        )

        source_html = _source_badge(source) if source else ""

        why_html = (
            f'<div style="font-size:12px;color:{TEXT_MUTED};font-style:italic;margin-top:2px;">{why}</div>'
        ) if why else ""

        border_style = f"border-bottom:1px solid {BORDER};" if i - 1 < len(highlights) else ""

        items.append(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="{border_style}"><tr>'
            f'<td width="36" valign="top" style="padding:14px 0;font-size:22px;'
            f'font-weight:700;color:{accent["primary"]};">{i}</td>'
            f'<td style="padding:14px 0 14px 12px;">'
            f'<div style="font-size:14px;line-height:1.4;color:{TEXT_PRIMARY};">{title_html}</div>'
            f'<div style="margin-top:4px;">{source_html}</div>'
            f'<div style="font-size:13px;color:{TEXT_SECONDARY};line-height:1.5;margin-top:4px;">{desc}</div>'
            f'{why_html}'
            f'</td>'
            f'</tr></table>'
        )

    return (
        f'<tr><td style="padding:12px 0 0 0;">'
        f'<div style="background:{BG_CARD};border:1px solid {BORDER};'
        f'border-radius:8px;padding:24px 28px;">'
        f'{_section_label("TOP PICKS", accent)}'
        f'{"".join(items)}'
        f'</div>'
        f'</td></tr>'
    )


def _build_trending(entries: list[DigestEntry], accent: dict[str, str]) -> str:
    """Trending keywords as pill badges."""
    if not entries:
        return ""
    keywords = _extract_keywords(entries)
    if not keywords:
        return ""

    badges = "".join(
        f'<span style="display:inline-block;margin:3px 4px 3px 0;'
        f'padding:4px 12px;border-radius:12px;'
        f'background:{accent["primary_light"]};color:{accent["primary_dark"]};'
        f'font-size:11px;font-weight:600;">'
        f'{html.escape(kw)}</span>'
        for kw in keywords
    )

    return (
        f'<tr><td style="padding:12px 0 0 0;">'
        f'<div style="background:{BG_CARD};border:1px solid {BORDER};'
        f'border-radius:8px;padding:24px 28px;">'
        f'{_section_label("TRENDING", accent)}'
        f'<div style="line-height:2;">{badges}</div>'
        f'</div>'
        f'</td></tr>'
    )


def _build_deep_reads(entries: list[DigestEntry], accent: dict[str, str]) -> str:
    """Top entries with full metadata: authors, abstract snippet, link."""
    if not entries:
        return ""

    cards = []
    for e in entries:
        safe_title = html.escape(e.title[:120])
        safe_url = html.escape(e.url)
        source = e.source
        score_pct = int(e.relevance_score * 100)
        pub_date = _format_published_date(e.published_at)

        # Title
        title_html = (
            f'<a href="{safe_url}" style="color:{TEXT_PRIMARY};text-decoration:none;'
            f'font-size:15px;font-weight:600;line-height:1.4;">{safe_title}</a>'
            if e.url else
            f'<span style="font-size:15px;font-weight:600;line-height:1.4;'
            f'color:{TEXT_PRIMARY};">{safe_title}</span>'
        )

        # Meta line: source badge | date | relevance
        meta_parts = [_source_badge(source)]
        if pub_date:
            meta_parts.append(f'<span style="color:{TEXT_MUTED};font-size:11px;">{html.escape(pub_date)}</span>')
        meta_parts.append(f'<span style="color:{TEXT_MUTED};font-size:11px;">{score_pct}% relevant</span>')
        meta_line = f' <span style="color:{TEXT_MUTED};"> | </span> '.join(meta_parts)

        # Authors
        authors_str = _format_authors(e.authors)
        authors_html = (
            f'<div style="font-size:12px;color:{TEXT_SECONDARY};margin:2px 0;">{authors_str}</div>'
        ) if authors_str else ""

        # Abstract snippet
        abstract_text = (e.abstract or "").strip()
        if len(abstract_text) > 200:
            abstract_text = abstract_text[:197].rsplit(" ", 1)[0] + "..."
        abstract_html = (
            f'<div style="font-size:13px;color:{TEXT_SECONDARY};line-height:1.6;'
            f'margin:6px 0 0 0;">{html.escape(abstract_text)}</div>'
        ) if abstract_text else ""

        # Read link
        read_html = (
            f'<a href="{safe_url}" style="font-size:12px;font-weight:600;'
            f'color:{accent["primary"]};text-decoration:none;display:inline-block;'
            f'margin-top:6px;">Read paper &#8594;</a>'
        ) if e.url else ""

        cards.append(
            f'<div style="padding:16px 0;border-bottom:1px solid {BORDER};">'
            f'<div style="margin-bottom:6px;">{meta_line}</div>'
            f'<div style="margin:6px 0;">{title_html}</div>'
            f'{authors_html}'
            f'{abstract_html}'
            f'{read_html}'
            f'</div>'
        )

    return (
        f'<tr><td style="padding:12px 0 0 0;">'
        f'<div style="background:{BG_CARD};border:1px solid {BORDER};'
        f'border-radius:8px;padding:24px 28px;">'
        f'{_section_label("DEEP READS", accent)}'
        f'{"".join(cards)}'
        f'</div>'
        f'</td></tr>'
    )


def _build_source_stats(source_breakdown: dict | None) -> str:
    """Compact inline source stats."""
    if not source_breakdown:
        return ""

    parts = []
    for src, count in sorted(source_breakdown.items(), key=lambda x: -x[1]):
        parts.append(f'{_source_badge(src)} <span style="color:{TEXT_PRIMARY};font-weight:600;'
                     f'font-size:13px;margin-right:12px;">{count}</span>')

    stats_line = f' <span style="color:{TEXT_MUTED};"> &middot; </span> '.join(parts)

    return (
        f'<tr><td style="padding:12px 0 0 0;">'
        f'<div style="background:{BG_CARD};border:1px solid {BORDER};'
        f'border-radius:8px;padding:20px 28px;">'
        f'<div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;'
        f'color:{TEXT_SECONDARY};font-weight:700;margin-bottom:12px;">SOURCES</div>'
        f'<div style="line-height:2.2;">{stats_line}</div>'
        f'</div>'
        f'</td></tr>'
    )


def _build_cta(dashboard_url: str, accent: dict[str, str]) -> str:
    """CTA button (table-wrapped for Outlook compatibility)."""
    safe_url = html.escape(f"{dashboard_url}/digest")
    return (
        f'<tr><td style="padding:24px 0;" align="center">'
        f'<table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="margin:0 auto;"><tr>'
        f'<td align="center" bgcolor="{accent["primary"]}" '
        f'style="background:{accent["primary"]};border-radius:6px;padding:12px 32px;">'
        f'<a href="{safe_url}" style="color:#ffffff;font-size:14px;font-weight:600;'
        f'text-decoration:none;letter-spacing:0.3px;display:inline-block;">'
        f'Explore Full Report in Dashboard</a>'
        f'</td></tr></table>'
        f'</td></tr>'
    )


def _build_footer(dashboard_url: str, cost: float) -> str:
    """Footer with branding, sources, cost, and unsubscribe."""
    safe_settings_url = html.escape(f"{dashboard_url}/settings")
    return (
        f'<tr><td style="padding:20px 28px;border-top:1px solid {BORDER};" align="center">'
        f'<div style="font-size:11px;font-weight:700;letter-spacing:1px;'
        f'text-transform:uppercase;color:{TEXT_MUTED};">BIOTEAM-AI</div>'
        f'<div style="font-size:11px;color:{TEXT_MUTED};margin-top:6px;">'
        f'Data from PubMed, bioRxiv, arXiv, GitHub, HuggingFace, Semantic Scholar</div>'
        f'<div style="font-size:10px;color:{TEXT_MUTED};margin-top:4px;">'
        f'LLM cost: ${cost:.4f}</div>'
        f'<div style="font-size:10px;color:{TEXT_MUTED};margin-top:8px;">'
        f'To stop receiving these emails, '
        f'<a href="{safe_settings_url}" style="color:{TEXT_MUTED};text-decoration:underline;">'
        f'update your digest settings</a>.</div>'
        f'</td></tr>'
    )


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------
def render_digest_email(
    report: DigestReport,
    topic: TopicProfile,
    entries: list[DigestEntry],
) -> str:
    """Render a magazine-style HTML email for a digest report.

    Uses inline CSS for email client compatibility.
    All user-supplied text is HTML-escaped to prevent injection.
    """
    accent = _get_accent(topic.name)

    # Build a title→URL lookup from entries for highlights that may lack URLs
    entry_url_map: dict[str, str] = {}
    for e in entries:
        if e.url and e.title:
            entry_url_map[e.title.strip().lower()] = e.url

    # Hero uses highlight #1; remaining go to Top Picks
    hero_html = ""
    remaining_highlights = list(report.highlights[:6]) if report.highlights else []
    if remaining_highlights:
        hero_html = _build_hero(remaining_highlights[0], accent, entry_url_map)
        remaining_highlights = remaining_highlights[1:]

    sections = [
        _build_masthead(topic.name, accent, report.period_end, report.entry_count),
        hero_html,
        _build_summary(report.summary, accent),
        _build_highlights(remaining_highlights, accent, entry_url_map),
        _build_trending(entries, accent),
        _build_deep_reads(entries[:5], accent),
        _build_source_stats(report.source_breakdown),
        _build_cta(settings.dashboard_url, accent),
        _build_footer(settings.dashboard_url, report.cost),
    ]

    body = "\n".join(s for s in sections if s)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:{BG_PAGE};font-family:{FONT_STACK};-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG_PAGE};">
<tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="{MAX_WIDTH}" cellpadding="0" cellspacing="0" style="max-width:{MAX_WIDTH}px;width:100%;">
{body}
</table>
</td></tr>
</table>
</body>
</html>"""
