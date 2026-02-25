"""AsyncWorkflowRunner — Phase 1 workflow execution with asyncio.

Runs workflow steps sequentially or in parallel using asyncio.gather.
Supports per-agent checkpointing and partial failure recovery.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.agents.registry import AgentRegistry
from app.api.v1.sse import SSEHub
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from app.models.workflow import StepCheckpoint, WorkflowInstance, WorkflowStepDef
from app.workflows.engine import WorkflowEngine


class AllAgentsFailedError(Exception):
    """Raised when all agents in a parallel step fail."""

    def __init__(self, step_id: str, failures: list[Any]) -> None:
        self.step_id = step_id
        self.failures = failures
        super().__init__(f"All agents failed in step {step_id}: {len(failures)} failures")


class AsyncWorkflowRunner:
    """Executes workflow steps using asyncio.gather for parallelism.

    Manages:
    - Sequential step execution
    - Parallel agent execution with Semaphore-based concurrency control
    - Per-agent checkpointing with idempotency tokens
    - Partial failure handling (some agents fail, workflow continues)
    - Budget checks before each step
    - SSE event broadcasting

    Usage:
        runner = AsyncWorkflowRunner(
            engine=WorkflowEngine(),
            registry=AgentRegistry(),
            sse_hub=SSEHub(),
            concurrency_limit=5,
        )

        result = await runner.run_step(
            instance=workflow_instance,
            step=step_definition,
            context=context_package,
        )
    """

    def __init__(
        self,
        engine: WorkflowEngine,
        registry: AgentRegistry,
        sse_hub: SSEHub | None = None,
        concurrency_limit: int = 5,
    ) -> None:
        self.engine = engine
        self.registry = registry
        self.sse_hub = sse_hub
        self.semaphore = asyncio.Semaphore(concurrency_limit)
        # In-memory checkpoint store (Phase 1). Phase 2: SQLite.
        self._checkpoints: dict[str, list[StepCheckpoint]] = {}

    async def run_step(
        self,
        instance: WorkflowInstance,
        step: WorkflowStepDef,
        context: ContextPackage,
    ) -> list[AgentOutput]:
        """Run a single workflow step (sequential or parallel).

        Args:
            instance: The workflow instance.
            step: The step definition.
            context: Context package for agents.

        Returns:
            List of AgentOutput results.
        """
        # Budget check
        if not self.engine.check_budget(instance, step.estimated_cost):
            self.engine.mark_over_budget(instance)
            await self._emit("workflow.over_budget", instance, step.id, payload={
                "budget_remaining": instance.budget_remaining,
                "step_cost": step.estimated_cost,
            })
            return []

        # Determine agents
        agent_ids = step.agent_id if isinstance(step.agent_id, list) else [step.agent_id]

        await self._emit("workflow.step_started", instance, step.id, payload={
            "agents": agent_ids,
            "is_parallel": step.is_parallel,
        })

        try:
            if step.is_parallel and len(agent_ids) > 1:
                results = await self._run_parallel(instance, step, agent_ids, context)
            else:
                results = await self._run_sequential(instance, step, agent_ids, context)

            # Deduct cost
            total_cost = sum(r.cost for r in results if r.is_success)
            self.engine.deduct_budget(instance, total_cost)

            # Record step completion
            self.engine.advance(instance, step.id, step_result={
                "agent_count": len(results),
                "success_count": sum(1 for r in results if r.is_success),
                "total_cost": total_cost,
            })

            await self._emit("workflow.step_completed", instance, step.id, payload={
                "success_count": sum(1 for r in results if r.is_success),
                "total_cost": total_cost,
            })

            return results

        except AllAgentsFailedError as e:
            self.engine.fail(instance, str(e))
            await self._emit("workflow.step_failed", instance, step.id, payload={
                "error": str(e),
                "failure_count": len(e.failures),
            })
            raise

    async def _run_sequential(
        self,
        instance: WorkflowInstance,
        step: WorkflowStepDef,
        agent_ids: list[str],
        context: ContextPackage,
    ) -> list[AgentOutput]:
        """Run agents one by one."""
        results = []
        for agent_id in agent_ids:
            output = await self._run_agent(instance, step, agent_id, context)
            results.append(output)
        return results

    async def _run_parallel(
        self,
        instance: WorkflowInstance,
        step: WorkflowStepDef,
        agent_ids: list[str],
        context: ContextPackage,
    ) -> list[AgentOutput]:
        """Run agents in parallel with Semaphore-based concurrency.

        Supports partial failure: if some agents fail but at least one
        succeeds, the step continues.
        """
        # Check for existing checkpoints (crash recovery)
        completed_results = self._load_completed_checkpoints(instance.id, step.id)
        completed_agent_ids = {cp.agent_id for cp in completed_results}

        # Only run agents that haven't completed yet
        remaining = [aid for aid in agent_ids if aid not in completed_agent_ids]

        async def run_one(agent_id: str) -> AgentOutput:
            async with self.semaphore:
                return await self._run_agent(instance, step, agent_id, context)

        # gather with return_exceptions=True — partial failure supported
        raw_results = await asyncio.gather(
            *[run_one(aid) for aid in remaining],
            return_exceptions=True,
        )

        # Combine with pre-completed results
        all_results: list[AgentOutput] = []

        # Add results from completed checkpoints
        for cp in completed_results:
            if cp.result:
                all_results.append(AgentOutput(**cp.result))

        # Process new results
        for result in raw_results:
            if isinstance(result, Exception):
                all_results.append(AgentOutput(
                    agent_id="unknown",
                    error=f"{type(result).__name__}: {result}",
                ))
            else:
                all_results.append(result)

        successes = [r for r in all_results if r.is_success]
        failures = [r for r in all_results if not r.is_success]

        if not successes:
            raise AllAgentsFailedError(step.id, failures)

        if failures:
            # Log partial failures but continue
            pass

        return all_results

    async def _run_agent(
        self,
        instance: WorkflowInstance,
        step: WorkflowStepDef,
        agent_id: str,
        context: ContextPackage,
    ) -> AgentOutput:
        """Run a single agent with checkpointing."""
        # Create checkpoint
        checkpoint = StepCheckpoint(
            workflow_id=instance.id,
            step_id=step.id,
            agent_id=agent_id,
            status="running",
            idempotency_token=str(uuid4()),
            started_at=datetime.now(timezone.utc),
        )
        self._save_checkpoint(checkpoint)

        # Get agent from registry
        agent = self.registry.get(agent_id)
        if agent is None:
            # Try substitution for optional agents
            substitute_id = self.registry.find_substitute(agent_id)
            if substitute_id:
                agent = self.registry.get(substitute_id)

        if agent is None:
            checkpoint.status = "failed"
            checkpoint.completed_at = datetime.now(timezone.utc)
            self._save_checkpoint(checkpoint)
            return AgentOutput(
                agent_id=agent_id,
                error=f"Agent {agent_id} not available and no substitute found",
            )

        try:
            output = await agent.execute(context)
            output.step_id = step.id
            output.workflow_id = instance.id

            checkpoint.status = "completed"
            checkpoint.result = output.model_dump()
            checkpoint.completed_at = datetime.now(timezone.utc)
            self._save_checkpoint(checkpoint)

            return output

        except Exception as e:
            checkpoint.status = "failed"
            checkpoint.completed_at = datetime.now(timezone.utc)
            self._save_checkpoint(checkpoint)
            return AgentOutput(
                agent_id=agent_id,
                error=f"{type(e).__name__}: {e}",
            )

    def _save_checkpoint(self, checkpoint: StepCheckpoint) -> None:
        """Save checkpoint to in-memory store."""
        key = f"{checkpoint.workflow_id}:{checkpoint.step_id}"
        if key not in self._checkpoints:
            self._checkpoints[key] = []
        # Update existing or add new
        for i, cp in enumerate(self._checkpoints[key]):
            if cp.agent_id == checkpoint.agent_id:
                self._checkpoints[key][i] = checkpoint
                return
        self._checkpoints[key].append(checkpoint)

    def _load_completed_checkpoints(
        self,
        workflow_id: str,
        step_id: str,
    ) -> list[StepCheckpoint]:
        """Load completed checkpoints for crash recovery."""
        key = f"{workflow_id}:{step_id}"
        checkpoints = self._checkpoints.get(key, [])
        return [cp for cp in checkpoints if cp.status == "completed"]

    def get_checkpoints(
        self,
        workflow_id: str,
        step_id: str | None = None,
    ) -> list[StepCheckpoint]:
        """Get all checkpoints for a workflow (optionally filtered by step)."""
        results = []
        for key, cps in self._checkpoints.items():
            wf_id, s_id = key.split(":", 1)
            if wf_id == workflow_id:
                if step_id is None or s_id == step_id:
                    results.extend(cps)
        return results

    async def _emit(
        self,
        event_type: str,
        instance: WorkflowInstance,
        step_id: str | None = None,
        agent_id: str | None = None,
        payload: dict | None = None,
    ) -> None:
        """Broadcast an SSE event if hub is available."""
        if self.sse_hub:
            await self.sse_hub.broadcast_dict(
                event_type=event_type,
                workflow_id=instance.id,
                step_id=step_id,
                agent_id=agent_id,
                payload=payload,
            )
