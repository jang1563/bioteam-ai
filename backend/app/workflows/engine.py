"""Workflow Engine — state machine + transition table.

Manages WorkflowInstance lifecycle with guard conditions
and illegal transition enforcement.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.workflow import WorkflowInstance

# === State Transition Table ===
# Key: (from_state, to_state) → guard description
# Absent pair → illegal transition

LEGAL_TRANSITIONS: dict[tuple[str, str], str] = {
    # From PENDING
    ("PENDING", "RUNNING"): "Director starts workflow",
    ("PENDING", "CANCELLED"): "Director cancels before start",
    # From RUNNING
    ("RUNNING", "RUNNING"): "Step completes, next step begins",
    ("RUNNING", "PAUSED"): "Director clicks Pause",
    ("RUNNING", "WAITING_HUMAN"): "Human checkpoint or QA rejection",
    ("RUNNING", "OVER_BUDGET"): "budget_remaining < next_step cost",
    ("RUNNING", "FAILED"): "Agent fails 3x after retry",
    ("RUNNING", "COMPLETED"): "Final step succeeds",
    ("RUNNING", "CANCELLED"): "Director cancels mid-run",
    # From PAUSED
    ("PAUSED", "RUNNING"): "Director clicks Resume",
    ("PAUSED", "CANCELLED"): "Director cancels while paused",
    # From WAITING_HUMAN
    ("WAITING_HUMAN", "RUNNING"): "Director approves / modifies",
    ("WAITING_HUMAN", "CANCELLED"): "Director cancels",
    ("WAITING_HUMAN", "PAUSED"): "24h timeout, auto-pause + notify",
    # From WAITING_DIRECTION (DC — auto-continues after timeout)
    ("WAITING_DIRECTION", "RUNNING"): "User responds or auto-continue timeout",
    ("WAITING_DIRECTION", "CANCELLED"): "Director cancels during direction check",
    ("RUNNING", "WAITING_DIRECTION"): "DC step reached — waiting for direction response",
    # From OVER_BUDGET
    ("OVER_BUDGET", "RUNNING"): "Director approves overage",
    ("OVER_BUDGET", "CANCELLED"): "Director cancels",
    # From FAILED
    ("FAILED", "RUNNING"): "Director retries with new params",
    ("FAILED", "CANCELLED"): "Director abandons",
    # Terminal states: COMPLETED, CANCELLED — no transitions out
}

TERMINAL_STATES = {"COMPLETED", "CANCELLED"}


class IllegalTransitionError(Exception):
    """Raised when attempting an illegal state transition."""

    def __init__(self, from_state: str, to_state: str) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Illegal transition: {from_state} → {to_state}. "
            f"See LEGAL_TRANSITIONS for valid transitions."
        )


class WorkflowEngine:
    """Core workflow engine with state machine enforcement.

    Manages state transitions, guard conditions, loop detection,
    and budget enforcement for WorkflowInstance objects.

    The engine is stateless — all state is in WorkflowInstance.
    This allows multiple engine instances to operate on the same
    workflow (crash recovery, horizontal scaling).

    Usage:
        engine = WorkflowEngine()
        instance = WorkflowInstance(template="W1")

        engine.start(instance)
        engine.advance(instance, step_id="SEARCH")
        engine.pause(instance)
        engine.resume(instance)
        engine.complete(instance)
    """

    def transition(self, instance: WorkflowInstance, to_state: str) -> None:
        """Transition a workflow to a new state with guard enforcement.

        Args:
            instance: The workflow instance to transition.
            to_state: Target state.

        Raises:
            IllegalTransitionError: If the transition is not legal.
        """
        from_state = instance.state

        if from_state in TERMINAL_STATES:
            raise IllegalTransitionError(from_state, to_state)

        key = (from_state, to_state)
        if key not in LEGAL_TRANSITIONS:
            raise IllegalTransitionError(from_state, to_state)

        instance.state = to_state
        instance.updated_at = datetime.now(timezone.utc)

    def start(self, instance: WorkflowInstance, first_step: str = "") -> None:
        """Start a pending workflow."""
        self.transition(instance, "RUNNING")
        if first_step:
            instance.current_step = first_step

    def advance(
        self,
        instance: WorkflowInstance,
        step_id: str,
        step_result: dict | None = None,
        *,
        agent_id: str = "",
        status: str = "completed",
        duration_ms: int = 0,
        cost: float = 0.0,
    ) -> None:
        """Record step completion and advance to next step.

        If the workflow is already RUNNING, this stays in RUNNING.

        Args:
            instance: The workflow instance.
            step_id: Completed step identifier.
            step_result: Optional result summary dict.
            agent_id: Agent that executed the step.
            status: Step outcome ("completed" | "failed" | "skipped").
            duration_ms: Wall-clock duration of the step.
            cost: Actual LLM cost for this step.
        """
        # Record in step_history
        entry: dict = {
            "step_id": step_id,
            "status": status,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
        }
        if agent_id:
            entry["agent_id"] = agent_id
        if cost > 0:
            entry["cost"] = cost
        if step_result:
            entry["result_summary"] = str(step_result)[:500]

        history = list(instance.step_history)
        history.append(entry)
        instance.step_history = history

        instance.current_step = step_id
        instance.updated_at = datetime.now(timezone.utc)

    def pause(self, instance: WorkflowInstance) -> None:
        """Pause a running workflow (Director action)."""
        self.transition(instance, "PAUSED")

    def resume(self, instance: WorkflowInstance) -> None:
        """Resume a paused or waiting workflow."""
        self.transition(instance, "RUNNING")

    def request_human(self, instance: WorkflowInstance) -> None:
        """Move to WAITING_HUMAN state (checkpoint or QA rejection)."""
        self.transition(instance, "WAITING_HUMAN")

    def mark_over_budget(self, instance: WorkflowInstance) -> None:
        """Move to OVER_BUDGET when insufficient budget for next step."""
        self.transition(instance, "OVER_BUDGET")

    def fail(self, instance: WorkflowInstance, error: str = "") -> None:
        """Mark workflow as failed after exhausting retries."""
        self.transition(instance, "FAILED")

    def complete(self, instance: WorkflowInstance) -> None:
        """Mark workflow as successfully completed."""
        self.transition(instance, "COMPLETED")

    def cancel(self, instance: WorkflowInstance) -> None:
        """Cancel a workflow (from any non-terminal state)."""
        self.transition(instance, "CANCELLED")

    def check_loop(
        self,
        instance: WorkflowInstance,
        step_id: str,
    ) -> bool:
        """Check if a loop step has exceeded max iterations.

        Args:
            instance: The workflow instance.
            step_id: The loop step ID.

        Returns:
            True if loop is within limits, False if maxed out.
        """
        counts = dict(instance.loop_count)
        current = counts.get(step_id, 0)
        return current < instance.max_loops

    def increment_loop(self, instance: WorkflowInstance, step_id: str) -> int:
        """Increment loop counter for a step.

        Returns:
            New loop count.
        """
        counts = dict(instance.loop_count)
        counts[step_id] = counts.get(step_id, 0) + 1
        instance.loop_count = counts
        instance.updated_at = datetime.now(timezone.utc)
        return counts[step_id]

    def check_budget(
        self,
        instance: WorkflowInstance,
        estimated_cost: float,
    ) -> bool:
        """Check if workflow has sufficient budget for next step.

        Returns:
            True if budget is sufficient.
        """
        return instance.budget_remaining >= estimated_cost

    def deduct_budget(
        self,
        instance: WorkflowInstance,
        actual_cost: float,
    ) -> float:
        """Deduct cost from workflow budget.

        Returns:
            Remaining budget after deduction.
        """
        instance.budget_remaining = max(0, instance.budget_remaining - actual_cost)
        instance.updated_at = datetime.now(timezone.utc)
        return instance.budget_remaining

    def wait_for_direction(self, instance: WorkflowInstance) -> None:
        """Move to WAITING_DIRECTION for a DC (Direction Check) step."""
        self.transition(instance, "WAITING_DIRECTION")

    def can_transition(self, from_state: str, to_state: str) -> bool:
        """Check if a transition is legal without performing it."""
        if from_state in TERMINAL_STATES:
            return False
        return (from_state, to_state) in LEGAL_TRANSITIONS

    def get_valid_transitions(self, from_state: str) -> list[str]:
        """Get all valid target states from a given state."""
        if from_state in TERMINAL_STATES:
            return []
        return [to for (fr, to) in LEGAL_TRANSITIONS if fr == from_state]
