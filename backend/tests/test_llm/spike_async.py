"""
Day 0 Spike: Validate AsyncAnthropic + Instructor works with await.

Run: python backend/tests/test_llm/spike_async.py

This tests:
1. instructor.from_anthropic() with AsyncAnthropic client
2. Structured output with a simple Pydantic model
3. Prompt caching with cache_control blocks
4. Error handling and retries
"""

import asyncio
import os
import sys
from typing import Literal

from pydantic import BaseModel, Field

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class SimpleClassification(BaseModel):
    """Test response model."""
    category: Literal["biology", "chemistry", "physics", "other"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


async def test_async_instructor():
    """Test 1: Basic async Instructor + Anthropic."""
    import anthropic
    import instructor

    # Create async client
    raw_client = anthropic.AsyncAnthropic()
    client = instructor.from_anthropic(raw_client)

    print("Test 1: AsyncAnthropic + Instructor structured output...")
    result = await client.messages.create(
        model="claude-haiku-4-5-20251001",  # Cheapest model for spike
        max_tokens=256,
        messages=[{"role": "user", "content": "Classify this topic: 'spaceflight-induced anemia mechanisms'"}],
        response_model=SimpleClassification,
    )

    assert isinstance(result, SimpleClassification), f"Expected SimpleClassification, got {type(result)}"
    assert result.category == "biology", f"Expected biology, got {result.category}"
    assert 0.0 <= result.confidence <= 1.0
    print(f"  PASS: category={result.category}, confidence={result.confidence}")
    print(f"  reasoning={result.reasoning[:80]}...")
    return True


async def test_async_raw():
    """Test 2: Raw AsyncAnthropic (no Instructor)."""
    import anthropic

    raw_client = anthropic.AsyncAnthropic()

    print("\nTest 2: Raw AsyncAnthropic...")
    response = await raw_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{"role": "user", "content": "What is hemoglobin? One sentence."}],
    )

    assert response.stop_reason == "end_turn"
    text = response.content[0].text
    print(f"  PASS: stop_reason={response.stop_reason}")
    print(f"  response={text[:100]}...")
    return True


async def test_prompt_caching():
    """Test 3: Prompt caching with cache_control blocks."""
    import anthropic

    raw_client = anthropic.AsyncAnthropic()

    system_prompt = (
        "You are a biology research assistant specializing in spaceflight biology. "
        "You help researchers analyze evidence about how spaceflight affects human physiology. "
        "Always respond concisely and cite specific mechanisms when possible."
    )

    print("\nTest 3: Prompt caching with cache_control...")
    response = await raw_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": "What causes space anemia?"}],
    )

    print(f"  stop_reason={response.stop_reason}")
    # Check usage for cache metrics
    usage = response.usage
    print(f"  PASS: input_tokens={usage.input_tokens}")
    if hasattr(usage, 'cache_creation_input_tokens'):
        print(f"  cache_creation_input_tokens={usage.cache_creation_input_tokens}")
    if hasattr(usage, 'cache_read_input_tokens'):
        print(f"  cache_read_input_tokens={usage.cache_read_input_tokens}")
    return True


async def test_instructor_with_system_cache():
    """Test 4: Instructor + cache_control combined (the key question)."""
    import anthropic
    import instructor

    raw_client = anthropic.AsyncAnthropic()
    client = instructor.from_anthropic(raw_client)

    print("\nTest 4: Instructor + system prompt with cache_control...")

    # Instructor's from_anthropic wraps messages.create
    # We need to check if it passes through the system parameter correctly
    try:
        result = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=[
                {
                    "type": "text",
                    "text": "You are a biology classifier. Classify topics precisely.",
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {"role": "user", "content": "Classify: 'CRISPR gene editing in zebrafish embryos'"}
            ],
            response_model=SimpleClassification,
        )
        assert isinstance(result, SimpleClassification)
        print("  PASS: Instructor works with cache_control system blocks")
        print(f"  category={result.category}, confidence={result.confidence}")
        return True
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        print("  Instructor may not pass cache_control through. Use raw client for cached calls.")
        return False


async def main():
    print("=" * 60)
    print("BioTeam-AI Day 0 Spike: AsyncAnthropic + Instructor")
    print("=" * 60)

    results = {}
    results["async_instructor"] = await test_async_instructor()
    results["async_raw"] = await test_async_raw()
    results["prompt_caching"] = await test_prompt_caching()
    results["instructor_with_cache"] = await test_instructor_with_system_cache()

    print("\n" + "=" * 60)
    print("RESULTS:")
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name}")

    all_passed = all(results.values())
    critical_passed = results["async_instructor"] and results["async_raw"]

    if critical_passed:
        print("\nCONCLUSION: AsyncAnthropic + Instructor works. Use async throughout.")
    else:
        print("\nCONCLUSION: CRITICAL FAILURE. Need alternative approach.")

    if not results["instructor_with_cache"]:
        print("NOTE: cache_control may need raw client. Use LLMLayer.complete_raw for cached calls,")
        print("      LLMLayer.complete_structured (Instructor) for structured output without caching,")
        print("      or use Instructor's raw mode with manual cache_control injection.")

    return all_passed


if __name__ == "__main__":
    asyncio.run(main())
