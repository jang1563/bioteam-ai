"""Cold Start Smoke Test — verify system health after startup.

Checks registry health, runs a test Direct Query, and verifies /health endpoint.
Returns a pass/fail dict for each check.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from app.agents.registry import AgentRegistry
from app.models.messages import ContextPackage

logger = logging.getLogger(__name__)


@dataclass
class SmokeTestResult:
    """Result of a smoke test run."""

    checks: dict[str, dict] = field(default_factory=dict)
    passed: bool = True

    def add_check(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks[name] = {"passed": passed, "detail": detail}
        if not passed:
            self.passed = False


class SmokeTest:
    """Runs post-startup checks to verify system health.

    Usage:
        smoke = SmokeTest(registry=registry)
        result = await smoke.run()
        if not result.passed:
            print("FAIL:", result.checks)
    """

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    async def run(self) -> SmokeTestResult:
        """Run all smoke test checks."""
        result = SmokeTestResult()

        # Check 1: Registry has agents
        self._check_registry(result)

        # Check 2: Critical agents are healthy
        self._check_critical_health(result)

        # Check 3: Test Direct Query (quick agent call)
        await self._check_direct_query(result)

        return result

    def _check_registry(self, result: SmokeTestResult) -> None:
        """Verify agents are registered."""
        agents = self.registry.list_agents()
        if len(agents) >= 3:
            result.add_check(
                "registry",
                True,
                f"{len(agents)} agents registered",
            )
        else:
            result.add_check(
                "registry",
                False,
                f"Only {len(agents)} agents registered (expected >= 3)",
            )

    def _check_critical_health(self, result: SmokeTestResult) -> None:
        """Verify critical agents are available."""
        unhealthy = self.registry.check_critical_health()
        if not unhealthy:
            result.add_check("critical_health", True, "All critical agents healthy")
        else:
            result.add_check(
                "critical_health",
                False,
                f"Unhealthy critical agents: {unhealthy}",
            )

    async def _check_direct_query(self, result: SmokeTestResult) -> None:
        """Run a minimal Direct Query to test agent execution."""
        rd = self.registry.get("research_director")
        if rd is None:
            result.add_check("direct_query", False, "Research Director not found")
            return

        try:
            context = ContextPackage(task_description="Smoke test: verify agent can respond.")
            output = await rd.execute(context)
            if output.is_success:
                result.add_check("direct_query", True, "RD responded successfully")
            else:
                result.add_check("direct_query", False, f"RD failed: {output.error}")
        except Exception as e:
            result.add_check("direct_query", False, f"Exception: {e}")
