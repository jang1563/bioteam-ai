"""W8 Report Builder — assembles peer review report, SessionManifest, and Markdown output.

Follows the report_builder.py pattern from W1.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.agent import AgentOutput
from app.models.evidence import SessionManifest
from app.models.peer_review import (
    MethodologyAssessment,
    NoveltyAssessment,
    PaperClaim,
    PeerReviewSynthesis,
    ReviewComment,
    W8PeerReviewReport,
)
from app.models.workflow import WorkflowInstance


def build_w8_session_manifest(
    instance: WorkflowInstance,
    step_results: dict[str, AgentOutput],
) -> dict:
    """Aggregate LLM metadata from all W8 step results into a SessionManifest."""
    llm_calls = []
    total_input = 0
    total_output = 0
    total_cost = 0.0
    model_versions: set[str] = set()

    for step_id, result in step_results.items():
        if not hasattr(result, "model_version"):
            continue
        if result.model_version and result.model_version != "deterministic":
            model_versions.add(result.model_version)
            llm_calls.append({
                "step_id": step_id,
                "agent_id": result.agent_id,
                "model_version": result.model_version,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cached_input_tokens": result.cached_input_tokens,
                "cost": result.cost,
            })
            total_input += result.input_tokens
            total_output += result.output_tokens
            total_cost += result.cost

    manifest = SessionManifest(
        workflow_id=instance.id,
        template="W8",
        query=instance.query,
        started_at=instance.created_at,
        completed_at=datetime.now(timezone.utc),
        llm_calls=llm_calls,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cost=total_cost,
        model_versions=sorted(model_versions),
        system_version="v0.5",
    )
    return manifest.model_dump(mode="json")


def build_peer_review_report(
    instance: WorkflowInstance,
    step_results: dict[str, AgentOutput],
    paper_title: str = "",
) -> W8PeerReviewReport:
    """Assemble W8PeerReviewReport from all step results."""
    # Extract claims
    claims: list[PaperClaim] = []
    extract_result = step_results.get("EXTRACT_CLAIMS")
    if extract_result and hasattr(extract_result, "output") and isinstance(extract_result.output, dict):
        for c in extract_result.output.get("claims", []):
            try:
                claims.append(PaperClaim(**c))
            except Exception:
                pass

    # Citation report
    citation_report = {}
    cite_result = step_results.get("CITE_VALIDATION")
    if cite_result and hasattr(cite_result, "output") and isinstance(cite_result.output, dict):
        citation_report = cite_result.output

    # Literature comparison
    literature_comparison = {}
    lit_result = step_results.get("BACKGROUND_LIT")
    if lit_result and hasattr(lit_result, "output") and isinstance(lit_result.output, dict):
        literature_comparison = lit_result.output

    # Novelty assessment
    novelty_assessment = None
    novelty_result = step_results.get("NOVELTY_CHECK")
    if novelty_result and hasattr(novelty_result, "output") and isinstance(novelty_result.output, dict):
        raw = {k: v for k, v in novelty_result.output.items() if k != "step"}
        if raw and not raw.get("skipped"):
            try:
                novelty_assessment = NoveltyAssessment(**raw)
            except Exception:
                pass

    # Integrity audit
    integrity_audit = {}
    integrity_result = step_results.get("INTEGRITY_AUDIT")
    if integrity_result and hasattr(integrity_result, "output") and isinstance(integrity_result.output, dict):
        integrity_audit = integrity_result.output

    # Contradiction findings
    contradiction_findings = {}
    contra_result = step_results.get("CONTRADICTION_CHECK")
    if contra_result and hasattr(contra_result, "output") and isinstance(contra_result.output, dict):
        contradiction_findings = contra_result.output

    # Methodology assessment
    methodology_assessment = None
    method_result = step_results.get("METHODOLOGY_REVIEW")
    if method_result and hasattr(method_result, "output") and isinstance(method_result.output, dict):
        try:
            methodology_assessment = MethodologyAssessment(**method_result.output)
        except Exception:
            pass

    # RCMXT scores
    rcmxt_scores = []
    rcmxt_result = step_results.get("EVIDENCE_GRADE")
    if rcmxt_result and hasattr(rcmxt_result, "output") and isinstance(rcmxt_result.output, dict):
        rcmxt_scores = rcmxt_result.output.get("scores", [])

    # Synthesis — try strict parse first, then map from generic research-director output
    synthesis = None
    synth_raw: dict = {}
    synth_result = step_results.get("SYNTHESIZE_REVIEW")
    if synth_result and hasattr(synth_result, "output") and isinstance(synth_result.output, dict):
        synth_raw = synth_result.output
        try:
            synthesis = PeerReviewSynthesis(**synth_raw)
        except Exception:
            # Generic research-director synthesis: map known fields → PeerReviewSynthesis
            summary_text = synth_raw.get("summary") or synth_raw.get("summary_assessment", "")
            confidence_text = synth_raw.get("confidence_assessment", "")
            # Extract decision from confidence_assessment or key_findings text
            decision: str = "major_revision"
            combined = " ".join([
                str(synth_raw.get("key_findings", [])),
                confidence_text,
            ]).lower()
            if "reject" in combined:
                decision = "reject"
            elif "minor revision" in combined or "minor_revision" in combined:
                decision = "minor_revision"
            elif "accept" in combined and "major" not in combined:
                decision = "accept"

            # Build ReviewComment list from key_findings + evidence_gaps + next_steps
            from app.models.peer_review import ReviewComment
            comments: list[ReviewComment] = []
            for item in synth_raw.get("key_findings", []):
                cat = "major" if any(kw in str(item).lower() for kw in ["major", "critical", "concern"]) else "minor"
                comments.append(ReviewComment(category=cat, section="General", comment=str(item)))
            for item in synth_raw.get("evidence_gaps", []):
                comments.append(ReviewComment(category="minor", section="Evidence", comment=str(item)))
            for item in synth_raw.get("next_steps", []):
                comments.append(ReviewComment(category="suggestion", section="Suggestions", comment=str(item)))

            try:
                synthesis = PeerReviewSynthesis(
                    summary_assessment=summary_text,
                    decision=decision,
                    decision_reasoning=confidence_text or summary_text[:500],
                    comments=comments,
                )
            except Exception:
                pass

    # Session manifest
    manifest = build_w8_session_manifest(instance, step_results)

    report = W8PeerReviewReport(
        paper_title=paper_title,
        claims_extracted=claims,
        citation_report=citation_report,
        literature_comparison=literature_comparison,
        novelty_assessment=novelty_assessment,
        integrity_audit=integrity_audit,
        contradiction_findings=contradiction_findings,
        methodology_assessment=methodology_assessment,
        rcmxt_scores=rcmxt_scores,
        synthesis=synthesis,
        session_manifest=manifest,
    )

    # Render markdown
    report.markdown_report = render_markdown_report(report)
    return report


def render_markdown_report(report: W8PeerReviewReport) -> str:
    """Render peer review report as Markdown."""
    lines: list[str] = []

    lines.append(f"# Peer Review Report: {report.paper_title}")
    lines.append(f"\n*Generated: {report.review_date.strftime('%Y-%m-%d %H:%M UTC')}*\n")

    # Summary Assessment
    if report.synthesis:
        lines.append("## Summary Assessment\n")
        lines.append(report.synthesis.summary_assessment)
        lines.append("")

        # Decision
        decision_display = report.synthesis.decision.replace("_", " ").title()
        lines.append(f"## Decision: **{decision_display}**\n")
        lines.append(report.synthesis.decision_reasoning)
        lines.append("")

        # Comments by category
        major = [c for c in report.synthesis.comments if c.category == "major"]
        minor = [c for c in report.synthesis.comments if c.category == "minor"]
        suggestions = [c for c in report.synthesis.comments if c.category == "suggestion"]
        questions = [c for c in report.synthesis.comments if c.category == "question"]

        if major:
            lines.append("## Major Comments\n")
            for i, c in enumerate(major, 1):
                lines.append(f"**{i}. [{c.section}]** {c.comment}")
                if c.evidence_basis:
                    lines.append(f"   *Basis: {c.evidence_basis}*")
                lines.append("")

        if minor:
            lines.append("## Minor Comments\n")
            for i, c in enumerate(minor, 1):
                lines.append(f"{i}. **[{c.section}]** {c.comment}")
            lines.append("")

        if suggestions:
            lines.append("## Suggestions\n")
            for i, c in enumerate(suggestions, 1):
                lines.append(f"{i}. **[{c.section}]** {c.comment}")
            lines.append("")

        if questions:
            lines.append("## Questions for Authors\n")
            for i, c in enumerate(questions, 1):
                lines.append(f"{i}. **[{c.section}]** {c.comment}")
            lines.append("")

    # Novelty Assessment (inserted before Methodology — high priority concern)
    if report.novelty_assessment:
        na = report.novelty_assessment
        score_label = (
            "High" if na.novelty_score >= 0.7
            else "Moderate" if na.novelty_score >= 0.4
            else "Low"
        )
        lines.append(f"## Novelty Assessment (Score: {na.novelty_score:.2f} — {score_label})\n")

        if na.already_established:
            lines.append("### Findings Already Established in Prior Work\n")
            for item in na.already_established:
                lines.append(f"- {item}")
            lines.append("")

        if na.unique_contributions:
            lines.append("### Unique Contributions\n")
            for item in na.unique_contributions:
                lines.append(f"- {item}")
            lines.append("")

        if na.landmark_papers_missing:
            lines.append("### Landmark Papers Authors Should Compare Against\n")
            for item in na.landmark_papers_missing:
                lines.append(f"- {item}")
            lines.append("")

        if na.novelty_recommendation:
            lines.append("### Novelty Recommendation\n")
            lines.append(na.novelty_recommendation)
            lines.append("")

    # Methodology Assessment
    if report.methodology_assessment:
        ma = report.methodology_assessment
        lines.append(f"## Methodology Assessment (Score: {ma.overall_methodology_score:.2f})\n")
        lines.append(f"**Study Design:** {ma.study_design_critique}\n")
        lines.append(f"**Statistical Methods:** {ma.statistical_methods}\n")
        lines.append(f"**Controls:** {ma.controls_adequacy}\n")
        lines.append(f"**Sample Size:** {ma.sample_size_assessment}\n")

        if ma.strengths:
            lines.append("**Strengths:**")
            for s in ma.strengths:
                lines.append(f"- {s}")
            lines.append("")

        if ma.potential_biases:
            lines.append("**Potential Biases:**")
            for b in ma.potential_biases:
                lines.append(f"- {b}")
            lines.append("")

        if ma.domain_specific_issues:
            lines.append("**Domain-Specific Issues:**")
            for d in ma.domain_specific_issues:
                lines.append(f"- {d}")
            lines.append("")

    # Evidence Quality
    if report.rcmxt_scores:
        lines.append(f"## Evidence Quality (RCMXT — {len(report.rcmxt_scores)} claims scored)\n")
        for score in report.rcmxt_scores[:10]:
            claim = score.get("claim", "")[:80]
            composite = score.get("composite", "N/A")
            lines.append(f"- **{claim}...** — Composite: {composite}")
        lines.append("")

    # Literature Cross-Check
    if report.literature_comparison:
        lines.append("## Literature Cross-Check\n")
        summary = report.literature_comparison.get("summary", "")
        if summary:
            lines.append(summary[:2000])
        else:
            # Fall back to listing retrieved papers
            papers = report.literature_comparison.get("papers", [])
            total = report.literature_comparison.get("total_found", len(papers))
            dbs = ", ".join(report.literature_comparison.get("databases_searched", []))
            lines.append(f"Retrieved {total} related paper(s) from {dbs}:\n")
            for p in papers[:10]:
                title = p.get("title", "Unknown")
                authors = p.get("authors", [])
                year = p.get("year", "")
                pmid = p.get("pmid", "")
                doi = p.get("doi", "")
                ref = f"PMID:{pmid}" if pmid else (f"DOI:{doi}" if doi else "")
                author_str = f"{authors[0]} et al." if authors else ""
                lines.append(f"- **{title}** — {author_str} {year} {ref}")
        lines.append("")

    # Citation Integrity
    if report.citation_report:
        total = report.citation_report.get("total_citations", 0)
        verified = report.citation_report.get("verified", 0)
        rate = report.citation_report.get("verification_rate", 0)
        notes = report.citation_report.get("notes", [])
        embedded = report.citation_report.get("embedded_dois_found", 0)
        lines.append("## Citation Integrity\n")
        if notes:
            for note in notes:
                lines.append(f"> ⚠️ {note}")
            lines.append("")
        if total > 0:
            lines.append(f"- Total citations: {total}")
            lines.append(f"- Verified: {verified} ({rate:.0%})")
        if embedded > 0:
            lines.append(f"- Embedded DOIs found in text: {embedded}")
        issues = report.citation_report.get("issues", [])
        if issues:
            lines.append(f"- Issues: {len(issues)}")
            for issue in issues[:5]:
                lines.append(f"  - {issue.get('issue_type', '?')}: {issue.get('citation_ref', '?')}")
        lines.append("")

    # AI Disclosure
    lines.append("## AI Disclosure\n")
    lines.append(
        "This review was generated with assistance from BioTeam-AI (W8 Paper Review pipeline). "
        "The AI system performed claim extraction, citation validation, literature cross-referencing, "
        "integrity auditing, contradiction detection, methodology assessment, and evidence grading. "
        "The final review was synthesized by AI and should be reviewed and edited by the human reviewer "
        "before submission to the journal."
    )

    cost = report.session_manifest.get("total_cost", 0)
    if cost:
        lines.append(f"\n*Pipeline cost: ${cost:.4f}*")

    return "\n".join(lines)


def generate_w8_report(
    instance: WorkflowInstance,
    step_results: dict[str, AgentOutput],
    paper_title: str = "",
) -> AgentOutput:
    """Generate final W8 report as AgentOutput (REPORT step)."""
    report = build_peer_review_report(instance, step_results, paper_title)

    return AgentOutput(
        agent_id="code_only",
        output=report.model_dump(mode="json"),
        output_type="W8PeerReviewReport",
        summary=f"W8 Peer Review: {paper_title[:80]} — {report.synthesis.decision if report.synthesis else 'incomplete'}",
    )
