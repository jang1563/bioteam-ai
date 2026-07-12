"""Cost tracking models."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel


class CostRecord(SQLModel, table=True):
    """Individual cost record per agent call."""

    __tablename__ = "cost_record"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    workflow_id: str | None = None
    step_id: str | None = None
    agent_id: str
    model_tier: str
    model_version: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cost_usd: float = 0.0
    timestamp: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class CostAccuracyReport(BaseModel):
    """Report comparing estimated vs actual costs."""

    workflow_id: str
    template: str
    estimated_cost: float
    actual_cost: float
    ratio: float  # actual / estimated
    per_step_breakdown: list[dict]
    generated_at: datetime
