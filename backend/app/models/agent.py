"""Agent models.

Includes: AgentSpec, AgentStatus, AgentOutput (the key missing piece from plan).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.config import ModelTier


class AgentSpec(BaseModel):
    """Agent specification loaded from YAML files.

    Defines an agent's identity, capabilities, and configuration.
    Stored in backend/app/agents/specs/*.yaml.
    """

    id: str                         # e.g., "research_director"
    name: str                       # e.g., "Research Director"
    tier: Literal["strategic", "domain_expert", "qa", "engine"]
    model_tier: ModelTier           # "opus", "sonnet", or "haiku"
    model_tier_secondary: ModelTier | None = None  # For dual-mode agents (e.g., RD: sonnet for routing, opus for synthesis)
    division: str | None = None     # e.g., "wet_to_dry", "computation", "translation", "cross_cutting"
    criticality: Literal["critical", "optional"] = "optional"

    # Prompt
    system_prompt_file: str         # Path to .md file (relative to agents/prompts/)
    output_schemas: list[str] = Field(default_factory=list)  # Pydantic model class names this agent can produce

    # Capabilities
    tools: list[str] = Field(default_factory=list)        # Tool names available to this agent
    mcp_access: list[str] = Field(default_factory=list)    # MCP server names this agent can use
    literature_access: bool = False   # Can access PubMed/S2/bioRxiv

    # Examples
    few_shot_examples: list[dict] = Field(default_factory=list)

    # Failure handling
    failure_modes: list[str] = Field(default_factory=list)  # Known failure patterns
    degradation_mode: str | None = None  # What happens when this agent is unavailable

    version: str = "0.1.0"


class AgentStatus(BaseModel):
    """Runtime status of an agent."""

    agent_id: str
    state: Literal["idle", "busy", "unavailable"] = "idle"
    current_workflow_id: str | None = None
    current_step_id: str | None = None
    consecutive_failures: int = 0
    last_active: datetime | None = None
    total_calls: int = 0
    total_cost: float = 0.0


class AgentOutput(BaseModel):
    """Standardized output from any agent execution.

    This is the key missing piece identified in the Day 0 review.
    Every agent.run() call returns this, and it is stored in StepCheckpoint.result.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str
    step_id: str | None = None
    workflow_id: str | None = None

    # The actual result — structured data from Instructor
    output: Any = None              # The Pydantic model instance (serialized to dict)
    output_type: str = ""           # Class name of the output model

    # Text summary for display
    summary: str = ""

    # Metadata
    model_tier: ModelTier = "sonnet"
    model_version: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cost: float = 0.0
    duration_ms: int = 0

    # Error handling
    error: str | None = None
    retry_count: int = 0

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_success(self) -> bool:
        return self.error is None
