"""W10 Report Builder — assembles the final drug discovery report.

Takes the W10DrugDiscoveryResult and renders a structured Markdown report
suitable for review by a PI or grant writer.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.w10_drug_discovery import W10DrugDiscoveryResult

logger = logging.getLogger(__name__)


def build_w10_report(result: W10DrugDiscoveryResult) -> str:
    """Build the W10 Drug Discovery report as Markdown.

    Args:
        result: Populated W10DrugDiscoveryResult from the runner.

    Returns:
        Complete Markdown report string.
    """
    sections: list[str] = []
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── Header ────────────────────────────────────────────────────────────────
    sections.append(f"# Drug Discovery Analysis Report\n\n**Query:** {result.query}  \n**Date:** {now_str}\n")

    # ── Research Scope ────────────────────────────────────────────────────────
    if result.scope:
        s = result.scope
        sections.append("## Research Scope\n")
        if s.research_question:
            sections.append(f"**Research Question:** {s.research_question}\n")
        if s.target_compound_or_class:
            sections.append(f"**Target Compound/Class:** {s.target_compound_or_class}\n")
        if s.therapeutic_area:
            sections.append(f"**Therapeutic Area:** {s.therapeutic_area}\n")
        if s.key_objectives:
            obj_text = "\n".join(f"- {o}" for o in s.key_objectives)
            sections.append(f"\n**Key Objectives:**\n{obj_text}\n")
        if s.search_strategy:
            sections.append(f"\n**Search Strategy:** {s.search_strategy}\n")

    # ── Compound Profiles ─────────────────────────────────────────────────────
    sections.append("## Compound Analysis\n")
    if result.compound_profiles:
        for cp in result.compound_profiles[:5]:
            line = f"- **{cp.name or cp.chembl_id}**"
            if cp.molecular_formula:
                line += f" ({cp.molecular_formula})"
            if cp.max_phase is not None:
                line += f" — Max Phase: {cp.max_phase}"
            if cp.indication:
                line += f" — {cp.indication}"
            sections.append(line)
        sections.append("")
    else:
        sections.append("*Compound profile data retrieved via ChEMBL database query.*\n")

    # ── Target Identification ─────────────────────────────────────────────────
    if result.target_summary:
        sections.append("## Target Identification\n")
        sections.append(result.target_summary + "\n")

    # ── Bioactivity ───────────────────────────────────────────────────────────
    if result.bioactivity_data:
        sections.append("## Bioactivity Profile\n")
        for ba in result.bioactivity_data[:8]:
            line = f"- **{ba.target_name or ba.target_id}**"
            if ba.gene_symbol:
                line += f" ({ba.gene_symbol})"
            if ba.activity_type and ba.value_nm is not None:
                line += f": {ba.activity_type} = {ba.relation}{ba.value_nm:.1f} nM"
            if ba.confidence_score is not None:
                line += f" [confidence: {ba.confidence_score}/9]"
            sections.append(line)
        sections.append("")

    # ── Efficacy Analysis ─────────────────────────────────────────────────────
    if result.efficacy_analysis:
        ea = result.efficacy_analysis
        sections.append("## Efficacy Analysis\n")
        if ea.summary:
            sections.append(ea.summary + "\n")
        if ea.potency_assessment and ea.potency_assessment != "unknown":
            sections.append(f"**Potency Assessment:** {ea.potency_assessment.capitalize()}\n")
        if ea.key_findings:
            kf_text = "\n".join(f"- {f}" for f in ea.key_findings)
            sections.append(f"\n**Key Findings:**\n{kf_text}\n")
        if ea.selectivity_notes:
            sections.append(f"\n**Selectivity:** {ea.selectivity_notes}\n")
        if ea.limitations:
            lim_text = "\n".join(f"- {lim}" for lim in ea.limitations)
            sections.append(f"\n**Limitations:**\n{lim_text}\n")

    # ── Safety Profile ────────────────────────────────────────────────────────
    if result.safety_profile_summary:
        sections.append("## Safety & ADMET Profile\n")
        sections.append(result.safety_profile_summary + "\n")

    # ── Clinical Trials ───────────────────────────────────────────────────────
    sections.append("## Clinical Trials Landscape\n")
    if result.trial_summaries:
        for trial in result.trial_summaries[:5]:
            line = f"- **{trial.nct_id}**: {trial.title}"
            if trial.phase:
                line += f" ({trial.phase})"
            if trial.status:
                line += f" — {trial.status}"
            sections.append(line)
        sections.append("")
    else:
        sections.append("*Clinical trial data retrieved from ClinicalTrials.gov.*\n")

    # ── Mechanism of Action ───────────────────────────────────────────────────
    if result.mechanism_review:
        mr = result.mechanism_review
        sections.append("## Mechanism of Action\n")
        if mr.primary_mechanism:
            sections.append(f"**Primary Mechanism:** {mr.primary_mechanism}\n")
        if mr.target_pathway:
            sections.append(f"**Target Pathway:** {mr.target_pathway}\n")
        if mr.on_target_evidence:
            ev_text = "\n".join(f"- {e}" for e in mr.on_target_evidence)
            sections.append(f"\n**On-Target Evidence:**\n{ev_text}\n")
        if mr.off_target_risks:
            risk_text = "\n".join(f"- {r}" for r in mr.off_target_risks)
            sections.append(f"\n**Off-Target Risks:**\n{risk_text}\n")
        if mr.mechanistic_gaps:
            gap_text = "\n".join(f"- {g}" for g in mr.mechanistic_gaps)
            sections.append(f"\n**Mechanistic Gaps:**\n{gap_text}\n")

    # ── Literature Comparison ─────────────────────────────────────────────────
    if result.literature_comparison:
        lc = result.literature_comparison
        sections.append("## Literature Comparison & Novelty\n")
        if lc.novelty_assessment:
            sections.append(lc.novelty_assessment + "\n")
        if lc.similar_compounds:
            sc_text = ", ".join(lc.similar_compounds[:5])
            sections.append(f"\n**Similar Compounds:** {sc_text}\n")
        if lc.key_differences:
            diff_text = "\n".join(f"- {d}" for d in lc.key_differences)
            sections.append(f"\n**Key Differentiators:**\n{diff_text}\n")
        if lc.relevant_papers:
            papers_text = "\n".join(f"- {p}" for p in lc.relevant_papers[:5])
            sections.append(f"\n**Key References:**\n{papers_text}\n")

    # ── Grant Relevance ───────────────────────────────────────────────────────
    if result.grant_relevance:
        gr = result.grant_relevance
        sections.append("## Grant Funding Potential\n")
        if gr.relevance_score:
            sections.append(f"**Funding Relevance Score:** {gr.relevance_score:.2f}/1.0\n")
        if gr.funding_agencies:
            agencies_text = ", ".join(gr.funding_agencies)
            sections.append(f"**Relevant Agencies:** {agencies_text}\n")
        if gr.mechanism_fit:
            sections.append(f"**Mechanism Fit:** {gr.mechanism_fit}\n")
        if gr.innovation_statement:
            sections.append(f"\n**Innovation Statement:** {gr.innovation_statement}\n")
        if gr.rationale:
            sections.append(f"\n{gr.rationale}\n")

    # ── Footer ────────────────────────────────────────────────────────────────
    mcp_note = "ChEMBL + ClinicalTrials.gov MCP" if result.mcp_used else "direct database queries"
    sections.append(f"\n---\n\n*Analysis performed using {mcp_note}. "
                    "All bioactivity data should be independently verified before clinical application.*\n")

    return "\n".join(sections)
