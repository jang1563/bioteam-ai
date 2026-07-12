"""WorkflowRouter — auto-recommend next workflow based on results.

Hybrid approach: rule-based (9 default rules) + LLM fallback.
Cycle detection: max routing depth=3, tracks chain in session_manifest.

Toggle: settings.routing_enabled (default False).
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.routing import (
    DEFAULT_ROUTING_RULES,
    RoutingRecommendation,
    RoutingRule,
)
from app.models.workflow import WorkflowInstance

logger = logging.getLogger(__name__)

# Maximum depth for auto-routing chains (prevents infinite loops)
MAX_ROUTING_DEPTH = 3


class WorkflowRouter:
    """Routes completed workflows to recommended next workflows.

    Uses rule-based matching against step results, with optional
    LLM fallback for cases where no rules match.
    """

    def __init__(
        self,
        rules: list[RoutingRule] | None = None,
        llm_layer=None,
        max_depth: int = MAX_ROUTING_DEPTH,
    ) -> None:
        self.rules = sorted(
            rules or DEFAULT_ROUTING_RULES,
            key=lambda r: r.priority,
            reverse=True,
        )
        self._llm_layer = llm_layer
        self._max_depth = max_depth

    def recommend_next(
        self,
        instance: WorkflowInstance,
        step_results: dict[str, Any],
    ) -> list[RoutingRecommendation]:
        """Generate routing recommendations for a completed workflow.

        Args:
            instance: The completed workflow instance.
            step_results: All step results from the workflow run.

        Returns:
            Sorted list of recommendations (highest confidence first).
        """
        if instance.state != "COMPLETED":
            return []

        # Cycle detection: check routing depth
        routing_chain = instance.session_manifest.get("routing_chain", [])
        if len(routing_chain) >= self._max_depth:
            logger.warning(
                "Routing depth %d reached max %d for workflow %s, stopping",
                len(routing_chain), self._max_depth, instance.id,
            )
            return []

        recommendations: list[RoutingRecommendation] = []

        for rule in self.rules:
            # Check source template match
            if rule.source_template != "*" and rule.source_template != instance.template:
                continue

            # Cycle detection: don't route to a template already in the chain
            if rule.target_template in routing_chain:
                logger.debug(
                    "Skipping rule %s→%s: cycle detected in chain %s",
                    rule.source_template, rule.target_template, routing_chain,
                )
                continue

            # Evaluate condition
            match, confidence, reason = self._evaluate_condition(
                rule, instance, step_results,
            )

            if match:
                recommendations.append(RoutingRecommendation(
                    target_template=rule.target_template,
                    reason=reason or rule.description,
                    confidence=confidence,
                    auto_execute=rule.auto_execute and confidence > 0.8,
                    rule_id=f"{rule.source_template}→{rule.target_template}:{rule.condition_type}",
                    params={"source_workflow_id": instance.id, "query": instance.query},
                ))

        # Sort by confidence descending
        recommendations.sort(key=lambda r: r.confidence, reverse=True)

        # Deduplicate by target_template (keep highest confidence)
        seen: set[str] = set()
        unique: list[RoutingRecommendation] = []
        for rec in recommendations:
            if rec.target_template not in seen:
                seen.add(rec.target_template)
                unique.append(rec)

        return unique

    def _evaluate_condition(
        self,
        rule: RoutingRule,
        instance: WorkflowInstance,
        step_results: dict[str, Any],
    ) -> tuple[bool, float, str]:
        """Evaluate a routing rule condition against step results.

        Returns (match, confidence, reason).
        """
        ctype = rule.condition_type

        if ctype == "contradiction_count":
            return self._eval_contradiction_count(rule, step_results)
        elif ctype == "integrity_severity":
            return self._eval_integrity_severity(rule, step_results)
        elif ctype == "completion":
            return self._eval_completion(rule, instance)
        elif ctype == "hypothesis_score":
            return self._eval_hypothesis_score(rule, step_results)
        elif ctype == "literature_gaps":
            return self._eval_literature_gaps(rule, step_results)
        elif ctype == "gene_issues":
            return self._eval_gene_issues(rule, step_results)
        else:
            logger.debug("Unknown condition type: %s", ctype)
            return False, 0.0, ""

    @staticmethod
    def _eval_contradiction_count(
        rule: RoutingRule, step_results: dict[str, Any],
    ) -> tuple[bool, float, str]:
        """Check if contradiction count exceeds threshold."""
        threshold = rule.condition_params.get("threshold", 2)
        contra_result = step_results.get("CONTRADICTION_CHECK")
        if not contra_result:
            return False, 0.0, ""

        output = contra_result.output if hasattr(contra_result, "output") else contra_result
        if not isinstance(output, dict):
            return False, 0.0, ""

        count = output.get("contradiction_count", 0)
        contradictions = output.get("contradictions", [])
        if isinstance(contradictions, list):
            count = max(count, len(contradictions))

        if count > threshold:
            confidence = min(0.9, 0.5 + (count - threshold) * 0.1)
            return True, confidence, f"Found {count} contradictions (threshold: {threshold})"
        return False, 0.0, ""

    @staticmethod
    def _eval_integrity_severity(
        rule: RoutingRule, step_results: dict[str, Any],
    ) -> tuple[bool, float, str]:
        """Check if integrity findings have severity >= min_severity."""
        min_severity = rule.condition_params.get("min_severity", "error")
        severity_order = {"info": 0, "warning": 1, "error": 2, "critical": 3}
        min_level = severity_order.get(min_severity, 2)

        integrity_result = step_results.get("INTEGRITY_CHECK")
        if not integrity_result:
            return False, 0.0, ""

        output = integrity_result.output if hasattr(integrity_result, "output") else integrity_result
        if not isinstance(output, dict):
            return False, 0.0, ""

        findings = output.get("findings", [])
        max_sev = 0
        for f in findings:
            sev = severity_order.get(f.get("severity", "info"), 0)
            max_sev = max(max_sev, sev)

        if max_sev >= min_level:
            sev_name = [k for k, v in severity_order.items() if v == max_sev][0]
            confidence = 0.6 + max_sev * 0.1
            return True, min(0.95, confidence), f"Integrity findings at {sev_name} level"
        return False, 0.0, ""

    @staticmethod
    def _eval_completion(
        rule: RoutingRule, instance: WorkflowInstance,
    ) -> tuple[bool, float, str]:
        """Check if workflow completed successfully."""
        if instance.state == "COMPLETED":
            return True, 0.5, f"{instance.template} completed successfully"
        return False, 0.0, ""

    @staticmethod
    def _eval_hypothesis_score(
        rule: RoutingRule, step_results: dict[str, Any],
    ) -> tuple[bool, float, str]:
        """Check if top hypothesis confidence exceeds threshold."""
        threshold = rule.condition_params.get("threshold", 0.7)

        # Look for hypothesis results in various step names
        for step_id in ("HYPOTHESIZE", "GENERATE", "RANK"):
            hyp_result = step_results.get(step_id)
            if hyp_result:
                output = hyp_result.output if hasattr(hyp_result, "output") else hyp_result
                if isinstance(output, dict):
                    hypotheses = output.get("hypotheses", [])
                    if hypotheses and isinstance(hypotheses, list):
                        top = hypotheses[0]
                        score = top.get("confidence", top.get("score", 0))
                        if score > threshold:
                            return True, score, f"Top hypothesis scored {score:.2f} (threshold: {threshold})"

        return False, 0.0, ""

    @staticmethod
    def _eval_literature_gaps(
        rule: RoutingRule, step_results: dict[str, Any],
    ) -> tuple[bool, float, str]:
        """Check if review identified literature gaps."""
        threshold = rule.condition_params.get("threshold", 1)

        review_result = step_results.get("SYNTHESIZE_REVIEW") or step_results.get("REPORT")
        if not review_result:
            return False, 0.0, ""

        output = review_result.output if hasattr(review_result, "output") else review_result
        if not isinstance(output, dict):
            return False, 0.0, ""

        gaps = output.get("literature_gaps", [])
        major_comments = output.get("major_comments", [])

        gap_count = len(gaps) if isinstance(gaps, list) else 0
        # Also count major comments mentioning "literature" as potential gaps
        lit_major = sum(
            1 for c in (major_comments if isinstance(major_comments, list) else [])
            if isinstance(c, (str, dict)) and "literature" in str(c).lower()
        )

        total_gaps = gap_count + lit_major
        if total_gaps >= threshold:
            return True, min(0.8, 0.4 + total_gaps * 0.1), f"Found {total_gaps} literature gaps"
        return False, 0.0, ""

    @staticmethod
    def _eval_gene_issues(
        rule: RoutingRule, step_results: dict[str, Any],
    ) -> tuple[bool, float, str]:
        """Check if gene name issues were found."""
        threshold = rule.condition_params.get("threshold", 1)

        # Check integrity step or any step with gene findings
        for step_id in ("INTEGRITY_CHECK", "GENOMIC_ANALYSIS", "REPORT"):
            result = step_results.get(step_id)
            if not result:
                continue
            output = result.output if hasattr(result, "output") else result
            if not isinstance(output, dict):
                continue

            findings = output.get("findings", [])
            gene_issues = [
                f for f in findings
                if isinstance(f, dict) and f.get("category") == "gene_name"
            ]
            if len(gene_issues) >= threshold:
                return True, min(0.85, 0.5 + len(gene_issues) * 0.1), \
                    f"Found {len(gene_issues)} gene name issues"

        return False, 0.0, ""
