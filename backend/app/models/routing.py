"""Routing models — auto-recommend next workflow based on results.

Defines routing rules, recommendations, and routing session tracking.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

# === Routing Rules ===


class RoutingRule(BaseModel):
    """A rule that maps workflow outcomes to recommended next workflows.

    Condition types:
    - contradiction_count: Number of contradictions found > threshold
    - integrity_severity: Max severity level in integrity findings
    - completion: Workflow completed successfully
    - hypothesis_score: Top hypothesis confidence > threshold
    - analysis_complete: Data analysis step completed
    - literature_gaps: Review identified gaps in literature
    - gene_issues: Gene name checker found issues
    """

    source_template: str  # e.g. "W1"
    condition_type: str  # e.g. "contradiction_count"
    condition_params: dict = Field(default_factory=dict)  # e.g. {"threshold": 2}
    target_template: str  # e.g. "W6"
    priority: int = 0  # Higher = evaluated first
    auto_execute: bool = False  # Auto-execute if confidence > 0.8
    description: str = ""


class RoutingRecommendation(BaseModel):
    """A recommendation for the next workflow to run."""

    target_template: str  # e.g. "W6"
    reason: str  # Human-readable explanation
    confidence: float = 0.0  # 0.0-1.0
    auto_execute: bool = False
    params: dict = Field(default_factory=dict)  # Params to pass to next workflow
    rule_id: str | None = None  # Which rule triggered this


class RoutingDecision(BaseModel):
    """Record of a routing decision (accepted or rejected)."""

    source_workflow_id: str
    source_template: str
    target_template: str
    target_workflow_id: str | None = None  # Set when accepted
    recommendation: RoutingRecommendation
    action: Literal["accepted", "rejected", "auto_executed"] = "accepted"
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# === Default Rules ===

DEFAULT_ROUTING_RULES: list[RoutingRule] = [
    # W1 → W6: contradictions found
    RoutingRule(
        source_template="W1",
        condition_type="contradiction_count",
        condition_params={"threshold": 2},
        target_template="W6",
        priority=10,
        description="Route to Ambiguity Analysis when >2 contradictions found",
    ),
    # W1 → W7: integrity findings at error level
    RoutingRule(
        source_template="W1",
        condition_type="integrity_severity",
        condition_params={"min_severity": "error"},
        target_template="W7",
        priority=9,
        description="Route to Integrity Audit when error-level integrity findings detected",
    ),
    # W1 → W2: standard flow on successful completion
    RoutingRule(
        source_template="W1",
        condition_type="completion",
        condition_params={},
        target_template="W2",
        priority=1,
        description="Route to Hypothesis Generation after successful literature review",
    ),
    # W2 → W3: top hypothesis scored high
    RoutingRule(
        source_template="W2",
        condition_type="hypothesis_score",
        condition_params={"threshold": 0.7},
        target_template="W3",
        priority=5,
        description="Route to Data Analysis when top hypothesis confidence >0.7",
    ),
    # W3 → W4: analysis complete, manuscript-ready
    RoutingRule(
        source_template="W3",
        condition_type="completion",
        condition_params={},
        target_template="W4",
        priority=3,
        description="Route to Manuscript Drafting after data analysis",
    ),
    # W3 → W5: results are grant-relevant
    RoutingRule(
        source_template="W3",
        condition_type="completion",
        condition_params={},
        target_template="W5",
        priority=2,
        description="Route to Grant Writing after data analysis (alternative)",
    ),
    # W8 → W1: review identified literature gaps
    RoutingRule(
        source_template="W8",
        condition_type="literature_gaps",
        condition_params={"threshold": 1},
        target_template="W1",
        priority=6,
        description="Route to Literature Review when peer review identified gaps",
    ),
    # W9 → W7: gene name issues found
    RoutingRule(
        source_template="W9",
        condition_type="gene_issues",
        condition_params={"threshold": 1},
        target_template="W7",
        priority=7,
        description="Route to Integrity Audit when gene name issues found in analysis",
    ),
    # Any → W7: general gene check failure
    RoutingRule(
        source_template="*",
        condition_type="gene_issues",
        condition_params={"threshold": 1},
        target_template="W7",
        priority=8,
        description="Route to Integrity Audit when gene name issues found (any workflow)",
    ),
]
