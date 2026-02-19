"""Tests for AgentRegistry — agent management and degradation."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from unittest.mock import MagicMock

from app.agents.registry import AgentRegistry
from app.models.agent import AgentSpec, AgentStatus


def _make_mock_agent(agent_id: str, state: str = "idle", failures: int = 0) -> MagicMock:
    """Create a mock agent with the given ID and status."""
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.spec = AgentSpec(
        id=agent_id,
        name=agent_id.replace("_", " ").title(),
        tier="domain_expert",
        model_tier="sonnet",
        system_prompt_file=f"{agent_id}.md",
    )
    agent.status = AgentStatus(agent_id=agent_id, state=state, consecutive_failures=failures)
    return agent


# === Registration Tests ===


def test_register_and_get():
    reg = AgentRegistry()
    agent = _make_mock_agent("t01_genomics")
    reg.register(agent)
    assert reg.get("t01_genomics") is agent
    print("  PASS: register_and_get")


def test_get_returns_none_for_missing():
    reg = AgentRegistry()
    assert reg.get("nonexistent") is None
    print("  PASS: get_returns_none_for_missing")


def test_get_or_raise_success():
    reg = AgentRegistry()
    agent = _make_mock_agent("knowledge_manager")
    reg.register(agent)
    result = reg.get_or_raise("knowledge_manager")
    assert result is agent
    print("  PASS: get_or_raise_success")


def test_get_or_raise_missing():
    reg = AgentRegistry()
    try:
        reg.get_or_raise("nonexistent")
        assert False, "Should have raised KeyError"
    except KeyError as e:
        assert "nonexistent" in str(e)
    print("  PASS: get_or_raise_missing")


def test_register_overwrites():
    reg = AgentRegistry()
    agent1 = _make_mock_agent("t01_genomics")
    agent2 = _make_mock_agent("t01_genomics")
    reg.register(agent1)
    reg.register(agent2)
    assert reg.get("t01_genomics") is agent2
    print("  PASS: register_overwrites")


# === Listing Tests ===


def test_list_agents():
    reg = AgentRegistry()
    reg.register(_make_mock_agent("t01_genomics"))
    reg.register(_make_mock_agent("t02_transcriptomics"))
    specs = reg.list_agents()
    assert len(specs) == 2
    ids = [s.id for s in specs]
    assert "t01_genomics" in ids
    assert "t02_transcriptomics" in ids
    print("  PASS: list_agents")


def test_list_agents_empty():
    reg = AgentRegistry()
    assert reg.list_agents() == []
    print("  PASS: list_agents_empty")


def test_list_statuses():
    reg = AgentRegistry()
    reg.register(_make_mock_agent("t01_genomics", state="busy"))
    reg.register(_make_mock_agent("t02_transcriptomics", state="idle"))
    statuses = reg.list_statuses()
    assert len(statuses) == 2
    states = {s.agent_id: s.state for s in statuses}
    assert states["t01_genomics"] == "busy"
    assert states["t02_transcriptomics"] == "idle"
    print("  PASS: list_statuses")


# === Availability Tests ===


def test_is_available_idle():
    reg = AgentRegistry()
    reg.register(_make_mock_agent("t01_genomics", state="idle", failures=0))
    assert reg.is_available("t01_genomics") is True
    print("  PASS: is_available_idle")


def test_is_available_busy():
    reg = AgentRegistry()
    reg.register(_make_mock_agent("t01_genomics", state="busy", failures=0))
    assert reg.is_available("t01_genomics") is True  # busy != unavailable
    print("  PASS: is_available_busy")


def test_is_available_unavailable_state():
    reg = AgentRegistry()
    reg.register(_make_mock_agent("t01_genomics", state="unavailable", failures=0))
    assert reg.is_available("t01_genomics") is False
    print("  PASS: is_available_unavailable_state")


def test_is_available_too_many_failures():
    reg = AgentRegistry()
    reg.register(_make_mock_agent("t01_genomics", state="idle", failures=3))
    assert reg.is_available("t01_genomics") is False
    print("  PASS: is_available_too_many_failures")


def test_is_available_two_failures_ok():
    reg = AgentRegistry()
    reg.register(_make_mock_agent("t01_genomics", state="idle", failures=2))
    assert reg.is_available("t01_genomics") is True
    print("  PASS: is_available_two_failures_ok")


def test_is_available_nonexistent():
    reg = AgentRegistry()
    assert reg.is_available("nonexistent") is False
    print("  PASS: is_available_nonexistent")


# === Mark Unavailable ===


def test_mark_unavailable():
    reg = AgentRegistry()
    agent = _make_mock_agent("t01_genomics")
    reg.register(agent)
    reg.mark_unavailable("t01_genomics")
    assert agent.status.state == "unavailable"
    assert reg.is_available("t01_genomics") is False
    print("  PASS: mark_unavailable")


def test_mark_unavailable_nonexistent():
    """Should not raise for missing agent."""
    reg = AgentRegistry()
    reg.mark_unavailable("nonexistent")  # No error
    print("  PASS: mark_unavailable_nonexistent")


# === Critical Health Tests ===


def test_critical_health_all_healthy():
    reg = AgentRegistry()
    reg.register(_make_mock_agent("research_director"))
    reg.register(_make_mock_agent("knowledge_manager"))
    unhealthy = reg.check_critical_health()
    assert unhealthy == []
    print("  PASS: critical_health_all_healthy")


def test_critical_health_rd_unavailable():
    reg = AgentRegistry()
    reg.register(_make_mock_agent("research_director", state="unavailable"))
    reg.register(_make_mock_agent("knowledge_manager"))
    unhealthy = reg.check_critical_health()
    assert "research_director" in unhealthy
    assert "knowledge_manager" not in unhealthy
    print("  PASS: critical_health_rd_unavailable")


def test_critical_health_km_too_many_failures():
    reg = AgentRegistry()
    reg.register(_make_mock_agent("research_director"))
    reg.register(_make_mock_agent("knowledge_manager", failures=3))
    unhealthy = reg.check_critical_health()
    assert "knowledge_manager" in unhealthy
    print("  PASS: critical_health_km_too_many_failures")


def test_critical_health_both_unhealthy():
    reg = AgentRegistry()
    reg.register(_make_mock_agent("research_director", state="unavailable"))
    reg.register(_make_mock_agent("knowledge_manager", state="unavailable"))
    unhealthy = reg.check_critical_health()
    assert len(unhealthy) == 2
    print("  PASS: critical_health_both_unhealthy")


def test_critical_health_neither_registered():
    """Unregistered critical agents are reported as unhealthy."""
    reg = AgentRegistry()
    unhealthy = reg.check_critical_health()
    assert "research_director" in unhealthy
    assert "knowledge_manager" in unhealthy
    print("  PASS: critical_health_neither_registered")


# === Substitution Tests ===


def test_find_substitute_genomics_to_transcriptomics():
    reg = AgentRegistry()
    reg.register(_make_mock_agent("t01_genomics"))
    reg.register(_make_mock_agent("t02_transcriptomics"))
    sub = reg.find_substitute("t01_genomics")
    assert sub == "t02_transcriptomics"
    print("  PASS: find_substitute_genomics_to_transcriptomics")


def test_find_substitute_reverse():
    reg = AgentRegistry()
    reg.register(_make_mock_agent("t01_genomics"))
    reg.register(_make_mock_agent("t02_transcriptomics"))
    sub = reg.find_substitute("t02_transcriptomics")
    assert sub == "t01_genomics"
    print("  PASS: find_substitute_reverse")


def test_find_substitute_candidate_unavailable():
    reg = AgentRegistry()
    reg.register(_make_mock_agent("t01_genomics"))
    reg.register(_make_mock_agent("t02_transcriptomics", state="unavailable"))
    sub = reg.find_substitute("t01_genomics")
    assert sub is None  # Only candidate is unavailable
    print("  PASS: find_substitute_candidate_unavailable")


def test_find_substitute_no_candidates():
    reg = AgentRegistry()
    reg.register(_make_mock_agent("t07_structural_bio"))
    sub = reg.find_substitute("t07_structural_bio")
    assert sub is None  # Empty substitution list
    print("  PASS: find_substitute_no_candidates")


def test_find_substitute_nonexistent_agent():
    reg = AgentRegistry()
    sub = reg.find_substitute("nonexistent")
    assert sub is None
    print("  PASS: find_substitute_nonexistent_agent")


def test_find_substitute_not_in_map():
    """Agents not in substitution_map return None."""
    reg = AgentRegistry()
    reg.register(_make_mock_agent("research_director"))
    sub = reg.find_substitute("research_director")
    assert sub is None
    print("  PASS: find_substitute_not_in_map")


def test_find_substitute_cross_cutting():
    """Test cross-cutting substitution: experimental_designer -> biostatistics."""
    reg = AgentRegistry()
    reg.register(_make_mock_agent("experimental_designer"))
    reg.register(_make_mock_agent("t04_biostatistics"))
    sub = reg.find_substitute("experimental_designer")
    assert sub == "t04_biostatistics"
    print("  PASS: find_substitute_cross_cutting")


if __name__ == "__main__":
    print("Testing AgentRegistry:")
    # Registration
    test_register_and_get()
    test_get_returns_none_for_missing()
    test_get_or_raise_success()
    test_get_or_raise_missing()
    test_register_overwrites()
    # Listing
    test_list_agents()
    test_list_agents_empty()
    test_list_statuses()
    # Availability
    test_is_available_idle()
    test_is_available_busy()
    test_is_available_unavailable_state()
    test_is_available_too_many_failures()
    test_is_available_two_failures_ok()
    test_is_available_nonexistent()
    # Mark unavailable
    test_mark_unavailable()
    test_mark_unavailable_nonexistent()
    # Critical health
    test_critical_health_all_healthy()
    test_critical_health_rd_unavailable()
    test_critical_health_km_too_many_failures()
    test_critical_health_both_unhealthy()
    test_critical_health_neither_registered()
    # Substitution
    test_find_substitute_genomics_to_transcriptomics()
    test_find_substitute_reverse()
    test_find_substitute_candidate_unavailable()
    test_find_substitute_no_candidates()
    test_find_substitute_nonexistent_agent()
    test_find_substitute_not_in_map()
    test_find_substitute_cross_cutting()
    print("\nAll AgentRegistry tests passed!")
