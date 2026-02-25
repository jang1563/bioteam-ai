"""W1 Report Builder — assembles final report, SessionManifest, and PRISMA flow.

Extracted from w1_literature.py to reduce module complexity.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.agent import AgentOutput
from app.models.evidence import SessionManifest, PRISMAFlow
from app.models.workflow import WorkflowInstance


def build_prisma_flow(step_results: dict[str, AgentOutput]) -> PRISMAFlow:
    """Build PRISMA flow diagram data from step results."""
    prisma = PRISMAFlow()

    search_result = step_results.get("SEARCH")
    if search_result and hasattr(search_result, 'output') and isinstance(search_result.output, dict):
        prisma.records_identified = search_result.output.get("total_found", 0)
        prisma.records_from_databases = search_result.output.get("total_found", 0)

    screen_result = step_results.get("SCREEN")
    if screen_result and hasattr(screen_result, 'output') and isinstance(screen_result.output, dict):
        prisma.records_screened = screen_result.output.get("total_screened", 0)
        prisma.records_excluded_screening = screen_result.output.get("excluded", 0)

    extract_result = step_results.get("EXTRACT")
    if extract_result and hasattr(extract_result, 'output') and isinstance(extract_result.output, dict):
        prisma.full_text_assessed = extract_result.output.get("total_extracted", 0)
        prisma.studies_included = extract_result.output.get("total_extracted", 0)

    neg_result = step_results.get("NEGATIVE_CHECK")
    if neg_result and hasattr(neg_result, 'output') and isinstance(neg_result.output, dict):
        prisma.negative_results_found = neg_result.output.get("negative_results_found", 0)

    return prisma


def build_session_manifest(
    query: str,
    instance: WorkflowInstance,
    step_results: dict[str, AgentOutput],
) -> dict:
    """Aggregate LLM metadata from all step results into a SessionManifest."""
    llm_calls = []
    total_input = 0
    total_output = 0
    total_cost = 0.0
    model_versions: set[str] = set()

    for step_id, result in step_results.items():
        if not hasattr(result, 'model_version'):
            continue
        if result.model_version and result.model_version != "deterministic":
            model_versions.add(result.model_version)
            llm_calls.append({
                "step_id": step_id,
                "agent_id": result.agent_id,
                "model_version": result.model_version,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cached_input_tokens": result.cached_input_tokens,
                "cost": result.cost,
            })
            total_input += result.input_tokens
            total_output += result.output_tokens
            total_cost += result.cost

    prisma = build_prisma_flow(step_results)

    manifest = SessionManifest(
        workflow_id=instance.id,
        template=instance.template,
        query=query,
        started_at=instance.created_at,
        completed_at=datetime.now(timezone.utc),
        llm_calls=llm_calls,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cost=total_cost,
        model_versions=sorted(model_versions),
        seed_papers=instance.seed_papers,
        system_version="v0.5",
        prisma=prisma,
    )
    return manifest.model_dump(mode="json")


def generate_report(
    query: str,
    instance: WorkflowInstance,
    step_results: dict[str, AgentOutput],
) -> AgentOutput:
    """Assemble the final W1 report from all step results, including SessionManifest."""
    report = {
        "title": f"W1 Literature Review: {query}",
        "query": query,
        "workflow_id": instance.id,
        "steps_completed": list(step_results.keys()),
        "budget_used": instance.budget_total - instance.budget_remaining,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Add step summaries
    for step_id, result in step_results.items():
        if hasattr(result, 'summary'):
            report[f"{step_id.lower()}_summary"] = result.summary
        elif hasattr(result, 'output') and result.output:
            report[f"{step_id.lower()}_summary"] = str(result.output)[:200]

    # Build and attach SessionManifest
    manifest = build_session_manifest(query, instance, step_results)
    report["session_manifest"] = manifest
    instance.session_manifest = manifest

    return AgentOutput(
        agent_id="code_only",
        output=report,
        output_type="W1Report",
        summary=f"W1 Report: {query[:100]}",
    )


def store_tier1_results(
    instance: WorkflowInstance,
    step_results: dict[str, AgentOutput],
) -> None:
    """Store citation report and RCMXT scores on the workflow instance."""
    citation_result = step_results.get("CITATION_CHECK")
    if citation_result and hasattr(citation_result, 'output') and isinstance(citation_result.output, dict):
        instance.citation_report = citation_result.output

    rcmxt_result = step_results.get("RCMXT_SCORE")
    if rcmxt_result and hasattr(rcmxt_result, 'output') and isinstance(rcmxt_result.output, dict):
        instance.rcmxt_scores = rcmxt_result.output.get("scores", [])
