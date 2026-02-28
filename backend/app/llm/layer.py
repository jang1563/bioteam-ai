"""LLM Layer — All agent LLM calls go through this layer.

Uses AsyncAnthropic + Instructor for structured outputs.
Validated in Day 0 spike: async works with both raw and Instructor calls.

v4.2 changes:
- temperature parameter added (default 0.0 for reproducibility)
- model_version auto-captured from API response
- LLMResponse dataclass carries metadata alongside results
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import anthropic
import instructor
from app.config import MODEL_MAP, ModelTier, settings
from pydantic import BaseModel

# Langfuse import with graceful fallback (same pattern as agents/base.py)
try:
    from langfuse.decorators import langfuse_context, observe
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False

    def observe(*args, **kwargs):  # type: ignore[misc]
        def wrapper(fn):
            return fn
        if args and callable(args[0]):
            return args[0]
        return wrapper

    class _NoopContext:
        def update_current_observation(self, **kwargs):
            pass

    langfuse_context = _NoopContext()  # type: ignore[assignment]

logger = logging.getLogger(__name__)


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


class CircuitBreaker:
    """Simple circuit breaker for external API calls.

    States: CLOSED (normal) → OPEN (fail-fast) → HALF_OPEN (probe).
    Opens after `failure_threshold` consecutive failures.
    Auto-resets to HALF_OPEN after `reset_timeout` seconds.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, reset_timeout: float = 60.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> str:
        if self._state == self.OPEN:
            if time.monotonic() - self._last_failure_time >= self.reset_timeout:
                self._state = self.HALF_OPEN
        return self._state

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = self.CLOSED

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = self.OPEN
            logger.warning("Circuit breaker OPEN after %d consecutive failures", self._failure_count)

    def allow_request(self) -> bool:
        state = self.state
        if state == self.CLOSED:
            return True
        if state == self.HALF_OPEN:
            return True  # Allow one probe request
        return False


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker is open and rejecting requests."""


async def _retry_with_backoff(
    coro_factory,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    circuit_breaker: CircuitBreaker | None = None,
):
    """Retry an async call with exponential backoff.

    Args:
        coro_factory: Callable that returns a new coroutine each time.
        max_retries: Maximum number of retries (0 = no retry).
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap.
        circuit_breaker: Optional circuit breaker instance.

    Returns:
        The result of the successful call.
    """
    if circuit_breaker and not circuit_breaker.allow_request():
        raise CircuitBreakerOpenError("Circuit breaker is open. Anthropic API calls temporarily disabled.")

    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            result = await coro_factory()
            if circuit_breaker:
                circuit_breaker.record_success()
            return result
        except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError) as e:
            last_exception = e
            if circuit_breaker:
                circuit_breaker.record_failure()
            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                logger.warning("LLM call attempt %d/%d failed (%s), retrying in %.1fs", attempt + 1, max_retries + 1, type(e).__name__, delay)
                await asyncio.sleep(delay)
            else:
                raise
        except Exception:
            # Non-retryable errors (auth, bad request, etc.)
            if circuit_breaker:
                circuit_breaker.record_failure()
            raise

    raise last_exception  # type: ignore[misc]


class LLMLayer:
    """Centralized LLM access for all agents.

    Provides three call patterns:
    - complete_structured: Pydantic-validated output via Instructor + auto-retry
    - complete_raw: Free-text or tool-use (direct Anthropic SDK)
    - complete_with_tools: Agentic tool-use loop (multi-turn)

    Includes circuit breaker and retry with exponential backoff for resilience.
    """

    def __init__(self) -> None:
        self.raw_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.client = instructor.from_anthropic(self.raw_client)
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, reset_timeout=60.0)

    @observe(as_type="generation", name="llm.complete_structured")
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

        result, raw_response = await _retry_with_backoff(
            coro_factory=lambda: self.client.messages.create_with_completion(**kwargs),
            max_retries=3,
            circuit_breaker=self.circuit_breaker,
        )

        meta = self._extract_metadata(raw_response, model_tier)
        self._tag_langfuse_generation(meta, response_model.__name__)
        return result, meta

    @observe(as_type="generation", name="llm.complete_raw")
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

        response = await _retry_with_backoff(
            coro_factory=lambda: self.raw_client.messages.create(**kwargs),
            max_retries=3,
            circuit_breaker=self.circuit_breaker,
        )

        meta = self._extract_metadata(response, model_tier)
        self._tag_langfuse_generation(meta)
        return response, meta

    # Note: @observe doesn't support async generators, so we tag manually inside
    async def complete_stream(
        self,
        messages: list[dict],
        model_tier: ModelTier,
        system: str | list[dict] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncGenerator[tuple[str, LLMResponse | None], None]:
        """Streaming completion — yields token chunks then final metadata.

        Yields:
            ("chunk_text", None) for each token chunk during streaming
            ("", LLMResponse) as the final yield with complete metadata

        Args:
            messages: Conversation messages.
            model_tier: "opus", "sonnet", or "haiku".
            system: Optional system prompt.
            max_tokens: Max output tokens.
            temperature: Sampling temperature.
        """
        if not self.circuit_breaker.allow_request():
            raise CircuitBreakerOpenError("Circuit breaker is open.")

        kwargs: dict[str, Any] = {
            "model": MODEL_MAP[model_tier],
            "max_tokens": max_tokens or settings.default_max_tokens,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.default_temperature,
        }
        if system:
            kwargs["system"] = system

        try:
            async with self.raw_client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text, None

                response = await stream.get_final_message()
                self.circuit_breaker.record_success()
                meta = self._extract_metadata(response, model_tier)
                yield "", meta
        except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError):
            self.circuit_breaker.record_failure()
            raise
        except Exception:
            self.circuit_breaker.record_failure()
            raise

    @observe(name="llm.complete_with_tools")
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
        self._tag_langfuse_generation(aggregated)
        return responses, aggregated

    @observe(name="llm.complete_with_ptc")
    async def complete_with_ptc(
        self,
        messages: list[dict],
        model_tier: ModelTier,
        system: str | list[dict],
        custom_tools: list[dict],
        tool_implementations: dict[str, Any],
        container_id: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> tuple[str, LLMResponse, str | None]:
        """Programmatic Tool Calling — Claude writes Python to orchestrate tools.

        Claude generates Python code that calls custom_tools in a sandbox.
        Tool results stay in the sandbox; only print() output enters context.
        Saves ~37% tokens compared to complete_with_tools for multi-tool scenarios.

        CONSTRAINTS:
        - Cannot use with MCP tools (use beta API with MCP instead)
        - Cannot use with strict structured outputs (Instructor)
        - Custom tools must have allowed_callers: ["code_execution_20260120"]

        Args:
            messages: Conversation messages.
            model_tier: "opus", "sonnet", or "haiku".
            system: System prompt.
            custom_tools: Tool definitions (code_execution + custom tools).
            tool_implementations: Map of tool name -> async callable(input_dict) -> result.
            container_id: Optional container ID for reuse across calls.
            max_tokens: Max output tokens.
            temperature: Sampling temperature.

        Returns:
            Tuple of (final_text, LLMResponse metadata, container_id or None).
        """
        from app.llm.ptc_tools import PTC_CODE_EXECUTION_TYPE, ensure_allowed_callers

        all_tools = ensure_allowed_callers(custom_tools)

        # Ensure code_execution tool is present
        has_code_exec = any(
            t.get("type") == PTC_CODE_EXECUTION_TYPE for t in all_tools
        )
        if not has_code_exec:
            all_tools.insert(0, {
                "type": PTC_CODE_EXECUTION_TYPE,
                "name": "code_execution",
            })

        kwargs: dict[str, Any] = {
            "model": MODEL_MAP[model_tier],
            "max_tokens": max_tokens or settings.default_max_tokens,
            "messages": list(messages),
            "tools": all_tools,
            "temperature": temperature if temperature is not None else settings.default_temperature,
        }
        if system:
            kwargs["system"] = system
        if container_id:
            kwargs["container"] = container_id

        # PTC multi-turn loop: Claude writes code → code calls tools → we execute → resume
        conversation = list(messages)
        total_input = 0
        total_output = 0
        total_cached = 0
        model_version = ""
        new_container_id: str | None = None

        _PTC_MAX_TURNS = 10
        for _turn in range(_PTC_MAX_TURNS):  # Safety limit
            response = await _retry_with_backoff(
                coro_factory=lambda: self.raw_client.messages.create(**{
                    **kwargs,
                    "messages": conversation,
                    **({"container": new_container_id} if new_container_id else {}),
                }),
                max_retries=3,
                circuit_breaker=self.circuit_breaker,
            )

            usage = response.usage
            total_input += getattr(usage, "input_tokens", 0)
            total_output += getattr(usage, "output_tokens", 0)
            total_cached += getattr(usage, "cache_read_input_tokens", 0) or 0
            model_version = response.model

            # Check for container ID in response
            if hasattr(response, "container") and response.container:
                new_container_id = getattr(response.container, "id", None)

            # If model finished, extract final text
            if response.stop_reason == "end_turn":
                break

            # Handle tool_use blocks (programmatic tool calls from code execution)
            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if getattr(block, "type", "") == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        impl = tool_implementations.get(tool_name)
                        if impl:
                            try:
                                result = await impl(tool_input)
                            except Exception as e:
                                result = {"error": str(e)}
                        else:
                            result = {"error": f"Unknown tool: {tool_name}"}
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(result) if not isinstance(result, str) else result,
                        })

                conversation.append({"role": "assistant", "content": response.content})
                conversation.append({"role": "user", "content": tool_results})
                continue

            # Any other stop reason — break
            break
        else:
            logger.warning(
                "complete_with_ptc hit safety turn limit (%d). "
                "Model may not have finished — final text may be incomplete.",
                _PTC_MAX_TURNS,
            )

        # Extract final text from last response
        final_text = ""
        for block in response.content:
            if getattr(block, "type", "") == "text":
                final_text += getattr(block, "text", "")

        meta = LLMResponse(
            model_version=model_version,
            input_tokens=total_input,
            output_tokens=total_output,
            cached_input_tokens=total_cached,
            stop_reason=response.stop_reason or "",
            cost=self.estimate_cost(model_tier, total_input, total_output, total_cached),
        )
        self._tag_langfuse_generation(meta)
        return final_text, meta, new_container_id

    def build_deferred_tools(
        self,
        always_loaded: list[dict],
        deferred: list[dict],
    ) -> list[dict]:
        """Build a tool list with deferred loading for context efficiency.

        Always-loaded tools are included in full. Deferred tools are marked
        for on-demand loading via BM25 search. Saves ~85% context tokens.

        Args:
            always_loaded: Tools that should always be available.
            deferred: Tools that can be loaded on demand.

        Returns:
            Combined tool list with tool_search_tool and deferred markers.
        """
        tool_search = {
            "type": "tool_search_tool_bm25_20251119",
            "name": "tool_search_tool_bm25",
        }

        deferred_tools = []
        for tool in deferred:
            t = dict(tool)
            t["defer_loading"] = True
            deferred_tools.append(t)

        return [tool_search] + always_loaded + deferred_tools

    def _tag_langfuse_generation(
        self,
        meta: LLMResponse,
        output_schema: str = "",
    ) -> None:
        """Tag the current Langfuse observation with LLM generation metadata."""
        if not LANGFUSE_AVAILABLE or not settings.langfuse_public_key:
            return
        langfuse_context.update_current_observation(
            model=meta.model_version,
            usage={
                "input": meta.input_tokens,
                "output": meta.output_tokens,
                "total": meta.input_tokens + meta.output_tokens,
                "unit": "TOKENS",
            },
            metadata={
                "cached_input_tokens": meta.cached_input_tokens,
                "cost_usd": meta.cost,
                "stop_reason": meta.stop_reason,
                **({"output_schema": output_schema} if output_schema else {}),
            },
        )

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
