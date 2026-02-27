"""CLI entry point for W8 Paper Review skill.

Usage:
    cd backend && uv run python -m app.skills.w8_cli --pdf paper.pdf --budget 3.0

Wraps the W8 Paper Review runner for CLI and Agent Skills invocation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def run_w8(pdf_path: str, budget: float = 3.0) -> dict:
    """Run the W8 Paper Review pipeline.

    Args:
        pdf_path: Path to the paper PDF file.
        budget: Maximum budget in USD.

    Returns:
        Pipeline result dict with review report.
    """
    from app.llm.layer import LLMLayer
    from app.memory.semantic import SemanticMemory
    from app.agents.registry import create_registry
    from app.workflows.runners.w8_paper_review import W8PaperReviewRunner

    llm = LLMLayer()
    memory = SemanticMemory()
    registry = create_registry(llm, memory)
    runner = W8PaperReviewRunner(
        registry=registry, llm_layer=llm, memory=memory,
    )

    result = await runner.run(
        pdf_path=pdf_path,
        budget=budget,
    )

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="BioTeam-AI W8 Paper Review")
    parser.add_argument("--pdf", "-p", required=True, help="Path to paper (PDF or DOCX)")
    parser.add_argument("--budget", "-b", type=float, default=3.0, help="Max budget (USD)")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--markdown", "-m", help="Output Markdown report file path")
    args = parser.parse_args()

    logger.info("Starting W8 Paper Review: %s (budget: $%.2f)", args.pdf, args.budget)

    result = asyncio.run(run_w8(args.pdf, args.budget))

    # Extract markdown report if available
    step_results = result.get("step_results", {})
    report_data = step_results.get("REPORT", {})
    markdown_report = ""
    if isinstance(report_data, dict):
        markdown_report = report_data.get("markdown_report", "")

    if args.markdown and markdown_report:
        with open(args.markdown, "w") as f:
            f.write(markdown_report)
        logger.info("Markdown report written to %s", args.markdown)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, default=str)
        logger.info("Results written to %s", args.output)
    else:
        # Print markdown if available, otherwise JSON
        if markdown_report:
            print(markdown_report)
        else:
            print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
