"""Mock LLM Layer for testing without API calls.

v4.2: Updated to return (result, LLMResponse) tuples matching real LLMLayer.
"""

from __future__ import annotations

from pydantic import BaseModel
from typing import Any

from app.config import ModelTier
from app.llm.layer import LLMResponse


class MockLLMLayer:
    """Returns predefined responses for testing.

    Usage:
        mock = MockLLMLayer({
            "sonnet:QueryClassification": QueryClassification(
                type="simple_query",
                reasoning="test",
                target_agent="t02_transcriptomics",
            ),
        })
        result, meta = await mock.complete_structured(
            messages=[...],
            model_tier="sonnet",
            response_model=QueryClassification,
        )
    """

    def __init__(self, responses: dict[str, BaseModel] | None = None) -> None:
        self.responses = responses or {}
        self.call_log: list[dict] = []

    def _mock_meta(self, model_tier: ModelTier) -> LLMResponse:
        return LLMResponse(
            model_version=f"mock-{model_tier}",
            input_tokens=100,
            output_tokens=50,
            stop_reason="end_turn",
            cost=0.0,
        )

    async def complete_structured(
        self,
        messages: list[dict],
        model_tier: ModelTier,
        response_model: type[BaseModel],
        system: str | list[dict] | None = None,
        max_tokens: int | None = None,
        max_retries: int | None = None,
        temperature: float | None = None,
    ) -> tuple[BaseModel, LLMResponse]:
        """Return predefined response or construct a default instance."""
        key = f"{model_tier}:{response_model.__name__}"
        self.call_log.append({
            "method": "complete_structured",
            "model_tier": model_tier,
            "response_model": response_model.__name__,
            "messages": messages,
            "system": system,
            "temperature": temperature,
        })
        result = self.responses.get(key)
        if result is None:
            result = _build_default(response_model)
        return result, self._mock_meta(model_tier)

    async def complete_raw(
        self,
        messages: list[dict],
        model_tier: ModelTier,
        system: str | list[dict] | None = None,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> tuple[Any, LLMResponse]:
        """Return a mock raw response."""
        key = f"{model_tier}:raw"
        self.call_log.append({
            "method": "complete_raw",
            "model_tier": model_tier,
            "messages": messages,
            "temperature": temperature,
        })
        result = self.responses.get(key, _MockMessage(text="Mock response"))
        return result, self._mock_meta(model_tier)

    async def complete_with_tools(
        self,
        messages: list[dict],
        model_tier: ModelTier,
        system: str | list[dict],
        tools: list[dict],
        tool_executor: Any,
        max_iterations: int = 10,
        temperature: float | None = None,
    ) -> tuple[list[Any], LLMResponse]:
        """Return empty tool loop (single end_turn response)."""
        self.call_log.append({
            "method": "complete_with_tools",
            "model_tier": model_tier,
            "messages": messages,
            "temperature": temperature,
        })
        return [_MockMessage(text="Mock tool response")], self._mock_meta(model_tier)

    def build_cached_system(self, text: str) -> list[dict]:
        return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]

    def estimate_cost(self, model_tier: ModelTier, input_tokens: int,
                      output_tokens: int, cached_input_tokens: int = 0) -> float:
        return 0.0


def _build_default(model: type[BaseModel]) -> BaseModel:
    """Build a default instance of a Pydantic model, filling required fields."""
    try:
        return model()
    except Exception:
        pass
    # Fill required fields with type-appropriate defaults
    defaults = {}
    for name, field_info in model.model_fields.items():
        if field_info.is_required():
            annotation = field_info.annotation
            if annotation is str or (hasattr(annotation, '__origin__') is False and annotation == str):
                defaults[name] = ""
            elif annotation is int:
                defaults[name] = 0
            elif annotation is float:
                defaults[name] = 0.0
            elif annotation is bool:
                defaults[name] = False
            elif annotation is list or (hasattr(annotation, '__origin__') and getattr(annotation, '__origin__', None) is list):
                defaults[name] = []
            elif annotation is dict or (hasattr(annotation, '__origin__') and getattr(annotation, '__origin__', None) is dict):
                defaults[name] = {}
            else:
                defaults[name] = ""
    try:
        return model(**defaults)
    except Exception:
        return model.model_construct(**defaults)


class _MockMessage:
    """Minimal mock of anthropic.types.Message for testing."""

    def __init__(self, text: str = "Mock response"):
        self.content = [_MockTextBlock(text)]
        self.stop_reason = "end_turn"
        self.model = "mock-model"
        self.usage = _MockUsage()


class _MockTextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _MockUsage:
    def __init__(self):
        self.input_tokens = 100
        self.output_tokens = 50
        self.cache_read_input_tokens = 0
