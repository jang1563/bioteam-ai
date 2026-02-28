"""HTML email template for digest reports."""

from __future__ import annotations

import html
import os
import re

from app.models.digest import DigestEntry, DigestReport, TopicProfile

# Stop-words to filter from keyword extraction
_STOPWORDS = frozenset(
    "a an the of in on at to for with by from and or but is are was were "
    "be been being have has had do does did will would could should may might "
    "this that these those it its we our you your they their their study "
    "analysis results findings new using via based data paper study research "
    "review evidence effect effects role function expression human cell cells "
    "patients model models approach method methods".split()
)


def _extract_keywords(entries: list[DigestEntry], top_n: int = 8) -> list[str]:
    """Extract trending keywords from entry titles (simple word-count approach)."""
    counts: dict[str, int] = {}
    for e in entries:
        words = re.findall(r"[a-zA-Z]{4,}", e.title.lower())
        for w in words:
            if w not in _STOPWORDS:
                counts[w] = counts.get(w, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda x: -x[1])[:top_n]]

# Source badge colors (matching frontend)
SOURCE_COLORS = {
    "pubmed": "#3b82f6",
    "biorxiv": "#f97316",
    "arxiv": "#ef4444",
    "github": "#a855f7",
    "huggingface": "#eab308",
    "semantic_scholar": "#22c55e",
}


def render_digest_email(
    report: DigestReport,
    topic: TopicProfile,
    entries: list[DigestEntry],
) -> str:
    """Render an HTML email for a digest report.

    Uses inline CSS for email client compatibility.
    All user-supplied text is HTML-escaped to prevent injection.
    """
    highlights_html = ""
    if report.highlights:
        items = []
        for i, h in enumerate(report.highlights[:6], 1):
            title = html.escape(h.get("title", ""))
            source = html.escape(h.get("source", ""))
            # Support both "description" and "one_liner" field names from DigestAgent
            desc = html.escape(h.get("description", "") or h.get("one_liner", ""))
            url = html.escape(h.get("url", ""))
            color = SOURCE_COLORS.get(h.get("source", ""), "#888")
            link = f' <a href="{url}" style="color:{color};text-decoration:none;">[Link]</a>' if url else ""
            items.append(
                f'<tr><td style="padding:8px 12px;vertical-align:top;color:#888;font-size:13px;">{i}</td>'
                f'<td style="padding:8px 0;">'
                f'<strong style="color:#e2e8f0;">{title}</strong>{link}<br>'
                f'<span style="display:inline-block;padding:1px 6px;border-radius:3px;'
                f'background:{color}22;color:{color};font-size:11px;margin:4px 0;">{source}</span> '
                f'<span style="color:#a0aec0;font-size:13px;">{desc}</span>'
                f'</td></tr>'
            )
        highlights_html = (
            '<h2 style="color:#00d4aa;font-size:16px;margin:24px 0 12px;">Highlights</h2>'
            '<table style="width:100%;border-collapse:collapse;">' + "".join(items) + "</table>"
        )

    # Source breakdown — proportional bar widths relative to the largest source
    breakdown_html = ""
    if report.source_breakdown:
        max_count = max(report.source_breakdown.values(), default=1)
        bars = []
        for src, count in sorted(report.source_breakdown.items(), key=lambda x: -x[1]):
            color = SOURCE_COLORS.get(src, "#888")
            bar_width = int((count / max_count) * 180)  # scale relative to max, cap at 180px
            bars.append(
                f'<div style="margin:4px 0;">'
                f'<span style="display:inline-block;width:120px;color:#a0aec0;font-size:13px;">'
                f'{html.escape(src)}</span>'
                f'<span style="display:inline-block;background:{color};height:14px;'
                f'width:{bar_width}px;border-radius:3px;vertical-align:middle;"></span>'
                f'<span style="color:#e2e8f0;font-size:13px;margin-left:8px;">{count}</span>'
                f'</div>'
            )
        breakdown_html = (
            '<h2 style="color:#00d4aa;font-size:16px;margin:24px 0 12px;">Source Breakdown</h2>'
            + "".join(bars)
        )

    # Top entries — card layout with collapsible abstract (<details>/<summary>)
    # Apple Mail: clickable toggle. Gmail: shows expanded.
    top_entries_html = ""
    if entries:
        cards = []
        for i, e in enumerate(entries[:10], 1):
            color = SOURCE_COLORS.get(e.source, "#888")
            score_pct = int(e.relevance_score * 100)
            safe_title = html.escape(e.title[:100])
            safe_source = html.escape(e.source)
            safe_url = html.escape(e.url)
            url_link = (
                f' <a href="{safe_url}" style="color:#00d4aa;text-decoration:none;font-size:12px;">'
                f'Read &rarr;</a>'
            ) if e.url else ""

            # Truncate abstract to ~3 lines
            abstract_text = (e.abstract or "").strip()
            if len(abstract_text) > 300:
                abstract_text = abstract_text[:297].rsplit(" ", 1)[0] + "..."
            safe_abstract = html.escape(abstract_text)

            abstract_block = ""
            if safe_abstract:
                abstract_block = (
                    f'<details style="margin-top:6px;">'
                    f'<summary style="color:#7a8ba7;font-size:12px;cursor:pointer;">'
                    f'&#9662; Summary</summary>'
                    f'<p style="color:#a0aec0;font-size:12px;line-height:1.6;'
                    f'margin:6px 0 0;padding:8px;background:#060a14;border-radius:4px;">'
                    f'{safe_abstract}</p>'
                    f'</details>'
                )

            cards.append(
                f'<div style="padding:12px 0;border-bottom:1px solid #1a2332;">'
                f'<div>'
                f'<span style="color:#4a5568;font-size:12px;margin-right:6px;">{i}.</span>'
                f'<span style="padding:2px 6px;border-radius:3px;'
                f'background:{color}22;color:{color};font-size:11px;margin-right:6px;">'
                f'{safe_source}</span>'
                f'<span style="color:#00d4aa;font-size:11px;">{score_pct}%</span>'
                f'{url_link}'
                f'</div>'
                f'<div style="color:#e2e8f0;font-size:13px;line-height:1.4;margin-top:4px;">'
                f'{safe_title}</div>'
                f'{abstract_block}'
                f'</div>'
            )
        top_entries_html = (
            '<h2 style="color:#00d4aa;font-size:16px;margin:24px 0 12px;">Top Papers</h2>'
            + "".join(cards)
        )

    # Trending keywords badges
    trending_html = ""
    if entries:
        keywords = _extract_keywords(entries)
        if keywords:
            badges = "".join(
                f'<span style="display:inline-block;margin:3px 4px 3px 0;'
                f'padding:3px 10px;border-radius:12px;'
                f'background:#0a1628;border:1px solid #1e3050;'
                f'color:#93c5fd;font-size:11px;">'
                f'{html.escape(kw)}</span>'
                for kw in keywords
            )
            trending_html = (
                '<h2 style="color:#00d4aa;font-size:16px;margin:24px 0 12px;">Trending Topics</h2>'
                f'<div style="line-height:2;">{badges}</div>'
            )

    period_str = ""
    if report.period_start and report.period_end:
        period_str = f"{report.period_start.strftime('%Y-%m-%d')} — {report.period_end.strftime('%Y-%m-%d')}"

    safe_topic_name = html.escape(topic.name)
    safe_summary = html.escape(report.summary) if report.summary else "No summary generated."

    # Dashboard CTA link
    dashboard_url = html.escape(os.environ.get("DASHBOARD_URL", "http://localhost:3000"))
    cta_html = (
        f'<div style="text-align:center;margin:24px 0;">'
        f'<a href="{dashboard_url}/digest" '
        f'style="display:inline-block;padding:10px 28px;'
        f'background:#00d4aa;color:#060a14;border-radius:6px;'
        f'text-decoration:none;font-weight:600;font-size:14px;">'
        f'View Full Report in Dashboard</a>'
        f'</div>'
    )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#060a14;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:640px;margin:0 auto;padding:24px;">

  <!-- Header -->
  <div style="background:#0a0f1e;border:1px solid #1a2332;border-radius:8px;padding:24px;margin-bottom:16px;">
    <h1 style="color:#00d4aa;font-size:20px;margin:0 0 4px;">BioTeam-AI Digest Report</h1>
    <div style="color:#7a8ba7;font-size:13px;">{safe_topic_name} · {period_str} · {report.entry_count} entries</div>
    <div style="color:#7a8ba7;font-size:12px;margin-top:4px;">LLM Cost: ${report.cost:.4f}</div>
  </div>

  <!-- Summary -->
  <div style="background:#0a0f1e;border:1px solid #1a2332;border-radius:8px;padding:24px;margin-bottom:16px;">
    <h2 style="color:#00d4aa;font-size:16px;margin:0 0 12px;">Executive Summary</h2>
    <p style="color:#e2e8f0;font-size:14px;line-height:1.7;margin:0;">
      {safe_summary}
    </p>

    {highlights_html}
    {trending_html}
    {breakdown_html}
    {top_entries_html}

    {cta_html}
  </div>

  <!-- Footer -->
  <div style="text-align:center;padding:16px;color:#4a5568;font-size:11px;">
    Generated by BioTeam-AI · Data from PubMed, bioRxiv, arXiv, GitHub, HuggingFace, Semantic Scholar<br>
    <span style="color:#334155;">To stop receiving these emails, update your digest settings in the dashboard.</span>
  </div>

</div>
</body>
</html>"""
