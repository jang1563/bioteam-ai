"""Refinement models — quality critique, config, and result tracking.

Used by the iterative Self-Refine loop:
  produce → critique → revise → critique → ... → final output

Quality dimensions are tuned for biology research outputs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class QualityCritique(BaseModel):
    """Structured quality critique produced by the LLM scorer.

    Dimensions are specific to biology research analysis.
    Each score is 0.0 (poor) to 1.0 (excellent).
    """

    rigor_score: float = Field(
        ge=0.0, le=1.0,
        description="Are claims well-supported by evidence? Are methods sound?",
    )
    completeness_score: float = Field(
        ge=0.0, le=1.0,
        description="Are all aspects of the question addressed?",
    )
    clarity_score: float = Field(
        ge=0.0, le=1.0,
        description="Is the output clear, well-structured, and actionable?",
    )
    accuracy_score: float = Field(
        ge=0.0, le=1.0,
        description="Are biological facts, gene names, pathway references correct?",
    )
    overall_score: float = Field(
        ge=0.0, le=1.0,
        description="Holistic quality score considering all dimensions.",
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Specific problems found that need fixing.",
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Concrete, actionable improvement suggestions.",
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="What was done well — preserve these in revision.",
    )


class RefinementConfig(BaseModel):
    """Configuration for the iterative refinement loop."""

    max_iterations: int = Field(default=2, ge=1, le=5)
    quality_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0,
        description="Minimum overall_score to pass without revision.",
    )
    budget_cap: float = Field(
        default=1.0, ge=0.0,
        description="Maximum additional cost ($) for all refinement iterations.",
    )
    min_improvement: float = Field(
        default=0.05, ge=0.0,
        description="Stop if score improvement < this between iterations (diminishing returns).",
    )
    scorer_model: str = Field(
        default="haiku",
        description="Model tier for the quality scorer (haiku is cheap + fast).",
    )

    @field_validator("scorer_model")
    @classmethod
    def validate_scorer_model(cls, v: str) -> str:
        valid = {"opus", "sonnet", "haiku"}
        if v not in valid:
            raise ValueError(f"scorer_model must be one of {valid}, got '{v}'")
        return v


class RefinementResult(BaseModel):
    """Outcome of a refinement cycle."""

    iterations_used: int = 0
    quality_scores: list[float] = Field(default_factory=list)
    critiques: list[QualityCritique] = Field(default_factory=list)
    total_cost: float = 0.0
    stopped_reason: str = ""
    # "quality_met" | "max_iterations" | "budget_exhausted" | "diminishing_returns" | "skipped"
