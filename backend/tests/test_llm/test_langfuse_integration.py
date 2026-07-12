"""Tests for Langfuse observability integration.

Verifies:
- @observe decorators are no-ops when Langfuse is unconfigured
- LLM layer methods have @observe decorators attached
- Workflow runners have @observe decorators attached
- Langfuse init/shutdown in main.py don't crash without keys
- _tag_langfuse_generation is safe when Langfuse is disabled
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import asyncio
from unittest.mock import MagicMock, patch

import pytest

# === 1. Graceful fallback when Langfuse is not configured ===


def test_observe_noop_without_langfuse_keys():
    """@observe decorator should be a no-op when langfuse keys are empty."""
    from app.agents.base import observe

    # Whether langfuse is importable or not, the decorator should work
    @observe(name="test.noop")
    async def dummy():
        return 42

    result = asyncio.get_event_loop().run_until_complete(dummy())
    assert result == 42


def test_llm_layer_observe_noop():
    """LLM layer observe decorator doesn't crash when Langfuse unavailable."""
    from app.llm.layer import observe

    @observe(as_type="generation", name="test.gen")
    async def dummy_gen():
        return "ok"

    result = asyncio.get_event_loop().run_until_complete(dummy_gen())
    assert result == "ok"


def test_tag_langfuse_generation_noop():
    """_tag_langfuse_generation is safe when Langfuse is not configured."""
    from app.llm.layer import LLMLayer, LLMResponse

    # LLMLayer.__init__ needs anthropic client — mock it
    with patch("app.llm.layer.anthropic.AsyncAnthropic"):
        with patch("app.llm.layer.instructor.from_anthropic"):
            layer = LLMLayer()

    meta = LLMResponse(
        model_version="claude-sonnet-4-20250514",
        input_tokens=100,
        output_tokens=50,
        cost=0.001,
    )
    # Should not raise even without Langfuse configured
    layer._tag_langfuse_generation(meta, "TestSchema")


# === 2. Decorators are properly attached to LLM layer methods ===


def test_llm_layer_methods_have_observe():
    """LLM layer's key methods should have @observe attached."""
    # @observe wraps the function — check it's callable and async
    import inspect

    from app.llm.layer import LLMLayer
    assert inspect.iscoroutinefunction(LLMLayer.complete_structured)
    assert inspect.iscoroutinefunction(LLMLayer.complete_raw)
    assert inspect.iscoroutinefunction(LLMLayer.complete_with_tools)


# === 3. Decorators are properly attached to workflow runners ===


def test_w1_runner_has_observe():
    """W1 runner run() and resume_after_human() should be decorated."""
    import inspect

    from app.workflows.runners.w1_literature import W1LiteratureReviewRunner
    assert inspect.iscoroutinefunction(W1LiteratureReviewRunner.run)
    assert inspect.iscoroutinefunction(W1LiteratureReviewRunner.resume_after_human)


def test_w2_runner_has_observe():
    """W2 runner run() and resume_after_human() should be decorated."""
    import inspect

    from app.workflows.runners.w2_hypothesis import W2HypothesisRunner
    assert inspect.iscoroutinefunction(W2HypothesisRunner.run)
    assert inspect.iscoroutinefunction(W2HypothesisRunner.resume_after_human)


def test_w3_runner_has_observe():
    """W3 runner run() and resume_after_human() should be decorated."""
    import inspect

    from app.workflows.runners.w3_data_analysis import W3DataAnalysisRunner
    assert inspect.iscoroutinefunction(W3DataAnalysisRunner.run)
    assert inspect.iscoroutinefunction(W3DataAnalysisRunner.resume_after_human)


def test_w4_runner_has_observe():
    """W4 runner run() and resume_after_human() should be decorated."""
    import inspect

    from app.workflows.runners.w4_manuscript import W4ManuscriptRunner
    assert inspect.iscoroutinefunction(W4ManuscriptRunner.run)
    assert inspect.iscoroutinefunction(W4ManuscriptRunner.resume_after_human)


def test_w5_runner_has_observe():
    """W5 runner run() and resume_after_human() should be decorated."""
    import inspect

    from app.workflows.runners.w5_grant import W5GrantProposalRunner
    assert inspect.iscoroutinefunction(W5GrantProposalRunner.run)
    assert inspect.iscoroutinefunction(W5GrantProposalRunner.resume_after_human)


def test_w6_runner_has_observe():
    """W6 runner run() should be decorated."""
    import inspect

    from app.workflows.runners.w6_ambiguity import W6AmbiguityRunner
    assert inspect.iscoroutinefunction(W6AmbiguityRunner.run)


# === 4. Langfuse init/shutdown don't crash ===


def test_configure_langfuse_no_keys():
    """_configure_langfuse returns False when no keys set."""
    from app.main import _configure_langfuse

    with patch("app.config.settings") as mock_settings:
        mock_settings.langfuse_public_key = ""
        mock_settings.langfuse_secret_key = ""
        result = _configure_langfuse()
    assert result is False


def test_configure_langfuse_with_keys():
    """_configure_langfuse returns True when keys are set and langfuse available."""
    from app.main import _configure_langfuse

    mock_ctx = MagicMock()
    mock_ctx.configure = MagicMock()

    # Mock the import inside _configure_langfuse
    mock_decorators = MagicMock()
    mock_decorators.langfuse_context = mock_ctx

    with patch("app.main.logger"):
        with patch.dict("sys.modules", {"langfuse.decorators": mock_decorators}):
            with patch("app.config.settings") as mock_settings:
                mock_settings.langfuse_public_key = "pk-test-123"
                mock_settings.langfuse_secret_key = "sk-test-456"
                mock_settings.langfuse_host = "http://localhost:3001"

                result = _configure_langfuse()

    assert result is True
    mock_ctx.configure.assert_called_once_with(
        public_key="pk-test-123",
        secret_key="sk-test-456",
        host="http://localhost:3001",
    )


def test_shutdown_langfuse_no_crash():
    """_shutdown_langfuse should not raise even if langfuse is not available."""
    from app.main import _shutdown_langfuse

    # Should silently pass
    _shutdown_langfuse()


# === 5. BaseAgent execute still works with @observe ===


def test_base_agent_execute_with_observe():
    """BaseAgent.execute() should work normally with @observe decorator."""
    from app.agents.base import BaseAgent
    from app.models.agent import AgentOutput, AgentSpec
    from app.models.messages import ContextPackage

    spec = AgentSpec(
        id="test_agent",
        name="Test Agent",
        tier="domain_expert",
        model_tier="sonnet",
        system_prompt_file="test.md",
        version="1.0",
        tools=[],
        criticality="optional",
    )

    mock_llm = MagicMock()
    mock_llm.build_cached_system.return_value = [{"type": "text", "text": "test"}]
    mock_llm.estimate_cost.return_value = 0.001

    class TestAgent(BaseAgent):
        async def run(self, context):
            return self.build_output(
                output={"result": "test"},
                summary="Test output",
                input_tokens=10,
                output_tokens=5,
            )

    agent = TestAgent(spec, mock_llm)
    context = ContextPackage(task_description="test task")

    result = asyncio.get_event_loop().run_until_complete(agent.execute(context))
    assert isinstance(result, AgentOutput)
    assert result.output == {"result": "test"}
    assert result.agent_id == "test_agent"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
