"""Tests for Tool Search / Deferred Tool Loading.

Tests the tool_registry classifications and BaseAgent.get_tool_list()
integration with deferred tool loading.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.llm.tool_registry import AGENT_TOOL_CLASSIFICATION, get_classification

# ── Tests: Tool Registry ──


class TestToolRegistry:
    def test_knowledge_manager_has_always_loaded(self):
        cls = get_classification("knowledge_manager")
        assert "search_pubmed" in cls["always_loaded"]
        assert "query_chromadb" in cls["always_loaded"]

    def test_knowledge_manager_has_deferred(self):
        cls = get_classification("knowledge_manager")
        assert "search_biorxiv" in cls["deferred"]
        assert "search_clinical_trials" in cls["deferred"]

    def test_research_director_has_no_deferred(self):
        cls = get_classification("research_director")
        assert cls["deferred"] == []

    def test_unknown_agent_returns_empty(self):
        cls = get_classification("nonexistent_agent_xyz")
        assert cls["always_loaded"] == []
        assert cls["deferred"] == []

    def test_all_classifications_have_both_keys(self):
        for agent_id, cls in AGENT_TOOL_CLASSIFICATION.items():
            assert "always_loaded" in cls, f"{agent_id} missing always_loaded"
            assert "deferred" in cls, f"{agent_id} missing deferred"

    def test_no_overlap_between_always_and_deferred(self):
        for agent_id, cls in AGENT_TOOL_CLASSIFICATION.items():
            overlap = set(cls["always_loaded"]) & set(cls["deferred"])
            assert not overlap, f"{agent_id} has overlap: {overlap}"


# ── Tests: BaseAgent.get_tool_list (integration) ──


class TestBaseAgentGetToolList:
    """Test get_tool_list via a minimal mock agent."""

    def _make_agent(self, agent_id: str = "knowledge_manager"):
        """Create a minimal mock agent with get_tool_list."""
        from app.llm.mock_layer import MockLLMLayer

        mock_spec = MagicMock()
        mock_spec.id = agent_id
        mock_spec.model_tier = "sonnet"
        mock_spec.system_prompt_file = "knowledge_manager.md"

        # Can't instantiate BaseAgent directly, so we test via import
        # and use the method logic directly
        mock_llm = MockLLMLayer()

        class _TestAgent:
            def __init__(self):
                self.agent_id = agent_id
                self.llm = mock_llm

        agent = _TestAgent()

        # Bind the get_tool_list method
        import types

        from app.agents.base import BaseAgent
        agent.get_tool_list = types.MethodType(BaseAgent.get_tool_list, agent)
        return agent

    def test_disabled_returns_full_list(self):
        agent = self._make_agent()
        full = [{"name": "search_pubmed"}, {"name": "search_biorxiv"}]

        with patch("app.agents.base.settings") as mock_settings:
            mock_settings.deferred_tools_enabled = False
            result = agent.get_tool_list(full)
            assert result == full

    def test_enabled_defers_classified_tools(self):
        agent = self._make_agent("knowledge_manager")
        full = [
            {"name": "search_pubmed"},
            {"name": "query_chromadb"},
            {"name": "search_biorxiv"},
            {"name": "search_clinical_trials"},
        ]

        with patch("app.agents.base.settings") as mock_settings:
            mock_settings.deferred_tools_enabled = True
            result = agent.get_tool_list(full)

            # Should have tool_search_tool first
            assert result[0]["type"] == "tool_search_tool_bm25_20251119"

            # Deferred tools should have defer_loading flag
            deferred = [t for t in result if t.get("defer_loading")]
            deferred_names = {t["name"] for t in deferred}
            assert "search_biorxiv" in deferred_names
            assert "search_clinical_trials" in deferred_names

            # Always-loaded should NOT have defer_loading
            always = [t for t in result if not t.get("defer_loading") and t.get("name")]
            always_names = {t["name"] for t in always}
            assert "search_pubmed" in always_names
            assert "query_chromadb" in always_names

    def test_unknown_agent_returns_full_list(self):
        agent = self._make_agent("unknown_agent_xyz")
        full = [{"name": "tool_a"}, {"name": "tool_b"}]

        with patch("app.agents.base.settings") as mock_settings:
            mock_settings.deferred_tools_enabled = True
            result = agent.get_tool_list(full)
            # No classification → return unchanged
            assert result == full
