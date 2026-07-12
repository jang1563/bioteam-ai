"""Shared checkpoint helpers for all workflow runners.

Provides convenience functions that wrap CheckpointManager operations
with error handling and logging, so individual runners don't need to
duplicate checkpoint logic.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.agent import AgentOutput
    from app.workflows.checkpoint_manager import CheckpointManager

logger = logging.getLogger(__name__)


def save_step_checkpoint(
    mgr: CheckpointManager | None,
    workflow_id: str,
    step_id: str,
    step_index: int,
    agent_id: str,
    output: AgentOutput | list[AgentOutput],
    cost: float = 0.0,
) -> None:
    """Save a completed step to the checkpoint store.

    No-op if *mgr* is None (checkpoint disabled).
    Catches exceptions to avoid breaking the workflow on checkpoint failure.
    """
    if mgr is None:
        return
    try:
        mgr.save_step(
            workflow_id=workflow_id,
            step_id=step_id,
            step_index=step_index,
            agent_id=agent_id,
            output=output,
            cost=cost,
        )
    except Exception as e:
        logger.warning("Checkpoint save failed for %s/%s: %s", workflow_id[:8], step_id, e)


def load_and_skip_completed(
    mgr: CheckpointManager | None,
    workflow_id: str,
    step_results: dict[str, Any],
) -> dict[str, Any]:
    """Load prior checkpoints and merge into the runner's step_results dict.

    Returns the loaded checkpoints (empty dict if none).
    The caller should skip steps whose IDs appear in *step_results*
    after this call.
    """
    if mgr is None:
        return {}
    try:
        prior = mgr.load_completed_steps(workflow_id)
        if prior:
            step_results.update(prior)
            logger.info(
                "Restored %d checkpointed steps for %s: %s",
                len(prior), workflow_id[:8], list(prior.keys()),
            )
        return prior
    except Exception as e:
        logger.warning("Checkpoint load failed for %s: %s", workflow_id[:8], e)
        return {}


def should_skip_step(step_id: str, step_results: dict[str, Any]) -> bool:
    """Return True if *step_id* was already completed (present in step_results)."""
    return step_id in step_results
