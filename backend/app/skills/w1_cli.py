"""CLI entry point for W1 Literature Review skill.

Usage:
    cd backend && uv run python -m app.skills.w1_cli --query "research question" --budget 5.0

This wraps the existing W1LiteratureReviewRunner for invocation from
Agent Skills (Claude Code, Cursor, etc.) or direct CLI usage.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def run_w1(query: str, budget: float = 5.0) -> dict:
    """Run the W1 Literature Review pipeline.

    Args:
        query: Research question or topic.
        budget: Maximum budget in USD.

    Returns:
        Complete pipeline result dict.
    """
    from app.agents.registry import create_registry
    from app.llm.layer import LLMLayer
    from app.memory.semantic import SemanticMemory
    from app.workflows.runners.w1_literature import W1LiteratureReviewRunner

    llm = LLMLayer()
    memory = SemanticMemory()
    registry = create_registry(llm, memory)
    runner = W1LiteratureReviewRunner(registry=registry, llm=llm, memory=memory)

    result = await runner.run(
        query=query,
        budget=budget,
    )

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="BioTeam-AI W1 Literature Review")
    parser.add_argument("--query", "-q", required=True, help="Research question")
    parser.add_argument("--budget", "-b", type=float, default=5.0, help="Max budget (USD)")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    args = parser.parse_args()

    logger.info("Starting W1 Literature Review: %s (budget: $%.2f)", args.query, args.budget)

    result = asyncio.run(run_w1(args.query, args.budget))

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, default=str)
        logger.info("Results written to %s", args.output)
    else:
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
