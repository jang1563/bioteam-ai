"""Agent Registry — manages all agent instances and their health.

Design decisions:
- Singleton registry holding all agent instances
- Health tracking with degradation modes
- Critical agents (Research Director, Knowledge Manager): workflow pauses on failure
- Optional agents: workflow degrades gracefully (skip or reroute)

v5 changes:
- Added create_registry() factory function for app startup
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.models.agent import AgentSpec, AgentStatus

if TYPE_CHECKING:
    from app.agents.base import BaseAgent
    from app.llm.layer import LLMLayer
    from app.memory.semantic import SemanticMemory

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Manages all agent instances and their runtime state."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Register an agent instance."""
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> BaseAgent | None:
        """Get agent by ID."""
        return self._agents.get(agent_id)

    def get_or_raise(self, agent_id: str) -> BaseAgent:
        """Get agent by ID, raising if not found."""
        agent = self._agents.get(agent_id)
        if agent is None:
            raise KeyError(f"Agent not found: {agent_id}")
        return agent

    def list_agents(self) -> list[AgentSpec]:
        """List all registered agent specs."""
        return [a.spec for a in self._agents.values()]

    def list_statuses(self) -> list[AgentStatus]:
        """List runtime status for all agents."""
        return [a.status for a in self._agents.values()]

    def is_available(self, agent_id: str) -> bool:
        """Check if agent is available (not failed 3x)."""
        agent = self._agents.get(agent_id)
        if agent is None:
            return False
        return agent.status.state != "unavailable" and agent.status.consecutive_failures < 3

    def mark_unavailable(self, agent_id: str) -> None:
        """Mark agent as unavailable after repeated failures."""
        agent = self._agents.get(agent_id)
        if agent:
            agent.status.state = "unavailable"

    def check_critical_health(self) -> list[str]:
        """Return list of critical agents that are unhealthy.

        Critical agents: Research Director, Knowledge Manager.
        If any are unavailable, all workflows should pause.
        """
        critical_ids = ["research_director", "knowledge_manager"]
        unhealthy = []
        for cid in critical_ids:
            if not self.is_available(cid):
                unhealthy.append(cid)
        return unhealthy

    def find_substitute(self, agent_id: str) -> str | None:
        """Find a substitute agent for a failed optional agent.

        Returns None if no substitute is available.
        Used by workflow engine for graceful degradation.
        """
        agent = self._agents.get(agent_id)
        if not agent:
            return None

        # Substitution rules based on spec
        substitution_map: dict[str, list[str]] = {
            "t01_genomics": ["t02_transcriptomics"],
            "t02_transcriptomics": ["t01_genomics"],
            "t03_proteomics": ["t02_transcriptomics"],
            "t04_biostatistics": ["t05_ml_dl"],
            "t05_ml_dl": ["t04_biostatistics"],
            "t06_systems_bio": ["integrative_biologist"],
            "t07_structural_bio": [],
            "t08_scicomm": [],
            "t09_grants": [],
            "t10_data_eng": [],
            "experimental_designer": ["t04_biostatistics"],
            "integrative_biologist": ["t06_systems_bio"],
        }

        candidates = substitution_map.get(agent_id, [])
        for candidate_id in candidates:
            if self.is_available(candidate_id):
                return candidate_id
        return None


def create_registry(llm: LLMLayer, memory: SemanticMemory | None = None) -> AgentRegistry:
    """Factory: create an AgentRegistry with all known agents.

    Creates and registers:
    - ResearchDirectorAgent (strategic, critical)
    - KnowledgeManagerAgent (strategic, critical)
    - ProjectManagerAgent (infrastructure, optional)
    - TranscriptomicsAgent (domain_expert, optional)
    - DataEngineeringAgent (domain_expert, optional)
    """
    from app.agents.base import BaseAgent
    from app.agents.research_director import ResearchDirectorAgent
    from app.agents.knowledge_manager import KnowledgeManagerAgent
    from app.agents.project_manager import ProjectManagerAgent
    from app.agents.ambiguity_engine import AmbiguityEngineAgent
    from app.agents.digest_agent import DigestAgent
    from app.agents.teams.t02_transcriptomics import TranscriptomicsAgent
    from app.agents.teams.t10_data_eng import DataEngineeringAgent

    registry = AgentRegistry()

    # Load specs and create agents
    agent_defs: list[tuple[type[BaseAgent], str, dict]] = [
        (ResearchDirectorAgent, "research_director", {}),
        (KnowledgeManagerAgent, "knowledge_manager", {"memory": memory}),
        (ProjectManagerAgent, "project_manager", {}),
        (AmbiguityEngineAgent, "ambiguity_engine", {"memory": memory}),
        (DigestAgent, "digest_agent", {}),
        (TranscriptomicsAgent, "t02_transcriptomics", {}),
        (DataEngineeringAgent, "t10_data_eng", {}),
    ]

    for agent_cls, spec_id, extra_kwargs in agent_defs:
        try:
            spec = BaseAgent.load_spec(spec_id)
            agent = agent_cls(spec=spec, llm=llm, **extra_kwargs)
            registry.register(agent)
            logger.info("Registered agent: %s", spec_id)
        except Exception as e:
            logger.error("Failed to register agent %s: %s", spec_id, e)

    return registry
