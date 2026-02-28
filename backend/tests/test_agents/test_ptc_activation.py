"""Tests for H1 PTC Activation — agent-level PTC wiring.

Validates:
1. BaseAgent._get_ptc_tool_names() returns correct tools per agent
2. BaseAgent._get_ptc_tools() returns tool definitions + implementations
3. BaseAgent.run_with_ptc() two-phase pattern works
4. Domain agents route to PTC when ptc_enabled=True
5. Domain agents fall through when ptc_enabled=False
6. Cost aggregation across PTC + Haiku parse phases
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.agents.base import BaseAgent
from app.config import ModelTier
from app.llm.layer import LLMResponse
from app.models.agent import AgentOutput, AgentSpec
from app.models.messages import ContextPackage
from pydantic import BaseModel, Field


# ── Helpers ────────────────────────────────────────────────────────────


class DummyResult(BaseModel):
    query: str = ""
    summary: str = ""
    confidence: float = 0.0


class ConcreteAgent(BaseAgent):
    """Concrete agent for testing BaseAgent methods."""

    async def run(self, context: ContextPackage) -> AgentOutput:
        return self.build_output(
            output={"query": context.task_description, "summary": "fallback"},
            output_type="DummyResult",
            summary="fallback run",
        )


def _make_spec(agent_id: str = "t01_genomics") -> AgentSpec:
    return AgentSpec(
        id=agent_id,
        name="Test Agent",
        tier="domain_expert",
        version="1.0",
        model_tier="sonnet",
        system_prompt_file="research_director.md",
    )


def _make_context(task: str = "Analyze TP53 variants") -> ContextPackage:
    return ContextPackage(task_description=task)


def _make_llm() -> MagicMock:
    llm = MagicMock()
    llm.build_cached_system.return_value = [{"type": "text", "text": "system", "cache_control": {"type": "ephemeral"}}]
    llm.estimate_cost.return_value = 0.0
    return llm


# ── H1.1: _get_ptc_tool_names ──────────────────────────────────────────


def test_get_ptc_tool_names_t01():
    agent = ConcreteAgent(_make_spec("t01_genomics"), _make_llm())
    names = agent._get_ptc_tool_names()
    assert "run_vep" in names
    assert "check_gene_names" in names
    assert "run_blast" in names


def test_get_ptc_tool_names_t04():
    agent = ConcreteAgent(_make_spec("t04_biostatistics"), _make_llm())
    names = agent._get_ptc_tool_names()
    assert "check_statistics" in names


def test_get_ptc_tool_names_t06():
    agent = ConcreteAgent(_make_spec("t06_systems_bio"), _make_llm())
    names = agent._get_ptc_tool_names()
    assert "run_go_enrichment" in names
    assert "check_gene_names" in names


def test_get_ptc_tool_names_no_classification():
    """Agent without tool classification returns empty list."""
    agent = ConcreteAgent(_make_spec("t05_clinical"), _make_llm())
    names = agent._get_ptc_tool_names()
    assert names == []


# ── H1.2: _get_ptc_tools ──────────────────────────────────────────────


def test_get_ptc_tools_returns_definitions_and_impls():
    agent = ConcreteAgent(_make_spec("t01_genomics"), _make_llm())
    tools, impls = agent._get_ptc_tools()

    # Should have code_execution + VEP + gene_names + blast
    assert len(tools) >= 3
    tool_names = [t.get("name") for t in tools]
    assert "code_execution" in tool_names
    assert "run_vep" in tool_names
    assert "check_gene_names" in tool_names

    # Implementations should match
    assert "run_vep" in impls
    assert "check_gene_names" in impls


def test_get_ptc_tools_no_classification():
    """Agent without classification returns empty tools."""
    agent = ConcreteAgent(_make_spec("t05_clinical"), _make_llm())
    tools, impls = agent._get_ptc_tools()
    assert tools == []
    assert impls == {}


# ── H1.3: run_with_ptc two-phase pattern ─────────────────────────────


@pytest.mark.asyncio
async def test_run_with_ptc_two_phase():
    """run_with_ptc should call complete_with_ptc then complete_structured."""
    llm = _make_llm()
    ptc_meta = LLMResponse(
        model_version="claude-sonnet-4-20250514",
        input_tokens=500, output_tokens=300, cost=0.01,
    )
    parse_meta = LLMResponse(
        model_version="claude-haiku-4-5-20251001",
        input_tokens=200, output_tokens=100, cost=0.001,
    )

    llm.complete_with_ptc = AsyncMock(return_value=(
        "TP53 variant analysis shows missense mutation at codon 175",
        ptc_meta,
        "container-123",
    ))
    llm.complete_structured = AsyncMock(return_value=(
        DummyResult(query="TP53", summary="VEP analysis complete", confidence=0.9),
        parse_meta,
    ))

    agent = ConcreteAgent(_make_spec("t01_genomics"), llm)
    ctx = _make_context("Analyze TP53 R175H variant")

    output = await agent.run_with_ptc(ctx, DummyResult)

    assert output.agent_id == "t01_genomics"
    assert output.output["summary"] == "VEP analysis complete"
    assert output.output["confidence"] == 0.9
    # Cost should be aggregated
    assert output.cost == pytest.approx(0.011)
    assert output.input_tokens == 700
    assert output.output_tokens == 400

    # Verify both phases were called
    llm.complete_with_ptc.assert_called_once()
    llm.complete_structured.assert_called_once()
    # Phase 2 should use Haiku
    call_kwargs = llm.complete_structured.call_args
    assert call_kwargs.kwargs.get("model_tier") == "haiku"


@pytest.mark.asyncio
async def test_run_with_ptc_fallback_no_tools():
    """run_with_ptc should fallback to run() if agent has no PTC tools."""
    llm = _make_llm()
    agent = ConcreteAgent(_make_spec("t05_clinical"), llm)
    ctx = _make_context("Analyze clinical data")

    output = await agent.run_with_ptc(ctx, DummyResult)

    # Should have used fallback run() — check summary
    assert output.summary == "fallback run"
    # PTC should NOT have been called
    assert not hasattr(llm, "complete_with_ptc") or not llm.complete_with_ptc.called


# ── H1.4: Domain agent routing ────────────────────────────────────────


@pytest.fixture
def enable_ptc(monkeypatch):
    """Enable PTC for tests."""
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "ptc_enabled", True)


@pytest.fixture
def disable_ptc(monkeypatch):
    """Ensure PTC is disabled for tests."""
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "ptc_enabled", False)


def _make_ptc_llm():
    """Create LLM mock with PTC and structured call mocks."""
    llm = _make_llm()
    ptc_meta = LLMResponse(model_version="claude-sonnet-4-20250514", cost=0.01)
    parse_meta = LLMResponse(model_version="claude-haiku-4-5-20251001", cost=0.001)

    llm.complete_with_ptc = AsyncMock(return_value=("tool result text", ptc_meta, None))
    llm.complete_structured = AsyncMock(return_value=(
        MagicMock(model_dump=lambda: {"query": "q", "summary": "PTC output"}, summary="PTC output"),
        parse_meta,
    ))
    return llm


@pytest.mark.asyncio
async def test_t01_routes_to_ptc_when_enabled(enable_ptc):
    """GenomicsAgent should route to run_with_ptc when ptc_enabled=True."""
    from app.agents.teams.t01_genomics import GenomicsAgent

    llm = _make_ptc_llm()
    agent = GenomicsAgent(_make_spec("t01_genomics"), llm)
    await agent.run(_make_context("Analyze TP53 variants"))
    assert llm.complete_with_ptc.called


@pytest.mark.asyncio
async def test_t01_uses_structured_when_ptc_disabled(disable_ptc):
    """GenomicsAgent should use complete_structured when ptc_enabled=False."""
    from app.agents.teams.t01_genomics import GenomicsAgent, GenomicsAnalysisResult

    llm = _make_llm()
    result_obj = GenomicsAnalysisResult(query="TP53", summary="structured result", confidence=0.8)
    meta = LLMResponse(model_version="claude-sonnet-4-20250514", cost=0.01)
    llm.complete_structured = AsyncMock(return_value=(result_obj, meta))

    agent = GenomicsAgent(_make_spec("t01_genomics"), llm)
    await agent.run(_make_context("Analyze TP53 variants"))

    assert llm.complete_structured.called


@pytest.mark.asyncio
async def test_t04_routes_to_ptc_when_enabled(enable_ptc):
    """BiostatisticsAgent should route to run_with_ptc when ptc_enabled=True."""
    from app.agents.teams.t04_biostatistics import BiostatisticsAgent

    llm = _make_ptc_llm()
    agent = BiostatisticsAgent(_make_spec("t04_biostatistics"), llm)
    await agent.run(_make_context("Check statistical consistency of reported means"))
    assert llm.complete_with_ptc.called


@pytest.mark.asyncio
async def test_t06_routes_to_ptc_when_enabled(enable_ptc):
    """SystemsBiologyAgent should route to run_with_ptc when ptc_enabled=True."""
    from app.agents.teams.t06_systems_bio import SystemsBiologyAgent

    llm = _make_ptc_llm()
    agent = SystemsBiologyAgent(_make_spec("t06_systems_bio"), llm)
    await agent.run(_make_context("BRCA1 BRCA2 network analysis"))
    assert llm.complete_with_ptc.called


@pytest.mark.asyncio
async def test_t07_routes_to_ptc_when_enabled(enable_ptc):
    """StructuralBiologyAgent should route to run_with_ptc when ptc_enabled=True."""
    from app.agents.teams.t07_structural_bio import StructuralBiologyAgent

    llm = _make_ptc_llm()
    agent = StructuralBiologyAgent(_make_spec("t07_structural_bio"), llm)
    await agent.run(_make_context("Analyze p53 binding site variants"))
    assert llm.complete_with_ptc.called


# ── H1.5: Cost aggregation ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ptc_cost_aggregation():
    """Both PTC and parse costs should be summed in the final output."""
    llm = _make_llm()
    ptc_meta = LLMResponse(
        model_version="claude-sonnet-4-20250514",
        input_tokens=1000, output_tokens=500, cost=0.03,
        cached_input_tokens=200,
    )
    parse_meta = LLMResponse(
        model_version="claude-haiku-4-5-20251001",
        input_tokens=300, output_tokens=150, cost=0.002,
    )
    llm.complete_with_ptc = AsyncMock(return_value=("analysis text", ptc_meta, None))
    llm.complete_structured = AsyncMock(return_value=(
        DummyResult(query="q", summary="s", confidence=0.5),
        parse_meta,
    ))

    agent = ConcreteAgent(_make_spec("t01_genomics"), llm)
    output = await agent.run_with_ptc(_make_context(), DummyResult)

    assert output.cost == pytest.approx(0.032)
    assert output.input_tokens == 1300
    assert output.output_tokens == 650
    assert output.model_version == "claude-sonnet-4-20250514"  # from PTC phase


# ── H1.6: PTC tool_implementations are callable ──────────────────────


def test_build_tool_implementations_callable():
    """build_tool_implementations should return async callables."""
    from app.llm.ptc_handler import build_tool_implementations

    impls = build_tool_implementations(["run_vep", "check_gene_names"])
    assert "run_vep" in impls
    assert "check_gene_names" in impls
    assert callable(impls["run_vep"])
    assert callable(impls["check_gene_names"])


def test_build_tool_implementations_filter():
    """build_tool_implementations should filter to requested tools only."""
    from app.llm.ptc_handler import build_tool_implementations

    impls = build_tool_implementations(["run_vep"])
    assert "run_vep" in impls
    assert "check_gene_names" not in impls
    assert "run_blast" not in impls
