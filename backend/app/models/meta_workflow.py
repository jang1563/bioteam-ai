"""Meta-Workflow models — DAG-based workflow chaining.

Defines MetaWorkflow nodes, definitions, and persistent instances
for orchestrating multi-workflow pipelines (e.g., W1→W2→W3→W4).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlmodel import JSON, Column, SQLModel
from sqlmodel import Field as SQLField

# === Node & Definition Models (Pydantic, in-memory) ===

MetaNodeState = Literal["pending", "running", "completed", "failed", "skipped"]


class MetaWorkflowNode(BaseModel):
    """A node in a meta-workflow DAG.

    Each node maps to a workflow template with optional conditions
    and dependencies.
    """

    id: str  # Unique node ID (e.g. "lit_review", "hypothesis")
    template: str  # Workflow template (e.g. "W1", "W2")
    params: dict = Field(default_factory=dict)  # Override params for the workflow
    condition: str | None = None  # Condition expression (e.g. "node.lit_review.completed")
    depends_on: list[str] = Field(default_factory=list)  # Node IDs this depends on
    human_checkpoint: bool = False  # Pause before this node for human review


class MetaWorkflowDef(BaseModel):
    """Definition of a meta-workflow DAG.

    Contains ordered nodes with dependencies and conditions.
    Used as a template to create MetaWorkflowInstance.
    """

    id: str  # Template ID (e.g. "full_research_pipeline")
    name: str  # Human-readable name
    description: str = ""
    nodes: list[MetaWorkflowNode] = Field(default_factory=list)

    def validate_dag(self) -> list[str]:
        """Validate the DAG structure. Returns list of errors."""
        errors = []
        node_ids = {n.id for n in self.nodes}

        for node in self.nodes:
            for dep in node.depends_on:
                if dep not in node_ids:
                    errors.append(f"Node '{node.id}' depends on unknown node '{dep}'")

        # Check for cycles using topological sort
        if not errors:
            visited: set[str] = set()
            in_stack: set[str] = set()
            dep_map = {n.id: n.depends_on for n in self.nodes}

            def _has_cycle(node_id: str) -> bool:
                if node_id in in_stack:
                    return True
                if node_id in visited:
                    return False
                visited.add(node_id)
                in_stack.add(node_id)
                for dep in dep_map.get(node_id, []):
                    if _has_cycle(dep):
                        return True
                in_stack.discard(node_id)
                return False

            for n in self.nodes:
                if _has_cycle(n.id):
                    errors.append("DAG contains a cycle")
                    break

        return errors


# === Persistent Instance (SQLModel) ===


class MetaWorkflowInstance(SQLModel, table=True):
    """A running or completed meta-workflow instance.

    Tracks which nodes have been executed, their results,
    and the overall budget.
    """

    __tablename__ = "meta_workflow_instance"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    definition_id: str  # Which MetaWorkflowDef was used
    name: str = ""
    state: str = "PENDING"  # PENDING, RUNNING, PAUSED, COMPLETED, FAILED
    query: str = ""  # Research query passed to sub-workflows
    budget_total: float = 20.0  # Higher budget for multi-workflow chains
    budget_remaining: float = 20.0

    # Node execution state
    node_states: dict[str, str] = SQLField(
        default_factory=dict, sa_column=Column(JSON),
    )  # {node_id: "pending"|"running"|"completed"|"failed"|"skipped"}
    node_results: dict[str, dict] = SQLField(
        default_factory=dict, sa_column=Column(JSON),
    )  # {node_id: {workflow_id, template, summary, cost}}
    spawned_workflows: list[str] = SQLField(
        default_factory=list, sa_column=Column(JSON),
    )  # List of spawned WorkflowInstance IDs

    # DAG definition stored inline for resumability
    dag_nodes: list[dict] = SQLField(
        default_factory=list, sa_column=Column(JSON),
    )

    # Routing chain for cycle detection
    routing_chain: list[str] = SQLField(
        default_factory=list, sa_column=Column(JSON),
    )

    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
