"""Tests for Programmatic Tool Calling (PTC) support in LLMLayer.

Tests the PTC tool definitions, ensure_allowed_callers helper,
MockLLMLayer.complete_with_ptc, and build_deferred_tools.
"""

from __future__ import annotations

import pytest

from app.llm.mock_layer import MockLLMLayer
from app.llm.ptc_tools import (
    CHROMADB_SEARCH_TOOL,
    CODE_EXECUTION_TOOL,
    DEDUP_TOOL,
    PTC_CODE_EXECUTION_TYPE,
    STORE_EVIDENCE_TOOL,
    ensure_allowed_callers,
    get_all_ptc_tools,
)


# ── Tests: PTC Tool Definitions ──


class TestPTCToolDefinitions:
    def test_chromadb_search_tool_has_required_fields(self):
        assert CHROMADB_SEARCH_TOOL["name"] == "search_memory"
        assert "input_schema" in CHROMADB_SEARCH_TOOL
        assert "query" in CHROMADB_SEARCH_TOOL["input_schema"]["properties"]
        assert "collection" in CHROMADB_SEARCH_TOOL["input_schema"]["properties"]

    def test_dedup_tool_has_required_fields(self):
        assert DEDUP_TOOL["name"] == "deduplicate_papers"
        assert "papers" in DEDUP_TOOL["input_schema"]["properties"]

    def test_store_evidence_tool_has_required_fields(self):
        assert STORE_EVIDENCE_TOOL["name"] == "store_evidence"
        assert "doc_id" in STORE_EVIDENCE_TOOL["input_schema"]["properties"]
        assert "text" in STORE_EVIDENCE_TOOL["input_schema"]["properties"]

    def test_all_custom_tools_have_allowed_callers(self):
        for tool in [CHROMADB_SEARCH_TOOL, DEDUP_TOOL, STORE_EVIDENCE_TOOL]:
            assert "allowed_callers" in tool
            assert PTC_CODE_EXECUTION_TYPE in tool["allowed_callers"]

    def test_code_execution_tool_has_correct_type(self):
        assert CODE_EXECUTION_TOOL["type"] == PTC_CODE_EXECUTION_TYPE
        assert CODE_EXECUTION_TOOL["name"] == "code_execution"

    def test_get_all_ptc_tools_includes_code_execution(self):
        tools = get_all_ptc_tools()
        types = [t.get("type") for t in tools]
        assert PTC_CODE_EXECUTION_TYPE in types

    def test_get_all_ptc_tools_includes_custom_tools(self):
        tools = get_all_ptc_tools()
        names = [t.get("name") for t in tools]
        assert "search_memory" in names
        assert "deduplicate_papers" in names
        assert "store_evidence" in names


# ── Tests: ensure_allowed_callers ──


class TestEnsureAllowedCallers:
    def test_adds_allowed_callers_to_tools_without_them(self):
        tools = [
            {"name": "my_tool", "input_schema": {}},
        ]
        result = ensure_allowed_callers(tools)
        assert result[0]["allowed_callers"] == [PTC_CODE_EXECUTION_TYPE]

    def test_preserves_existing_allowed_callers(self):
        tools = [
            {"name": "my_tool", "allowed_callers": ["custom_caller"]},
        ]
        result = ensure_allowed_callers(tools)
        assert result[0]["allowed_callers"] == ["custom_caller"]

    def test_skips_code_execution_tool(self):
        tools = [CODE_EXECUTION_TOOL]
        result = ensure_allowed_callers(tools)
        assert result[0] == CODE_EXECUTION_TOOL
        assert "allowed_callers" not in result[0]

    def test_does_not_mutate_original(self):
        original = {"name": "my_tool", "input_schema": {}}
        tools = [original]
        ensure_allowed_callers(tools)
        assert "allowed_callers" not in original  # Original unchanged


# ── Tests: MockLLMLayer PTC Support ──


class TestMockLLMLayerPTC:
    @pytest.mark.asyncio
    async def test_complete_with_ptc_returns_triple(self):
        mock = MockLLMLayer()
        text, meta, container_id = await mock.complete_with_ptc(
            messages=[{"role": "user", "content": "test"}],
            model_tier="sonnet",
            system="test system",
            custom_tools=get_all_ptc_tools(),
            tool_implementations={},
        )
        assert isinstance(text, str)
        assert text == "Mock PTC result"
        assert meta.model_version == "mock-sonnet"
        assert container_id == "mock-container-id"

    @pytest.mark.asyncio
    async def test_complete_with_ptc_logs_call(self):
        mock = MockLLMLayer()
        await mock.complete_with_ptc(
            messages=[{"role": "user", "content": "test"}],
            model_tier="opus",
            system="sys",
            custom_tools=[CHROMADB_SEARCH_TOOL],
            tool_implementations={},
        )
        assert len(mock.call_log) == 1
        assert mock.call_log[0]["method"] == "complete_with_ptc"
        assert mock.call_log[0]["model_tier"] == "opus"
        assert "search_memory" in mock.call_log[0]["tools"]


# ── Tests: build_deferred_tools ──


class TestBuildDeferredTools:
    def setup_method(self):
        self.mock = MockLLMLayer()

    def test_includes_tool_search_tool(self):
        result = self.mock.build_deferred_tools(
            always_loaded=[{"name": "core_tool"}],
            deferred=[{"name": "rare_tool"}],
        )
        assert result[0]["type"] == "tool_search_tool_bm25_20251119"
        assert result[0]["name"] == "tool_search_tool_bm25"

    def test_deferred_tools_have_defer_loading_flag(self):
        result = self.mock.build_deferred_tools(
            always_loaded=[{"name": "core"}],
            deferred=[{"name": "rare1"}, {"name": "rare2"}],
        )
        deferred = [t for t in result if t.get("defer_loading")]
        assert len(deferred) == 2

    def test_always_loaded_not_deferred(self):
        result = self.mock.build_deferred_tools(
            always_loaded=[{"name": "core"}],
            deferred=[{"name": "rare"}],
        )
        core = [t for t in result if t.get("name") == "core"]
        assert len(core) == 1
        assert "defer_loading" not in core[0]

    def test_empty_deferred_still_has_search_tool(self):
        result = self.mock.build_deferred_tools(
            always_loaded=[{"name": "core"}],
            deferred=[],
        )
        assert result[0]["type"] == "tool_search_tool_bm25_20251119"
        assert len(result) == 2  # search tool + core

    def test_order_is_search_then_always_then_deferred(self):
        result = self.mock.build_deferred_tools(
            always_loaded=[{"name": "a"}, {"name": "b"}],
            deferred=[{"name": "c"}],
        )
        names = [t.get("name") for t in result]
        assert names == ["tool_search_tool_bm25", "a", "b", "c"]
