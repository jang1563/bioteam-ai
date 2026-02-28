"""CLI entry point for W6 Contradiction Analysis skill.

Usage:
    cd backend && uv run python -m app.skills.w6_cli --topic "research topic" --budget 2.0

Wraps the W6 Ambiguity Engine runner for CLI and Agent Skills invocation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def run_w6(topic: str, budget: float = 2.0) -> dict:
    """Run the W6 Ambiguity/Contradiction Analysis pipeline.

    Args:
        topic: Research topic to analyze for contradictions.
        budget: Maximum budget in USD.

    Returns:
        Pipeline result dict with contradictions and hypotheses.
    """
    from app.agents.registry import create_registry
    from app.llm.layer import LLMLayer
    from app.memory.semantic import SemanticMemory
    from app.workflows.runners.w6_ambiguity import W6AmbiguityRunner

    llm = LLMLayer()
    memory = SemanticMemory()
    registry = create_registry(llm, memory)
    runner = W6AmbiguityRunner(registry=registry, llm=llm, memory=memory)

    result = await runner.run(
        topic=topic,
        budget=budget,
    )

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="BioTeam-AI W6 Contradiction Analysis")
    parser.add_argument("--topic", "-t", required=True, help="Research topic")
    parser.add_argument("--budget", "-b", type=float, default=2.0, help="Max budget (USD)")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    args = parser.parse_args()

    logger.info("Starting W6 Contradiction Analysis: %s (budget: $%.2f)", args.topic, args.budget)

    result = asyncio.run(run_w6(args.topic, args.budget))

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, default=str)
        logger.info("Results written to %s", args.output)
    else:
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
