"""Machine Learning & Deep Learning Agent (Team 5) — ML/DL model design, training, evaluation.

Responsibilities:
1. Model recommendation and architecture design (default run)
2. Feature engineering guidance for omics data
3. Training strategy and validation design
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field

# === Output Models ===


class MLAnalysisResult(BaseModel):
    """Result of a machine learning / deep learning analysis query."""

    query: str
    models_recommended: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    metrics: list[dict] = Field(default_factory=list)
    architecture: str = ""
    training_strategy: str = ""
    validation_approach: str = ""
    summary: str = ""
    confidence: float = 0.0
    caveats: list[str] = Field(default_factory=list)


# === Agent Implementation ===


class MachineLearningAgent(BaseAgent):
    """Specialist agent for machine learning and deep learning in biology.

    Covers classical ML (random forests, SVMs, gradient boosting), deep learning
    (CNNs, transformers, autoencoders), and bioinformatics-specific models
    (protein language models, single-cell foundation models).
    """

    async def run(self, context: ContextPackage) -> AgentOutput:
        """Answer a machine learning or deep learning query."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Analyze this machine learning / deep learning query:\n\n"
                    f"{context.task_description}\n\n"
                    f"Provide a structured analysis including recommended models, "
                    f"feature engineering, evaluation metrics, architecture details, "
                    f"training strategy, validation approach, and confidence level."
                ),
            }
        ]

        result, meta = await self.llm.complete_structured(
            messages=messages,
            model_tier=self.model_tier,
            response_model=MLAnalysisResult,
            system=self.system_prompt_cached,
        )

        return self.build_output(
            output=result.model_dump(),
            output_type="MLAnalysisResult",
            summary=result.summary[:200] if result.summary else f"Analyzed: {context.task_description[:100]}",
            llm_response=meta,
        )
