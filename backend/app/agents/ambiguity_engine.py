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

from app.agents.base import BaseAgent
from app.config import settings
from app.engines.ambiguity.contradiction_detector import ContradictionDetector
from app.engines.ambiguity.taxonomy import GENUINE_TYPES, normalize_type_list
from app.engines.rcmxt_scorer import RCMXTScorer
from app.models.agent import AgentOutput
from app.models.evidence import ContradictionEntry, RCMXTScore
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field, field_validator, model_validator

if TYPE_CHECKING:
    from app.llm.gemini_layer import GeminiResponse
    from app.llm.layer import LLMResponse
    from app.memory.semantic import SemanticMemory

logger = logging.getLogger(__name__)

# Budget cap: maximum LLM classify calls per run
MAX_CLASSIFY_CALLS = 10


# === Pydantic Output Models ===


class ContradictionClassification(BaseModel):
    """LLM output for classifying one contradiction pair."""

    types: list[str] = Field(
        default_factory=list,
        description="Canonical taxonomy labels: direct, contextual, methodological, "
        "temporal, magnitude (legacy labels auto-mapped)",
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
        description="Context that may reconcile claims (especially for contextual cases)",
    )

    @field_validator("types", mode="before")
    @classmethod
    def _normalize_types(cls, v):  # type: ignore[no-untyped-def]
        if v is None:
            return []
        if isinstance(v, str):
            return normalize_type_list([v])
        if isinstance(v, list):
            return normalize_type_list([str(x) for x in v])
        return []

    @model_validator(mode="after")
    def _enforce_genuine_type_consistency(self) -> "ContradictionClassification":
        """Keep genuine/contextual semantics internally consistent.

        - non-genuine => contextual type
        - any contextual signal => non-genuine contextual (conservative)
        - genuine => only genuine types kept
        - empty/unknown genuine typing => downgraded to non-genuine contextual
        """
        # self.types already normalized by _normalize_types field_validator
        normalized = self.types

        if not self.is_genuine_contradiction:
            self.types = ["contextual"]
            return self

        if "contextual" in normalized:
            self.is_genuine_contradiction = False
            self.types = ["contextual"]
            if not self.context_dependence:
                self.context_dependence = (
                    "Contextual differences likely explain the apparent contradiction."
                )
            return self

        genuine_only = [t for t in normalized if t in GENUINE_TYPES]
        if genuine_only:
            self.types = genuine_only
            return self

        self.is_genuine_contradiction = False
        self.types = ["contextual"]
        if not self.context_dependence:
            self.context_dependence = (
                "No valid genuine contradiction type identified."
            )
        return self


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
        self._gemini_layer = None

    def _get_gemini_layer(self):
        """Lazy-init Gemini layer for free-tier ambiguity calls."""
        if self._gemini_layer is None:
            from app.llm.gemini_layer import GeminiLayer
            self._gemini_layer = GeminiLayer()
        return self._gemini_layer

    @property
    def _use_gemini(self) -> bool:
        """Gemini is used only when explicitly selected and key is available."""
        # Keep unit tests deterministic when using MockLLMLayer fixtures.
        if self.llm.__class__.__name__ == "MockLLMLayer":
            return False
        return (
            settings.ambiguity_llm_provider.lower() == "gemini"
            and bool(settings.google_api_key)
        )

    async def _complete_structured(
        self,
        *,
        messages: list[dict],
        response_model: type[BaseModel],
        temperature: float = 0.0,
    ) -> tuple[BaseModel, "LLMResponse | GeminiResponse"]:
        """Provider-switching wrapper for structured completions."""
        if self._use_gemini:
            gemini = self._get_gemini_layer()
            return await gemini.complete_structured(
                messages=messages,
                response_model=response_model,
                system=self.system_prompt_cached,
                temperature=temperature,
            )

        return await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=response_model,
            system=self.system_prompt_cached,
            temperature=temperature,
        )

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

        # For explicit two-claim comparisons, always classify at least one pair.
        # This prevents detector marker miss from skipping the core contradiction check.
        if not candidate_pairs and len(claims) == 2:
            candidate_pairs = [(claims[0], claims[1], 0.5)]

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
        pairs_classified = 0
        model_versions: set[str] = set()

        for claim_a, claim_b, similarity in candidate_pairs[:MAX_CLASSIFY_CALLS]:
            try:
                classification, meta = await self._classify_pair_llm(
                    claim_a, claim_b, similarity
                )
                total_input_tokens += meta.input_tokens
                total_output_tokens += meta.output_tokens
                total_cost += meta.cost
                if meta.model_version:
                    model_versions.add(meta.model_version)
                pairs_classified += 1

                marker_hit = self._detector._has_contradiction_markers(claim_a, claim_b)
                if not classification.is_genuine_contradiction and marker_hit:
                    retry_cls, retry_meta = await self._classify_pair_llm(
                        claim_a,
                        claim_b,
                        similarity,
                        marker_challenge=True,
                    )
                    total_input_tokens += retry_meta.input_tokens
                    total_output_tokens += retry_meta.output_tokens
                    total_cost += retry_meta.cost
                    if retry_meta.model_version:
                        model_versions.add(retry_meta.model_version)
                    pairs_classified += 1
                    classification = retry_cls

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
                    if res_meta.model_version:
                        model_versions.add(res_meta.model_version)
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
        ambiguity_level = self._compute_ambiguity_level(n_found)
        summary = self._build_summary(n_found, pairs_screened, pairs_classified, ambiguity_level)
        action = self._recommend_action(ambiguity_level, entries)

        analysis = ContradictionAnalysis(
            query=query,
            contradictions_found=n_found,
            pairs_screened=pairs_screened,
            pairs_classified=pairs_classified,
            entries=[e.model_dump(mode="json") for e in entries],
            overall_ambiguity_level=ambiguity_level,
            summary=summary,
            recommended_action=action,
        )

        return AgentOutput(
            agent_id=self.agent_id,
            output=analysis.model_dump(),
            output_type="ContradictionAnalysis",
            summary=summary,
            model_tier=self.model_tier,
            model_version=",".join(sorted(model_versions)),
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            cost=round(total_cost, 6),
        )

    # === LLM-powered methods ===

    async def _classify_pair_llm(
        self,
        claim_a: str,
        claim_b: str,
        similarity: float,
        marker_challenge: bool = False,
    ) -> tuple[ContradictionClassification, "LLMResponse | GeminiResponse"]:
        """Classify a single pair via LLM structured output."""

        challenge_hint = ""
        if marker_challenge:
            challenge_hint = (
                "\n\nMarker challenge: opposite-direction lexical markers were detected. "
                "Choose contextual only if explicit context mismatch evidence is present in claim text."
            )

        messages = [
            {
                "role": "user",
                "content": (
                    f"## Claim A\n{claim_a}\n\n"
                    f"## Claim B\n{claim_b}\n\n"
                    f"## Metadata\n"
                    f"Semantic similarity: {similarity:.2f}\n\n"
                    f"Follow the 5-step decision procedure from the system prompt. "
                    f"Answer each step:\n"
                    f"1. METHODOLOGICAL? Are different methods/techniques being compared?\n"
                    f"2. TEMPORAL? Do claims differ by time-point/phase/stage?\n"
                    f"3. MAGNITUDE? Same direction but different effect size/significance?\n"
                    f"4. CONTEXTUAL? Different biological contexts explain the difference?\n"
                    f"5. If none above -> DIRECT (opposite direction, same conditions).\n\n"
                    f"Classify this pair using the taxonomy."
                    f"{challenge_hint}"
                ),
            }
        ]

        result, meta = await self._complete_structured(
            messages=messages,
            response_model=ContradictionClassification,
            temperature=0.0,
        )
        return result, meta

    async def classify_pair(
        self,
        claim_a: str,
        claim_b: str,
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
    ) -> tuple[ResolutionOutput, "LLMResponse | GeminiResponse"]:
        """Generate resolution hypotheses for a confirmed contradiction."""

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

        result, meta = await self._complete_structured(
            messages=messages,
            response_model=ResolutionOutput,
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
            if not isinstance(output, dict):
                continue

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


class _NullMemory:
    """Null-object memory that returns empty results."""

    def search(self, collection: str, query: str, n_results: int = 5) -> list[dict]:
        return []
