"""Data Integrity Auditor Agent — deterministic checkers + LLM contextual analysis.

Hybrid engine architecture:
  Phase 1: Run all deterministic checkers (gene names, statistics, retractions, metadata)
  Phase 2: LLM contextualizes findings (filter false positives, adjust severity)

Budget cap: max 10 LLM contextualization calls per invocation.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.engines.integrity.finding_models import IntegrityFinding, IntegrityReport
from app.engines.integrity.gene_name_checker import GeneNameChecker
from app.engines.integrity.metadata_validator import MetadataValidator
from app.engines.integrity.retraction_checker import RetractionChecker
from app.engines.integrity.statistical_checker import StatisticalChecker
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage

if TYPE_CHECKING:
    from app.integrations.crossref import CrossrefClient
    from app.integrations.hgnc import HGNCClient
    from app.integrations.pubpeer import PubPeerClient
    from app.llm.layer import LLMResponse

logger = logging.getLogger(__name__)

MAX_LLM_CONTEXT_CALLS = 10

# Valid severity values — used to validate LLM output
_VALID_SEVERITIES = frozenset({"info", "warning", "error", "critical"})

# Regex for extracting DOIs from text
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


# === Pydantic Output Models ===


class IntegrityContextAssessment(BaseModel):
    """LLM output for contextualizing a single deterministic finding."""

    finding_id: str = ""
    is_likely_real: bool = True
    adjusted_severity: str = ""
    biological_context: str = ""
    false_positive_reasoning: str = ""
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class IntegrityAnalysis(BaseModel):
    """Full agent output from audit."""

    query: str = ""
    total_findings: int = 0
    findings_by_severity: dict[str, int] = Field(default_factory=dict)
    findings_by_category: dict[str, int] = Field(default_factory=dict)
    findings: list[dict] = Field(default_factory=list)
    overall_level: Literal["clean", "minor_issues", "significant_issues", "critical"] = "clean"
    summary: str = ""
    recommended_action: str = ""


# === Agent Implementation ===


class DataIntegrityAuditorAgent(BaseAgent):
    """Hybrid engine: deterministic checkers + LLM contextual analysis.

    Phase 1: Run all deterministic checkers (zero LLM cost)
    Phase 2: LLM contextualizes top findings (filter false positives)
    """

    def __init__(
        self,
        spec,
        llm,
        crossref_client: CrossrefClient | None = None,
        hgnc_client: HGNCClient | None = None,
        pubpeer_client: PubPeerClient | None = None,
    ) -> None:
        super().__init__(spec, llm)
        self._gene_checker = GeneNameChecker(hgnc_client=hgnc_client)
        self._stat_checker = StatisticalChecker()
        self._retraction_checker = RetractionChecker(
            crossref_client=crossref_client,
            pubpeer_client=pubpeer_client,
        )
        self._metadata_validator = MetadataValidator()

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Core execution: run full integrity audit pipeline."""
        return await self.audit(context)

    async def audit(self, context: ContextPackage) -> AgentOutput:
        """Full audit pipeline: deterministic checks → LLM contextualization.

        Phase 1: Run all deterministic checkers
        Phase 2: LLM contextualizes findings (capped at MAX_LLM_CONTEXT_CALLS)
        """
        query = context.task_description
        text = self._extract_text(context)
        dois = self._extract_dois(text)

        # Phase 1: Deterministic checks
        findings: list[IntegrityFinding] = []

        # Gene name checks
        gene_findings = self._gene_checker.check_text(text)
        findings.extend(gene_findings)

        # Statistical checks
        stat_findings = self._stat_checker.extract_and_check_stats(text)
        findings.extend(stat_findings)

        # Retraction checks (async)
        if dois:
            retraction_findings = await self._retraction_checker.check_batch(dois)
            findings.extend(retraction_findings)

        # Metadata checks
        metadata_findings = self._metadata_validator.check_all(text)
        findings.extend(metadata_findings)

        # Phase 2: LLM contextualization (capped)
        total_input_tokens = 0
        total_output_tokens = 0

        # Only contextualize warning+ findings
        contextualizable = [f for f in findings if f.severity in ("warning", "error", "critical")]
        for finding in contextualizable[:MAX_LLM_CONTEXT_CALLS]:
            try:
                assessment, meta = await self._contextualize_finding(finding, text)
                total_input_tokens += meta.input_tokens
                total_output_tokens += meta.output_tokens

                # Apply LLM adjustments
                if not assessment.is_likely_real:
                    finding.confidence *= 0.3  # Heavily reduce confidence
                    finding.severity = "info"  # Downgrade
                elif assessment.adjusted_severity and assessment.adjusted_severity in _VALID_SEVERITIES:
                    finding.severity = assessment.adjusted_severity
                finding.confidence = min(finding.confidence, assessment.confidence)

            except Exception as e:
                logger.debug("LLM contextualization failed for finding %s: %s", finding.id, e)
                continue

        # Build report
        report = self._build_report(findings, query)

        return self.build_output(
            output=IntegrityAnalysis(
                query=query,
                total_findings=report.total_findings,
                findings_by_severity=report.findings_by_severity,
                findings_by_category=report.findings_by_category,
                findings=[f.model_dump(mode="json") for f in report.findings],
                overall_level=report.overall_level,
                summary=report.summary,
                recommended_action=report.recommended_action,
            ).model_dump(),
            output_type="IntegrityAnalysis",
            summary=report.summary,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
        )

    async def contextualize_only(
        self,
        findings_dicts: list[dict],
        text: str,
        query: str = "contextualize",
    ) -> AgentOutput:
        """LLM-only contextualization of pre-collected findings (used by W7).

        Skips all deterministic checkers — assumes findings were already collected
        by the W7 runner's individual steps. Only runs LLM Phase 2.
        """
        # Reconstruct IntegrityFinding objects from dicts
        findings: list[IntegrityFinding] = []
        for fd in findings_dicts:
            try:
                findings.append(IntegrityFinding(**fd))
            except Exception:
                # If the dict doesn't match, create a minimal finding
                findings.append(IntegrityFinding(
                    category=fd.get("category", "metadata_error"),
                    severity=fd.get("severity", "warning"),
                    title=fd.get("title", ""),
                    description=fd.get("description", ""),
                    source_text=fd.get("source_text", ""),
                    confidence=fd.get("confidence", 0.8),
                    checker=fd.get("checker", ""),
                ))

        # Phase 2: LLM contextualization only
        total_input_tokens = 0
        total_output_tokens = 0

        contextualizable = [f for f in findings if f.severity in ("warning", "error", "critical")]
        for finding in contextualizable[:MAX_LLM_CONTEXT_CALLS]:
            try:
                assessment, meta = await self._contextualize_finding(finding, text)
                total_input_tokens += meta.input_tokens
                total_output_tokens += meta.output_tokens

                if not assessment.is_likely_real:
                    finding.confidence *= 0.3
                    finding.severity = "info"
                elif assessment.adjusted_severity and assessment.adjusted_severity in _VALID_SEVERITIES:
                    finding.severity = assessment.adjusted_severity
                finding.confidence = min(finding.confidence, assessment.confidence)
            except Exception as e:
                logger.debug("LLM contextualization failed for finding: %s", e)
                continue

        report = self._build_report(findings, query)

        return self.build_output(
            output=IntegrityAnalysis(
                query=query,
                total_findings=report.total_findings,
                findings_by_severity=report.findings_by_severity,
                findings_by_category=report.findings_by_category,
                findings=[f.model_dump(mode="json") for f in report.findings],
                overall_level=report.overall_level,
                summary=report.summary,
                recommended_action=report.recommended_action,
            ).model_dump(),
            output_type="IntegrityAnalysis",
            summary=report.summary,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
        )

    async def quick_check(self, text: str, dois: list[str] | None = None) -> AgentOutput:
        """Lightweight check for W1 integration (deterministic only, no LLM).

        Zero LLM cost. Returns findings from deterministic checkers only.
        """
        findings: list[IntegrityFinding] = []

        # Gene name checks
        findings.extend(self._gene_checker.check_text(text))

        # Statistical checks
        findings.extend(self._stat_checker.extract_and_check_stats(text))

        # Retraction checks (async)
        if dois:
            findings.extend(await self._retraction_checker.check_batch(dois))

        # Metadata checks
        findings.extend(self._metadata_validator.check_all(text))

        report = self._build_report(findings, "quick_check")

        return self.build_output(
            output=IntegrityAnalysis(
                query="quick_check",
                total_findings=report.total_findings,
                findings_by_severity=report.findings_by_severity,
                findings_by_category=report.findings_by_category,
                findings=[f.model_dump(mode="json") for f in report.findings],
                overall_level=report.overall_level,
                summary=report.summary,
                recommended_action=report.recommended_action,
            ).model_dump(),
            output_type="IntegrityAnalysis",
            summary=report.summary,
        )

    # === LLM contextualization ===

    async def _contextualize_finding(
        self,
        finding: IntegrityFinding,
        full_text: str,
    ) -> tuple[IntegrityContextAssessment, "LLMResponse"]:
        """Use LLM to assess whether a deterministic finding is a true positive."""
        # Truncate context to keep prompt manageable
        context_window = full_text[:3000] if len(full_text) > 3000 else full_text

        messages = [
            {
                "role": "user",
                "content": (
                    f"## Finding to Assess\n"
                    f"**Category**: {finding.category}\n"
                    f"**Severity**: {finding.severity}\n"
                    f"**Title**: {finding.title}\n"
                    f"**Description**: {finding.description}\n"
                    f"**Source text**: '{finding.source_text}'\n\n"
                    f"## Surrounding Context\n{context_window}\n\n"
                    f"Assess this finding. Is it a genuine integrity issue or a false positive? "
                    f"Consider the biological and textual context."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=IntegrityContextAssessment,
            system=self.system_prompt_cached,
            temperature=0.0,
        )
        result.finding_id = finding.id
        return result, meta

    # === Helpers ===

    def _extract_text(self, context: ContextPackage) -> str:
        """Extract all text from context package for analysis."""
        parts: list[str] = []

        if context.task_description:
            parts.append(context.task_description)

        for step_out in context.prior_step_outputs:
            output = step_out.get("output", step_out) if isinstance(step_out, dict) else step_out
            if isinstance(output, dict):
                for key in ("text", "content", "abstract", "summary", "key_findings"):
                    val = output.get(key, "")
                    if isinstance(val, str) and val:
                        parts.append(val)
                    elif isinstance(val, list):
                        parts.extend(str(v) for v in val if v)

        return "\n\n".join(parts)

    def _extract_dois(self, text: str) -> list[str]:
        """Extract DOIs from text."""
        return list(set(_DOI_RE.findall(text)))

    def _build_report(self, findings: list[IntegrityFinding], query: str) -> IntegrityReport:
        """Build an IntegrityReport from a list of findings."""
        # Count by severity and category
        by_severity: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for f in findings:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
            by_category[f.category] = by_category.get(f.category, 0) + 1

        total = len(findings)
        level = self._compute_level(by_severity)
        summary = self._build_summary(total, by_severity, level)
        action = self._recommend_action(level)

        return IntegrityReport(
            total_findings=total,
            findings_by_severity=by_severity,
            findings_by_category=by_category,
            findings=findings,
            overall_level=level,
            summary=summary,
            recommended_action=action,
        )

    @staticmethod
    def _compute_level(by_severity: dict[str, int]) -> str:
        if by_severity.get("critical", 0) > 0:
            return "critical"
        if by_severity.get("error", 0) > 0:
            return "significant_issues"
        if by_severity.get("warning", 0) > 0:
            return "minor_issues"
        return "clean"

    @staticmethod
    def _build_summary(total: int, by_severity: dict[str, int], level: str) -> str:
        if total == 0:
            return "No data integrity issues found."
        parts = [f"Found {total} integrity issue(s)."]
        for sev in ("critical", "error", "warning", "info"):
            count = by_severity.get(sev, 0)
            if count > 0:
                parts.append(f"{count} {sev}")
        parts.append(f"Overall: {level}.")
        return " ".join(parts)

    @staticmethod
    def _recommend_action(level: str) -> str:
        if level == "clean":
            return "No action needed."
        if level == "minor_issues":
            return "Review flagged items when convenient."
        if level == "significant_issues":
            return "Review flagged items before relying on this data."
        return "Critical integrity issues detected. Immediate review required."
