"""MetaWorkflowOrchestrator — DAG-based workflow chaining.

Executes a meta-workflow by topologically sorting DAG nodes,
evaluating conditions, and spawning sub-workflows in order.

Toggle: settings.routing_enabled (meta-workflows require routing).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from app.models.meta_workflow import MetaWorkflowDef, MetaWorkflowInstance, MetaWorkflowNode

logger = logging.getLogger(__name__)


class MetaWorkflowOrchestrator:
    """Executes meta-workflow DAGs by spawning and tracking sub-workflows.

    Usage:
        orchestrator = MetaWorkflowOrchestrator(
            run_workflow_fn=run_workflow,  # async (template, query, budget) → dict
            persist_fn=persist_meta,       # async (MetaWorkflowInstance) → None
        )
        result = await orchestrator.run(definition, query="TP53 mechanisms")
    """

    def __init__(
        self,
        run_workflow_fn=None,  # async callable(template, query, budget, **params) → dict
        persist_fn=None,       # async callable(MetaWorkflowInstance) → None
        sse_hub=None,
    ) -> None:
        self._run_workflow = run_workflow_fn
        self._persist_fn = persist_fn
        self._sse_hub = sse_hub
        self._skip_checkpoints: set[str] = set()  # Node IDs to skip HC on resume

    async def _persist(self, instance: MetaWorkflowInstance) -> None:
        if self._persist_fn:
            await self._persist_fn(instance)

    async def _broadcast(self, event_type: str, instance: MetaWorkflowInstance, **kwargs) -> None:
        if self._sse_hub:
            await self._sse_hub.broadcast_dict(
                event_type=event_type,
                workflow_id=instance.id,
                payload=kwargs,
            )

    async def run(
        self,
        definition: MetaWorkflowDef,
        query: str,
        budget: float = 20.0,
        instance: MetaWorkflowInstance | None = None,
    ) -> MetaWorkflowInstance:
        """Execute a meta-workflow DAG.

        Args:
            definition: The DAG definition to execute.
            query: Research query to pass to sub-workflows.
            budget: Total budget across all sub-workflows.
            instance: Optional existing instance (for resume).

        Returns:
            The MetaWorkflowInstance with all results.
        """
        # Validate DAG
        errors = definition.validate_dag()
        if errors:
            raise ValueError(f"Invalid DAG: {'; '.join(errors)}")

        # Create or resume instance
        if instance is None:
            instance = MetaWorkflowInstance(
                definition_id=definition.id,
                name=definition.name,
                query=query,
                budget_total=budget,
                budget_remaining=budget,
                dag_nodes=[n.model_dump() for n in definition.nodes],
                node_states={n.id: "pending" for n in definition.nodes},
            )

        instance.state = "RUNNING"
        await self._persist(instance)
        await self._broadcast("meta.started", instance, name=definition.name)

        # Topological sort
        execution_order = self._topological_sort(definition.nodes)

        for node in execution_order:
            if instance.state not in ("RUNNING",):
                break

            # Skip already completed nodes (for resume)
            if instance.node_states.get(node.id) == "completed":
                continue

            # Check dependencies
            deps_met = all(
                instance.node_states.get(dep) == "completed"
                for dep in node.depends_on
            )
            if not deps_met:
                # Check if any dependency failed → skip this node
                deps_failed = any(
                    instance.node_states.get(dep) in ("failed", "skipped")
                    for dep in node.depends_on
                )
                if deps_failed:
                    instance.node_states[node.id] = "skipped"
                    await self._persist(instance)
                    await self._broadcast(
                        "meta.node_skipped", instance,
                        node_id=node.id, reason="dependency_failed",
                    )
                    continue
                # Dependencies not met and not failed → should not happen in topo sort
                logger.warning("Dependencies not met for node %s, skipping", node.id)
                instance.node_states[node.id] = "skipped"
                await self._persist(instance)
                continue

            # Evaluate condition
            if node.condition and not self._evaluate_condition(node.condition, instance):
                instance.node_states[node.id] = "skipped"
                await self._persist(instance)
                await self._broadcast(
                    "meta.node_skipped", instance,
                    node_id=node.id, reason="condition_not_met",
                    condition=node.condition,
                )
                continue

            # Human checkpoint (skip if resuming past this node)
            if node.human_checkpoint and node.id not in self._skip_checkpoints:
                instance.state = "PAUSED"
                instance.node_states[node.id] = "pending"
                await self._persist(instance)
                await self._broadcast(
                    "meta.human_checkpoint", instance,
                    node_id=node.id, template=node.template,
                )
                logger.info("Meta-workflow paused at node %s for human review", node.id)
                break

            # Budget check
            if instance.budget_remaining <= 0:
                instance.state = "FAILED"
                instance.node_states[node.id] = "failed"
                await self._persist(instance)
                await self._broadcast(
                    "meta.failed", instance,
                    node_id=node.id, reason="budget_exhausted",
                )
                break

            # Execute node
            await self._execute_node(node, instance, query)

        # Check completion
        all_done = all(
            s in ("completed", "skipped")
            for s in instance.node_states.values()
        )
        if all_done and instance.state == "RUNNING":
            instance.state = "COMPLETED"
            instance.updated_at = datetime.now(timezone.utc)
            await self._persist(instance)
            await self._broadcast("meta.completed", instance, name=instance.name)

        return instance

    async def resume(
        self,
        instance: MetaWorkflowInstance,
        definition: MetaWorkflowDef | None = None,
    ) -> MetaWorkflowInstance:
        """Resume a paused meta-workflow after human checkpoint."""
        if instance.state != "PAUSED":
            raise ValueError(f"Cannot resume meta-workflow in state {instance.state}")

        # Reconstruct definition from stored DAG nodes
        if definition is None:
            definition = MetaWorkflowDef(
                id=instance.definition_id,
                name=instance.name,
                nodes=[MetaWorkflowNode(**n) for n in instance.dag_nodes],
            )

        # Find the HC node that caused the pause and skip its checkpoint on resume
        for node in definition.nodes:
            if node.human_checkpoint and instance.node_states.get(node.id) == "pending":
                self._skip_checkpoints.add(node.id)

        return await self.run(
            definition=definition,
            query=instance.query,
            budget=instance.budget_remaining,
            instance=instance,
        )

    async def _execute_node(
        self,
        node: MetaWorkflowNode,
        instance: MetaWorkflowInstance,
        query: str,
    ) -> None:
        """Execute a single node by spawning a sub-workflow."""
        instance.node_states[node.id] = "running"
        await self._persist(instance)
        await self._broadcast(
            "meta.node_started", instance,
            node_id=node.id, template=node.template,
        )

        try:
            # Calculate per-node budget
            remaining_nodes = sum(
                1 for s in instance.node_states.values()
                if s in ("pending", "running")
            )
            node_budget = min(
                instance.budget_remaining,
                instance.budget_remaining / max(1, remaining_nodes),
            )

            # Run sub-workflow
            if self._run_workflow:
                result = await self._run_workflow(
                    template=node.template,
                    query=query,
                    budget=node_budget,
                    **node.params,
                )
            else:
                # Dry-run mode (for testing)
                result = {
                    "instance": {"id": f"dry-{node.id}", "state": "COMPLETED"},
                    "step_results": {},
                }

            # Extract result data
            sub_instance = result.get("instance", {})
            if hasattr(sub_instance, "id"):
                wf_id = sub_instance.id
                wf_state = sub_instance.state
                wf_cost = sub_instance.budget_total - sub_instance.budget_remaining
            else:
                wf_id = sub_instance.get("id", f"unknown-{node.id}")
                wf_state = sub_instance.get("state", "COMPLETED")
                wf_cost = 0.0

            instance.spawned_workflows = list(instance.spawned_workflows) + [wf_id]

            # Store node result
            step_results = result.get("step_results", {})
            instance.node_results[node.id] = {
                "workflow_id": wf_id,
                "template": node.template,
                "state": wf_state,
                "cost": wf_cost,
                "step_results": step_results,
            }

            # Deduct cost
            instance.budget_remaining = max(0, instance.budget_remaining - wf_cost)

            if wf_state == "COMPLETED":
                instance.node_states[node.id] = "completed"
            else:
                instance.node_states[node.id] = "failed"

            await self._persist(instance)
            await self._broadcast(
                "meta.node_completed", instance,
                node_id=node.id, template=node.template,
                workflow_id=wf_id, cost=wf_cost,
            )

        except Exception as e:
            logger.error("Meta-workflow node %s failed: %s", node.id, e)
            instance.node_states[node.id] = "failed"
            instance.node_results[node.id] = {"error": str(e)}
            await self._persist(instance)
            await self._broadcast(
                "meta.failed", instance,
                node_id=node.id, reason=str(e),
            )

    @staticmethod
    def _topological_sort(nodes: list[MetaWorkflowNode]) -> list[MetaWorkflowNode]:
        """Topological sort of DAG nodes using Kahn's algorithm."""
        node_map = {n.id: n for n in nodes}
        in_degree: dict[str, int] = {n.id: 0 for n in nodes}

        for n in nodes:
            for dep in n.depends_on:
                if dep in in_degree:
                    in_degree[n.id] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        result: list[MetaWorkflowNode] = []

        while queue:
            # Sort for deterministic order
            queue.sort()
            nid = queue.pop(0)
            result.append(node_map[nid])

            for n in nodes:
                if nid in n.depends_on:
                    in_degree[n.id] -= 1
                    if in_degree[n.id] == 0:
                        queue.append(n.id)

        return result

    @staticmethod
    def _evaluate_condition(condition: str, instance: MetaWorkflowInstance) -> bool:
        """Safely evaluate a condition expression against node results.

        Supported patterns:
        - node.<node_id>.completed → check if node completed
        - node.<node_id>.<field> > <number> → numeric comparison
        - node.<node_id>.<field> → truthy check

        Returns True if condition is met, False otherwise.
        Safe: no eval(), only pattern matching.
        """
        if not condition:
            return True

        # Pattern: node.<id>.completed
        m = re.match(r"node\.(\w+)\.completed", condition)
        if m:
            node_id = m.group(1)
            return instance.node_states.get(node_id) == "completed"

        # Pattern: node.<id>.<field> > <number>
        m = re.match(r"node\.(\w+)\.(\w+)\s*>\s*(\d+)", condition)
        if m:
            node_id, field, threshold = m.group(1), m.group(2), int(m.group(3))
            result = instance.node_results.get(node_id, {})
            step_results = result.get("step_results", {})

            # Look for the field in step results
            for step_data in step_results.values():
                if isinstance(step_data, dict):
                    output = step_data.get("output", step_data)
                    if isinstance(output, dict) and field in output:
                        val = output[field]
                        if isinstance(val, (int, float)):
                            return val > threshold
                        if isinstance(val, list):
                            return len(val) > threshold

            return False

        # Pattern: node.<id>.<field> (truthy)
        m = re.match(r"node\.(\w+)\.(\w+)", condition)
        if m:
            node_id, field = m.group(1), m.group(2)
            result = instance.node_results.get(node_id, {})

            # Direct field check
            if field in result:
                return bool(result[field])

            # Check step results
            step_results = result.get("step_results", {})
            for step_data in step_results.values():
                if isinstance(step_data, dict):
                    output = step_data.get("output", step_data)
                    if isinstance(output, dict) and field in output:
                        val = output[field]
                        if isinstance(val, (int, float)):
                            return val > 0
                        return bool(val)

            return False

        logger.warning("Unknown condition pattern: %s", condition)
        return False
