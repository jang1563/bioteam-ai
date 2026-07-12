"""Preset meta-workflow templates — common multi-workflow pipelines.

Templates:
- FULL_RESEARCH_PIPELINE: W1→W2→W6(conditional)→W3→W4
- INTEGRITY_DEEP_DIVE: W1→W7→W8(conditional)
- DRUG_DISCOVERY_PIPELINE: W1→W10→W8
"""

from __future__ import annotations

from app.models.meta_workflow import MetaWorkflowDef, MetaWorkflowNode

# ── Full Research Pipeline ────────────────────────────────────────────
# W1 (Literature) → W2 (Hypothesis) → W6 (Ambiguity, conditional)
# → W3 (Data Analysis) → W4 (Manuscript)

FULL_RESEARCH_PIPELINE = MetaWorkflowDef(
    id="full_research_pipeline",
    name="Full Research Pipeline",
    description=(
        "End-to-end research workflow: literature review → hypothesis generation "
        "→ ambiguity analysis (if contradictions found) → data analysis → manuscript drafting"
    ),
    nodes=[
        MetaWorkflowNode(
            id="lit_review",
            template="W1",
            depends_on=[],
        ),
        MetaWorkflowNode(
            id="hypothesis",
            template="W2",
            depends_on=["lit_review"],
        ),
        MetaWorkflowNode(
            id="ambiguity",
            template="W6",
            depends_on=["lit_review"],
            condition="node.lit_review.contradiction_count > 2",
        ),
        MetaWorkflowNode(
            id="data_analysis",
            template="W3",
            depends_on=["hypothesis"],
            human_checkpoint=True,
        ),
        MetaWorkflowNode(
            id="manuscript",
            template="W4",
            depends_on=["data_analysis"],
        ),
    ],
)

# ── Integrity Deep Dive ──────────────────────────────────────────────
# W1 (Literature) → W7 (Integrity Audit) → W8 (Peer Review, conditional)

INTEGRITY_DEEP_DIVE = MetaWorkflowDef(
    id="integrity_deep_dive",
    name="Integrity Deep Dive",
    description=(
        "Literature review with thorough integrity auditing and optional "
        "peer review for papers with identified issues"
    ),
    nodes=[
        MetaWorkflowNode(
            id="lit_review",
            template="W1",
            depends_on=[],
        ),
        MetaWorkflowNode(
            id="integrity",
            template="W7",
            depends_on=["lit_review"],
        ),
        MetaWorkflowNode(
            id="peer_review",
            template="W8",
            depends_on=["integrity"],
            condition="node.integrity.findings_count > 0",
            human_checkpoint=True,
        ),
    ],
)

# ── Drug Discovery Pipeline ─────────────────────────────────────────
# W1 (Literature) → W10 (Drug Discovery) → W8 (Peer Review)

DRUG_DISCOVERY_PIPELINE = MetaWorkflowDef(
    id="drug_discovery_pipeline",
    name="Drug Discovery Pipeline",
    description=(
        "Literature review → drug discovery analysis (ChEMBL + ClinicalTrials) "
        "→ peer review of findings"
    ),
    nodes=[
        MetaWorkflowNode(
            id="lit_review",
            template="W1",
            depends_on=[],
        ),
        MetaWorkflowNode(
            id="drug_discovery",
            template="W10",
            depends_on=["lit_review"],
        ),
        MetaWorkflowNode(
            id="peer_review",
            template="W8",
            depends_on=["drug_discovery"],
            human_checkpoint=True,
        ),
    ],
)

# ── Registry of all preset templates ─────────────────────────────────

META_TEMPLATES: dict[str, MetaWorkflowDef] = {
    "full_research_pipeline": FULL_RESEARCH_PIPELINE,
    "integrity_deep_dive": INTEGRITY_DEEP_DIVE,
    "drug_discovery_pipeline": DRUG_DISCOVERY_PIPELINE,
}
