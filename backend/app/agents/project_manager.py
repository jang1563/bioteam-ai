"""Project Manager Agent — lightweight task tracking and status reporting.

Model: Haiku (fast, cheap for status summaries)
Criticality: Optional (workflows run without PM)
Degradation: skip (no status updates, but workflows continue)
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field

# === Output Models ===


class TaskSummary(BaseModel):
    """Summary of a single task or workflow step."""

    task_id: str = ""
    title: str = ""
    status: str = ""  # "pending", "in_progress", "completed", "blocked"
    assigned_to: str = ""
    blockers: list[str] = Field(default_factory=list)
    cost_so_far: float = 0.0
    notes: str = ""


class ProjectStatus(BaseModel):
    """Overall project status report."""

    active_workflows: int = 0
    completed_workflows: int = 0
    total_cost: float = 0.0
    budget_remaining: float = 0.0
    active_tasks: list[TaskSummary] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    milestones_upcoming: list[str] = Field(default_factory=list)
    summary: str = ""


# === Agent Implementation ===


class ProjectManagerAgent(BaseAgent):
    """Lightweight task tracking and status reporting agent.

    Uses Haiku for fast, low-cost status summarization.
    Optional: workflows continue without PM if unavailable.
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Generate a project status report from current context."""
        return await self.generate_status(context)

    async def generate_status(self, context: ContextPackage) -> AgentOutput:
        """Summarize current project/workflow state.

        Reads prior_step_outputs and constraints to produce a status report.
        """
        # Build context summary from available data
        workflow_info = context.constraints.get("workflow_info", {})
        cost_info = context.constraints.get("cost_info", {})

        messages = [
            {
                "role": "user",
                "content": (
                    f"Generate a concise project status report.\n\n"
                    f"Current task: {context.task_description}\n\n"
                    f"Workflow info: {workflow_info}\n"
                    f"Cost info: {cost_info}\n"
                    f"Prior outputs: {len(context.prior_step_outputs)} steps completed\n\n"
                    f"Provide a brief status summary with active tasks, blockers, "
                    f"and upcoming milestones."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier="haiku",  # Always Haiku for PM
            response_model=ProjectStatus,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="ProjectStatus",
            summary=result.summary[:200] if result.summary else "Status report generated",
            llm_response=meta,
        )

    async def summarize_task(self, context: ContextPackage) -> AgentOutput:
        """Summarize a single task for the activity feed."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Summarize this task concisely:\n\n"
                    f"{context.task_description}\n\n"
                    f"Output a brief task summary."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier="haiku",
            response_model=TaskSummary,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="TaskSummary",
            summary=f"{result.title}: {result.status}",
            llm_response=meta,
        )
