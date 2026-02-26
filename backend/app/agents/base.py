"""BaseAgent — abstract base class for all BioTeam-AI agents.

Design decisions (Day 0):
- All agents inherit from BaseAgent
- Each agent has a spec (YAML) and a system prompt (.md)
- Langfuse tracing via @observe decorator (simplest, most reliable pattern)
- Retry: Instructor handles schema validation retries; BaseAgent handles API-level retries
- Every run() returns AgentOutput with cost tracking

v4.2 changes:
- build_output accepts LLMResponse for automatic metadata propagation
- model_version auto-captured from LLM responses
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml
from app.config import ModelTier, settings
from app.llm.layer import LLMLayer, LLMResponse
from app.models.agent import AgentOutput, AgentSpec, AgentStatus
from app.models.messages import ContextPackage

# Langfuse import with graceful fallback
try:
    from langfuse.decorators import langfuse_context, observe
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    # Provide no-op decorator
    def observe(*args, **kwargs):  # type: ignore
        def wrapper(fn):
            return fn
        if args and callable(args[0]):
            return args[0]
        return wrapper


AGENTS_DIR = Path(__file__).parent
PROMPTS_DIR = AGENTS_DIR / "prompts"
SPECS_DIR = AGENTS_DIR / "specs"


class BaseAgent(ABC):
    """Abstract base class for all BioTeam-AI agents.

    Subclasses must implement:
    - run(context) -> AgentOutput: Core execution logic

    Usage (v4.2):
        class MyAgent(BaseAgent):
            async def run(self, context: ContextPackage) -> AgentOutput:
                result, meta = await self.llm.complete_structured(
                    messages=[{"role": "user", "content": context.task_description}],
                    model_tier=self.model_tier,
                    response_model=MyOutputModel,
                    system=self.system_prompt_cached,
                )
                return self.build_output(
                    output=result.model_dump(),
                    summary="...",
                    llm_response=meta,
                )
    """

    def __init__(self, spec: AgentSpec, llm: LLMLayer) -> None:
        self.spec = spec
        self.llm = llm
        self.status = AgentStatus(agent_id=spec.id)

        # Load system prompt from .md file
        self._system_prompt = self._load_prompt()

        # Pre-build cached version for prompt caching
        self.system_prompt_cached = self.llm.build_cached_system(self._system_prompt)

    @property
    def agent_id(self) -> str:
        return self.spec.id

    @property
    def model_tier(self) -> ModelTier:
        return self.spec.model_tier

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def _load_prompt(self) -> str:
        """Load system prompt from markdown file."""
        prompt_path = PROMPTS_DIR / self.spec.system_prompt_file
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return f"You are {self.spec.name}, a specialized biology research agent."

    @observe(name="agent.run")
    async def execute(self, context: ContextPackage) -> AgentOutput:
        """Execute the agent with tracing, timing, and error handling.

        This wraps the subclass's run() method with:
        1. Status management (idle -> busy -> idle)
        2. Timing and cost tracking
        3. Langfuse trace metadata
        4. Error handling with retry (API-level)
        """
        self.status.state = "busy"
        start_time = time.time()
        last_error: Exception | None = None

        # Tag Langfuse trace
        if LANGFUSE_AVAILABLE and settings.langfuse_public_key:
            langfuse_context.update_current_observation(
                metadata={
                    "agent_id": self.agent_id,
                    "model_tier": self.model_tier,
                    "spec_version": self.spec.version,
                },
            )

        # API-level retry (network errors, rate limits)
        max_api_retries = 3
        for attempt in range(max_api_retries):
            try:
                output = await self.run(context)
                output.duration_ms = int((time.time() - start_time) * 1000)
                output.agent_id = self.agent_id
                output.retry_count = attempt

                self.status.state = "idle"
                self.status.total_calls += 1
                self.status.total_cost += output.cost
                self.status.consecutive_failures = 0
                return output

            except Exception as e:
                last_error = e
                if attempt < max_api_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s
                    await asyncio.sleep(2 ** attempt)
                    continue

        # All retries failed
        self.status.state = "idle"
        self.status.consecutive_failures += 1
        duration_ms = int((time.time() - start_time) * 1000)

        return AgentOutput(
            agent_id=self.agent_id,
            error=f"{type(last_error).__name__}: {last_error}" if last_error else "Unknown error",
            duration_ms=duration_ms,
            retry_count=max_api_retries,
            model_tier=self.model_tier,
        )

    @abstractmethod
    async def run(self, context: ContextPackage) -> AgentOutput:
        """Core agent logic. Subclasses implement this.

        Args:
            context: Full context package with task, memory, prior outputs, etc.

        Returns:
            AgentOutput with the structured result.
        """
        ...

    def build_output(
        self,
        output: Any = None,
        output_type: str = "",
        summary: str = "",
        llm_response: LLMResponse | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_input_tokens: int = 0,
    ) -> AgentOutput:
        """Helper to construct AgentOutput with cost estimation.

        v4.2: Accepts LLMResponse for automatic metadata propagation.
        If llm_response is provided, token counts and cost are taken from it.

        Usage (v4.2 style):
            result, meta = await self.llm.complete_structured(...)
            return self.build_output(
                output=result.model_dump(),
                output_type="MyModel",
                summary="...",
                llm_response=meta,
            )
        """
        if llm_response is not None:
            return AgentOutput(
                agent_id=self.agent_id,
                output=output,
                output_type=output_type,
                summary=summary,
                model_tier=self.model_tier,
                model_version=llm_response.model_version,
                input_tokens=llm_response.input_tokens,
                output_tokens=llm_response.output_tokens,
                cached_input_tokens=llm_response.cached_input_tokens,
                cost=llm_response.cost,
            )
        # Fallback: manual token counts (backward compatibility)
        cost = self.llm.estimate_cost(
            model_tier=self.model_tier,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
        )
        # Resolve model_version from MODEL_MAP when LLM tokens were actually used,
        # so session manifest correctly records this call. Leave empty for
        # code-only/memory-only steps that don't call an LLM.
        resolved_version = ""
        if input_tokens > 0 or output_tokens > 0:
            from app.config import MODEL_MAP
            resolved_version = MODEL_MAP.get(self.model_tier, "")
        return AgentOutput(
            agent_id=self.agent_id,
            output=output,
            output_type=output_type,
            summary=summary,
            model_tier=self.model_tier,
            model_version=resolved_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            cost=cost,
        )

    @classmethod
    def load_spec(cls, spec_id: str) -> AgentSpec:
        """Load an AgentSpec from a YAML file."""
        spec_path = SPECS_DIR / f"{spec_id}.yaml"
        if not spec_path.exists():
            raise FileNotFoundError(f"Agent spec not found: {spec_path}")
        data = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        return AgentSpec(**data)
