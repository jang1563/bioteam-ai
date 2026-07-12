"""Phase 0 Pilot: Run W8 on 5 eLife papers and generate comparison report.

Usage:
    uv run python backend/scripts/run_w8_pilot.py [--paper-id ID]

Outputs:
    backend/data/phase0_pilot/{id}_w8_result.json   ← W8 raw output
    backend/data/phase0_pilot/pilot_comparison.md   ← Human vs W8 comparison report
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("w8_pilot")

PILOT_DIR = Path(__file__).parent.parent / "data" / "phase0_pilot"

PILOT_PAPERS = {
    "85560": "Multimodal HLA-I regulation by CMV US10 (microbiology)",
    "83069": "GAS6 macrophage efferocytosis osteoarthritis (immunology)",
    "11058": "TSC2-Rheb arginine mTORC1 (cell-biology)",
    "107189": "Accelerated evolution Pseudomonas aeruginosa (evolutionary)",
    "00969": "BRAF inhibitors JNK signaling apoptosis (cancer)",
}


async def run_w8_on_paper(paper_id: str, budget: float = 2.0) -> dict:
    """Run W8 pipeline on a single paper PDF."""
    from app.agents.registry import create_registry
    from app.llm.layer import LLMLayer
    from app.workflows.runners.w8_paper_review import W8PaperReviewRunner

    pdf_path = PILOT_DIR / f"{paper_id}.pdf"
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    llm = LLMLayer()
    registry = create_registry(llm, memory=None)

    runner = W8PaperReviewRunner(
        registry=registry,
        llm_layer=llm,
    )

    logger.info("Running W8 on paper %s: %s", paper_id, PILOT_PAPERS.get(paper_id, ""))
    result = await runner.run(
        pdf_path=str(pdf_path),
        budget=budget,
        skip_human_checkpoint=True,  # batch mode: skip human pause
    )

    return result


def load_ground_truth(paper_id: str) -> dict:
    """Load eLife decision letter and author response as ground truth."""
    gt_path = PILOT_DIR / f"{paper_id}.json"
    if not gt_path.exists():
        return {}
    with open(gt_path) as f:
        return json.load(f)


def extract_w8_concerns(result: dict) -> list[str]:
    """Flatten W8 output into a list of concern strings for comparison."""
    concerns = []
    steps = result.get("step_results", {})

    # From synthesis.comments (PeerReviewSynthesis format)
    synth = steps.get("SYNTHESIZE_REVIEW", {})
    if isinstance(synth, dict):
        output = synth.get("output", {})
        # PeerReviewSynthesis format
        for comment in output.get("comments", []) or []:
            cat = comment.get("category", "")
            text = comment.get("comment", "")
            section = comment.get("section", "")
            concerns.append(f"[{cat.upper()}] ({section}) {text}")
        # ResearchDirector generic format (key_findings, evidence_gaps)
        for kf in output.get("key_findings", []) or []:
            if isinstance(kf, str) and len(kf) > 30:
                concerns.append(f"[SYNTHESIS/FINDING] {kf[:300]}")
        for eg in output.get("evidence_gaps", []) or []:
            if isinstance(eg, str) and len(eg) > 20:
                concerns.append(f"[SYNTHESIS/GAP] {eg[:300]}")

    # From methodology assessment
    method = steps.get("METHODOLOGY_REVIEW", {})
    if isinstance(method, dict):
        output = method.get("output", {})
        for field in ["study_design_critique", "statistical_methods", "controls_adequacy", "sample_size_assessment"]:
            val = output.get(field, "")
            if val and len(val) > 30:
                concerns.append(f"[METHODOLOGY/{field}] {val[:300]}")
        for bias in output.get("potential_biases", []):
            concerns.append(f"[BIAS] {bias}")
        for rep in output.get("reproducibility_concerns", []):
            concerns.append(f"[REPRODUCIBILITY] {rep}")

    # From integrity audit
    integrity = steps.get("INTEGRITY_AUDIT", {})
    if isinstance(integrity, dict):
        output = integrity.get("output", {})
        issues = output.get("issues", [])
        for issue in issues[:5]:
            concerns.append(f"[INTEGRITY] {issue}")

    # From contradiction check
    contra = steps.get("CONTRADICTION_CHECK", {})
    if isinstance(contra, dict):
        output = contra.get("output", {})
        if output.get("summary"):
            concerns.append(f"[CONTRADICTION] {output['summary'][:200]}")

    return concerns


def generate_comparison_report(paper_id: str, w8_result: dict, ground_truth: dict) -> str:
    """Generate a markdown comparison between W8 output and human review."""
    title = ground_truth.get("title", paper_id)
    subjects = ground_truth.get("subjects", [])
    dl = ground_truth.get("decision_letter", "N/A")
    ar_preview = ground_truth.get("author_response", "")[:500]

    w8_concerns = extract_w8_concerns(w8_result)

    # W8 decision
    synth_output = w8_result.get("step_results", {}).get("SYNTHESIZE_REVIEW", {}).get("output", {})
    # Support both PeerReviewSynthesis and ResearchDirector generic format
    w8_decision = synth_output.get("decision", synth_output.get("confidence_assessment", "N/A"))
    w8_summary = (synth_output.get("summary_assessment") or synth_output.get("summary", ""))[:600]
    w8_method_score = w8_result.get("step_results", {}).get("METHODOLOGY_REVIEW", {}).get("output", {}).get("overall_methodology_score", "N/A")

    lines = [
        f"# W8 Pilot Review: {paper_id}",
        f"**Title:** {title}",
        f"**Subjects:** {', '.join(subjects)}",
        "",
        "---",
        "",
        "## W8 Output",
        f"**Decision:** `{w8_decision}`",
        f"**Methodology score:** `{w8_method_score}`",
        "",
        "**Summary assessment:**",
        w8_summary,
        "",
        f"**W8 concerns identified ({len(w8_concerns)}):**",
    ]
    for c in w8_concerns:
        lines.append(f"- {c[:200]}")

    lines += [
        "",
        "---",
        "",
        "## Human Reviewer Decision Letter",
        "```",
        dl[:2000],
        "```",
        "",
        "## Author Response (preview)",
        "```",
        ar_preview,
        "```",
        "",
        "---",
        "",
        "## Manual Comparison (fill in after reading)",
        "",
        "### W8 catches (✓ / ✗ for each human concern):",
        "<!-- Fill in manually after reviewing both outputs -->",
        "",
        "### W8 missed (human concerns not in W8 output):",
        "- [ ] ...",
        "",
        "### W8 over-flagged (W8 concerns NOT in human review):",
        "- [ ] ...",
        "",
        "### Notes:",
        "",
    ]

    return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(description="W8 Phase 0 Pilot")
    parser.add_argument("--paper-id", help="Run only this paper ID (default: all)")
    parser.add_argument("--budget", type=float, default=2.0, help="Budget per paper in USD")
    parser.add_argument("--report-only", action="store_true", help="Generate report from existing W8 results only")
    args = parser.parse_args()

    paper_ids = [args.paper_id] if args.paper_id else list(PILOT_PAPERS.keys())
    comparison_sections = []

    for paper_id in paper_ids:
        gt = load_ground_truth(paper_id)
        result_path = PILOT_DIR / f"{paper_id}_w8_result.json"

        if args.report_only and result_path.exists():
            logger.info("Loading existing W8 result for %s", paper_id)
            with open(result_path) as f:
                result = json.load(f)
        else:
            try:
                result = await run_w8_on_paper(paper_id, budget=args.budget)
                # Serialize instance separately (not JSON-serializable as-is)
                serializable = {
                    "paper_id": paper_id,
                    "step_results": result.get("step_results", {}),
                    "paused_at": result.get("paused_at"),
                }
                with open(result_path, "w") as f:
                    json.dump(serializable, f, indent=2, default=str)
                logger.info("Saved W8 result to %s", result_path)
                result = serializable
            except Exception as e:
                logger.error("W8 failed for %s: %s", paper_id, e)
                result = {"paper_id": paper_id, "step_results": {}, "error": str(e)}

        section = generate_comparison_report(paper_id, result, gt)
        comparison_sections.append(section)

        # Print W8 concerns for immediate review
        concerns = extract_w8_concerns(result)
        print(f"\n{'='*60}")
        print(f"[{paper_id}] {gt.get('title', '')[:60]}")
        print(f"W8 decision: {result.get('step_results', {}).get('SYNTHESIZE_REVIEW', {}).get('output', {}).get('decision', 'N/A')}")
        print(f"W8 concerns ({len(concerns)}):")
        for c in concerns[:10]:
            print(f"  {c[:120]}")

    # Write full comparison report
    report_path = PILOT_DIR / "pilot_comparison.md"
    with open(report_path, "w") as f:
        f.write("# Phase 0 Pilot: W8 vs. Human Reviewer Comparison\n\n")
        f.write(f"Papers reviewed: {len(paper_ids)}\n\n")
        f.write("---\n\n")
        f.write("\n\n---\n\n".join(comparison_sections))

    print(f"\n\nComparison report saved to: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
