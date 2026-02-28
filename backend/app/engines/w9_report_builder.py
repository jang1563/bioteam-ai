"""W9 Report Builder — assembles the final bioinformatics analysis report.

Takes the accumulated step_results from the W9 runner and constructs
a complete W9BioinformaticsReport with all phase outputs.

Anti-hallucination: aggregates unverified_bio_claims from all phases
into the top-level all_unverified_claims field for reviewer attention.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.w9_analysis import (
    CrossOmicsIntegrationResult,
    DataManifest,
    ExperimentalDesignPlan,
    ExpressionAnalysisResult,
    GrantRelevanceAnalysis,
    NetworkAnalysisResult,
    NoveltyAssessment,
    PathwayEnrichmentResult,
    ProteinAnalysisResult,
    QCReport,
    ResearchScopeDefinition,
    VariantAnnotationResult,
    W9BioinformaticsReport,
)

logger = logging.getLogger(__name__)


def build_w9_report(
    workflow_id: str,
    query: str,
    step_results: dict[str, Any],
    total_cost_usd: float = 0.0,
) -> W9BioinformaticsReport:
    """Build the complete W9 report from accumulated step results.

    Args:
        workflow_id: The workflow instance ID.
        query: Original research query.
        step_results: Dict of {step_id: step_output} from the runner.
        total_cost_usd: Total cost incurred by the workflow.

    Returns:
        Complete W9BioinformaticsReport ready for serialization.
    """
    def _get(step_id: str, model_class, default=None):
        """Extract a step result and cast to the expected model, or return default."""
        raw = step_results.get(step_id)
        if raw is None:
            return default or model_class()
        if isinstance(raw, model_class):
            return raw
        if isinstance(raw, dict):
            try:
                return model_class(**raw)
            except Exception:
                return default or model_class()
        return default or model_class()

    # Collect all unverified claims across phases
    all_unverified: list[str] = []
    for step_id, result in step_results.items():
        if isinstance(result, dict):
            claims = result.get("unverified_bio_claims", [])
        elif hasattr(result, "unverified_bio_claims"):
            claims = result.unverified_bio_claims
        else:
            claims = []
        for claim in claims:
            all_unverified.append(f"[{step_id}] {claim}")

    # Extract key findings from novelty assessment
    novelty: NoveltyAssessment = _get("NOVELTY_ASSESSMENT", NoveltyAssessment)
    key_findings = []
    for finding in novelty.novel_findings[:5]:
        if isinstance(finding, dict):
            key_findings.append(finding.get("description", str(finding)))
        else:
            key_findings.append(str(finding))
    for finding in novelty.confirmed_findings[:3]:
        if isinstance(finding, dict):
            key_findings.append(f"[Confirmed] {finding.get('description', str(finding))}")

    # Executive summary from cross-omics or novelty
    cross_omics: CrossOmicsIntegrationResult = _get("CROSS_OMICS_INTEGRATION", CrossOmicsIntegrationResult)
    exec_summary = step_results.get("REPORT_DRAFT", "")
    if not exec_summary:
        exec_summary = (
            f"Analysis of '{query}' identified {len(cross_omics.causal_candidates)} "
            f"causal candidates and {len(novelty.novel_findings)} novel findings."
        )

    # Limitations
    limitations = []
    qc: QCReport = _get("QC", QCReport)
    if qc.samples_failed > 0:
        limitations.append(f"{qc.samples_failed} samples failed QC and were excluded.")
    if all_unverified:
        limitations.append(
            f"{len(all_unverified)} biological claims could not be fully grounded "
            "in provided data — see all_unverified_claims."
        )

    report = W9BioinformaticsReport(
        workflow_id=workflow_id,
        query=query,
        generated_at=datetime.now(timezone.utc),
        scope=_get("SCOPE", ResearchScopeDefinition),
        data_manifest=_get("INGEST_DATA", DataManifest),
        qc_report=qc,
        variant_annotation=_get("VARIANT_ANNOTATION", VariantAnnotationResult),
        expression_analysis=_get("EXPRESSION_ANALYSIS", ExpressionAnalysisResult),
        protein_analysis=_get("PROTEIN_ANALYSIS", ProteinAnalysisResult),
        pathway_enrichment=_get("PATHWAY_ENRICHMENT", PathwayEnrichmentResult),
        network_analysis=_get("NETWORK_ANALYSIS", NetworkAnalysisResult),
        cross_omics=cross_omics,
        novelty_assessment=novelty,
        experimental_design=_get("EXPERIMENTAL_DESIGN", ExperimentalDesignPlan),
        grant_relevance=_get("GRANT_RELEVANCE", GrantRelevanceAnalysis),
        executive_summary=exec_summary,
        key_findings=key_findings,
        limitations=limitations,
        total_cost_usd=total_cost_usd,
        all_unverified_claims=all_unverified,
    )
    return report


def save_report(
    report: W9BioinformaticsReport,
    output_dir: str | Path = "data/runs",
) -> Path:
    """Save the W9 report as JSON to the output directory.

    Args:
        report: Complete W9BioinformaticsReport.
        output_dir: Directory to save the report file.

    Returns:
        Path to the saved report file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"w9_{report.workflow_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    path = output_dir / filename

    try:
        path.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("W9 report saved to %s", path)
    except Exception as e:
        logger.warning("Failed to save W9 report to %s: %s", path, e)

    return path
