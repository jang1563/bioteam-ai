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
    - SciCommAgent (domain_expert, translation)
    - GrantWritingAgent (domain_expert, translation)
    - ExperimentalDesignerAgent (domain_expert, cross_cutting)
    - IntegrativeBiologistAgent (domain_expert, cross_cutting)
    - StatisticalRigorQA (qa, independent)
    - BiologicalPlausibilityQA (qa, independent)
    - ReproducibilityQA (qa, independent)
    """
    from app.agents.ambiguity_engine import AmbiguityEngineAgent
    from app.agents.base import BaseAgent
    from app.agents.claim_extractor import ClaimExtractorAgent
    from app.agents.data_integrity_auditor import DataIntegrityAuditorAgent
    from app.agents.digest_agent import DigestAgent
    from app.agents.experimental_designer import ExperimentalDesignerAgent
    from app.agents.integrative_biologist import IntegrativeBiologistAgent
    from app.agents.knowledge_manager import KnowledgeManagerAgent
    from app.agents.methodology_reviewer import MethodologyReviewerAgent
    from app.agents.project_manager import ProjectManagerAgent
    from app.agents.qa_agents import (
        BiologicalPlausibilityQA,
        ReproducibilityQA,
        StatisticalRigorQA,
    )
    from app.agents.research_director import ResearchDirectorAgent
    from app.agents.teams.t01_genomics import GenomicsAgent
    from app.agents.teams.t02_transcriptomics import TranscriptomicsAgent
    from app.agents.teams.t03_proteomics import ProteomicsAgent
    from app.agents.teams.t04_biostatistics import BiostatisticsAgent
    from app.agents.teams.t05_ml_dl import MachineLearningAgent
    from app.agents.teams.t06_systems_bio import SystemsBiologyAgent
    from app.agents.teams.t07_structural_bio import StructuralBiologyAgent
    from app.agents.teams.t08_scicomm import SciCommAgent
    from app.agents.teams.t09_grants import GrantWritingAgent
    from app.agents.teams.t10_data_eng import DataEngineeringAgent
    from app.config import settings

    registry = AgentRegistry()

    # Shared external clients for integrity checks.
    crossref_client = None
    pubpeer_client = None
    try:
        from app.integrations.crossref import CrossrefClient
        crossref_client = CrossrefClient(email=settings.crossref_email)
    except Exception as e:
        logger.warning("Crossref client init failed in registry: %s", e)
    try:
        from app.integrations.pubpeer import PubPeerClient
        pubpeer_client = PubPeerClient()
    except Exception as e:
        logger.warning("PubPeer client init failed in registry: %s", e)

    # Load specs and create agents — add new agents here and the count auto-updates
    agent_defs: list[tuple[type[BaseAgent], str, dict]] = [
        (ResearchDirectorAgent, "research_director", {}),
        (KnowledgeManagerAgent, "knowledge_manager", {"memory": memory}),
        (ProjectManagerAgent, "project_manager", {}),
        (AmbiguityEngineAgent, "ambiguity_engine", {"memory": memory}),
        (
            DataIntegrityAuditorAgent,
            "data_integrity_auditor",
            {
                "crossref_client": crossref_client,
                "pubpeer_client": pubpeer_client,
            },
        ),
        (DigestAgent, "digest_agent", {}),
        (GenomicsAgent, "t01_genomics", {}),
        (TranscriptomicsAgent, "t02_transcriptomics", {}),
        (ProteomicsAgent, "t03_proteomics", {}),
        (BiostatisticsAgent, "t04_biostatistics", {}),
        (MachineLearningAgent, "t05_ml_dl", {}),
        (SystemsBiologyAgent, "t06_systems_bio", {}),
        (StructuralBiologyAgent, "t07_structural_bio", {}),
        (SciCommAgent, "t08_scicomm", {}),
        (GrantWritingAgent, "t09_grants", {}),
        (DataEngineeringAgent, "t10_data_eng", {}),
        (ExperimentalDesignerAgent, "experimental_designer", {}),
        (IntegrativeBiologistAgent, "integrative_biologist", {}),
        (StatisticalRigorQA, "qa_statistical_rigor", {}),
        (BiologicalPlausibilityQA, "qa_biological_plausibility", {}),
        (ReproducibilityQA, "qa_reproducibility", {}),
        (ClaimExtractorAgent, "claim_extractor", {}),
        (MethodologyReviewerAgent, "methodology_reviewer", {}),
    ]

    for agent_cls, spec_id, extra_kwargs in agent_defs:
        try:
            spec = BaseAgent.load_spec(spec_id)
            agent = agent_cls(spec=spec, llm=llm, **extra_kwargs)
            registry.register(agent)
            logger.info("Registered agent: %s", spec_id)
        except Exception as e:
            logger.error("Failed to register agent %s: %s", spec_id, e)

    registry._expected_count = len(agent_defs)
    return registry
