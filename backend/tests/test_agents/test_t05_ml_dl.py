"""Tests for Machine Learning Agent (Team 5) — run, output type, summary."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.agents.teams.t05_ml_dl import (
    MachineLearningAgent,
    MLAnalysisResult,
)
from app.llm.mock_layer import MockLLMLayer
from app.models.messages import ContextPackage


def make_agent(mock_responses: dict | None = None) -> MachineLearningAgent:
    """Create a MachineLearningAgent with MockLLMLayer."""
    spec = BaseAgent.load_spec("t05_ml_dl")
    mock = MockLLMLayer(mock_responses or {})
    return MachineLearningAgent(spec=spec, llm=mock)


def test_run_returns_output():
    """T05 should answer an ML/DL query and return AgentOutput."""
    result = MLAnalysisResult(
        query="Astronaut health risk classifier from multi-omics",
        models_recommended=["XGBoost", "Multi-modal autoencoder"],
        features=["top 500 DEGs", "differentially abundant proteins", "DNA methylation CpGs"],
        metrics=[
            {"name": "AUROC", "value": 0.89},
            {"name": "AUPRC", "value": 0.76},
        ],
        architecture="Late-fusion multi-modal: separate encoders per omics + shared classifier head",
        training_strategy="5-fold stratified CV with early stopping on validation AUROC",
        validation_approach="Leave-one-mission-out cross-validation",
        summary="XGBoost baseline achieves 0.89 AUROC; multi-modal autoencoder recommended for production.",
        confidence=0.80,
        caveats=["Small n limits deep learning generalization; prefer ensemble methods"],
    )
    agent = make_agent({"sonnet:MLAnalysisResult": result})

    context = ContextPackage(
        task_description="Design a classifier to predict astronaut health risk from multi-omics data"
    )

    output = asyncio.run(agent.execute(context))
    assert output.is_success, f"Agent failed: {output.error}"
    assert "XGBoost" in output.output["models_recommended"]
    assert len(output.output["metrics"]) == 2
    assert output.model_version.startswith("mock-")
    print("  PASS: run_returns_output")


def test_output_type():
    """T05 output should have correct output_type."""
    result = MLAnalysisResult(
        query="Test query",
        summary="Test summary for ML output type verification.",
        confidence=0.75,
    )
    agent = make_agent({"sonnet:MLAnalysisResult": result})
    context = ContextPackage(task_description="Test ML query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.output_type == "MLAnalysisResult"
    print("  PASS: output_type")


def test_summary_populated():
    """T05 output should have a populated summary."""
    result = MLAnalysisResult(
        query="Protein-ligand binding prediction architecture",
        summary="Transformer-based model with ESM-2 embeddings recommended for binding affinity prediction.",
        confidence=0.77,
    )
    agent = make_agent({"sonnet:MLAnalysisResult": result})
    context = ContextPackage(task_description="Architecture for predicting protein-ligand binding from sequence")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.summary
    assert len(output.summary) > 0
    assert "Transformer" in output.summary
    print("  PASS: summary_populated")


def test_agent_metadata():
    """T05 output should carry correct agent metadata."""
    agent = make_agent()
    context = ContextPackage(task_description="Test query")

    output = asyncio.run(agent.execute(context))
    assert output.is_success
    assert output.agent_id == "t05_ml_dl"
    assert output.model_tier == "sonnet"
    assert output.model_version == "mock-sonnet"
    assert output.duration_ms >= 0
    print("  PASS: agent_metadata")


def test_spec_loaded_correctly():
    """T05 spec should have expected fields."""
    spec = BaseAgent.load_spec("t05_ml_dl")
    assert spec.id == "t05_ml_dl"
    assert spec.tier == "domain_expert"
    assert spec.model_tier == "sonnet"
    assert spec.criticality == "optional"
    assert spec.division == "computation"
    print("  PASS: spec_loaded_correctly")


if __name__ == "__main__":
    print("Testing Machine Learning Agent (T05):")
    test_run_returns_output()
    test_output_type()
    test_summary_populated()
    test_agent_metadata()
    test_spec_loaded_correctly()
    print("\nAll Machine Learning Agent tests passed!")
