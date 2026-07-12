"""Gemini LLM Layer — lightweight wrapper for Google Gemini API.

Used by DigestAgent for cost-free summarization (Gemini 2.0 Flash free tier).
Mirrors the complete_structured interface of LLMLayer so agents can swap
providers with minimal code changes.

Uses the official ``google-genai`` SDK (not the deprecated google-generativeai).

Usage:
    layer = GeminiLayer()
    result, meta = await layer.complete_structured(
        messages=[{"role": "user", "content": "..."}],
        response_model=DigestSummary,
        system="You are a research summarizer.",
    )
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass
class GeminiResponse:
    """Metadata from a Gemini API call, compatible with LLMResponse interface."""

    model_version: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    stop_reason: str = ""
    cost: float = 0.0  # Free tier = $0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class GeminiLayer:
    """Lightweight Gemini API wrapper for structured output.

    Supports complete_structured() for Pydantic-validated JSON responses.
    Uses the google-genai SDK with native async support.
    """

    def __init__(self, api_key: str = "", model: str = "") -> None:
        self._api_key = api_key or settings.google_api_key
        self._model_name = model or settings.gemini_model
        self._client = None

    def _get_client(self):
        """Lazy-init Google GenAI client."""
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=self._api_key)
            except ImportError:
                raise ImportError(
                    "google-genai is required for Gemini support. "
                    "Install with: uv add google-genai"
                )
        return self._client

    async def complete_structured(
        self,
        messages: list[dict],
        response_model: type[BaseModel],
        system: str | list[dict] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> tuple[BaseModel, GeminiResponse]:
        """Structured output with Pydantic validation.

        Args:
            messages: Conversation messages (OpenAI format).
            response_model: Pydantic model class for output validation.
            system: System prompt (str or list of dicts with "text" key).
            max_tokens: Max output tokens.
            temperature: Sampling temperature.

        Returns:
            Tuple of (validated Pydantic model, GeminiResponse metadata).
        """
        from google.genai import types

        client = self._get_client()

        # Resolve system text
        system_text = ""
        if isinstance(system, str):
            system_text = system
        elif isinstance(system, list):
            system_text = "\n".join(
                block.get("text", "") for block in system if isinstance(block, dict)
            )

        # Generate JSON schema from Pydantic model for the prompt
        schema_json = json.dumps(response_model.model_json_schema(), indent=2)

        # Build user content from messages
        user_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                user_parts.append(content)
            elif role == "assistant":
                user_parts.append(f"Previous response:\n{content}")

        user_parts.append(
            f"\nRespond ONLY with valid JSON matching this schema:\n{schema_json}"
        )
        user_content = "\n\n".join(user_parts)

        # Build contents in google-genai format
        contents = [types.Content(role="user", parts=[types.Part(text=user_content)])]

        config = types.GenerateContentConfig(
            system_instruction=system_text or None,
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
        )

        # Use async API
        try:
            response = await client.aio.models.generate_content(
                model=self._model_name,
                contents=contents,
                config=config,
            )
        except Exception as e:
            logger.error("Gemini API call failed: %s", e)
            raise

        # Extract text from response
        raw_text = response.text or ""
        usage = getattr(response, "usage_metadata", None)

        meta = GeminiResponse(
            model_version=self._model_name,
            input_tokens=getattr(usage, "prompt_token_count", 0) if usage else 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) if usage else 0,
            stop_reason="end_turn",
            cost=0.0,  # Free tier
        )

        # Parse JSON and validate with Pydantic
        try:
            parsed = json.loads(raw_text)
            result = response_model.model_validate(parsed)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Gemini JSON parse failed, attempting cleanup: %s", e)
            # Try to extract JSON from markdown code blocks
            clean = raw_text.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            try:
                parsed = json.loads(clean)
                result = response_model.model_validate(parsed)
            except Exception as e2:
                logger.error("Gemini structured output failed: %s\nRaw: %s", e2, raw_text[:500])
                raise ValueError(f"Failed to parse Gemini response: {e2}") from e2

        return result, meta

    def build_cached_system(self, text: str) -> str:
        """Build system prompt (no caching for Gemini, returns as-is)."""
        return text

    @staticmethod
    def estimate_cost(*args: Any, **kwargs: Any) -> float:
        """Gemini free tier — always returns 0."""
        return 0.0
