"""LLM Layer — All agent LLM calls go through this layer.

Uses AsyncAnthropic + Instructor for structured outputs.
Validated in Day 0 spike: async works with both raw and Instructor calls.

v4.2 changes:
- temperature parameter added (default 0.0 for reproducibility)
- model_version auto-captured from API response
- LLMResponse dataclass carries metadata alongside results
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import anthropic
import instructor
from pydantic import BaseModel
from typing import Any, Literal

from app.config import MODEL_MAP, ModelTier, settings


@dataclass
class LLMResponse:
    """Metadata from an LLM call, for reproducibility tracking.

    v4.2: Every LLM call returns this alongside the actual result,
    enabling session manifests and reproducibility reports.
    """

    model_version: str = ""          # Exact model ID from API response
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    stop_reason: str = ""
    cost: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class LLMLayer:
    """Centralized LLM access for all agents.

    Provides three call patterns:
    - complete_structured: Pydantic-validated output via Instructor + auto-retry
    - complete_raw: Free-text or tool-use (direct Anthropic SDK)
    - complete_with_tools: Agentic tool-use loop (multi-turn)

    v4.2: All methods accept temperature (default 0.0 for deterministic,
    reproducible outputs). Use temperature > 0 only for creative tasks
    like hypothesis generation or manuscript drafting.
    """

    def __init__(self) -> None:
        self.raw_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.client = instructor.from_anthropic(self.raw_client)

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
        """Structured output with Pydantic validation + auto-retry.

        Args:
            messages: Conversation messages.
            model_tier: "opus", "sonnet", or "haiku".
            response_model: Pydantic model class for output validation.
            system: System prompt (str or list of cache_control blocks).
            max_tokens: Max output tokens.
            max_retries: Instructor retry count on validation failure.
            temperature: Sampling temperature (0.0 = deterministic).

        Returns:
            Tuple of (validated Pydantic model, LLMResponse metadata).
        """
        kwargs: dict[str, Any] = {
            "model": MODEL_MAP[model_tier],
            "max_tokens": max_tokens or settings.default_max_tokens,
            "messages": messages,
            "response_model": response_model,
            "max_retries": max_retries or settings.default_max_retries,
            "temperature": temperature if temperature is not None else settings.default_temperature,
        }
        if system:
            kwargs["system"] = system

        result, raw_response = await self.client.messages.create_with_completion(**kwargs)

        meta = self._extract_metadata(raw_response, model_tier)
        return result, meta

    async def complete_raw(
        self,
        messages: list[dict],
        model_tier: ModelTier,
        system: str | list[dict] | None = None,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> tuple[anthropic.types.Message, LLMResponse]:
        """Raw completion for free-text or tool-use scenarios.

        Args:
            messages: Conversation messages.
            model_tier: "opus", "sonnet", or "haiku".
            system: System prompt (str or list of cache_control blocks).
            max_tokens: Max output tokens.
            tools: Tool definitions for tool_use.
            temperature: Sampling temperature (0.0 = deterministic).

        Returns:
            Tuple of (raw Anthropic Message, LLMResponse metadata).
        """
        kwargs: dict[str, Any] = {
            "model": MODEL_MAP[model_tier],
            "max_tokens": max_tokens or settings.default_max_tokens,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.default_temperature,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        response = await self.raw_client.messages.create(**kwargs)

        meta = self._extract_metadata(response, model_tier)
        return response, meta

    async def complete_with_tools(
        self,
        messages: list[dict],
        model_tier: ModelTier,
        system: str | list[dict],
        tools: list[dict],
        tool_executor: Any,  # Callable[[str, dict], Awaitable[Any]]
        max_iterations: int = 10,
        temperature: float | None = None,
    ) -> tuple[list[anthropic.types.Message], LLMResponse]:
        """Agentic tool-use loop.

        Runs multi-turn conversation until the model stops using tools
        or max_iterations is reached.

        Args:
            messages: Initial conversation messages.
            model_tier: Model tier.
            system: System prompt.
            tools: Tool definitions.
            tool_executor: Async callable(tool_name, tool_input) -> result.
            max_iterations: Safety limit on turns.
            temperature: Sampling temperature.

        Returns:
            Tuple of (list of all model responses, aggregated LLMResponse metadata).
        """
        conversation = list(messages)
        responses: list[anthropic.types.Message] = []
        total_input = 0
        total_output = 0
        total_cached = 0
        model_version = ""

        for _ in range(max_iterations):
            response, meta = await self.complete_raw(
                messages=conversation,
                model_tier=model_tier,
                system=system,
                tools=tools,
                temperature=temperature,
            )
            responses.append(response)
            total_input += meta.input_tokens
            total_output += meta.output_tokens
            total_cached += meta.cached_input_tokens
            model_version = meta.model_version

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = await tool_executor(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(result),
                        })

                conversation.append({"role": "assistant", "content": response.content})
                conversation.append({"role": "user", "content": tool_results})

        aggregated = LLMResponse(
            model_version=model_version,
            input_tokens=total_input,
            output_tokens=total_output,
            cached_input_tokens=total_cached,
            stop_reason=responses[-1].stop_reason if responses else "",
            cost=self.estimate_cost(model_tier, total_input, total_output, total_cached),
        )
        return responses, aggregated

    def _extract_metadata(
        self, response: anthropic.types.Message, model_tier: ModelTier
    ) -> LLMResponse:
        """Extract metadata from an Anthropic API response."""
        usage = response.usage
        input_tokens = getattr(usage, "input_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", 0)
        cached = getattr(usage, "cache_read_input_tokens", 0) or 0

        return LLMResponse(
            model_version=response.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached,
            stop_reason=response.stop_reason or "",
            cost=self.estimate_cost(model_tier, input_tokens, output_tokens, cached),
        )

    def build_cached_system(self, text: str) -> list[dict]:
        """Build a system prompt with ephemeral cache_control.

        Use this for system prompts that are shared across multiple agent calls
        within a short window (~5 min). Saves ~90% on input token costs.
        """
        return [
            {
                "type": "text",
                "text": text,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def estimate_cost(
        self,
        model_tier: ModelTier,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
    ) -> float:
        """Estimate cost for a single API call.

        Prices as of 2026-02 (per million tokens):
        - Opus:   input $15, output $75, cache read $1.50
        - Sonnet: input $3,  output $15, cache read $0.30
        - Haiku:  input $0.80, output $4, cache read $0.08
        """
        prices = {
            "opus":   {"input": 15.0,  "output": 75.0, "cache_read": 1.50},
            "sonnet": {"input": 3.0,   "output": 15.0, "cache_read": 0.30},
            "haiku":  {"input": 0.80,  "output": 4.0,  "cache_read": 0.08},
        }
        p = prices[model_tier]
        non_cached_input = input_tokens - cached_input_tokens
        cost = (
            (non_cached_input / 1_000_000) * p["input"]
            + (cached_input_tokens / 1_000_000) * p["cache_read"]
            + (output_tokens / 1_000_000) * p["output"]
        )
        return round(cost, 6)
