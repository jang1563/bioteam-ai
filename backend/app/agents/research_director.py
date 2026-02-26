"""Research Director Agent — orchestrates all research workflows.

Dual-mode:
- Routing mode (Sonnet): Classifies queries, routes to specialists
- Synthesis mode (Opus): Merges multi-agent outputs into coherent conclusions

Phase 1 implements routing mode only.
"""

from __future__ import annotations

from typing import Literal

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field

# === Output Models ===


class QueryClassification(BaseModel):
    """Classification of an incoming query."""

    type: Literal["simple_query", "needs_workflow"]
    reasoning: str = Field(description="Why this classification was chosen")
    target_agent: str | None = Field(
        default=None,
        description="Agent ID for simple_query (e.g., 't02_transcriptomics')",
    )
    workflow_type: str | None = Field(
        default=None,
        description="Workflow template for needs_workflow (e.g., 'W1')",
    )


class SynthesisReport(BaseModel):
    """Synthesized output from multiple agent results."""

    title: str
    summary: str
    key_findings: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    contradictions_noted: list[str] = Field(default_factory=list)
    confidence_assessment: str = ""
    next_steps: list[str] = Field(default_factory=list)
    sources_cited: list[str] = Field(default_factory=list)


# === Agent Implementation ===


class ResearchDirectorAgent(BaseAgent):
    """Orchestrator agent for all research workflows.

    Phase 1: Routing mode — classifies queries and routes to specialists.
    Phase 2+: + Synthesis mode — merges multi-agent outputs (uses Opus).
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Classify a query and route it appropriately."""
        return await self.classify_query(context)

    async def classify_query(self, context: ContextPackage) -> AgentOutput:
        """Classify an incoming query as simple or needing a workflow.

        Uses Sonnet tier for fast, cost-effective classification.
        """
        messages = [
            {
                "role": "user",
                "content": (
                    f"Classify this research query:\n\n"
                    f"{context.task_description}\n\n"
                    f"Determine if this is a simple_query (answerable by 1 specialist) "
                    f"or needs_workflow (requires a full research pipeline)."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier="sonnet",  # Always Sonnet for routing
            response_model=QueryClassification,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="QueryClassification",
            summary=f"{result.type}: {result.reasoning[:100]}",
            llm_response=meta,
        )

    async def synthesize(self, context: ContextPackage) -> AgentOutput:
        """Synthesize outputs from multiple agents into a coherent report.

        Uses Opus tier for high-quality synthesis.
        """
        # Build synthesis prompt from prior step outputs
        prior_outputs = "\n\n".join(
            f"--- Agent Output ---\n{str(o)}" for o in context.prior_step_outputs
        )

        # Build paper grounding section from metadata (injected by W1 runner)
        papers_list = context.metadata.get("available_papers", "")
        papers_section = ""
        grounding_rules = ""
        if papers_list:
            papers_section = (
                f"## Available Papers (you may ONLY cite from this list)\n"
                f"{papers_list}\n\n"
            )
            grounding_rules = (
                "\n\nGROUNDING RULES:\n"
                "1. Only cite papers from the Available Papers list above.\n"
                "2. Use the exact PMID/DOI from the list when citing.\n"
                "3. If you know of a relevant paper NOT in the list, note it as "
                "'(not retrieved in current search)' — do NOT present it as a cited source.\n"
                "4. In sources_cited, include ONLY papers from the Available Papers list."
            )

        messages = [
            {
                "role": "user",
                "content": (
                    f"Research question: {context.task_description}\n\n"
                    f"{papers_section}"
                    f"Agent outputs to synthesize:\n{prior_outputs}\n\n"
                    f"Synthesize these into a coherent report.{grounding_rules}"
                ),
            }
        ]

        # Use secondary model tier (Opus) for synthesis
        model_tier = self.spec.model_tier_secondary or self.model_tier

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=model_tier,
            response_model=SynthesisReport,
            system=self.system_prompt_cached,
            max_tokens=16384,  # Synthesis of many papers produces large structured output
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="SynthesisReport",
            summary=result.summary[:200],
            llm_response=meta,
        )
