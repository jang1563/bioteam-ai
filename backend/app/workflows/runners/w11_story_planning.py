"""W11 Story Planning Runner — 4-step pipeline for narrative frame generation.

Steps:
  SCOPE [HC] → GENERATE_FRAMES (Opus) → HUMAN_CHECKPOINT [HC] → PRESENT (code)

SCOPE: Human checkpoint — user reviews research context and selects target tier.
GENERATE_FRAMES: Single Opus call generates 3-5 StoryFrame options as StoryFrameSet.
HUMAN_CHECKPOINT: Human checkpoint — user selects a frame via inject_note.
PRESENT: Code step — stores selected frame in session_manifest and completes.

Two HC pauses managed via session_manifest["w11_phase"]:
  "awaiting_scope"     → first HC fired, waiting for tier selection
  "awaiting_selection" → second HC fired, waiting for frame_id selection
  "complete"           → workflow done, selected_story_frame available

Estimated budget: ~$1.50 (Opus GENERATE_FRAMES ~$0.90 + overhead)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.agents.base import observe
from app.agents.registry import AgentRegistry
from app.api.v1.sse import SSEHub
from app.cost.tracker import COST_PER_1K_INPUT, COST_PER_1K_OUTPUT
from app.models.agent import AgentOutput
from app.models.story_frame import StoryFrame, StoryFrameSet
from app.models.workflow import WorkflowInstance, WorkflowStepDef
from app.workflows.engine import WorkflowEngine

if TYPE_CHECKING:
    from app.llm.layer import LLMLayer

logger = logging.getLogger(__name__)


def _estimate_step_cost(model_tier: str, est_input_tokens: int, est_output_tokens: int) -> float:
    input_rate = COST_PER_1K_INPUT.get(model_tier, 0.0)
    output_rate = COST_PER_1K_OUTPUT.get(model_tier, 0.0)
    return (est_input_tokens / 1000) * input_rate + (est_output_tokens / 1000) * output_rate


# === Step Definitions ===

W11_STEPS: list[WorkflowStepDef] = [
    WorkflowStepDef(
        id="SCOPE",
        agent_id="code_only",
        output_schema="dict",
        next_step="GENERATE_FRAMES",
        is_human_checkpoint=True,
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="GENERATE_FRAMES",
        agent_id="code_only",  # Direct LLM call in runner, not via agent
        output_schema="StoryFrameSet",
        next_step="HUMAN_CHECKPOINT",
        estimated_cost=_estimate_step_cost("opus", est_input_tokens=3000, est_output_tokens=2000),
    ),
    WorkflowStepDef(
        id="HUMAN_CHECKPOINT",
        agent_id="code_only",
        output_schema="dict",
        next_step="PRESENT",
        is_human_checkpoint=True,
        estimated_cost=0.0,
    ),
    WorkflowStepDef(
        id="PRESENT",
        agent_id="code_only",
        output_schema="dict",
        next_step=None,
        estimated_cost=0.0,
    ),
]


# === Prompts ===

_SYSTEM_PROMPT = """\
You are a scientific editor and narrative strategist. Your task is to help a researcher
identify the strongest narrative angles for their paper before they begin writing.

Generate 3-5 distinct StoryFrame options from the research data provided.
Each frame should use a DIFFERENT narrative_type and approach the same data
from a unique angle that would resonate with a specific audience.

For each StoryFrame:
- hook: The first sentence of the paper — must grab a Nature/NEJM/Cell editor immediately
- central_tension: The expected vs. found conflict that drives the story
- core_claim: One crisp sentence stating the contribution
- supporting_findings: Which specific data points carry THIS frame
- figure_sequence: Suggested figure order that builds the narrative
- target_tier: Match to the journal tier requested (nature_cell / specialty / grant)
- novelty_rationale: Why this angle is novel vs. prior literature
- blind_spots: What this framing intentionally leaves unaddressed
- impact_score: 0.9+ paradigm-shifting, 0.7-0.89 solid advance, <0.7 incremental

Rank frames by impact_score (highest first).
Generate frames from these perspectives:
  1. Mechanism discovery: what molecular/cellular switch does this reveal?
  2. Paradigm challenge: what assumption does this overturn?
  3. Clinical/translational: what does this mean for patients or treatment?
  4. Field bridge: does this unify two previously separate fields?
  5. Negative reframe: if expected result absent, what does that reveal?
"""

_FRAME_USER_PROMPT = """\
Research query: {query}

Target journal tier: {tier}

Research context and prior findings:
{prior_context}

Generate 3-5 StoryFrame options for this research. Rank by impact_score (descending).
"""


# === Helper functions ===

def _extract_tier_from_notes(injected_notes: list[dict]) -> str:
    """Extract target_tier from the most recent inject_note.

    Looks for patterns like "target_tier: nature_cell" or "tier: specialty"
    in FREE_TEXT notes. Falls back to "specialty" if not found.
    """
    tier_keywords = ("target_tier:", "tier:")
    for note in reversed(injected_notes):  # Most recent first
        text = (note.get("text") or "").lower()
        for kw in tier_keywords:
            if kw in text:
                value = text.split(kw, 1)[1].strip().split()[0].strip(".,;\"'")
                if value in ("nature_cell", "specialty", "grant"):
                    return value
    return "specialty"  # Safe default


def _extract_selected_frame_id(injected_notes: list[dict]) -> str | None:
    """Extract selected_frame_id from the most recent inject_note.

    Looks for patterns like "selected_frame_id: SF-002" or "SF-002".
    """
    for note in reversed(injected_notes):
        text = (note.get("text") or "").strip()
        # Explicit key-value
        if "selected_frame_id:" in text.lower():
            value = text.lower().split("selected_frame_id:", 1)[1].strip().split()[0].strip(".,;\"'")
            return value.upper()
        # Bare frame ID (e.g. "SF-001")
        if text.upper().startswith("SF-"):
            return text.split()[0].upper()
    return None


# === Runner ===

class W11StoryPlanningRunner:
    """Orchestrates the W11 Story Planning pipeline.

    Generates 3-5 StoryFrame options via a single Opus call, then lets
    the researcher select the best narrative anchor before writing (W4).

    Two HC pauses tracked via session_manifest["w11_phase"]:
      - "awaiting_scope"     → SCOPE HC fired
      - "awaiting_selection" → HUMAN_CHECKPOINT HC fired
      - "complete"           → PRESENT done, selected_story_frame available
    """

    def __init__(
        self,
        registry: AgentRegistry,
        engine: WorkflowEngine | None = None,
        sse_hub: SSEHub | None = None,
        persist_fn=None,
        checkpoint_manager=None,
        lab_kb=None,
    ) -> None:
        self.registry = registry
        self.engine = engine or WorkflowEngine()
        self.sse_hub = sse_hub
        self._persist_fn = persist_fn
        self._checkpoint_manager = checkpoint_manager
        self.lab_kb = lab_kb
        self._step_results: dict[str, AgentOutput] = {}
        # LLM layer — resolved lazily from registry's research_director
        self._llm: LLMLayer | None = None

    def _get_llm(self) -> LLMLayer | None:
        if self._llm is not None:
            return self._llm
        director = self.registry.get("research_director")
        if director and hasattr(director, "llm"):
            self._llm = director.llm
        return self._llm

    async def _persist(self, instance: WorkflowInstance) -> None:
        if self._persist_fn:
            await self._persist_fn(instance)

    async def _emit(
        self,
        event_type: str,
        instance: WorkflowInstance,
        step_id: str,
        payload: dict | None = None,
    ) -> None:
        if self.sse_hub:
            await self.sse_hub.broadcast_dict(
                event_type=event_type,
                workflow_id=instance.id,
                step_id=step_id,
                agent_id="code_only",
                payload=payload or {},
            )

    @observe(name="workflow.w11_story_planning")
    async def run(
        self,
        query: str,
        instance: WorkflowInstance | None = None,
        budget: float = 2.0,
    ) -> dict[str, Any]:
        """Start W11 — pauses immediately at SCOPE HC.

        User must approve SCOPE (via /intervene?action=resume) to continue.
        """
        if instance is None:
            instance = WorkflowInstance(
                template="W11",
                query=query,
                budget_total=budget,
                budget_remaining=budget,
            )

        self.engine.start(instance, first_step="SCOPE")
        self._step_results = {}

        # Store initial research context in session_manifest
        manifest = instance.session_manifest or {}
        manifest["query"] = query
        manifest["w11_phase"] = "awaiting_scope"
        manifest["scope_summary"] = (
            f"Research query: {query[:500]}\n"
            "Please confirm this is correct and specify your target journal tier "
            "(nature_cell / specialty / grant) via inject_note before approving."
        )
        instance.session_manifest = manifest

        await self._emit("workflow.step_started", instance, "SCOPE")
        await self._persist(instance)

        # Fire SCOPE HC — stops here
        self.engine.request_human(instance)
        await self._persist(instance)

        logger.info("W11 paused at SCOPE HC for query: %s", query[:80])

        return {
            "instance": instance,
            "step_results": {},
            "paused_at": "SCOPE",
        }

    @observe(name="workflow.w11_story_planning.resume")
    async def resume_after_human(
        self,
        instance: WorkflowInstance,
        query: str,
    ) -> dict[str, Any]:
        """Handle resume from either HC pause, determined by w11_phase.

        Phase "awaiting_scope" → run GENERATE_FRAMES → fire HUMAN_CHECKPOINT HC
        Phase "awaiting_selection" → run PRESENT → complete
        """
        if instance.state != "RUNNING":
            self.engine.resume(instance)

        manifest = instance.session_manifest or {}
        phase = manifest.get("w11_phase", "")

        if phase == "awaiting_scope":
            return await self._resume_from_scope(instance, query, manifest)
        elif phase == "awaiting_selection":
            return await self._resume_from_selection(instance, query, manifest)
        else:
            logger.warning("W11 resume called with unexpected phase: %r", phase)
            return {"instance": instance, "completed": False, "error": f"Unknown phase: {phase}"}

    async def _resume_from_scope(
        self,
        instance: WorkflowInstance,
        query: str,
        manifest: dict,
    ) -> dict[str, Any]:
        """User approved SCOPE → run GENERATE_FRAMES → fire HUMAN_CHECKPOINT HC."""
        await self._emit("workflow.step_completed", instance, "SCOPE")

        # Extract target tier from injected notes
        tier = _extract_tier_from_notes(list(instance.injected_notes))
        manifest["target_tier"] = tier

        # Run GENERATE_FRAMES
        await self._emit("workflow.step_started", instance, "GENERATE_FRAMES")
        self.engine.advance(instance, "SCOPE")

        frame_set = await self._generate_frames(query, tier, instance, manifest)

        self._step_results["GENERATE_FRAMES"] = AgentOutput(
            agent_id="code_only",
            output=frame_set.model_dump(mode="json"),
            output_type="StoryFrameSet",
            summary=(
                f"Generated {len(frame_set.frames)} story frames for tier '{tier}'"
                if frame_set.generation_mode == "llm"
                else f"Generated {len(frame_set.frames)} synthetic fallback frames for tier '{tier}'"
            ),
        )

        # Store frames for frontend display at HC
        manifest.pop("selection_error", None)
        manifest["frame_options"] = frame_set.model_dump(mode="json")
        manifest["w11_phase"] = "awaiting_selection"
        instance.session_manifest = manifest

        await self._emit("workflow.step_completed", instance, "GENERATE_FRAMES", payload={
            "frames_count": len(frame_set.frames),
            "top_frame": frame_set.frames[0].hook[:120] if frame_set.frames else "",
        })
        await self._persist(instance)

        # Fire HUMAN_CHECKPOINT HC — stops here
        await self._emit("workflow.step_started", instance, "HUMAN_CHECKPOINT")
        self.engine.request_human(instance)
        await self._persist(instance)

        logger.info("W11 paused at HUMAN_CHECKPOINT with %d frames", len(frame_set.frames))

        return {
            "instance": instance,
            "step_results": {
                k: v.model_dump(mode="json") if hasattr(v, "model_dump") else v
                for k, v in self._step_results.items()
            },
            "paused_at": "HUMAN_CHECKPOINT",
            "frames_count": len(frame_set.frames),
        }

    async def _resume_from_selection(
        self,
        instance: WorkflowInstance,
        query: str,
        manifest: dict,
    ) -> dict[str, Any]:
        """User selected a frame → run PRESENT → complete."""
        # Parse the selected frame ID from inject_notes
        selected_id = _extract_selected_frame_id(list(instance.injected_notes))

        # Load frame options from session_manifest
        frame_options = manifest.get("frame_options", {})
        frame_set = StoryFrameSet(**frame_options) if frame_options else StoryFrameSet(frames=[])

        if not frame_set.frames:
            manifest["selection_error"] = "No story frames are available to select."
            manifest["w11_phase"] = "awaiting_selection"
            instance.session_manifest = manifest
            self.engine.request_human(instance)
            await self._persist(instance)
            return {"instance": instance, "completed": False, "error": manifest["selection_error"]}

        if not selected_id:
            manifest["selection_error"] = "No story frame was selected. Choose a frame before resuming."
            manifest["w11_phase"] = "awaiting_selection"
            instance.session_manifest = manifest
            self.engine.request_human(instance)
            await self._persist(instance)
            return {"instance": instance, "completed": False, "error": manifest["selection_error"]}

        selected_frame = next(
            (f for f in frame_set.frames if f.frame_id.upper() == selected_id.upper()),
            None,
        )
        if selected_frame is None:
            manifest["selection_error"] = f"Invalid story frame selection: {selected_id}"
            manifest["w11_phase"] = "awaiting_selection"
            instance.session_manifest = manifest
            self.engine.request_human(instance)
            await self._persist(instance)
            logger.warning("W11: invalid frame_id %s requested; staying at selection checkpoint", selected_id)
            return {"instance": instance, "completed": False, "error": manifest["selection_error"]}

        await self._emit("workflow.step_completed", instance, "HUMAN_CHECKPOINT")

        # Run PRESENT
        await self._emit("workflow.step_started", instance, "PRESENT")
        self.engine.advance(instance, "HUMAN_CHECKPOINT")

        manifest.pop("selection_error", None)
        manifest["selected_story_frame"] = selected_frame.model_dump(mode="json")
        manifest["w11_phase"] = "complete"
        instance.session_manifest = manifest

        self._step_results["PRESENT"] = AgentOutput(
            agent_id="code_only",
            output={
                "selected_frame_id": selected_frame.frame_id,
                "selected_story_frame": selected_frame.model_dump(mode="json"),
                "workflow_id": instance.id,
            },
            output_type="StoryFrame",
            summary=f"Selected frame {selected_frame.frame_id}: {selected_frame.hook[:80]}",
        )

        self.engine.advance(instance, "PRESENT")
        self.engine.complete(instance)
        await self._persist(instance)

        await self._emit("workflow.step_completed", instance, "PRESENT", payload={
            "selected_frame_id": selected_frame.frame_id if selected_frame else None,
        })

        logger.info("W11 completed. Selected frame: %s", selected_frame.frame_id if selected_frame else "none")

        return {
            "instance": instance,
            "step_results": {
                k: v.model_dump(mode="json") if hasattr(v, "model_dump") else v
                for k, v in self._step_results.items()
            },
            "completed": True,
            "selected_frame_id": selected_frame.frame_id if selected_frame else None,
        }

    async def _generate_frames(
        self,
        query: str,
        tier: str,
        instance: WorkflowInstance,
        manifest: dict,
    ) -> StoryFrameSet:
        """Generate 3-5 StoryFrame options via single Opus call.

        Falls back to a minimal synthetic frame set if LLM unavailable.
        """
        llm = self._get_llm()
        if llm is None:
            logger.warning("W11: LLM not available — returning synthetic fallback frames")
            return self._synthetic_fallback_frames(query, reason="LLM unavailable")

        # Build prior context from session_manifest (W1 results, Lab KB, etc.)
        prior_context = self._build_prior_context(manifest)

        messages = [
            {
                "role": "user",
                "content": _FRAME_USER_PROMPT.format(
                    query=query,
                    tier=tier,
                    prior_context=prior_context[:2000],
                ),
            }
        ]

        try:
            frame_set, meta = await llm.complete_structured(
                messages=messages,
                model_tier="opus",
                response_model=StoryFrameSet,
                system=_SYSTEM_PROMPT,
                temperature=0.7,
                max_tokens=4096,
            )
            # Deduct Opus cost from budget
            if meta and hasattr(meta, "cost") and meta.cost > 0:
                self.engine.deduct_budget(instance, meta.cost)

            # Ensure frames have unique IDs
            for i, frame in enumerate(frame_set.frames, 1):
                if not frame.frame_id:
                    frame.frame_id = f"SF-{i:03d}"
                frame.provenance = "llm"

            # Fill generation_context
            frame_set.generation_context = query[:200]
            frame_set.generation_mode = "llm"
            frame_set.fallback_reason = None
            return frame_set

        except Exception as e:
            logger.error("W11 GENERATE_FRAMES LLM call failed: %s — using fallback", e)
            return self._synthetic_fallback_frames(query, reason=str(e))

    def _build_prior_context(self, manifest: dict) -> str:
        """Build context string from session_manifest (W1 results, etc.)."""
        parts: list[str] = []

        # W1 literature synthesis if available
        if "literature_synthesis" in manifest:
            parts.append(f"Literature synthesis:\n{manifest['literature_synthesis'][:800]}")

        # Lab KB highlights if available
        if "lab_kb_summary" in manifest:
            parts.append(f"Lab knowledge base:\n{manifest['lab_kb_summary'][:400]}")

        return "\n\n".join(parts) if parts else "No prior literature context available."

    def _synthetic_fallback_frames(self, query: str, reason: str = "LLM unavailable") -> StoryFrameSet:
        """Minimal fallback when LLM is unavailable (e.g. in tests without API key)."""
        from app.models.story_frame import NarrativeType
        return StoryFrameSet(
            frames=[
                StoryFrame(
                    frame_id="SF-001",
                    narrative_type=NarrativeType.mechanism_discovery,
                    hook=f"This study reveals the molecular mechanism underlying {query[:60]}.",
                    central_tension="Mechanism was unknown; this work identifies the key pathway.",
                    core_claim=f"We identify the core mechanism of {query[:60]}.",
                    supporting_findings=["See data analysis for supporting evidence"],
                    figure_sequence=["Fig1: Overview", "Fig2: Mechanism", "Fig3: Validation"],
                    target_tier="specialty",
                    novelty_rationale="First mechanistic characterization of this phenomenon.",
                    blind_spots=["Clinical relevance requires further study"],
                    impact_score=0.75,
                    provenance="synthetic_fallback",
                ),
            ],
            generation_context=query[:200],
            generation_mode="synthetic_fallback",
            fallback_reason=reason,
        )
