"""Ambiguity Engine Agent — contradiction detection, classification, and resolution.

Combines deterministic pre-screening (ContradictionDetector) with LLM-powered
classification using Instructor structured outputs.

Pipeline:
1. Extract claims from context (task_description + prior_step_outputs)
2. Find candidate pairs via ContradictionDetector (ChromaDB cosine + markers)
3. Classify each pair with LLM (5-type taxonomy, multi-label)
4. Score RCMXT for genuine contradictions
5. Generate resolution hypotheses for confirmed contradictions
6. Persist ContradictionEntry to DB

Budget cap: max 10 classify calls per invocation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.engines.ambiguity.contradiction_detector import ContradictionDetector
from app.engines.rcmxt_scorer import RCMXTScorer
from app.models.agent import AgentOutput
from app.models.evidence import ContradictionEntry, ContradictionType, RCMXTScore
from app.models.messages import ContextPackage

if TYPE_CHECKING:
    from app.memory.semantic import SemanticMemory

logger = logging.getLogger(__name__)

# Budget cap: maximum LLM classify calls per run
MAX_CLASSIFY_CALLS = 10


# === Pydantic Output Models ===


class ContradictionClassification(BaseModel):
    """LLM output for classifying one contradiction pair."""

    types: list[str] = Field(
        default_factory=list,
        description="Multi-label: subset of conditional_truth, technical_artifact, "
        "interpretive_framing, statistical_noise, temporal_dynamics",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Classification confidence",
    )
    type_reasoning: dict[str, str] = Field(
        default_factory=dict,
        description="Per-type reasoning: {type_name: reasoning_string}",
    )
    is_genuine_contradiction: bool = Field(
        default=False,
        description="False if the pair is a rephrasing, unrelated, or compatible",
    )
    context_dependence: str = Field(
        default="",
        description="Under what conditions each claim holds (if conditional_truth)",
    )


class ResolutionHypothesis(BaseModel):
    """A single resolution hypothesis for a contradiction."""

    hypothesis: str = Field(description="The resolution hypothesis text")
    hypothesis_type: Literal[
        "reconciling", "one_is_wrong", "needs_more_data", "methodological"
    ] = "reconciling"
    testable_prediction: str = Field(
        default="",
        description="A concrete experiment or analysis that would test this hypothesis",
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ResolutionOutput(BaseModel):
    """LLM output for generating resolution hypotheses."""

    hypotheses: list[ResolutionHypothesis] = Field(default_factory=list)
    discriminating_experiment: str = Field(
        default="",
        description="Single best experiment to resolve this contradiction",
    )


class ContradictionAnalysis(BaseModel):
    """Full agent output from detect_contradictions."""

    query: str = ""
    contradictions_found: int = 0
    pairs_screened: int = 0
    pairs_classified: int = 0
    entries: list[dict] = Field(
        default_factory=list,
        description="Serialized ContradictionEntry dicts",
    )
    overall_ambiguity_level: Literal["low", "moderate", "high", "critical"] = "low"
    summary: str = ""
    recommended_action: str = ""


# === Agent Implementation ===


class AmbiguityEngineAgent(BaseAgent):
    """Detects, classifies, and resolves contradictions in scientific claims.

    Two-phase architecture:
      Phase 1: Deterministic pre-screening (ContradictionDetector)
      Phase 2: LLM classification + resolution (Instructor structured output)
    """

    def __init__(
        self,
        spec,
        llm,
        memory: SemanticMemory | None = None,
        rcmxt_mode: str = "heuristic",
    ) -> None:
        super().__init__(spec, llm)
        self._detector = ContradictionDetector()
        self._rcmxt_mode = rcmxt_mode
        self.memory = memory
        # Lazily initialized
        self._scorer: RCMXTScorer | None = None

    def _get_scorer(self) -> RCMXTScorer:
        if self._scorer is None:
            if self._rcmxt_mode == "heuristic":
                self._scorer = RCMXTScorer(mode="heuristic")
            else:
                self._scorer = RCMXTScorer(mode=self._rcmxt_mode, llm_layer=self.llm)
        return self._scorer

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Core execution: run full contradiction detection pipeline."""
        return await self.detect_contradictions(context)

    async def detect_contradictions(self, context: ContextPackage) -> AgentOutput:
        """Full pipeline: extract → find pairs → classify → score → resolve → persist.

        Returns AgentOutput with ContradictionAnalysis as output.
        """
        query = context.task_description

        # Step 1: Extract claims
        claims = self._extract_claims(context)
        if len(claims) < 2:
            analysis = ContradictionAnalysis(
                query=query,
                pairs_screened=0,
                pairs_classified=0,
                contradictions_found=0,
                overall_ambiguity_level="low",
                summary="Insufficient claims for contradiction analysis.",
                recommended_action="No action needed.",
            )
            return self.build_output(
                output=analysis.model_dump(),
                output_type="ContradictionAnalysis",
                summary=analysis.summary,
            )

        # Step 2: Find candidate pairs (deterministic)
        if self.memory is not None:
            candidate_pairs = self._detector.find_candidate_pairs(
                claims=claims,
                memory=self.memory,
            )
        else:
            # No memory → only use all-pairs marker matching
            candidate_pairs = self._detector.find_candidate_pairs(
                claims=claims,
                memory=_NullMemory(),
            )

        pairs_screened = len(candidate_pairs)
        if not candidate_pairs:
            analysis = ContradictionAnalysis(
                query=query,
                pairs_screened=0,
                pairs_classified=0,
                contradictions_found=0,
                overall_ambiguity_level="low",
                summary="No candidate contradiction pairs found.",
                recommended_action="No action needed.",
            )
            return self.build_output(
                output=analysis.model_dump(),
                output_type="ContradictionAnalysis",
                summary=analysis.summary,
            )

        # Step 3: Classify pairs via LLM (capped at MAX_CLASSIFY_CALLS)
        entries: list[ContradictionEntry] = []
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        model_version = ""
        pairs_classified = 0

        for claim_a, claim_b, similarity in candidate_pairs[:MAX_CLASSIFY_CALLS]:
            try:
                classification, meta = await self._classify_pair_llm(
                    claim_a, claim_b, similarity
                )
                total_input_tokens += meta.input_tokens
                total_output_tokens += meta.output_tokens
                total_cost += meta.cost
                model_version = meta.model_version
                pairs_classified += 1

                if not classification.is_genuine_contradiction:
                    continue

                # Step 4: RCMXT scoring for genuine contradictions
                rcmxt_a = self._score_rcmxt(claim_a)
                rcmxt_b = self._score_rcmxt(claim_b)

                # Step 5: Resolution hypotheses
                resolution_hyps: list[str] = []
                disc_experiment = ""
                try:
                    resolution_output, res_meta = await self._generate_resolutions_llm(
                        claim_a, claim_b, classification
                    )
                    total_input_tokens += res_meta.input_tokens
                    total_output_tokens += res_meta.output_tokens
                    total_cost += res_meta.cost
                    resolution_hyps = [h.hypothesis for h in resolution_output.hypotheses]
                    disc_experiment = resolution_output.discriminating_experiment
                except Exception as e:
                    logger.warning("Resolution generation failed: %s", e)

                # Step 6: Build ContradictionEntry
                entry = ContradictionEntry(
                    id=str(uuid4()),
                    claim_a=claim_a,
                    claim_b=claim_b,
                    types=classification.types,
                    resolution_hypotheses=resolution_hyps,
                    rcmxt_a=rcmxt_a.model_dump(mode="json") if rcmxt_a else {},
                    rcmxt_b=rcmxt_b.model_dump(mode="json") if rcmxt_b else {},
                    discriminating_experiment=disc_experiment,
                    detected_at=datetime.now(timezone.utc),
                    detected_by=self.agent_id,
                    workflow_id=context.constraints.get("workflow_id"),
                )
                entries.append(entry)

            except Exception as e:
                logger.warning("Failed to classify pair: %s", e)
                continue

        # Build analysis summary
        n_found = len(entries)
        ambiguity_level = self._compute_ambiguity_level(n_found, pairs_screened)
        summary = self._build_summary(n_found, pairs_screened, pairs_classified, ambiguity_level)
        action = self._recommend_action(ambiguity_level, entries)

        analysis = ContradictionAnalysis(
            query=query,
            contradictions_found=n_found,
            pairs_screened=pairs_screened,
            pairs_classified=pairs_classified,
            entries=[self._entry_to_dict(e) for e in entries],
            overall_ambiguity_level=ambiguity_level,
            summary=summary,
            recommended_action=action,
        )

        return self.build_output(
            output=analysis.model_dump(),
            output_type="ContradictionAnalysis",
            summary=summary,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
        )

    # === LLM-powered methods ===

    async def _classify_pair_llm(
        self,
        claim_a: str,
        claim_b: str,
        similarity: float,
    ) -> tuple[ContradictionClassification, "LLMResponse"]:
        """Classify a single pair via LLM structured output."""
        from app.llm.layer import LLMResponse

        messages = [
            {
                "role": "user",
                "content": (
                    f"## Claim A\n{claim_a}\n\n"
                    f"## Claim B\n{claim_b}\n\n"
                    f"## Metadata\n"
                    f"Semantic similarity: {similarity:.2f}\n\n"
                    f"Classify this pair. Is it a genuine contradiction? "
                    f"If yes, assign one or more contradiction types from the taxonomy."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=ContradictionClassification,
            system=self.system_prompt_cached,
            temperature=0.0,
        )
        return result, meta

    async def classify_pair(
        self,
        claim_a: str,
        claim_b: str,
        evidence: list[dict] | None = None,
        similarity_score: float = 0.5,
    ) -> ContradictionClassification:
        """Public API: classify a single pair (for W6 usage)."""
        result, _ = await self._classify_pair_llm(claim_a, claim_b, similarity_score)
        return result

    async def _generate_resolutions_llm(
        self,
        claim_a: str,
        claim_b: str,
        classification: ContradictionClassification,
    ) -> tuple[ResolutionOutput, "LLMResponse"]:
        """Generate resolution hypotheses for a confirmed contradiction."""
        from app.llm.layer import LLMResponse

        types_str = ", ".join(classification.types) if classification.types else "unknown"
        messages = [
            {
                "role": "user",
                "content": (
                    f"## Contradiction\n"
                    f"**Claim A**: {claim_a}\n"
                    f"**Claim B**: {claim_b}\n\n"
                    f"**Types**: {types_str}\n"
                    f"**Confidence**: {classification.confidence:.2f}\n\n"
                    f"Generate resolution hypotheses. Prefer 'reconciling' type. "
                    f"Include a discriminating experiment that could resolve this."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=ResolutionOutput,
            system=self.system_prompt_cached,
            temperature=0.2,
        )
        return result, meta

    async def generate_resolutions(
        self,
        contradiction: dict,
        evidence: list[dict] | None = None,
    ) -> list[str]:
        """Public API: generate resolutions for an existing contradiction dict."""
        claim_a = contradiction.get("claim_a", "")
        claim_b = contradiction.get("claim_b", "")
        types = contradiction.get("types", [])

        classification = ContradictionClassification(
            types=types,
            is_genuine_contradiction=True,
            confidence=0.7,
        )
        try:
            output, _ = await self._generate_resolutions_llm(claim_a, claim_b, classification)
            return [h.hypothesis for h in output.hypotheses]
        except Exception as e:
            logger.warning("Resolution generation failed: %s", e)
            return []

    # === Claim extraction ===

    def _extract_claims(self, context: ContextPackage) -> list[str]:
        """Extract claims from context package.

        Sources:
        1. task_description (split by newlines if multi-line)
        2. prior_step_outputs: key_findings, contradictions_noted
        """
        claims: list[str] = []

        # From task description
        desc = context.task_description.strip()
        if desc:
            # If multi-line, treat each line as a separate claim
            lines = [ln.strip() for ln in desc.split("\n") if ln.strip()]
            if len(lines) > 1:
                claims.extend(lines)
            else:
                claims.append(desc)

        # From prior step outputs
        for step_out in context.prior_step_outputs:
            output = step_out.get("output", step_out)

            # key_findings from synthesis
            for finding in output.get("key_findings", []):
                if isinstance(finding, str) and finding.strip():
                    claims.append(finding.strip())

            # contradictions_noted from research director
            for note in output.get("contradictions_noted", []):
                if isinstance(note, str) and note.strip():
                    claims.append(note.strip())

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for c in claims:
            if c not in seen:
                seen.add(c)
                unique.append(c)

        return unique

    # === RCMXT scoring ===

    def _score_rcmxt(self, claim: str) -> RCMXTScore | None:
        """Score a single claim using heuristic RCMXT."""
        try:
            scorer = self._get_scorer()
            return scorer.score_claim(claim)
        except Exception as e:
            logger.warning("RCMXT scoring failed for claim: %s", e)
            return None

    # === Ambiguity level computation ===

    @staticmethod
    def _compute_ambiguity_level(
        n_contradictions: int,
        n_screened: int,
    ) -> Literal["low", "moderate", "high", "critical"]:
        """Compute overall ambiguity level from contradiction count."""
        if n_contradictions == 0:
            return "low"
        if n_contradictions <= 2:
            return "moderate"
        if n_contradictions <= 5:
            return "high"
        return "critical"

    @staticmethod
    def _build_summary(
        n_found: int,
        n_screened: int,
        n_classified: int,
        level: str,
    ) -> str:
        if n_found == 0:
            return f"Screened {n_screened} candidate pairs, classified {n_classified}. No genuine contradictions found."
        return (
            f"Found {n_found} genuine contradiction(s) from {n_screened} candidate pairs "
            f"({n_classified} classified). Ambiguity level: {level}."
        )

    @staticmethod
    def _recommend_action(
        level: str,
        entries: list[ContradictionEntry],
    ) -> str:
        if level == "low":
            return "No action needed. Evidence base is consistent."
        if level == "moderate":
            return "Review flagged contradictions. May be conditional truths — check context dependence."
        if level == "high":
            return "Significant contradictions detected. Consider running W6 Ambiguity Resolution workflow."
        return "Critical ambiguity in evidence base. Manual review strongly recommended before drawing conclusions."

    @staticmethod
    def _entry_to_dict(entry: ContradictionEntry) -> dict:
        """Serialize ContradictionEntry to dict for JSON storage."""
        return {
            "id": entry.id,
            "claim_a": entry.claim_a,
            "claim_b": entry.claim_b,
            "types": entry.types,
            "resolution_hypotheses": entry.resolution_hypotheses,
            "rcmxt_a": entry.rcmxt_a,
            "rcmxt_b": entry.rcmxt_b,
            "discriminating_experiment": entry.discriminating_experiment,
            "detected_at": entry.detected_at.isoformat() if entry.detected_at else None,
            "detected_by": entry.detected_by,
            "workflow_id": entry.workflow_id,
        }


class _NullMemory:
    """Null-object memory that returns empty results."""

    def search(self, collection: str, query: str, n_results: int = 5) -> list[dict]:
        return []
