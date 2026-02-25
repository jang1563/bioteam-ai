"""NoteProcessor — reads and applies DirectorNotes from WorkflowInstance.

Centralized logic for processing injected_notes so all runners (W1-W6)
handle note actions consistently.

Supported actions:
  ADD_PAPER: Add DOI to seed_papers constraint
  EXCLUDE_PAPER: Add DOI to excluded_dois constraint
  MODIFY_QUERY: Override task description for next agent call
  EDIT_TEXT: Inject revision instructions into prior_step_outputs
  FREE_TEXT: Inject as general context into prior_step_outputs
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.messages import ContextPackage
from app.models.workflow import WorkflowInstance

logger = logging.getLogger(__name__)


class NoteProcessor:
    """Reads injected_notes from WorkflowInstance and applies them to agent context."""

    @staticmethod
    def get_pending_notes(instance: WorkflowInstance, step_id: str) -> list[dict]:
        """Return unprocessed notes targeting this step.

        A note targets a step if:
        - note["target_step"] == step_id, OR
        - note["target_step"] is None (applies to next step)

        Already-processed notes (those with "processed_at") are skipped.
        Each returned dict includes "_index" for mark_processed().
        """
        pending = []
        for i, note in enumerate(instance.injected_notes):
            if note.get("processed_at"):
                continue
            target = note.get("target_step")
            if target is None or target == step_id:
                pending.append({**note, "_index": i})
        return pending

    @staticmethod
    def apply_to_context(
        notes: list[dict],
        context: ContextPackage,
        step_results: dict | None = None,
    ) -> ContextPackage:
        """Apply note actions to a ContextPackage, returning a modified copy.

        Does NOT mutate the original context.
        """
        new_constraints = dict(context.constraints)
        new_prior_outputs = list(context.prior_step_outputs)
        new_task = context.task_description

        for note in notes:
            action = note.get("action", "FREE_TEXT")
            text = note.get("text", "")
            metadata = note.get("metadata", {})

            if action == "ADD_PAPER":
                seeds = list(new_constraints.get("seed_papers", []))
                doi = metadata.get("doi", text.strip())
                if doi and doi not in seeds:
                    seeds.append(doi)
                new_constraints["seed_papers"] = seeds
                logger.info("NoteProcessor: ADD_PAPER — added %s", doi)

            elif action == "EXCLUDE_PAPER":
                excluded = list(new_constraints.get("excluded_dois", []))
                doi = metadata.get("doi", text.strip())
                if doi and doi not in excluded:
                    excluded.append(doi)
                new_constraints["excluded_dois"] = excluded
                logger.info("NoteProcessor: EXCLUDE_PAPER — excluded %s", doi)

            elif action == "MODIFY_QUERY":
                new_task = text
                logger.info("NoteProcessor: MODIFY_QUERY — updated task to: %s", text[:100])

            elif action == "EDIT_TEXT":
                new_prior_outputs.append({
                    "type": "director_revision_instruction",
                    "instruction": text,
                    "source": "director_note",
                })
                logger.info("NoteProcessor: EDIT_TEXT — injected revision instruction")

            elif action == "FREE_TEXT":
                new_prior_outputs.append({
                    "type": "director_note",
                    "content": text,
                    "source": "director_note",
                })
                logger.info("NoteProcessor: FREE_TEXT — injected director context")

            else:
                logger.warning("NoteProcessor: unknown action '%s', treating as FREE_TEXT", action)
                new_prior_outputs.append({
                    "type": "director_note",
                    "content": text,
                    "source": "director_note",
                })

        return ContextPackage(
            task_description=new_task,
            relevant_memory=context.relevant_memory,
            prior_step_outputs=new_prior_outputs,
            negative_results=context.negative_results,
            rcmxt_context=context.rcmxt_context,
            constraints=new_constraints,
        )

    @staticmethod
    def mark_processed(instance: WorkflowInstance, note_indices: list[int]) -> None:
        """Mark notes as processed by adding a processed_at timestamp.

        Modifies instance.injected_notes in-place (the list is a JSON column).
        """
        notes = list(instance.injected_notes)
        now = datetime.now(timezone.utc).isoformat()
        for idx in note_indices:
            if 0 <= idx < len(notes):
                notes[idx] = {**notes[idx], "processed_at": now}
        instance.injected_notes = notes
