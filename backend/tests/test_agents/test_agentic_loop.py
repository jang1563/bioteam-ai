"""Tests for H3 Agentic Loop — multi-turn tool calling.

Validates:
1. agent_tools.py tool schemas and per-agent mapping
2. AgenticToolExecutor routes to correct handlers
3. BaseAgent.run_with_tools() two-phase pattern works
4. Timeout and cost cap safety controls
5. Fallback when no agentic tools available
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.agents.base import BaseAgent
from app.llm.layer import LLMResponse
from app.models.agent import AgentOutput, AgentSpec
from app.models.messages import ContextPackage
from pydantic import BaseModel

# ── Helpers ────────────────────────────────────────────────────────────


class DummyResult(BaseModel):
    query: str = ""
    summary: str = ""
    confidence: float = 0.0


class ConcreteAgent(BaseAgent):
    async def run(self, context: ContextPackage) -> AgentOutput:
        return self.build_output(
            output={"query": context.task_description, "summary": "fallback"},
            summary="fallback run",
        )


def _make_spec(agent_id: str = "knowledge_manager") -> AgentSpec:
    return AgentSpec(
        id=agent_id, name="Test Agent", tier="domain_expert",
        version="1.0", model_tier="sonnet",
        system_prompt_file="research_director.md",
    )


def _make_llm() -> MagicMock:
    llm = MagicMock()
    llm.build_cached_system.return_value = [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}]
    llm.estimate_cost.return_value = 0.0
    return llm


def _make_context(task: str = "Search literature on TP53") -> ContextPackage:
    return ContextPackage(task_description=task)


# ── H3.1: agent_tools.py ─────────────────────────────────────────────


def test_get_tools_for_agent_km():
    from app.llm.agent_tools import get_tools_for_agent

    tools = get_tools_for_agent("knowledge_manager")
    names = [t["name"] for t in tools]
    assert "search_pubmed" in names
    assert "search_semantic_scholar" in names


def test_get_tools_for_agent_t01():
    from app.llm.agent_tools import get_tools_for_agent

    tools = get_tools_for_agent("t01_genomics")
    names = [t["name"] for t in tools]
    assert "query_ensembl_vep" in names


def test_get_tools_for_agent_t06():
    from app.llm.agent_tools import get_tools_for_agent

    tools = get_tools_for_agent("t06_systems_bio")
    names = [t["name"] for t in tools]
    assert "query_string_db" in names
    assert "query_go_enrichment" in names


def test_get_tools_for_agent_no_tools():
    from app.llm.agent_tools import get_tools_for_agent

    tools = get_tools_for_agent("t05_clinical")
    assert tools == []


def test_all_tools_have_valid_schema():
    from app.llm.agent_tools import ALL_AGENTIC_TOOLS

    for name, tool in ALL_AGENTIC_TOOLS.items():
        assert "name" in tool, f"{name} missing 'name'"
        assert "description" in tool, f"{name} missing 'description'"
        assert "input_schema" in tool, f"{name} missing 'input_schema'"
        assert tool["input_schema"]["type"] == "object"


# ── H3.2: AgenticToolExecutor ────────────────────────────────────────


@pytest.mark.asyncio
async def test_executor_unknown_tool():
    from app.llm.tool_executor import AgenticToolExecutor

    executor = AgenticToolExecutor()
    result = await executor("nonexistent_tool", {})
    assert "error" in result
    assert "Unknown tool" in result


@pytest.mark.asyncio
async def test_executor_handler_error():
    """Executor should return error JSON, not raise."""
    from app.llm.tool_executor import AgenticToolExecutor

    executor = AgenticToolExecutor()
    # search_pubmed with empty query will try to import PubMedClient
    # which may fail in test env — the point is it returns JSON error
    result = await executor("search_pubmed", {"query": ""})
    import json
    parsed = json.loads(result)
    # Either succeeds with papers or returns error — both are valid JSON
    assert isinstance(parsed, dict)


# ── H3.3: BaseAgent._get_agentic_tools ───────────────────────────────


def test_get_agentic_tools_km():
    agent = ConcreteAgent(_make_spec("knowledge_manager"), _make_llm())
    tools = agent._get_agentic_tools()
    assert len(tools) >= 2
    names = [t["name"] for t in tools]
    assert "search_pubmed" in names


def test_get_agentic_tools_no_tools():
    agent = ConcreteAgent(_make_spec("t05_clinical"), _make_llm())
    tools = agent._get_agentic_tools()
    assert tools == []


# ── H3.4: run_with_tools two-phase pattern ───────────────────────────


@pytest.mark.asyncio
async def test_run_with_tools_two_phase():
    """run_with_tools should call complete_with_tools then complete_structured."""
    llm = _make_llm()

    # Mock agentic loop response
    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="Found 5 papers on TP53")]
    agentic_meta = LLMResponse(
        model_version="claude-sonnet-4-20250514",
        input_tokens=800, output_tokens=400, cost=0.02,
    )
    llm.complete_with_tools = AsyncMock(return_value=([mock_response], agentic_meta))

    # Mock Haiku parse
    parse_meta = LLMResponse(
        model_version="claude-haiku-4-5-20251001",
        input_tokens=200, output_tokens=100, cost=0.001,
    )
    llm.complete_structured = AsyncMock(return_value=(
        DummyResult(query="TP53", summary="5 papers found", confidence=0.8),
        parse_meta,
    ))

    agent = ConcreteAgent(_make_spec("knowledge_manager"), llm)
    output = await agent.run_with_tools(_make_context(), DummyResult)

    assert output.output["summary"] == "5 papers found"
    assert output.cost == pytest.approx(0.021)
    assert output.input_tokens == 1000
    llm.complete_with_tools.assert_called_once()
    llm.complete_structured.assert_called_once()


@pytest.mark.asyncio
async def test_run_with_tools_fallback_no_tools():
    """run_with_tools should fallback to run() if agent has no agentic tools."""
    llm = _make_llm()
    agent = ConcreteAgent(_make_spec("t05_clinical"), llm)
    output = await agent.run_with_tools(_make_context(), DummyResult)
    assert output.summary == "fallback run"


@pytest.mark.asyncio
async def test_run_with_tools_timeout():
    """run_with_tools should handle timeout gracefully."""
    import asyncio

    llm = _make_llm()

    async def slow_tools(*args, **kwargs):
        raise asyncio.TimeoutError()

    llm.complete_with_tools = slow_tools

    agent = ConcreteAgent(_make_spec("knowledge_manager"), llm)
    output = await agent.run_with_tools(_make_context(), DummyResult)

    assert "error" in (output.output or {})
    assert "timed out" in output.output.get("error", "").lower() or "timeout" in output.summary.lower()


@pytest.mark.asyncio
async def test_run_with_tools_cost_aggregation():
    """Costs from agentic loop + Haiku parse should be summed."""
    llm = _make_llm()

    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="Analysis result")]
    agentic_meta = LLMResponse(
        model_version="claude-sonnet-4-20250514",
        input_tokens=2000, output_tokens=1000, cost=0.05,
    )
    llm.complete_with_tools = AsyncMock(return_value=([mock_response], agentic_meta))

    parse_meta = LLMResponse(
        model_version="claude-haiku-4-5-20251001",
        input_tokens=500, output_tokens=200, cost=0.003,
    )
    llm.complete_structured = AsyncMock(return_value=(
        DummyResult(query="q", summary="s"),
        parse_meta,
    ))

    agent = ConcreteAgent(_make_spec("knowledge_manager"), llm)
    output = await agent.run_with_tools(_make_context(), DummyResult)

    assert output.cost == pytest.approx(0.053)
    assert output.input_tokens == 2500
    assert output.output_tokens == 1200


# ── H3.5: _select_execution_mode agentic ──────────────────────────────


def test_select_execution_mode_agentic(monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "mcp_enabled", False)
    monkeypatch.setattr(cfg.settings, "ptc_enabled", False)
    monkeypatch.setattr(cfg.settings, "agentic_enabled", True)
    agent = ConcreteAgent(_make_spec("knowledge_manager"), _make_llm())
    assert agent._select_execution_mode() == "agentic"


def test_select_execution_mode_agentic_no_tools(monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "mcp_enabled", False)
    monkeypatch.setattr(cfg.settings, "ptc_enabled", False)
    monkeypatch.setattr(cfg.settings, "agentic_enabled", True)
    agent = ConcreteAgent(_make_spec("t05_clinical"), _make_llm())
    assert agent._select_execution_mode() == "structured"


def test_select_execution_mode_mcp_over_agentic(monkeypatch):
    """MCP takes priority over agentic when both are enabled."""
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "mcp_enabled", True)
    monkeypatch.setattr(cfg.settings, "ptc_enabled", False)
    monkeypatch.setattr(cfg.settings, "agentic_enabled", True)
    agent = ConcreteAgent(_make_spec("t07_structural_bio"), _make_llm())
    assert agent._select_execution_mode() == "mcp"


# ── H3.6: WorkflowStepDef use_agentic flag ────────────────────────────


def test_workflow_step_use_agentic_default():
    from app.models.workflow import WorkflowStepDef

    step = WorkflowStepDef(id="TEST", agent_id="km", output_schema="dict")
    assert step.use_agentic is False


def test_workflow_step_use_agentic_set():
    from app.models.workflow import WorkflowStepDef

    step = WorkflowStepDef(id="TEST", agent_id="km", output_schema="dict", use_agentic=True)
    assert step.use_agentic is True


def test_w1_search_step_agentic():
    """W1 SEARCH step should have use_agentic=True."""
    from app.workflows.runners.w1_literature import W1_STEPS

    search_step = next(s for s in W1_STEPS if s.id == "SEARCH")
    assert search_step.use_agentic is True


def test_w1_scope_step_not_agentic():
    """W1 SCOPE step should NOT have use_agentic=True."""
    from app.workflows.runners.w1_literature import W1_STEPS

    scope_step = next(s for s in W1_STEPS if s.id == "SCOPE")
    assert scope_step.use_agentic is False


def test_w9_genomic_analysis_step_agentic():
    """W9 GENOMIC_ANALYSIS step should have use_agentic=True."""
    from app.workflows.runners.w9_bioinformatics import W9_STEPS

    ga_step = next(s for s in W9_STEPS if s.id == "GENOMIC_ANALYSIS")
    assert ga_step.use_agentic is True
