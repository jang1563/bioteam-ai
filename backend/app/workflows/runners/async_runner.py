"""AsyncWorkflowRunner — Phase 1 workflow execution with asyncio.

Runs workflow steps sequentially or in parallel using asyncio.gather.
Supports per-agent checkpointing and partial failure recovery.

v5.3: DC (Direction Check) + EC (Error Checkpoint) interaction types.
      Error classification via StepErrorReport.
      CheckpointManager SQLite integration for long-term recovery.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.agents.registry import AgentRegistry
from app.api.v1.sse import SSEHub
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from app.models.step_error import StepErrorReport
from app.models.workflow import StepCheckpoint, WorkflowInstance, WorkflowStepDef
from app.workflows.engine import WorkflowEngine

logger = logging.getLogger(__name__)


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
        checkpoint_manager=None,  # Optional CheckpointManager for SQLite persistence
    ) -> None:
        self.engine = engine
        self.registry = registry
        self.sse_hub = sse_hub
        self.semaphore = asyncio.Semaphore(concurrency_limit)
        self.checkpoint_manager = checkpoint_manager  # CheckpointManager | None
        # In-memory checkpoint store (always used for parallel step recovery)
        self._checkpoints: dict[str, list[StepCheckpoint]] = {}
        # User adjustment from most recent DC response (injected into next step context)
        self._pending_user_adjustment: str | None = None

    async def run_step(
        self,
        instance: WorkflowInstance,
        step: WorkflowStepDef,
        context: ContextPackage,
    ) -> list[AgentOutput]:
        """Run a single workflow step (sequential or parallel).

        Handles DC (Direction Check) and HC (Human Checkpoint) interaction types.
        For DC steps: broadcasts a summary SSE event and pauses with WAITING_DIRECTION state.
                      Auto-continues after dc_auto_continue_minutes with no user response.
        For HC steps: transitions to WAITING_HUMAN and returns immediately (caller loops).

        Args:
            instance: The workflow instance.
            step: The step definition.
            context: Context package for agents.

        Returns:
            List of AgentOutput results (empty for DC/HC steps until resumed).
        """
        # --- DC: Direction Check (lightweight, no LLM cost) ---
        if step.interaction_type == "DC":
            return await self._handle_direction_check(instance, step, context)

        # --- HC: Human Checkpoint (handled by caller, runner just signals) ---
        if step.is_human_checkpoint or step.interaction_type == "HC":
            self.engine.request_human(instance)
            await self._emit("workflow.human_checkpoint", instance, step.id, payload={
                "message": f"Human checkpoint: {step.id}. Awaiting approval.",
            })
            return []

        # --- Budget check ---
        if not self.engine.check_budget(instance, step.estimated_cost):
            self.engine.mark_over_budget(instance)
            await self._emit("workflow.over_budget", instance, step.id, payload={
                "budget_remaining": instance.budget_remaining,
                "step_cost": step.estimated_cost,
                "cost_used": instance.budget_total - instance.budget_remaining,
                "budget_total": instance.budget_total,
                "resume_hint": f"POST /api/v1/workflows/{instance.id}/resume?budget_top_up=5.0",
            })
            return []

        # Inject pending user adjustment into context metadata
        if self._pending_user_adjustment:
            ctx_meta = dict(context.metadata or {})
            ctx_meta["user_adjustment"] = self._pending_user_adjustment
            context = context.model_copy(update={"metadata": ctx_meta})

        # Determine agents
        agent_ids = step.agent_id if isinstance(step.agent_id, list) else [step.agent_id]

        await self._emit("workflow.step_started", instance, step.id, payload={
            "agents": agent_ids,
            "is_parallel": step.is_parallel,
        })

        retry_count = 0
        max_retries = 3

        while retry_count <= max_retries:
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

                # Save to SQLite checkpoint if manager available
                if self.checkpoint_manager and results:
                    step_index = len(instance.step_history)
                    primary_agent = agent_ids[0] if agent_ids else "unknown"
                    self.checkpoint_manager.save_step(
                        workflow_id=instance.id,
                        step_id=step.id,
                        step_index=step_index,
                        agent_id=primary_agent,
                        output=results,
                        cost=total_cost,
                    )

                await self._emit("workflow.step_completed", instance, step.id, payload={
                    "success_count": sum(1 for r in results if r.is_success),
                    "total_cost": total_cost,
                })

                return results

            except AllAgentsFailedError as e:
                error_report = StepErrorReport.classify(
                    step_id=step.id,
                    agent_id=str(agent_ids),
                    exception=e,
                    retry_count=retry_count,
                )
                await self._handle_step_error(instance, step, error_report, retry_count, max_retries)

                if error_report.error_type == "TRANSIENT" and retry_count < max_retries:
                    retry_count += 1
                    await asyncio.sleep(2 ** retry_count)  # exponential backoff
                    continue
                elif error_report.error_type == "SKIP_SAFE":
                    logger.warning("Skipping step %s (SKIP_SAFE): %s", step.id, e)
                    return [AgentOutput(agent_id="skipped", error=f"skipped: {e}")]
                else:
                    self.engine.fail(instance, str(e))
                    await self._emit("workflow.step_failed", instance, step.id, payload={
                        "error": str(e),
                        "failure_count": len(e.failures),
                    })
                    raise

            except Exception as e:
                error_report = StepErrorReport.classify(
                    step_id=step.id,
                    agent_id=str(agent_ids),
                    exception=e,
                    retry_count=retry_count,
                )
                await self._handle_step_error(instance, step, error_report, retry_count, max_retries)

                if error_report.error_type == "TRANSIENT" and retry_count < max_retries:
                    retry_count += 1
                    await asyncio.sleep(2 ** retry_count)
                    continue
                elif error_report.error_type == "SKIP_SAFE":
                    logger.warning("Skipping step %s (SKIP_SAFE): %s", step.id, e)
                    return [AgentOutput(agent_id="skipped", error=f"skipped: {e}")]
                elif error_report.error_type in ("USER_INPUT", "FATAL"):
                    # EC: emit error checkpoint event and stop
                    await self._emit("workflow.error_checkpoint", instance, step.id, payload={
                        "error_type": error_report.error_type,
                        "message": error_report.error_message,
                        "recovery_suggestions": error_report.recovery_suggestions,
                        "suggested_action": error_report.suggested_action,
                        "recovery_options": [
                            {"action": "retry", "label": "다시 시도"},
                            {"action": "skip", "label": "건너뛰기"},
                            {"action": "abort", "label": "중단"},
                        ],
                    })
                    if self.checkpoint_manager:
                        self.checkpoint_manager.save_error_report(instance.id, step.id, error_report)
                    self.engine.fail(instance, error_report.error_message)
                    raise
                else:
                    if retry_count >= max_retries:
                        self.engine.fail(instance, str(e))
                        raise
                    retry_count += 1
                    await asyncio.sleep(2 ** retry_count)

        # Should not reach here
        return []

    async def _handle_direction_check(
        self,
        instance: WorkflowInstance,
        step: WorkflowStepDef,
        context: ContextPackage,
    ) -> list[AgentOutput]:
        """Handle a DC (Direction Check) step.

        Builds a phase summary from prior step results and emits a
        workflow.direction_check SSE event. Transitions to WAITING_DIRECTION
        and waits up to dc_auto_continue_minutes for user response.

        DC costs $0 — no LLM calls made here.
        """
        summary, key_findings = self._build_phase_summary(instance, context)

        # Transition to WAITING_DIRECTION
        self.engine.wait_for_direction(instance)

        await self._emit("workflow.direction_check", instance, step.id, payload={
            "event_type": "workflow.direction_check",
            "step_id": step.id,
            "summary": summary,
            "key_findings": key_findings,
            "options": ["continue", "focus:<gene_or_topic>", "skip_next_step", "adjust:<free text>"],
            "auto_continue_after_minutes": step.dc_auto_continue_minutes,
            "cost_remaining": round(instance.budget_remaining, 2),
        })

        # Wait for user response (polling loop with auto-continue)
        timeout_seconds = step.dc_auto_continue_minutes * 60
        poll_interval = 5  # seconds
        elapsed = 0

        while elapsed < timeout_seconds:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            # Reload instance state (user may have submitted direction_response)
            from app.db.database import engine as db_engine
            from sqlmodel import Session
            with Session(db_engine) as db_sess:
                fresh = db_sess.get(type(instance), instance.id)
                if fresh:
                    db_sess.expunge(fresh)
                    current_state = fresh.state
                    # Check for user adjustment
                    manifest = fresh.session_manifest or {}
                    adjustment = manifest.get("pending_user_adjustment")
                    if adjustment:
                        self._pending_user_adjustment = adjustment
                        # Clear the pending flag
                        manifest["pending_user_adjustment"] = None
                        fresh.session_manifest = manifest
                        db_sess.merge(fresh)
                        db_sess.commit()
                else:
                    current_state = instance.state

            if current_state == "RUNNING":
                # User submitted a response and the resume endpoint already transitioned
                logger.info("DC step %s: user responded, continuing", step.id)
                return []

            if current_state in ("CANCELLED", "FAILED"):
                logger.info("DC step %s: workflow %s, aborting", step.id, current_state)
                return []

        # Auto-continue after timeout
        logger.info("DC step %s: auto-continuing after %d min timeout", step.id, step.dc_auto_continue_minutes)
        self.engine.resume(instance)
        await self._emit("workflow.direction_check_autocontinued", instance, step.id, payload={
            "message": f"No response received. Automatically continuing after {step.dc_auto_continue_minutes} minutes.",
        })
        return []

    async def _handle_step_error(
        self,
        instance: WorkflowInstance,
        step: WorkflowStepDef,
        error_report: StepErrorReport,
        retry_count: int,
        max_retries: int,
    ) -> None:
        """Emit error events and log based on error classification."""
        logger.warning(
            "Step %s error [%s] attempt %d/%d: %s",
            step.id, error_report.error_type, retry_count + 1, max_retries + 1,
            error_report.error_message,
        )
        await self._emit("workflow.step_error", instance, step.id, payload={
            "error_type": error_report.error_type,
            "message": error_report.error_message,
            "retry_count": retry_count,
            "suggested_action": error_report.suggested_action,
        })

    def _build_phase_summary(
        self,
        instance: WorkflowInstance,
        context: ContextPackage,
    ) -> tuple[str, list[str]]:
        """Build a concise summary from recent step history for DC events.

        Returns:
            (summary_text, key_findings_list)
        """
        recent_steps = instance.step_history[-6:] if instance.step_history else []
        step_count = len(recent_steps)
        completed_ids = [s.get("step_id", "") for s in recent_steps if s.get("status") == "completed"]

        summary = (
            f"지금까지 {step_count}단계 완료: {', '.join(completed_ids[:4])}. "
            f"예산 사용: ${instance.budget_total - instance.budget_remaining:.2f}/"
            f"${instance.budget_total:.2f}."
        )

        # Extract key findings from context metadata if available
        key_findings: list[str] = []
        if context.metadata:
            for key in ("variant_count", "deg_count", "pathway_count", "novel_count"):
                val = context.metadata.get(key)
                if val is not None:
                    key_findings.append(f"{key}: {val}")

        return summary, key_findings

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
