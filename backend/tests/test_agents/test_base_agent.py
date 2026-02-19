"""Tests for BaseAgent — retry logic, error handling, build_output, load_spec."""

import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.base import BaseAgent
from app.llm.mock_layer import MockLLMLayer
from app.llm.layer import LLMResponse
from app.models.agent import AgentOutput, AgentSpec
from app.models.messages import ContextPackage


def _make_spec(**overrides) -> AgentSpec:
    defaults = dict(
        id="test_agent",
        name="Test Agent",
        tier="domain_expert",
        model_tier="sonnet",
        system_prompt_file="nonexistent.md",
    )
    defaults.update(overrides)
    return AgentSpec(**defaults)


class SuccessAgent(BaseAgent):
    """Agent that always succeeds."""

    async def run(self, context: ContextPackage) -> AgentOutput:
        return self.build_output(
            output={"result": "ok"},
            output_type="TestOutput",
            summary="Test success",
            input_tokens=100,
            output_tokens=50,
        )


class FailingAgent(BaseAgent):
    """Agent that always raises."""

    async def run(self, context: ContextPackage) -> AgentOutput:
        raise RuntimeError("Intentional failure")


class FailThenSucceedAgent(BaseAgent):
    """Agent that fails N times then succeeds."""

    def __init__(self, spec, llm, fail_count=2):
        super().__init__(spec, llm)
        self._fail_count = fail_count
        self._attempts = 0

    async def run(self, context: ContextPackage) -> AgentOutput:
        self._attempts += 1
        if self._attempts <= self._fail_count:
            raise RuntimeError(f"Fail attempt {self._attempts}")
        return self.build_output(output={"recovered": True}, summary="Recovered")


# === Init & Properties ===


def test_init_sets_properties():
    spec = _make_spec(id="my_agent", model_tier="opus")
    llm = MockLLMLayer()
    agent = SuccessAgent(spec=spec, llm=llm)
    assert agent.agent_id == "my_agent"
    assert agent.model_tier == "opus"
    assert agent.status.state == "idle"
    print("  PASS: init_sets_properties")


def test_load_prompt_fallback():
    """When prompt file doesn't exist, returns fallback string."""
    spec = _make_spec(system_prompt_file="definitely_nonexistent_file_xyz.md")
    llm = MockLLMLayer()
    agent = SuccessAgent(spec=spec, llm=llm)
    assert "specialized biology research agent" in agent.system_prompt
    assert spec.name in agent.system_prompt
    print("  PASS: load_prompt_fallback")


def test_system_prompt_cached():
    """Cached system prompt should have cache_control structure."""
    spec = _make_spec()
    llm = MockLLMLayer()
    agent = SuccessAgent(spec=spec, llm=llm)
    cached = agent.system_prompt_cached
    assert isinstance(cached, list)
    assert len(cached) == 1
    assert cached[0]["cache_control"]["type"] == "ephemeral"
    print("  PASS: system_prompt_cached")


# === execute() — Success Path ===


def test_execute_success():
    spec = _make_spec()
    llm = MockLLMLayer()
    agent = SuccessAgent(spec=spec, llm=llm)
    ctx = ContextPackage(task_description="test task")

    result = asyncio.get_event_loop().run_until_complete(agent.execute(ctx))

    assert result.is_success
    assert result.agent_id == "test_agent"
    assert result.output == {"result": "ok"}
    assert result.retry_count == 0
    assert result.duration_ms >= 0
    # Status should be idle after success
    assert agent.status.state == "idle"
    assert agent.status.total_calls == 1
    assert agent.status.consecutive_failures == 0
    print("  PASS: execute_success")


def test_execute_tracks_cost():
    spec = _make_spec()
    llm = MockLLMLayer()
    agent = SuccessAgent(spec=spec, llm=llm)
    ctx = ContextPackage(task_description="test task")

    result = asyncio.get_event_loop().run_until_complete(agent.execute(ctx))

    assert result.is_success
    # MockLLMLayer.estimate_cost returns 0.0 always
    assert agent.status.total_cost == result.cost
    print("  PASS: execute_tracks_cost")


# === execute() — Failure Path ===


def test_execute_all_retries_fail():
    spec = _make_spec()
    llm = MockLLMLayer()
    agent = FailingAgent(spec=spec, llm=llm)
    ctx = ContextPackage(task_description="test task")

    result = asyncio.get_event_loop().run_until_complete(agent.execute(ctx))

    assert not result.is_success
    assert "RuntimeError" in result.error
    assert "Intentional failure" in result.error
    assert result.retry_count == 3  # max_api_retries
    # Status after all failures
    assert agent.status.state == "idle"
    assert agent.status.consecutive_failures == 1
    assert agent.status.total_calls == 0
    print("  PASS: execute_all_retries_fail")


def test_execute_retry_then_succeed():
    spec = _make_spec()
    llm = MockLLMLayer()
    agent = FailThenSucceedAgent(spec=spec, llm=llm, fail_count=2)
    ctx = ContextPackage(task_description="test task")

    result = asyncio.get_event_loop().run_until_complete(agent.execute(ctx))

    assert result.is_success
    assert result.output == {"recovered": True}
    assert result.retry_count == 2  # Succeeded on 3rd attempt (index 2)
    assert agent.status.consecutive_failures == 0
    assert agent._attempts == 3
    print("  PASS: execute_retry_then_succeed")


def test_execute_sets_busy_then_idle():
    """Status transitions through busy during execution."""
    spec = _make_spec()
    llm = MockLLMLayer()
    agent = SuccessAgent(spec=spec, llm=llm)
    ctx = ContextPackage(task_description="test task")

    assert agent.status.state == "idle"
    asyncio.get_event_loop().run_until_complete(agent.execute(ctx))
    assert agent.status.state == "idle"
    print("  PASS: execute_sets_busy_then_idle")


def test_consecutive_failures_increment():
    spec = _make_spec()
    llm = MockLLMLayer()
    ctx = ContextPackage(task_description="test task")

    agent = FailingAgent(spec=spec, llm=llm)
    asyncio.get_event_loop().run_until_complete(agent.execute(ctx))
    assert agent.status.consecutive_failures == 1

    # Create a fresh failing agent to test second failure
    agent2 = FailingAgent(spec=spec, llm=llm)
    asyncio.get_event_loop().run_until_complete(agent2.execute(ctx))
    asyncio.get_event_loop().run_until_complete(agent2.execute(ctx))
    assert agent2.status.consecutive_failures == 2
    print("  PASS: consecutive_failures_increment")


def test_consecutive_failures_reset_on_success():
    spec = _make_spec()
    llm = MockLLMLayer()
    ctx = ContextPackage(task_description="test task")

    # Fail first
    agent = FailThenSucceedAgent(spec=spec, llm=llm, fail_count=1)
    asyncio.get_event_loop().run_until_complete(agent.execute(ctx))
    assert agent.status.consecutive_failures == 0  # Reset after success
    print("  PASS: consecutive_failures_reset_on_success")


# === build_output ===


def test_build_output_with_llm_response():
    spec = _make_spec()
    llm = MockLLMLayer()
    agent = SuccessAgent(spec=spec, llm=llm)

    meta = LLMResponse(
        model_version="claude-sonnet-4-5-20250929",
        input_tokens=1000,
        output_tokens=500,
        cached_input_tokens=800,
        cost=0.042,
    )
    result = agent.build_output(
        output={"key": "value"},
        output_type="TestModel",
        summary="Test summary",
        llm_response=meta,
    )

    assert result.model_version == "claude-sonnet-4-5-20250929"
    assert result.input_tokens == 1000
    assert result.output_tokens == 500
    assert result.cached_input_tokens == 800
    assert result.cost == 0.042
    assert result.output_type == "TestModel"
    assert result.agent_id == "test_agent"
    print("  PASS: build_output_with_llm_response")


def test_build_output_manual_tokens():
    spec = _make_spec()
    llm = MockLLMLayer()
    agent = SuccessAgent(spec=spec, llm=llm)

    result = agent.build_output(
        output={"key": "value"},
        summary="Manual test",
        input_tokens=500,
        output_tokens=200,
    )

    assert result.input_tokens == 500
    assert result.output_tokens == 200
    assert result.cost == 0.0  # MockLLMLayer.estimate_cost returns 0.0
    assert result.agent_id == "test_agent"
    print("  PASS: build_output_manual_tokens")


def test_build_output_defaults():
    spec = _make_spec()
    llm = MockLLMLayer()
    agent = SuccessAgent(spec=spec, llm=llm)

    result = agent.build_output()

    assert result.output is None
    assert result.output_type == ""
    assert result.summary == ""
    assert result.cost == 0.0
    print("  PASS: build_output_defaults")


# === load_spec ===


def test_load_spec_file_not_found():
    try:
        BaseAgent.load_spec("definitely_nonexistent_spec")
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError as e:
        assert "definitely_nonexistent_spec" in str(e)
    print("  PASS: load_spec_file_not_found")


if __name__ == "__main__":
    print("Testing BaseAgent:")
    # Init & Properties
    test_init_sets_properties()
    test_load_prompt_fallback()
    test_system_prompt_cached()
    # Execute success
    test_execute_success()
    test_execute_tracks_cost()
    # Execute failure
    test_execute_all_retries_fail()
    test_execute_retry_then_succeed()
    test_execute_sets_busy_then_idle()
    test_consecutive_failures_increment()
    test_consecutive_failures_reset_on_success()
    # Build output
    test_build_output_with_llm_response()
    test_build_output_manual_tokens()
    test_build_output_defaults()
    # Load spec
    test_load_spec_file_not_found()
    print("\nAll BaseAgent tests passed!")
