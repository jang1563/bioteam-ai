"""Shared test fixtures for BioTeam-AI backend tests."""

import os
import sys

import pytest

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.knowledge_manager import NoveltyAssessment
from app.agents.project_manager import ProjectStatus
from app.agents.registry import create_registry
from app.agents.research_director import QueryClassification, SynthesisReport
from app.agents.teams.t02_transcriptomics import (
    ExtractedPaperData,
    ExtractionResult,
    ScreeningDecision,
    ScreeningResult,
)
from app.llm.mock_layer import MockLLMLayer
from app.memory.semantic import SemanticMemory
from app.models.evidence import AxisExplanation, LLMRCMXTResponse
from pydantic import BaseModel, Field


class _MockSearchTerms(BaseModel):
    """Mock for KM's internal SearchTerms model."""
    pubmed_queries: list[str] = Field(default_factory=lambda: ["spaceflight anemia[MeSH]"])
    semantic_scholar_queries: list[str] = Field(default_factory=lambda: ["spaceflight anemia erythropoiesis"])
    keywords: list[str] = Field(default_factory=lambda: ["spaceflight", "anemia"])


def _w1_mock_responses() -> dict:
    """Build mock LLM responses covering all W1 agent steps."""
    return {
        "sonnet:QueryClassification": QueryClassification(
            type="simple_query",
            reasoning="Test classification",
            target_agent="t02_transcriptomics",
        ),
        "haiku:ProjectStatus": ProjectStatus(summary="All systems operational"),
        "opus:SynthesisReport": SynthesisReport(
            title="Scope: Spaceflight Anemia Mechanisms",
            summary="Research scope defined: hemolysis, erythropoiesis, and cfRNA biomarkers.",
            key_findings=["Focus on splenic hemolysis pathway"],
        ),
        "sonnet:SearchTerms": _MockSearchTerms(),
        "sonnet:ScreeningResult": ScreeningResult(
            total_screened=3,
            included=2,
            excluded=1,
            decisions=[
                ScreeningDecision(paper_id="p1", decision="include", relevance_score=0.9),
                ScreeningDecision(paper_id="p2", decision="include", relevance_score=0.7),
                ScreeningDecision(paper_id="p3", decision="exclude", relevance_score=0.1),
            ],
        ),
        "sonnet:ExtractionResult": ExtractionResult(
            total_extracted=2,
            papers=[
                ExtractedPaperData(paper_id="p1", genes=["EPO", "TNFSF11"], organism="human"),
                ExtractedPaperData(paper_id="p2", genes=["HBA1"], organism="mouse"),
            ],
            common_genes=["EPO"],
        ),
        "sonnet:NoveltyAssessment": NoveltyAssessment(
            finding="Splenic hemolysis increases by 54% in microgravity",
            is_novel=True,
            novelty_score=0.8,
            reasoning="No prior study quantified splenic contribution specifically.",
        ),
        "sonnet:LLMRCMXTResponse": LLMRCMXTResponse(
            claim_text="Focus on splenic hemolysis pathway",
            axes=[
                AxisExplanation(axis="R", score=0.7, reasoning="Replicated across ISS missions with consistent findings."),
                AxisExplanation(axis="C", score=0.5, reasoning="Condition-specific to microgravity exposure."),
                AxisExplanation(axis="M", score=0.75, reasoning="Well-designed studies with proper controls and DEXA validation."),
                AxisExplanation(axis="T", score=0.65, reasoning="Established finding over multiple missions spanning decades."),
            ],
            x_applicable=False,
            overall_assessment="Well-supported spaceflight physiology finding with moderate confidence.",
            confidence_in_scoring=0.8,
        ),
    }


@pytest.fixture
def mock_llm():
    """MockLLMLayer with standard responses for all W1 agents."""
    return MockLLMLayer(_w1_mock_responses())


@pytest.fixture
def mock_registry(mock_llm):
    """Full registry with mocked agents."""
    return create_registry(mock_llm)


@pytest.fixture
def temp_memory(tmp_path):
    """SemanticMemory with temp directory (auto-cleaned)."""
    return SemanticMemory(persist_dir=str(tmp_path / "chroma"))


@pytest.fixture
def seeded_memory(tmp_path):
    """SemanticMemory with 2 seed papers in literature collection."""
    memory = SemanticMemory(persist_dir=str(tmp_path / "chroma_seeded"))
    memory.add(
        "literature",
        "doi:10.1038/s41591-021-01637-7",
        "Hemolysis is a primary driver of space anemia during spaceflight. "
        "Red blood cell destruction increases by 54% in microgravity.",
        metadata={"doi": "10.1038/s41591-021-01637-7", "year": "2022", "source": "pubmed"},
    )
    memory.add(
        "literature",
        "doi:10.1182/blood.2021014479",
        "TNFSF11 shows significant upregulation in spaceflight cfRNA data, "
        "suggesting bone-blood crosstalk in microgravity adaptation.",
        metadata={"doi": "10.1182/blood.2021014479", "year": "2023", "source": "pubmed"},
    )
    return memory
