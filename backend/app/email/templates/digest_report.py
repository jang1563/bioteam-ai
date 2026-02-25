"""HTML email template for digest reports."""

from __future__ import annotations

from app.models.digest import DigestEntry, DigestReport, TopicProfile

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
    """
    highlights_html = ""
    if report.highlights:
        items = []
        for i, h in enumerate(report.highlights[:6], 1):
            title = h.get("title", "")
            source = h.get("source", "")
            desc = h.get("description", "")
            url = h.get("url", "")
            color = SOURCE_COLORS.get(source, "#888")
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

    # Source breakdown
    breakdown_html = ""
    if report.source_breakdown:
        bars = []
        for src, count in sorted(report.source_breakdown.items(), key=lambda x: -x[1]):
            color = SOURCE_COLORS.get(src, "#888")
            bars.append(
                f'<div style="margin:4px 0;">'
                f'<span style="display:inline-block;width:120px;color:#a0aec0;font-size:13px;">{src}</span>'
                f'<span style="display:inline-block;background:{color};height:14px;'
                f'width:{min(count * 20, 200)}px;border-radius:3px;vertical-align:middle;"></span>'
                f'<span style="color:#e2e8f0;font-size:13px;margin-left:8px;">{count}</span>'
                f'</div>'
            )
        breakdown_html = (
            '<h2 style="color:#00d4aa;font-size:16px;margin:24px 0 12px;">Source Breakdown</h2>'
            + "".join(bars)
        )

    # Top entries table
    top_entries_html = ""
    if entries:
        rows = []
        for e in entries[:10]:
            color = SOURCE_COLORS.get(e.source, "#888")
            score_pct = int(e.relevance_score * 100)
            url_link = f'<a href="{e.url}" style="color:#00d4aa;text-decoration:none;">Link</a>' if e.url else ""
            rows.append(
                f'<tr style="border-bottom:1px solid #1a2332;">'
                f'<td style="padding:8px;"><span style="padding:2px 6px;border-radius:3px;'
                f'background:{color}22;color:{color};font-size:11px;">{e.source}</span></td>'
                f'<td style="padding:8px;color:#e2e8f0;font-size:13px;">{e.title[:80]}</td>'
                f'<td style="padding:8px;color:#00d4aa;font-size:13px;text-align:center;">{score_pct}%</td>'
                f'<td style="padding:8px;text-align:center;">{url_link}</td>'
                f'</tr>'
            )
        top_entries_html = (
            '<h2 style="color:#00d4aa;font-size:16px;margin:24px 0 12px;">Top Papers</h2>'
            '<table style="width:100%;border-collapse:collapse;">'
            '<tr style="border-bottom:1px solid #1a2332;">'
            '<th style="padding:8px;color:#7a8ba7;font-size:12px;text-align:left;">Source</th>'
            '<th style="padding:8px;color:#7a8ba7;font-size:12px;text-align:left;">Title</th>'
            '<th style="padding:8px;color:#7a8ba7;font-size:12px;text-align:center;">Score</th>'
            '<th style="padding:8px;color:#7a8ba7;font-size:12px;text-align:center;">Link</th>'
            '</tr>' + "".join(rows) + '</table>'
        )

    period_str = ""
    if report.period_start and report.period_end:
        period_str = f"{report.period_start.strftime('%Y-%m-%d')} — {report.period_end.strftime('%Y-%m-%d')}"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#060a14;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:640px;margin:0 auto;padding:24px;">

  <!-- Header -->
  <div style="background:#0a0f1e;border:1px solid #1a2332;border-radius:8px;padding:24px;margin-bottom:16px;">
    <h1 style="color:#00d4aa;font-size:20px;margin:0 0 4px;">BioTeam-AI Digest Report</h1>
    <div style="color:#7a8ba7;font-size:13px;">{topic.name} · {period_str} · {report.entry_count} entries</div>
    <div style="color:#7a8ba7;font-size:12px;margin-top:4px;">LLM Cost: ${report.cost:.4f}</div>
  </div>

  <!-- Summary -->
  <div style="background:#0a0f1e;border:1px solid #1a2332;border-radius:8px;padding:24px;margin-bottom:16px;">
    <h2 style="color:#00d4aa;font-size:16px;margin:0 0 12px;">Executive Summary</h2>
    <p style="color:#e2e8f0;font-size:14px;line-height:1.7;margin:0;">
      {report.summary or "No summary generated."}
    </p>

    {highlights_html}
    {breakdown_html}
    {top_entries_html}
  </div>

  <!-- Footer -->
  <div style="text-align:center;padding:16px;color:#4a5568;font-size:11px;">
    Generated by BioTeam-AI · All paper data sourced from public APIs (PubMed, bioRxiv, arXiv, GitHub, HuggingFace, Semantic Scholar)
  </div>

</div>
</body>
</html>"""
