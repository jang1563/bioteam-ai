"""Tests for DigestAgent."""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.digest_agent import DigestAgent, DigestHighlight, DigestSummary
from app.llm.mock_layer import MockLLMLayer
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage

# === Fixtures ===


def _make_mock_summary():
    return DigestSummary(
        executive_summary="This week saw major advances in AI-driven protein structure prediction and new genomics tools.",
        highlights=[
            DigestHighlight(
                title="AlphaFold 3 Update",
                source="arxiv",
                one_liner="Extended protein folding to RNA-protein complexes",
                why_important="Broadens structural prediction beyond proteins.",
            ),
            DigestHighlight(
                title="BioGPT-2",
                source="huggingface",
                one_liner="New foundation model for biomedical text",
                why_important="State-of-the-art on biomedical NER benchmarks.",
            ),
        ],
        trends=[
            "Foundation models increasingly applied to biology",
            "Growing interest in multimodal biology-AI integration",
        ],
        recommended_reads=[
            "AlphaFold 3 Update",
            "BioGPT-2",
        ],
    )


def _make_agent(mock_summary=None):
    responses = {}
    if mock_summary:
        responses["haiku:DigestSummary"] = mock_summary
    mock = MockLLMLayer(responses)
    spec = DigestAgent.load_spec("digest_agent")
    return DigestAgent(spec, mock), mock


def _make_context(entries=None, topic_name="AI in Biology"):
    data = {
        "topic_name": topic_name,
        "entries": entries or [
            {"title": "Paper A", "source": "arxiv", "abstract": "AI for genomics."},
            {"title": "Paper B", "source": "pubmed", "abstract": "ML in drug discovery."},
        ],
    }
    return ContextPackage(task_description=json.dumps(data))


# === Output Model Tests ===


def test_digest_summary_creation():
    """DigestSummary should be constructable with all fields."""
    summary = _make_mock_summary()
    assert len(summary.highlights) == 2
    assert len(summary.trends) == 2
    assert len(summary.recommended_reads) == 2
    assert "protein" in summary.executive_summary.lower()


def test_digest_summary_defaults():
    """DigestSummary should have sensible defaults."""
    summary = DigestSummary(executive_summary="Test")
    assert summary.highlights == []
    assert summary.trends == []
    assert summary.recommended_reads == []


def test_digest_highlight_model():
    """DigestHighlight should have required fields."""
    hl = DigestHighlight(
        title="Test Paper",
        source="arxiv",
        one_liner="Important finding",
    )
    assert hl.title == "Test Paper"
    assert hl.why_important == ""  # Optional


# === Agent Tests ===


def test_agent_loads_spec():
    """Agent should load spec from YAML."""
    agent, _ = _make_agent()
    assert agent.spec.id == "digest_agent"
    assert agent.spec.model_tier == "haiku"
    assert agent.spec.tier == "engine"


def test_agent_loads_prompt():
    """Agent should load system prompt from .md file."""
    agent, _ = _make_agent()
    assert "Research Digest Agent" in agent.system_prompt


def test_summarize_returns_agent_output():
    """summarize should return an AgentOutput."""
    agent, _ = _make_agent(_make_mock_summary())
    context = _make_context()
    output = asyncio.run(agent.run(context))

    assert isinstance(output, AgentOutput)
    assert output.output_type == "DigestSummary"
    assert output.error is None


def test_summarize_output_structure():
    """Output should contain DigestSummary fields."""
    agent, _ = _make_agent(_make_mock_summary())
    context = _make_context()
    output = asyncio.run(agent.run(context))

    assert "executive_summary" in output.output
    assert "highlights" in output.output
    assert "trends" in output.output
    assert "recommended_reads" in output.output


def test_summarize_sends_correct_messages():
    """Agent should send context entries to LLM."""
    agent, mock = _make_agent(_make_mock_summary())
    entries = [
        {"title": "Specific Paper", "source": "biorxiv", "abstract": "Novel method."},
    ]
    context = _make_context(entries=entries)
    asyncio.run(agent.run(context))

    assert len(mock.call_log) == 1
    call = mock.call_log[0]
    assert call["model_tier"] == "haiku"
    assert "Specific Paper" in call["messages"][0]["content"]


def test_summarize_summary_truncated():
    """Output summary should be truncated to 200 chars."""
    long_summary = DigestSummary(
        executive_summary="A" * 300,
        highlights=[],
        trends=[],
        recommended_reads=[],
    )
    agent, _ = _make_agent(long_summary)
    context = _make_context()
    output = asyncio.run(agent.run(context))

    assert len(output.summary) <= 200


def test_summarize_with_default_mock():
    """Agent should work even without pre-configured mock responses (uses _build_default)."""
    agent, _ = _make_agent()  # No mock responses configured
    context = _make_context()
    output = asyncio.run(agent.run(context))

    assert isinstance(output, AgentOutput)
    assert output.error is None


# === Highlight URL Tests ===


def test_digest_highlight_with_url():
    """DigestHighlight should accept url field."""
    hl = DigestHighlight(
        title="Paper with URL",
        source="arxiv",
        one_liner="Important finding",
        url="https://arxiv.org/abs/2502.11111",
    )
    assert hl.url == "https://arxiv.org/abs/2502.11111"


def test_digest_highlight_url_defaults_empty():
    """DigestHighlight url should default to empty string."""
    hl = DigestHighlight(
        title="Paper without URL",
        source="pubmed",
        one_liner="Finding",
    )
    assert hl.url == ""
