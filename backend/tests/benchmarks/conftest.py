"""Shared fixtures for benchmark tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from app.models.agent import AgentOutput

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def make_agent_output(output: dict[str, Any], summary: str = "") -> AgentOutput:
    """Create a mock AgentOutput with the given output dict."""
    return AgentOutput(
        agent_id="mock",
        output=output,
        summary=summary or str(output),
    )


@pytest.fixture()
def cancer_pathway_step_results() -> dict[str, AgentOutput]:
    """Realistic step_results for cancer_pathway benchmark.

    Returns mock W9 outputs that overlap with cancer_pathway ground truth
    (TP53, PIK3CA, PTEN, ERBB2, etc.) to test the full scoring pipeline.
    """
    return {
        "LITERATURE_COMPARISON": make_agent_output({
            "genes_mentioned": ["TP53", "PIK3CA", "PTEN", "ERBB2", "MYC", "ESR1", "CDH1", "GATA3"],
            "validated_genes": ["TP53", "PIK3CA", "ERBB2"],
            "key_pathways": [
                "PI3K-Akt signaling pathway",
                "p53 signaling pathway",
                "cell cycle",
                "MAPK signaling pathway",
                "estrogen signaling pathway",
            ],
        }),
        "CROSS_OMICS_INTEGRATION": make_agent_output({
            "key_genes": ["TP53", "PIK3CA", "PTEN", "AKT1", "ERBB2", "MYC", "RB1"],
            "pathways": [
                "apoptosis",
                "mTOR signaling",
                "DNA repair",
            ],
        }),
        "PATHWAY_ENRICHMENT": make_agent_output({
            "top_pathways": [
                {"name": "PI3K-Akt signaling pathway", "pvalue": 1e-8},
                {"name": "p53 signaling pathway", "pvalue": 1e-6},
                {"name": "cell cycle", "pvalue": 1e-5},
            ],
        }),
        "EXPRESSION_ANALYSIS": make_agent_output({
            "up_regulated": [
                {"gene": "PIK3CA", "log2FC": 1.5},
                {"gene": "ERBB2", "log2FC": 2.8},
                {"gene": "MYC", "log2FC": 1.2},
                {"gene": "ESR1", "log2FC": 0.9},
            ],
            "down_regulated": [
                {"gene": "TP53", "log2FC": -1.8},
                {"gene": "PTEN", "log2FC": -2.1},
                {"gene": "CDH1", "log2FC": -1.5},
            ],
        }),
    }


@pytest.fixture()
def fixture_degs_step_results() -> dict[str, AgentOutput]:
    """Step results for fixture_degs benchmark (from sample_degs.tsv)."""
    return {
        "EXPRESSION_ANALYSIS": make_agent_output({
            "up_regulated": [
                {"gene": "TP53", "log2FC": 1.82},
                {"gene": "EGFR", "log2FC": 3.21},
                {"gene": "KRAS", "log2FC": 2.67},
                {"gene": "PIK3CA", "log2FC": 1.43},
                {"gene": "ERBB2", "log2FC": 4.12},
            ],
            "down_regulated": [
                {"gene": "BRCA1", "log2FC": -2.45},
                {"gene": "MYC", "log2FC": -1.05},
                {"gene": "CDH1", "log2FC": -3.14},
                {"gene": "CDKN2A", "log2FC": -2.78},
                {"gene": "PTEN", "log2FC": -0.89},
            ],
        }),
        "PATHWAY_ENRICHMENT": make_agent_output({
            "top_pathways": [
                {"name": "PI3K-Akt signaling pathway", "pvalue": 1e-10},
                {"name": "p53 signaling pathway", "pvalue": 1e-7},
                {"name": "MAPK signaling pathway", "pvalue": 1e-6},
                {"name": "cell cycle", "pvalue": 1e-5},
                {"name": "Wnt signaling pathway", "pvalue": 1e-4},
            ],
        }),
    }


@pytest.fixture()
def alzheimer_step_results() -> dict[str, AgentOutput]:
    """Step results for BioAgent Bench alzheimer_mouse task."""
    return {
        "LITERATURE_COMPARISON": make_agent_output({
            "genes_mentioned": ["APP", "PSEN1", "MAPT", "APOE", "TREM2", "CLU", "BACE1", "GSK3B"],
            "key_pathways": [
                "Alzheimer's disease",
                "oxidative phosphorylation",
                "neurotrophin signaling pathway",
                "MAPK signaling pathway",
                "calcium signaling pathway",
            ],
        }),
        "PATHWAY_ENRICHMENT": make_agent_output({
            "top_pathways": [
                {"name": "Alzheimer's disease", "pvalue": 1e-12},
                {"name": "synaptic vesicle cycle", "pvalue": 1e-8},
                {"name": "oxidative phosphorylation", "pvalue": 1e-7},
            ],
        }),
        "CROSS_OMICS_INTEGRATION": make_agent_output({
            "key_genes": ["APP", "PSEN1", "PSEN2", "MAPT", "APOE", "TREM2"],
            "pathways": ["PI3K-Akt signaling pathway", "apoptosis"],
        }),
        "EXPRESSION_ANALYSIS": make_agent_output({
            "up_regulated": [
                {"gene": "APP", "log2FC": 1.5},
                {"gene": "BACE1", "log2FC": 0.8},
                {"gene": "GSK3B", "log2FC": 0.6},
            ],
            "down_regulated": [
                {"gene": "ADAM10", "log2FC": -0.7},
                {"gene": "SORL1", "log2FC": -1.2},
            ],
        }),
    }
