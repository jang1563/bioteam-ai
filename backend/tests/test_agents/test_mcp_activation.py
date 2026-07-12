"""Tests for H6 MCP Activation — multi-agent MCP access.

Validates:
1. MCPConnector.execute() returns MCPExecutionResult
2. AGENT_MCP_SERVERS maps agents correctly
3. BaseAgent._get_mcp_servers() returns correct servers per agent
4. BaseAgent.run_with_mcp() two-phase pattern works
5. T07 routes to MCP when mcp_enabled=True
6. T04 routes to MCP when mcp_enabled=True
7. MCP takes priority over PTC (mutual exclusion)
8. _select_execution_mode() returns correct mode
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.agents.base import BaseAgent
from app.llm.layer import LLMResponse
from app.llm.mock_layer import MockLLMLayer
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


def _make_spec(agent_id: str = "t07_structural_bio") -> AgentSpec:
    return AgentSpec(
        id=agent_id, name="Test Agent", tier="domain_expert",
        version="1.0", model_tier="sonnet",
        system_prompt_file="research_director.md",
    )


def _make_context(task: str = "Find ChEMBL data on imatinib") -> ContextPackage:
    return ContextPackage(task_description=task)


def _make_llm() -> MagicMock:
    llm = MagicMock()
    llm.build_cached_system.return_value = [{"type": "text", "text": "system", "cache_control": {"type": "ephemeral"}}]
    llm.estimate_cost.return_value = 0.01
    return llm


# ── H6.1: MCPConnector.execute() ──────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_execute_returns_result():
    """MCPConnector.execute() should return MCPExecutionResult."""
    from app.integrations.mcp_connector import MCPConnector, MCPExecutionResult

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="Imatinib is a tyrosine kinase inhibitor")]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50, cache_read_input_tokens=0)
    mock_response.model = "claude-sonnet-4-20250514"
    mock_client.beta.messages.create = AsyncMock(return_value=mock_response)

    connector = MCPConnector(client=mock_client)

    with patch.object(connector, "_build_mcp_servers", return_value=[{"type": "url", "name": "chembl", "url": "http://test"}]):
        result = await connector.execute(
            task="Find data on imatinib",
            sources=["chembl"],
        )

    assert isinstance(result, MCPExecutionResult)
    assert "tyrosine kinase" in result.text_output
    assert result.input_tokens == 100
    assert result.source == "chembl"


@pytest.mark.asyncio
async def test_mcp_execute_empty_servers():
    """MCPConnector.execute() should return empty result for no servers."""
    from app.integrations.mcp_connector import MCPConnector, MCPExecutionResult

    connector = MCPConnector(client=MagicMock())
    with patch.object(connector, "_build_mcp_servers", return_value=[]):
        result = await connector.execute(task="test", sources=["nonexistent"])

    assert isinstance(result, MCPExecutionResult)
    assert result.text_output == ""


# ── H6.2: AGENT_MCP_SERVERS mapping ──────────────────────────────────


def test_agent_mcp_servers_mapping():
    """AGENT_MCP_SERVERS should map T07 to ChEMBL and T04 to ClinicalTrials."""
    from app.integrations.mcp_connector import AGENT_MCP_SERVERS

    assert "chembl" in AGENT_MCP_SERVERS["t07_structural_bio"]
    assert "clinical_trials" in AGENT_MCP_SERVERS["t04_biostatistics"]
    assert "pubmed" in AGENT_MCP_SERVERS["knowledge_manager"]


# ── H6.3: BaseAgent._get_mcp_servers() ───────────────────────────────


def test_get_mcp_servers_t07():
    agent = ConcreteAgent(_make_spec("t07_structural_bio"), _make_llm())
    servers = agent._get_mcp_servers()
    assert "chembl" in servers


def test_get_mcp_servers_t04():
    agent = ConcreteAgent(_make_spec("t04_biostatistics"), _make_llm())
    servers = agent._get_mcp_servers()
    assert "clinical_trials" in servers


def test_get_mcp_servers_no_access():
    """Agent without MCP access returns empty list."""
    agent = ConcreteAgent(_make_spec("t01_genomics"), _make_llm())
    servers = agent._get_mcp_servers()
    assert servers == []


# ── H6.4: run_with_mcp two-phase pattern ─────────────────────────────


@pytest.mark.asyncio
async def test_run_with_mcp_two_phase():
    """run_with_mcp should call MCP execute then Haiku structured parse."""
    from app.integrations.mcp_connector import MCPExecutionResult

    llm = _make_llm()
    parse_meta = LLMResponse(model_version="claude-haiku-4-5-20251001", input_tokens=200, output_tokens=100, cost=0.001)
    llm.complete_structured = AsyncMock(return_value=(
        DummyResult(query="imatinib", summary="ChEMBL data", confidence=0.9),
        parse_meta,
    ))

    mock_mcp_result = MCPExecutionResult(
        source="chembl", text_output="Imatinib IC50: 100nM against ABL1",
        input_tokens=300, output_tokens=200, model="claude-sonnet-4-20250514",
    )

    agent = ConcreteAgent(_make_spec("t07_structural_bio"), llm)

    with patch("app.integrations.mcp_connector.MCPConnector") as MockConnector:
        mock_instance = MagicMock()
        mock_instance.execute = AsyncMock(return_value=mock_mcp_result)
        MockConnector.return_value = mock_instance

        output = await agent.run_with_mcp(_make_context(), DummyResult)

    assert output.output["summary"] == "ChEMBL data"
    assert output.cost > 0
    assert output.input_tokens == 500  # 300 MCP + 200 parse
    llm.complete_structured.assert_called_once()


@pytest.mark.asyncio
async def test_run_with_mcp_fallback_no_servers():
    """run_with_mcp should fallback to run() if agent has no MCP servers."""
    llm = _make_llm()
    agent = ConcreteAgent(_make_spec("t01_genomics"), llm)
    output = await agent.run_with_mcp(_make_context(), DummyResult)
    assert output.summary == "fallback run"


# ── H6.5: Domain agent routing with MCP ──────────────────────────────


@pytest.fixture
def enable_mcp(monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "mcp_enabled", True)
    monkeypatch.setattr(cfg.settings, "ptc_enabled", False)


@pytest.fixture
def enable_both(monkeypatch):
    """Enable both MCP and PTC to test priority."""
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "mcp_enabled", True)
    monkeypatch.setattr(cfg.settings, "ptc_enabled", True)


@pytest.mark.asyncio
async def test_t07_routes_to_mcp_when_enabled(enable_mcp):
    """StructuralBiologyAgent should route to run_with_mcp when mcp_enabled=True."""
    from app.agents.teams.t07_structural_bio import StructuralBiologyAgent
    from app.integrations.mcp_connector import MCPExecutionResult

    llm = _make_llm()
    parse_meta = LLMResponse(model_version="claude-haiku-4-5-20251001", cost=0.001)
    llm.complete_structured = AsyncMock(return_value=(
        MagicMock(model_dump=lambda: {"query": "q", "summary": "MCP out"}, summary="MCP out"),
        parse_meta,
    ))

    agent = StructuralBiologyAgent(_make_spec("t07_structural_bio"), llm)

    with patch("app.integrations.mcp_connector.MCPConnector") as MockConnector:
        mock_instance = MagicMock()
        mock_instance.execute = AsyncMock(return_value=MCPExecutionResult(
            source="chembl", text_output="ChEMBL result",
            input_tokens=100, output_tokens=50, model="claude-sonnet-4-20250514",
        ))
        MockConnector.return_value = mock_instance

        await agent.run(_make_context("Find compound data"))

    mock_instance.execute.assert_called_once()


@pytest.mark.asyncio
async def test_t04_routes_to_mcp_when_enabled(enable_mcp):
    """BiostatisticsAgent should route to run_with_mcp when mcp_enabled=True."""
    from app.agents.teams.t04_biostatistics import BiostatisticsAgent
    from app.integrations.mcp_connector import MCPExecutionResult

    llm = _make_llm()
    parse_meta = LLMResponse(model_version="claude-haiku-4-5-20251001", cost=0.001)
    llm.complete_structured = AsyncMock(return_value=(
        MagicMock(model_dump=lambda: {"query": "q", "summary": "MCP out"}, summary="MCP out"),
        parse_meta,
    ))

    agent = BiostatisticsAgent(_make_spec("t04_biostatistics"), llm)

    with patch("app.integrations.mcp_connector.MCPConnector") as MockConnector:
        mock_instance = MagicMock()
        mock_instance.execute = AsyncMock(return_value=MCPExecutionResult(
            source="clinical_trials", text_output="CT.gov trial data",
            input_tokens=100, output_tokens=50, model="claude-sonnet-4-20250514",
        ))
        MockConnector.return_value = mock_instance

        await agent.run(_make_context("Find Phase 3 trials for glioblastoma"))

    mock_instance.execute.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("spec_id", "task"),
    [
        pytest.param("t04_biostatistics", "Find Phase 3 trials for glioblastoma", id="t04"),
        pytest.param("t07_structural_bio", "Find compound data", id="t07"),
    ],
)
async def test_mock_llm_bypasses_mcp_when_enabled(enable_mcp, spec_id, task):
    """MockLLMLayer unit tests should stay on the structured path even when MCP is enabled."""
    if spec_id == "t04_biostatistics":
        from app.agents.teams.t04_biostatistics import BiostatisticsAgent as agent_cls
        from app.agents.teams.t04_biostatistics import StatisticalAnalysisResult as response_model
    elif spec_id == "t07_structural_bio":
        from app.agents.teams.t07_structural_bio import StructuralAnalysisResult as response_model
        from app.agents.teams.t07_structural_bio import StructuralBiologyAgent as agent_cls
    else:
        raise AssertionError(f"Unhandled spec_id: {spec_id}")

    llm = MockLLMLayer(
        {
            f"sonnet:{response_model.__name__}": response_model(
                query=task,
                summary=f"mock structured output for {spec_id}",
                confidence=0.8,
            ),
        }
    )
    agent = agent_cls(_make_spec(spec_id), llm)

    with patch("app.integrations.mcp_connector.MCPConnector") as MockConnector:
        await agent.run(_make_context(task))

    assert [entry["method"] for entry in llm.call_log] == ["complete_structured"]
    MockConnector.assert_not_called()


# ── H6.6: MCP + PTC mutual exclusion ─────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_takes_priority_over_ptc(enable_both):
    """When both MCP and PTC are enabled, MCP should take priority for T07."""
    from app.agents.teams.t07_structural_bio import StructuralBiologyAgent
    from app.integrations.mcp_connector import MCPExecutionResult

    llm = _make_llm()
    parse_meta = LLMResponse(model_version="claude-haiku-4-5-20251001", cost=0.001)
    llm.complete_structured = AsyncMock(return_value=(
        MagicMock(model_dump=lambda: {"query": "q", "summary": "MCP out"}, summary="MCP out"),
        parse_meta,
    ))
    llm.complete_with_ptc = AsyncMock()  # Should NOT be called

    agent = StructuralBiologyAgent(_make_spec("t07_structural_bio"), llm)

    with patch("app.integrations.mcp_connector.MCPConnector") as MockConnector:
        mock_instance = MagicMock()
        mock_instance.execute = AsyncMock(return_value=MCPExecutionResult(
            source="chembl", text_output="ChEMBL data",
            input_tokens=100, output_tokens=50, model="claude-sonnet-4-20250514",
        ))
        MockConnector.return_value = mock_instance

        await agent.run(_make_context("Compound analysis"))

    # MCP was called, PTC was NOT
    mock_instance.execute.assert_called_once()
    llm.complete_with_ptc.assert_not_called()


# ── H6.7: _select_execution_mode() ───────────────────────────────────


def test_select_execution_mode_mcp(monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "mcp_enabled", True)
    monkeypatch.setattr(cfg.settings, "ptc_enabled", True)
    agent = ConcreteAgent(_make_spec("t07_structural_bio"), _make_llm())
    assert agent._select_execution_mode() == "mcp"


def test_select_execution_mode_ptc(monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "mcp_enabled", False)
    monkeypatch.setattr(cfg.settings, "ptc_enabled", True)
    agent = ConcreteAgent(_make_spec("t01_genomics"), _make_llm())
    assert agent._select_execution_mode() == "ptc"


def test_select_execution_mode_structured(monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "mcp_enabled", False)
    monkeypatch.setattr(cfg.settings, "ptc_enabled", False)
    agent = ConcreteAgent(_make_spec("t01_genomics"), _make_llm())
    assert agent._select_execution_mode() == "structured"


def test_select_execution_mode_mcp_no_servers(monkeypatch):
    """MCP enabled but agent has no MCP servers → falls to PTC or structured."""
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "mcp_enabled", True)
    monkeypatch.setattr(cfg.settings, "ptc_enabled", True)
    # T01 has PTC tools but no MCP servers
    agent = ConcreteAgent(_make_spec("t01_genomics"), _make_llm())
    assert agent._select_execution_mode() == "ptc"
