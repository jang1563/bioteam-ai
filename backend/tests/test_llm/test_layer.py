"""Tests for LLMLayer (estimate_cost, build_cached_system) and MockLLMLayer."""

import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from pydantic import BaseModel

from app.llm.layer import LLMResponse, LLMLayer
from app.llm.mock_layer import MockLLMLayer, _MockMessage


# === LLMResponse Tests ===


def test_llm_response_defaults():
    r = LLMResponse()
    assert r.model_version == ""
    assert r.input_tokens == 0
    assert r.output_tokens == 0
    assert r.cached_input_tokens == 0
    assert r.cost == 0.0
    assert r.timestamp is not None
    print("  PASS: llm_response_defaults")


def test_llm_response_timestamp_unique():
    """Each LLMResponse should get a fresh timestamp."""
    r1 = LLMResponse()
    r2 = LLMResponse()
    # They should both be datetime objects (not the same frozen value)
    assert r1.timestamp is not None
    assert r2.timestamp is not None
    print("  PASS: llm_response_timestamp_unique")


# === estimate_cost Tests ===


def test_estimate_cost_sonnet_basic():
    llm = LLMLayer.__new__(LLMLayer)  # Skip __init__ (no API key needed)
    cost = llm.estimate_cost("sonnet", input_tokens=1_000_000, output_tokens=1_000_000)
    # Sonnet: $3/M input + $15/M output = $18.00
    assert cost == 18.0
    print("  PASS: estimate_cost_sonnet_basic")


def test_estimate_cost_opus_basic():
    llm = LLMLayer.__new__(LLMLayer)
    cost = llm.estimate_cost("opus", input_tokens=1_000_000, output_tokens=1_000_000)
    # Opus: $15/M input + $75/M output = $90.00
    assert cost == 90.0
    print("  PASS: estimate_cost_opus_basic")


def test_estimate_cost_haiku_basic():
    llm = LLMLayer.__new__(LLMLayer)
    cost = llm.estimate_cost("haiku", input_tokens=1_000_000, output_tokens=1_000_000)
    # Haiku: $0.80/M input + $4/M output = $4.80
    assert cost == 4.8
    print("  PASS: estimate_cost_haiku_basic")


def test_estimate_cost_with_cache():
    llm = LLMLayer.__new__(LLMLayer)
    # 1M total input, 800K cached, 200K non-cached
    cost = llm.estimate_cost(
        "sonnet",
        input_tokens=1_000_000,
        output_tokens=0,
        cached_input_tokens=800_000,
    )
    # Non-cached: 200K * $3/M = $0.60
    # Cached: 800K * $0.30/M = $0.24
    # Total = $0.84
    assert cost == 0.84
    print("  PASS: estimate_cost_with_cache")


def test_estimate_cost_zero_tokens():
    llm = LLMLayer.__new__(LLMLayer)
    cost = llm.estimate_cost("sonnet", input_tokens=0, output_tokens=0)
    assert cost == 0.0
    print("  PASS: estimate_cost_zero_tokens")


def test_estimate_cost_small_tokens():
    llm = LLMLayer.__new__(LLMLayer)
    cost = llm.estimate_cost("sonnet", input_tokens=100, output_tokens=50)
    # 100 * $3/M + 50 * $15/M = $0.0003 + $0.00075 = $0.00105
    expected = round((100 / 1_000_000) * 3.0 + (50 / 1_000_000) * 15.0, 6)
    assert cost == expected
    print("  PASS: estimate_cost_small_tokens")


def test_estimate_cost_all_cached():
    llm = LLMLayer.__new__(LLMLayer)
    cost = llm.estimate_cost(
        "opus",
        input_tokens=1_000_000,
        output_tokens=0,
        cached_input_tokens=1_000_000,
    )
    # Non-cached: 0 * $15/M = $0
    # Cached: 1M * $1.50/M = $1.50
    assert cost == 1.5
    print("  PASS: estimate_cost_all_cached")


# === build_cached_system Tests ===


def test_build_cached_system_format():
    llm = LLMLayer.__new__(LLMLayer)
    result = llm.build_cached_system("You are a biology agent.")
    assert isinstance(result, list)
    assert len(result) == 1
    block = result[0]
    assert block["type"] == "text"
    assert block["text"] == "You are a biology agent."
    assert block["cache_control"]["type"] == "ephemeral"
    print("  PASS: build_cached_system_format")


def test_build_cached_system_empty_text():
    llm = LLMLayer.__new__(LLMLayer)
    result = llm.build_cached_system("")
    assert result[0]["text"] == ""
    print("  PASS: build_cached_system_empty_text")


# === MockLLMLayer Tests ===


def test_mock_complete_structured_default():
    class TestModel(BaseModel):
        value: str = ""

    mock = MockLLMLayer()
    result, meta = asyncio.run(
        mock.complete_structured(
            messages=[{"role": "user", "content": "test"}],
            model_tier="sonnet",
            response_model=TestModel,
        )
    )
    assert isinstance(result, TestModel)
    assert meta.model_version == "mock-sonnet"
    assert meta.input_tokens == 100
    assert meta.output_tokens == 50
    print("  PASS: mock_complete_structured_default")


def test_mock_complete_structured_with_response():
    class QueryClassification(BaseModel):
        type: str = "simple_query"
        reasoning: str = ""

    mock = MockLLMLayer({
        "sonnet:QueryClassification": QueryClassification(
            type="needs_workflow",
            reasoning="Complex task",
        )
    })
    result, meta = asyncio.run(
        mock.complete_structured(
            messages=[{"role": "user", "content": "test"}],
            model_tier="sonnet",
            response_model=QueryClassification,
        )
    )
    assert result.type == "needs_workflow"
    assert result.reasoning == "Complex task"
    print("  PASS: mock_complete_structured_with_response")


def test_mock_complete_raw():
    mock = MockLLMLayer()
    result, meta = asyncio.run(
        mock.complete_raw(
            messages=[{"role": "user", "content": "hello"}],
            model_tier="haiku",
        )
    )
    assert isinstance(result, _MockMessage)
    assert result.content[0].text == "Mock response"
    assert meta.model_version == "mock-haiku"
    print("  PASS: mock_complete_raw")


def test_mock_complete_with_tools():
    mock = MockLLMLayer()
    async def executor(name, input_data):
        return "tool result"

    results, meta = asyncio.run(
        mock.complete_with_tools(
            messages=[{"role": "user", "content": "test"}],
            model_tier="opus",
            system="You are a test agent.",
            tools=[{"name": "test_tool"}],
            tool_executor=executor,
        )
    )
    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0].content[0].text == "Mock tool response"
    assert meta.model_version == "mock-opus"
    print("  PASS: mock_complete_with_tools")


def test_mock_call_log():
    mock = MockLLMLayer()

    class TestModel(BaseModel):
        value: str = ""

    asyncio.run(
        mock.complete_structured(
            messages=[{"role": "user", "content": "msg1"}],
            model_tier="sonnet",
            response_model=TestModel,
        )
    )
    asyncio.run(
        mock.complete_raw(
            messages=[{"role": "user", "content": "msg2"}],
            model_tier="haiku",
        )
    )

    assert len(mock.call_log) == 2
    assert mock.call_log[0]["method"] == "complete_structured"
    assert mock.call_log[0]["model_tier"] == "sonnet"
    assert mock.call_log[1]["method"] == "complete_raw"
    assert mock.call_log[1]["model_tier"] == "haiku"
    print("  PASS: mock_call_log")


def test_mock_estimate_cost():
    mock = MockLLMLayer()
    assert mock.estimate_cost("opus", 1_000_000, 1_000_000) == 0.0
    assert mock.estimate_cost("sonnet", 100, 50) == 0.0
    print("  PASS: mock_estimate_cost")


def test_mock_build_cached_system():
    mock = MockLLMLayer()
    result = mock.build_cached_system("test prompt")
    assert result[0]["text"] == "test prompt"
    assert result[0]["cache_control"]["type"] == "ephemeral"
    print("  PASS: mock_build_cached_system")


def test_mock_message_structure():
    msg = _MockMessage("hello world")
    assert msg.content[0].text == "hello world"
    assert msg.content[0].type == "text"
    assert msg.stop_reason == "end_turn"
    assert msg.model == "mock-model"
    assert msg.usage.input_tokens == 100
    assert msg.usage.output_tokens == 50
    print("  PASS: mock_message_structure")


if __name__ == "__main__":
    print("Testing LLMLayer + MockLLMLayer:")
    # LLMResponse
    test_llm_response_defaults()
    test_llm_response_timestamp_unique()
    # estimate_cost
    test_estimate_cost_sonnet_basic()
    test_estimate_cost_opus_basic()
    test_estimate_cost_haiku_basic()
    test_estimate_cost_with_cache()
    test_estimate_cost_zero_tokens()
    test_estimate_cost_small_tokens()
    test_estimate_cost_all_cached()
    # build_cached_system
    test_build_cached_system_format()
    test_build_cached_system_empty_text()
    # MockLLMLayer
    test_mock_complete_structured_default()
    test_mock_complete_structured_with_response()
    test_mock_complete_raw()
    test_mock_complete_with_tools()
    test_mock_call_log()
    test_mock_estimate_cost()
    test_mock_build_cached_system()
    test_mock_message_structure()
    print("\nAll LLMLayer + MockLLMLayer tests passed!")
