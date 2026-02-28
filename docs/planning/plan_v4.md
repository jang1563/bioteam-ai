# BioTeam-AI — Implementation Plan v4.2

## Context

JangKeun Kim (Weill Cornell Medicine) is building a personal AI Science Team for biology research. The system provides a dashboard for directing specialized AI agent teams through research workflows. This plan merges:

1. **BioTeam-AI Proposal** (BioTeam-AI_Proposal.docx) — Ambiguity Resolution Engine, RCMXT Evidence Scoring, Negative Results Integration Module
2. **Implementation planning session** — practical tech stack, 10 specialist teams, dashboard design
3. **v1 Critical Review** — 11 issues identified and resolved
4. **v2 Multi-Perspective Review** — 6 expert perspectives, 21 actionable findings incorporated
5. **v3 Critical Review** — 3 parallel deep analyses: 53 raw issues → 34 unique → 3 blockers + 5 critical + 15 major + 6 minor *(NEW in v4)*
6. **Resource Research** — 30+ curated tools, libraries, and patterns (see `resources_guide.md`) *(NEW in v4)*
7. **Researcher Feedback Review** — 3-perspective analysis (Trust, UX, Publication) → 22 unique issues → 6 CRITICAL, 9 HIGH, 7 MEDIUM *(NEW in v4.2)*

Key differentiator: biology-aware epistemology that handles contradictions, negative results, and context-dependent truth.

### v3 → v4 Changelog

| # | Change | Source | Severity |
|---|--------|--------|----------|
| 1 | **Anthropic Client SDK + Instructor** replaces Claude Agent SDK | B1 (BLOCKER) | Architecture |
| 2 | **Docker Compose local-only** deployment (Vercel deferred to Phase 4) | B2 (BLOCKER) | Architecture |
| 3 | **Phase 1 W1 reduced** — skip CONTRADICTION MAP and RCMXT scoring | B3 (BLOCKER) | Roadmap |
| 4 | **Provenance tagging** prevents circular reasoning amplification | C1 (CRITICAL) | Data integrity |
| 5 | **RCMXT distribution monitoring** detects score hedging | C2 (CRITICAL) | Scoring |
| 6 | **State transition table** with guard conditions | C3 (CRITICAL) | Workflow engine |
| 7 | **Per-agent checkpointing** with idempotency tokens | C4 (CRITICAL) | Reliability |
| 8 | **DataRegistry + Evidence types** defined as Pydantic models | C5 (CRITICAL) | Data models |
| 9 | **Agent count corrected: 18** (was "15") | M1 (MAJOR) | Documentation |
| 10 | **asyncio.gather(return_exceptions=True)** replaces TaskGroup | M2 (MAJOR) | Orchestration |
| 11 | **Direct Query 2-type classification** (simplified) | M3 (MAJOR) | Direct Query |
| 12 | **input_mapper type signature** defined | M4 (MAJOR) | Workflow engine |
| 13 | **ChromaDB dedup** via content-addressed DOI/PMID hashing | M5 (MAJOR) | Memory |
| 14 | **Week 1-2 scope** reduced (defer backup + CostTracker to Week 3) | M14 (MAJOR) | Roadmap |
| 15 | **Prompt caching** strategy for 90% cost reduction | Resources | Cost |
| 16 | **Semantic Scholar API** added alongside PubMed | Resources | Literature |
| 17 | **Biopython** for PubMed access (replaces raw HTTP) | Resources | Literature |
| 18 | **sse-starlette** for production SSE | Resources | Real-time |
| 19 | **React Flow** for workflow visualization | Resources | Dashboard |
| 20 | **Singleton agent degradation modes** defined | M15 (MAJOR) | Reliability |
| 21 | **SSE event schema** defined | M8 (MAJOR) | Real-time |
| 22 | **Drill-down interaction** — click agents/workflows for detail + instruction | UX Review | Dashboard |
| 23 | **AgentDetailSheet + WorkflowDetailSheet** — shadcn/ui Sheet components | UX Review | Dashboard |
| 24 | **API endpoints defined** for agent detail, workflow detail, instruction injection | UX Review | API |

### v4 → v4.2 Changelog *(NEW)*

Source: Researcher Feedback Review — 3 parallel deep analyses from perspectives of (1) skeptical postdoc (trust/verification), (2) PI running a lab (workflow/UX), (3) journal editor/reviewer (publication rigor). 38 total issues → 22 unique after dedup → 6 CRITICAL, 9 HIGH, 7 MEDIUM.

| # | Change | Source | Severity | Code Changed |
|---|--------|--------|----------|-------------|
| 25 | **LLMLayer temperature parameter** (default 0.0 for reproducibility) | Trust/Pub | CRITICAL | `config.py`, `layer.py` |
| 26 | **LLMResponse metadata** auto-captured from every API call (model_version, tokens, cost) | Trust/Pub | CRITICAL | `layer.py`, `mock_layer.py` |
| 27 | **Evidence.verbatim_quote** anchors claims to source text | Trust | CRITICAL | `evidence.py` |
| 28 | **CitationValidator** — deterministic post-processing cross-references synthesis citations against search results | Trust | CRITICAL | `engines/citation_validator.py` (NEW) |
| 29 | **SessionManifest** — auto-generated reproducibility metadata per workflow run | Pub | CRITICAL | `evidence.py` |
| 30 | **PRISMAFlow** — auto-generated PRISMA flow diagram data for W1 | Pub | CRITICAL | `evidence.py` |
| 31 | **NegativeResult verification tracking** (verified_by, verification_status) | Trust | HIGH | `negative_result.py` |
| 32 | **ContradictionEntry multi-label** — types changed from str to list[str] | Pub | HIGH | `evidence.py` |
| 33 | **DirectorNote structured actions** (ADD_PAPER, EXCLUDE_PAPER, MODIFY_QUERY, etc.) | UX | HIGH | `workflow.py` |
| 34 | **WorkflowInstance.seed_papers** — researcher-provided DOIs | UX | HIGH | `workflow.py` |
| 35 | **SemanticMemory.search_literature()** — restricts to literature collection by default | Trust | HIGH | `semantic.py` |
| 36 | **SemanticMemory.search_all()** — cross-collection search with provenance tagging | Trust | HIGH | `semantic.py` |
| 37 | **BaseAgent.build_output(llm_response=)** — auto-propagates model_version from LLMResponse | Trust/Pub | HIGH | `base.py` |
| 38 | **Export models** — BibTeX + Markdown export with AI disclosure | UX/Pub | HIGH | `evidence.py` |
| 39 | **AI Disclosure templates** — auto-generated statements for manuscripts | Pub | MEDIUM | `evidence.py` |
| 40 | **Cold Start Quick Start mode** — bypass full protocol, try Direct Query immediately | UX | HIGH | (deferred to implementation) |

---

## Design Principles

1. **Biology ≠ SWE** — Context-dependent truth. Every claim gets an RCMXT confidence vector, not true/false.
2. **Multi-agent is not always better** (Google 180-experiment study) — Research Director decides single vs. multi-agent per task.
3. **QA must be structurally independent** — QA agents report directly to Director, never subordinate to teams they review.
4. **Memory is infrastructure** (NTT AI Constellation) — Episodic + semantic memory prevents rediscovery.
5. **Negative results are first-class data** — Publication bias hides 85% of failures; the system must mine them.
6. **Bidirectional iteration** — Every workflow loops back; no unidirectional pipelines.
7. **Schema-enforced outputs** — All agent outputs validated via Instructor + Pydantic.
8. **Cost-aware execution** — Model tier per agent; token budgets per workflow; prompt caching.
9. **Code generation, not code execution** — Agents produce code; Docker sandbox executes.
10. **Progressive complexity** — Start minimal (asyncio, SQLite, 3 panels), scale up only when needed.
11. **Ship research value early** — Every phase delivers a usable standalone capability.
12. **Provenance is mandatory** — Every piece of data is tagged with its origin to prevent circular reasoning. *(NEW in v4)*
13. **Reproducibility by default** — temperature=0.0, model_version tracked, SessionManifest auto-generated. Every workflow run can be audited. *(NEW in v4.2)*
14. **Trust through transparency** — CitationValidator verifies sources, verbatim_quote anchors claims, PRISMA flow tracks inclusion/exclusion. Researchers should never wonder "where did the AI get this?" *(NEW in v4.2)*

---

## Three-Tier Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DASHBOARD (Next.js 15)                         │
│  Phase 1: Mission Control │ Projects │ Lab KB                    │
│  Phase 2+: + Teams │ Quality │ Evidence │ Knowledge │ Analytics  │
│  Visualization: React Flow (workflow graphs)                     │
└────────────────────────────┬────────────────────────────────────┘
                             │ SSE (sse-starlette) + REST (/api/v1/)
┌────────────────────────────┴────────────────────────────────────┐
│                    FASTAPI BACKEND                               │
│  REST API │ SSE Hub │ Background Tasks                           │
│  Deployment: Docker Compose (local-only, Phase 1-3)              │
├─────────────────────────────────────────────────────────────────┤
│  LLM Layer:                                                      │
│  Anthropic Client SDK (client.messages.create)                   │
│  + Instructor (structured output + validation + retries)         │
│  + Prompt Caching (system prompts, tool defs, research briefs)   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ═══════════ TIER 1: STRATEGIC LAYER ═══════════                │
│                                                                  │
│  ┌──────────────┐  ┌──────────────────┐  ┌───────────────┐      │
│  │   Director    │  │ Research Director │  │   Project     │      │
│  │   (Human)     │◄►│ (Opus: synth)    │◄►│   Manager     │      │
│  └──────────────┘  │ (Sonnet: route)   │  │   (Haiku)     │      │
│                     └────────┬─────────┘  └───────────────┘      │
│                              │                                    │
│       ┌──────────────────────┤  Direct Query mode:               │
│       │                      │  simple_query → 1 specialist      │
│       │                      │  needs_workflow → route to W1-W6  │
│       │                      │                                    │
│  ┌────┴───────────────────────────────────────────────────┐      │
│  │        CORE ENGINES (hybrid: code + LLM)                │      │
│  │  ┌─────────────────┐  ┌──────────────────────────┐      │      │
│  │  │ Ambiguity Engine │  │ Negative Results Module  │      │      │
│  │  │ Code: metadata   │  │ Code: pattern matching,  │      │      │
│  │  │   extraction,    │  │   API queries, diffing   │      │      │
│  │  │   DB queries     │  │ LLM: interpretation,     │      │      │
│  │  │ LLM: classif,   │  │   implication extraction  │      │      │
│  │  │   resolution     │  │   (Sonnet)               │      │      │
│  │  │   hypotheses     │  └──────────────────────────┘      │      │
│  │  │   (Sonnet)       │                                    │      │
│  │  └─────────────────┘                                     │      │
│  │  ┌─────────────────┐                                     │      │
│  │  │ Knowledge Mgr   │  Semantic: ChromaDB (dedup by DOI)  │      │
│  │  │ (Sonnet)         │  Episodic: SQLite (WAL mode)        │      │
│  │  │                  │  Literature: PubMed (Biopython) +   │      │
│  │  │                  │    Semantic Scholar + bioRxiv/medRxiv│      │
│  │  └─────────────────┘                                     │      │
│  └──────────────────────────────────────────────────────────┘      │
│                                                                    │
│  ═══════════ TIER 2: DOMAIN EXPERT LAYER ═══════════             │
│                                                                    │
│  Cross-cutting:                                                    │
│  ┌──────────────────────┐  ┌──────────────────────┐               │
│  │ Experimental Designer │  │ Integrative Biologist │               │
│  │ (Sonnet)              │  │ (Sonnet)              │               │
│  └──────────────────────┘  └──────────────────────┘               │
│                                                                    │
│  Specialists (all Sonnet):                                         │
│  [1] Genomics    [4] BioStats    [8] SciComm                      │
│  [2] Transcrip   [5] ML/DL       [9] Grants (Opus)                │
│  [3] Proteomics  [6] Systems Bio  [10] Data Eng (Haiku)            │
│                  [7] Struct Bio                                     │
│                                                                    │
│  ═══════════ TIER 3: QA LAYER (Independent) ═══════════          │
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐        │
│  │ Statistical   │  │ Biological   │  │ Reproducibility   │        │
│  │ Rigor (Sonnet)│  │ Plausibility │  │ & Standards       │        │
│  │               │  │ (Sonnet)     │  │ (Haiku)           │        │
│  └──────────────┘  └──────────────┘  └──────────────────┘        │
│                                                                    │
├────────────────────────────────────────────────────────────────────┤
│  INFRASTRUCTURE (grows with phases)                                │
│  Phase 1: SQLite (WAL) │ ChromaDB │ Langfuse │ asyncio            │
│  Phase 2: + Redis │ Celery │ Docker Sandbox                       │
│  Phase 4: + HPC Runner │ PostgreSQL (optional) │ Vercel (optional)│
│  Always:  /health endpoint │ daily backups │ .env secrets          │
└────────────────────────────────────────────────────────────────────┘
```

---

## RESOLVED: LLM Layer Architecture *(v4 — was BLOCKER B1)*

### The Problem (v3)

v3 specified "Claude Agent SDK" as the agent runtime. The Agent SDK wraps the Claude Code CLI — it spawns a subprocess, provides file-system tools (Read/Write/Bash), and runs autonomous multi-turn sessions. This is architecturally wrong for BioTeam-AI because:
- Each `query()` creates an uncontrollable autonomous session
- Cost per call is unpredictable (multi-turn internally)
- No fine-grained model tier control
- Requires Node.js as a hidden dependency

### The Solution (v4)

Use the **Anthropic Client SDK** (`pip install anthropic`) with **Instructor** (`pip install instructor`) for structured outputs.

```python
# backend/app/llm/adapter.py
import anthropic
import instructor
from pydantic import BaseModel
from typing import Literal

# Model ID mapping
MODEL_MAP = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-5-20250929",
    "haiku": "claude-haiku-4-5-20251001",
}

# Initialize Instructor-wrapped client
raw_client = anthropic.Anthropic()
client = instructor.from_anthropic(raw_client)

class LLMLayer:
    """All agent LLM calls go through this layer."""

    def __init__(self):
        self.raw_client = anthropic.Anthropic()
        self.client = instructor.from_anthropic(self.raw_client)

    async def complete_structured(
        self,
        messages: list[dict],
        model_tier: Literal["opus", "sonnet", "haiku"],
        response_model: type[BaseModel],
        system: str | None = None,
        max_tokens: int = 4096,
        max_retries: int = 2,
    ) -> BaseModel:
        """Structured output with Pydantic validation + auto-retry."""
        return self.client.messages.create(
            model=MODEL_MAP[model_tier],
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            response_model=response_model,
            max_retries=max_retries,
        )

    async def complete_raw(
        self,
        messages: list[dict],
        model_tier: Literal["opus", "sonnet", "haiku"],
        system: str | None = None,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> anthropic.types.Message:
        """Raw completion for free-text or tool-use scenarios."""
        kwargs = {
            "model": MODEL_MAP[model_tier],
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        return self.raw_client.messages.create(**kwargs)

    async def complete_with_tools(
        self,
        messages: list[dict],
        model_tier: Literal["opus", "sonnet", "haiku"],
        system: str,
        tools: list[dict],
        max_iterations: int = 10,
    ) -> list[dict]:
        """Agentic tool-use loop (~30 lines)."""
        conversation = list(messages)
        results = []
        for _ in range(max_iterations):
            response = await self.complete_raw(
                messages=conversation,
                model_tier=model_tier,
                system=system,
                tools=tools,
            )
            if response.stop_reason == "end_turn":
                results.append(response)
                break
            if response.stop_reason == "tool_use":
                # Extract tool calls, execute, append results
                tool_results = await self._execute_tools(response)
                conversation.append({"role": "assistant", "content": response.content})
                conversation.append({"role": "user", "content": tool_results})
                results.append(response)
        return results

    async def _execute_tools(self, response) -> list[dict]:
        """Execute tool calls from response. Agent-specific tool registry."""
        # Implementation: look up tool in agent's registry, execute, return result
        ...
```

### Prompt Caching Strategy *(NEW in v4)*

Prompt caching reduces input token cost by 90% for repeated content. Critical for 18 agents sharing large system prompts.

```python
# Prompt caching with Anthropic API
# Cache breakpoints on: system prompt, tool definitions, research brief

response = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=4096,
    system=[
        {
            "type": "text",
            "text": agent_system_prompt,        # 1000-2000 tokens
            "cache_control": {"type": "ephemeral"}  # Cache for 5 min
        }
    ],
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": research_brief,      # Shared context across agents
                    "cache_control": {"type": "ephemeral"}
                },
                {
                    "type": "text",
                    "text": specific_task         # Unique per call
                }
            ]
        }
    ]
)

# Cost impact:
# Without caching: 18 agents × ~2000 system tokens × $3/M = $0.108/workflow
# With caching: first call full price, subsequent 17 calls at $0.30/M = ~$0.016/workflow
# Savings: ~85% on system prompt tokens
```

### MockLLMLayer for Testing

```python
class MockLLMLayer(LLMLayer):
    """Returns predefined responses for testing without API calls."""
    def __init__(self, responses: dict[str, BaseModel]):
        self.responses = responses

    async def complete_structured(self, messages, model_tier, response_model, **kwargs):
        key = f"{model_tier}:{response_model.__name__}"
        if key in self.responses:
            return self.responses[key]
        # Return a default instance with all fields populated
        return response_model.model_construct()
```

**Benefits over v3 (Agent SDK):**
- Single API call per agent step (predictable cost)
- Full control over model tier, system prompt, output schema
- Pure Python (no Node.js dependency)
- Instructor handles validation + retry automatically
- Prompt caching reduces cost by ~85%
- Mock layer enables testing without API calls

---

## NEW: Mission Control Drill-Down Interaction *(v4)*

### Design: Click-to-Inspect with Side Panel

All agents and workflows in Mission Control are clickable. Clicking opens a shadcn/ui `Sheet` (right slide-over panel, ~450px) that preserves the Mission Control view underneath.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Mission Control (always visible)          │ Sheet Panel (450px)         │
│                                           │                             │
│ ┌─ Agent Grid ─────────────────────┐      │ ┌─ AgentDetailSheet ──────┐ │
│ │ [Research Dir ●] [PM ○] [KM ●]   │      │ │ Research Director       │ │
│ │ [T1 ○] [T2 ●] [T3 ○] ...        │─click─│ │ Model: Opus/Sonnet dual │ │
│ └──────────────────────────────────┘      │ │ Status: BUSY (W1)       │ │
│                                           │ │ Current: SYNTHESIZE step │ │
│ ┌─ Active Workflows ──────────────┐      │ │                          │ │
│ │ W1: Spaceflight anemia  RUNNING  │      │ │ Capabilities:            │ │
│ │ W2: cfRNA biomarker     WAITING  │─click─│ │ • Routing (Sonnet)      │ │
│ │ W3: DEG analysis        RUNNING  │      │ │ • Synthesis (Opus)       │ │
│ └──────────────────────────────────┘      │ │ • Task decomposition     │ │
│                                           │ │                          │ │
│ ┌─ Activity Feed ─────────────────┐      │ │ [View in Workflow]       │ │
│ │ 14:31 KM found 12 papers...     │─click─│ │ [Direct Query to Agent] │ │
│ │ 14:28 W2 awaiting approval...   │      │ └──────────────────────────┘ │
│ └──────────────────────────────────┘      │                             │
└──────────────────────────────────────────────────────────────────────────┘
```

### Phase 1: Read-Only Drill-Down (Week 5)

**AgentDetailSheet** — Click any agent cell:
- Agent name, model tier, status (idle/busy/active)
- Capabilities: tools, MCP access (from AgentSpec YAML)
- Current task: linked workflow + step (if busy)
- Role description (from system prompt summary)
- No history (insufficient data in Phase 1), no instruction sending

**WorkflowDetailSheet** — Click any workflow row:
- Pipeline progress visualization (mini version of Workflow Tracker)
- Per-step status with expandable outputs (click step → see AgentOutput summary)
- Budget progress bar with per-step cost breakdown
- Loop counter
- Intervention actions: Continue, Inject Note, Pause, Cancel (same as existing spec)

### Phase 2: Interactive Drill-Down (Week 9)

**AgentDetailSheet additions:**
- Execution history (last 20 runs, from Langfuse traces)
- Cost-per-agent summary (total spend, avg cost per call)
- Success/failure rate
- "Direct Query to Agent" button — bypasses Research Director routing

**WorkflowDetailSheet additions:**
- Step detail: click any step → full AgentOutput display (structured data, not just summary)
- "Modify Parameters" form for WAITING_HUMAN steps (e.g., change search terms)
- Activity feed items clickable → opens relevant agent or workflow sheet

### Instruction Injection (All via Workflow Engine)

```python
class WorkflowInstance(BaseModel):
    # ... existing fields ...
    injected_notes: list[DirectorNote] = []  # (v4: NEW)

class DirectorNote(BaseModel):
    text: str
    target_step: str | None     # None = next step
    injected_at: datetime

# Workflow engine includes notes in ContextPackage:
def build_context(self, step: WorkflowStep, instance: WorkflowInstance) -> ContextPackage:
    relevant_notes = [n for n in instance.injected_notes
                      if n.target_step is None or n.target_step == step.id]
    return ContextPackage(
        task_description=step.task,
        constraints={
            "budget_remaining": instance.budget_remaining,
            "director_notes": [n.text for n in relevant_notes],  # Injected here
        },
        ...
    )
```

**Key principle:** No separate agent communication channel. All instructions go through the workflow engine via `injected_notes` → `ContextPackage.constraints.director_notes`.

### API Endpoints for Drill-Down *(v4: NEW)*

```
# Agent endpoints
GET  /api/v1/agents                          # List all agents with status
GET  /api/v1/agents/{agent_id}               # Full detail (spec, status, current task)
GET  /api/v1/agents/{agent_id}/history       # Execution history (Phase 2)
POST /api/v1/agents/{agent_id}/query         # Direct Query to specific agent (Phase 2)

# Workflow detail endpoints
GET  /api/v1/workflows/{workflow_id}         # Full state including step_history
GET  /api/v1/workflows/{workflow_id}/steps/{step_id}  # Specific step output
POST /api/v1/workflows/{workflow_id}/intervene        # Pause/resume/cancel/inject note
POST /api/v1/workflows/{workflow_id}/steps/{step_id}/modify  # Modify params (Phase 2)
```

---

## Direct Query Mode *(v3, simplified in v4)*

### v4 Change: 2-Type Classification (was 3-type in v3)

```
┌──────────────────────────────────────────────────────────────┐
│                    DIRECT QUERY MODE                          │
│                                                               │
│  Research Director (Sonnet-tier for routing):                 │
│  Classify: simple_query | needs_workflow                      │
│                                                               │
│  If simple_query:                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │ Knowledge    │ →  │ Specialist   │ →  │ Response     │     │
│  │ Manager      │    │ (1 agent)    │    │ (SSE push)   │     │
│  │ (memory +    │    │              │    │              │     │
│  │  literature) │    │              │    │              │     │
│  └─────────────┘    └──────────────┘    └──────────────┘     │
│  ~1-3 LLM calls, < $0.50, < 30 seconds                       │
│                                                               │
│  If needs_workflow:                                            │
│  → Route to appropriate W1-W6 with explanation to Director    │
│                                                               │
│  Classification (Pydantic-enforced):                          │
│  class QueryClassification(BaseModel):                        │
│      type: Literal["simple_query", "needs_workflow"]          │
│      reasoning: str                                           │
│      target_agent: str | None      # For simple_query         │
│      workflow_type: str | None     # For needs_workflow       │
│                                                               │
│  Heuristics:                                                   │
│  - Single entity lookup → simple_query                        │
│  - "What is X?" / "Is X true?" → simple_query                │
│  - "Compare X across Y" → needs_workflow (W1)                │
│  - "Analyze dataset Z" → needs_workflow (W3)                 │
└──────────────────────────────────────────────────────────────┘
```

---

## Workflow Engine Architecture *(v3, enhanced in v4)*

### State Machine Design

```
WorkflowInstance {
    id: str
    template: W1 | W2 | W3 | W4 | W5 | W6
    state: PENDING | RUNNING | PAUSED | WAITING_HUMAN |
           COMPLETED | FAILED | CANCELLED | OVER_BUDGET
    current_step: str
    step_history: list[StepResult]
    checkpoint: bytes | None
    loop_count: dict[str, int]
    max_loops: int = 3
    budget_remaining: float
    created_at, updated_at: datetime
}
```

### RESOLVED: State Transition Table *(v4 — was CRITICAL C3)*

```
┌────────────────────────────────────────────────────────────────────┐
│                   STATE TRANSITION TABLE                            │
├──────────────┬───────────────────┬─────────────────────────────────┤
│ From State   │ To State          │ Guard Condition                 │
├──────────────┼───────────────────┼─────────────────────────────────┤
│ PENDING      │ RUNNING           │ Director starts workflow        │
│ PENDING      │ CANCELLED         │ Director cancels before start   │
├──────────────┼───────────────────┼─────────────────────────────────┤
│ RUNNING      │ RUNNING           │ Step completes, next step begins│
│ RUNNING      │ PAUSED            │ Director clicks Pause           │
│ RUNNING      │ WAITING_HUMAN     │ Human checkpoint reached        │
│ RUNNING      │ WAITING_HUMAN     │ QA agent rejects output         │
│ RUNNING      │ OVER_BUDGET       │ budget_remaining < next_step    │
│ RUNNING      │ FAILED            │ Agent fails 3x after retry      │
│ RUNNING      │ COMPLETED         │ Final step succeeds             │
│ RUNNING      │ CANCELLED         │ Director cancels mid-run        │
├──────────────┼───────────────────┼─────────────────────────────────┤
│ PAUSED       │ RUNNING           │ Director clicks Resume          │
│ PAUSED       │ CANCELLED         │ Director cancels while paused   │
├──────────────┼───────────────────┼─────────────────────────────────┤
│ WAITING_HUMAN│ RUNNING           │ Director approves / modifies    │
│ WAITING_HUMAN│ CANCELLED         │ Director cancels                │
│ WAITING_HUMAN│ PAUSED            │ 24h timeout, auto-pause + notify│
├──────────────┼───────────────────┼─────────────────────────────────┤
│ OVER_BUDGET  │ RUNNING           │ Director approves overage       │
│ OVER_BUDGET  │ CANCELLED         │ Director cancels                │
│ OVER_BUDGET  │ RUNNING           │ Director skips remaining steps  │
├──────────────┼───────────────────┼─────────────────────────────────┤
│ FAILED       │ RUNNING           │ Director retries with new params│
│ FAILED       │ CANCELLED         │ Director abandons               │
├──────────────┼───────────────────┼─────────────────────────────────┤
│ COMPLETED    │ (terminal)        │ No transitions out              │
│ CANCELLED    │ (terminal)        │ No transitions out              │
└──────────────┴───────────────────┴─────────────────────────────────┘

Illegal transitions (enforced by engine):
- COMPLETED → anything
- CANCELLED → anything
- PENDING → PAUSED (must start first)
- PENDING → OVER_BUDGET (no cost yet)
- Any state → PENDING (no backward to initial)
```

### Step Definition *(v4: input_mapper typed)*

```python
class WorkflowStep(BaseModel):
    id: str                                # e.g., "SEARCH"
    agent_id: str | list[str]              # Single or parallel
    input_mapper: Callable[[list[StepResult]], ContextPackage]  # (v4: typed)
    output_schema: type[BaseModel]
    next_step: str | Callable[[StepResult], str]  # Static or conditional
    is_parallel: bool = False
    is_human_checkpoint: bool = False
    is_loop_point: bool = False
    loop_condition: Callable[[StepResult], bool] | None = None
    estimated_cost: float
    idempotency_key: str | None = None     # (v4: for checkpoint resumption)
```

### RESOLVED: Per-Agent Checkpointing *(v4 — was CRITICAL C4)*

```python
class StepCheckpoint(BaseModel):
    """Checkpoint for resuming parallel steps after crash."""
    workflow_id: str
    step_id: str
    agent_id: str
    status: Literal["pending", "running", "completed", "failed"]
    result: AgentOutput | None
    idempotency_token: str          # Unique per agent+step+attempt
    started_at: datetime | None
    completed_at: datetime | None

# Crash recovery logic:
# 1. On crash during parallel step (4 of 7 agents done):
#    - Load all StepCheckpoints for this step
#    - Skip agents with status="completed" (reuse their results)
#    - Re-run only agents with status="pending" or "running"
# 2. Idempotency tokens prevent duplicate work
# 3. SQLite WAL mode ensures atomic checkpoint writes
```

### Execution: asyncio.gather *(v4 — was MAJOR M2)*

```python
# Phase 1: AsyncWorkflowRunner
async def run_parallel_step(
    self,
    step: WorkflowStep,
    agents: list[str],
    context: ContextPackage,
    semaphore: asyncio.Semaphore,
) -> list[AgentOutput]:
    """Run multiple agents in parallel with partial failure support."""

    async def run_one(agent_id: str) -> AgentOutput:
        async with semaphore:  # Limit concurrency (e.g., 5)
            checkpoint = self._create_checkpoint(agent_id, step.id)
            try:
                result = await self.agent_registry.get(agent_id).run(context)
                checkpoint.status = "completed"
                checkpoint.result = result
                self._save_checkpoint(checkpoint)
                return result
            except Exception as e:
                checkpoint.status = "failed"
                self._save_checkpoint(checkpoint)
                return AgentOutput(error=str(e), agent_id=agent_id)

    # gather with return_exceptions=True — partial failure supported
    results = await asyncio.gather(
        *[run_one(a) for a in agents],
        return_exceptions=True,
    )

    # Classify results: successes vs failures
    successes = [r for r in results if isinstance(r, AgentOutput) and not r.error]
    failures = [r for r in results if isinstance(r, Exception) or (isinstance(r, AgentOutput) and r.error)]

    if not successes:
        raise AllAgentsFailedError(step.id, failures)

    # Partial success: log warnings, continue with available results
    if failures:
        self._log_partial_failures(step.id, failures)

    return successes
```

### RESOLVED: SSE Event Schema *(v4 — was MAJOR M8)*

```python
class SSEEvent(BaseModel):
    """All SSE events follow this schema."""
    event_type: Literal[
        "workflow.started",
        "workflow.step_started",
        "workflow.step_completed",
        "workflow.step_failed",
        "workflow.paused",
        "workflow.waiting_human",
        "workflow.over_budget",
        "workflow.completed",
        "workflow.failed",
        "workflow.cancelled",
        "agent.token_stream",       # For real-time LLM output
        "system.health_changed",
        "system.cost_alert",
    ]
    workflow_id: str | None
    step_id: str | None
    agent_id: str | None
    payload: dict                   # Event-specific data
    timestamp: datetime

# Example events:
# {"event_type": "workflow.step_completed", "workflow_id": "w1_abc",
#  "step_id": "SEARCH", "agent_id": "knowledge_manager",
#  "payload": {"papers_found": 47, "cost": 0.12}, "timestamp": "..."}

# {"event_type": "workflow.over_budget", "workflow_id": "w1_abc",
#  "payload": {"budget_remaining": 0.50, "next_step_cost": 1.20,
#              "actions": ["approve_overage", "cancel", "skip"]},
#  "timestamp": "..."}
```

### Budget Enforcement

Pre-step: estimate cost, check budget_remaining. If insufficient: state → OVER_BUDGET, SSE alert. Director can: (a) approve overage, (b) cancel, (c) skip step.

### Loop Detection

Each loop_point tracks iteration count. If `loop_count[step_id] >= max_loops`: force proceed + warn. Director can override max_loops from dashboard.

### Human Intervention

Triggered at `is_human_checkpoint` steps, and also by: OVER_BUDGET, agent failure (3x retry), QA rejection. Dashboard shows: current state, outputs so far, action menu (continue, modify, skip, cancel, inject note). Timeout: 24h → auto-pause with notification.

---

## RESOLVED: Data Models *(v4 — was CRITICAL C5)*

### Evidence Types (were undefined in v3)

```python
# backend/app/models/evidence.py

class Evidence(BaseModel):
    """A single piece of evidence from literature or internal sources."""
    id: str                         # UUID
    claim: str                      # The assertion this evidence supports
    source_doi: str | None          # DOI if from published paper
    source_pmid: str | None         # PubMed ID
    source_type: Literal[           # (v4: provenance tagging for C1)
        "primary_literature",       # Published paper
        "preprint",                 # bioRxiv/medRxiv
        "internal_synthesis",       # Agent-generated synthesis
        "lab_kb",                   # Manual lab entry
        "clinical_trial",          # ClinicalTrials.gov
    ]
    text: str                       # The relevant excerpt or summary
    organism: str | None            # Species
    cell_type: str | None
    condition: str | None           # Experimental condition
    sample_size: int | None
    methodology: str | None
    findings: list[str]
    created_at: datetime
    created_by: str                 # Agent ID or "human"

class DataRegistry(BaseModel):
    """Tracks all data files referenced by the system."""
    id: str
    name: str
    file_path: str                  # Local or HPC path
    file_type: Literal["csv", "tsv", "h5ad", "fastq", "bam", "vcf", "other"]
    organism: str | None
    data_type: Literal["rnaseq", "scrnaseq", "chipseq", "atacseq",
                        "proteomics", "metabolomics", "clinical", "other"]
    sample_count: int | None
    columns: list[str] | None      # Column names for tabular data
    size_bytes: int
    checksum: str                   # SHA256
    registered_at: datetime
    registered_by: str              # "human" or agent_id
    notes: str | None
```

### RESOLVED: Provenance Tagging *(v4 — was CRITICAL C1)*

The `source_type` field on `Evidence` prevents circular reasoning:

```python
# Rule enforced by Knowledge Manager:
# When storing agent-generated synthesis → source_type = "internal_synthesis"
# When computing RCMXT R-axis (replication count):
#   - ONLY count evidence with source_type = "primary_literature" or "preprint"
#   - EXCLUDE "internal_synthesis" from replication count
#   - This prevents: Agent A synthesizes → stored → Agent B retrieves as "evidence"
#                     → stored again → single source inflated to multi-source

# ChromaDB collection separation:
COLLECTIONS = {
    "literature": "primary papers, preprints",       # Source of truth
    "synthesis": "agent-generated interpretations",   # Clearly labeled
    "lab_kb": "manually entered lab knowledge",       # Human-verified
}

# R-axis scoring:
def count_replications(claim: str, evidence: list[Evidence]) -> int:
    """Only primary literature counts toward replication."""
    primary = [e for e in evidence if e.source_type in ("primary_literature", "preprint")]
    # Group by unique research group (first author + institution)
    unique_groups = set()
    for e in primary:
        unique_groups.add(e.source_doi)  # Simplified: DOI = unique study
    return len(unique_groups)
```

### RCMXT Score Model *(enhanced in v4)*

```python
class RCMXTScore(BaseModel):
    claim: str
    R: float                        # Reproducibility (0.0-1.0)
    C: float                        # Condition Specificity
    M: float                        # Methodological Robustness
    X: float | None                 # Cross-Omics (NULL if unavailable)
    T: float                        # Temporal Stability
    composite: float | None         # Average (4 or 5 axes depending on X)
    sources: list[str]              # Evidence IDs used for scoring
    provenance: Literal["primary_literature", "internal_synthesis"]
    scored_at: datetime
    scorer_version: str             # Prompt version for traceability
    model_version: str              # e.g., "claude-sonnet-4-5-20250929"

class OmicsLayerStatus(BaseModel):
    layers_available: list[Literal["genomic", "transcriptomic", "proteomic",
                                   "metabolomic", "functional"]]
    layers_agreeing: list[str]
    layers_contradicting: list[str]
    multi_omics_available: bool     # True if ≥2 layers present
```

### RESOLVED: RCMXT Distribution Monitoring *(v4 — was CRITICAL C2)*

```python
class RCMXTMonitor:
    """Detects score hedging (all-0.5 syndrome) in production."""

    def check_distribution(self, recent_scores: list[RCMXTScore]) -> list[str]:
        """Returns list of warnings if scores appear hedged."""
        warnings = []
        for axis in ["R", "C", "M", "T"]:
            values = [getattr(s, axis) for s in recent_scores]
            if len(values) < 20:
                continue  # Need minimum sample
            std = statistics.stdev(values)
            if std < 0.10:
                warnings.append(
                    f"RCMXT {axis}-axis std={std:.3f} < 0.10 across last "
                    f"{len(values)} scores — possible hedging"
                )
            # Entropy check: scores should use the full range
            hist = Counter(round(v, 1) for v in values)
            entropy = -sum((c/len(values)) * math.log2(c/len(values))
                           for c in hist.values())
            max_entropy = math.log2(len(hist))
            if max_entropy > 0 and entropy / max_entropy < 0.5:
                warnings.append(
                    f"RCMXT {axis}-axis low entropy ({entropy:.2f}/{max_entropy:.2f})"
                    f" — scores concentrated in narrow range"
                )
        return warnings

    def production_holdout(self, known_claims: list[dict]) -> dict:
        """Monthly: score 20 known claims, compare to reference scores."""
        # known_claims: [{"claim": "...", "expected_R": 0.9, ...}, ...]
        # Returns: Pearson r per axis, drift detection
        ...
```

### ContradictionEntry Model

```python
class ContradictionEntry(BaseModel):
    """A detected contradiction between two claims."""
    id: str
    claim_a: str
    claim_b: str
    type: Literal["conditional_truth", "technical_artifact",
                  "interpretive_framing", "statistical_noise",
                  "temporal_dynamics"]
    resolution_hypotheses: list[str]
    rcmxt_a: RCMXTScore
    rcmxt_b: RCMXTScore
    discriminating_experiment: str | None
    detected_at: datetime
    detected_by: str                # Agent ID
    workflow_id: str | None
```

### NegativeResult Model

```python
class NegativeResult(BaseModel):
    """A negative result from any of the 4 data sources."""
    id: str
    claim: str                      # What was expected
    outcome: str                    # What actually happened
    conditions: dict                # Experimental conditions
    source: Literal["internal", "clinical_trial", "shadow", "preprint_delta"]
    confidence: float               # 0.0-1.0
    failure_category: Literal["protocol", "reagent", "analysis", "biological"]
    implications: list[str]         # What this means for related research
    source_id: str | None           # DOI, trial ID, or Lab KB entry ID
    organism: str | None
    created_at: datetime
    created_by: str                 # Agent ID or "human"
    # v4.2: human verification tracking
    verified_by: str | None         # human ID who verified
    verification_status: Literal["unverified", "confirmed", "rejected", "ambiguous"]
```

### v4.2: Reproducibility & Trust Models *(NEW)*

#### LLMResponse — Metadata from Every LLM Call

```python
@dataclass
class LLMResponse:
    """Returned alongside every LLM call result for reproducibility tracking."""
    model_version: str = ""         # Exact model ID from API response
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    stop_reason: str = ""
    cost: float = 0.0
    timestamp: datetime

# All LLMLayer methods return tuple[result, LLMResponse]:
result, meta = await llm.complete_structured(
    messages=[...], model_tier="sonnet", response_model=MyModel,
    temperature=0.0,  # v4.2: deterministic by default
)
# meta.model_version → "claude-sonnet-4-5-20250929" (from API response)
```

#### CitationValidator — Deterministic Source Verification

```python
class CitationValidator:
    """Cross-references synthesis citations against search results.
    No LLM calls — purely deterministic DOI/PMID/title matching.

    Usage in W1 SYNTHESIZE step:
        validator = CitationValidator()
        validator.register_sources(search_results)  # From SEARCH step
        report = validator.validate(synthesis_text)
        if not report.is_clean:
            # Flag for human review or re-run
    """
    def register_sources(self, sources: list[dict]) -> None: ...
    def validate(self, text: str) -> CitationReport: ...

class CitationReport:
    total_citations: int
    verified: int
    issues: list[CitationIssue]     # DOIs not found in search results
    verification_rate: float        # verified / total
    is_clean: bool                  # No issues found
```

#### SessionManifest — Reproducibility Metadata

```python
class SessionManifest(BaseModel):
    """Auto-generated at workflow completion. Captures every parameter
    needed to reproduce or audit a session."""
    workflow_id: str
    template: str
    query: str
    started_at: datetime
    completed_at: datetime | None

    # LLM call log
    llm_calls: list[dict]           # List of LLMResponse-like dicts
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float

    # Model versions + temperatures
    model_versions: list[str]       # Unique model IDs seen
    temperature_settings: dict[str, float]  # step_id -> temperature

    # Data provenance
    search_queries: list[str]
    databases_searched: list[str]
    papers_retrieved: list[str]     # DOIs
    seed_papers: list[str]          # User-provided DOIs

    # System version
    system_version: str
    config_snapshot: dict

    # PRISMA (for W1)
    prisma: PRISMAFlow | None
```

#### PRISMAFlow — Systematic Review Tracking

```python
class PRISMAFlow(BaseModel):
    """PRISMA-style flow diagram data for W1 Literature Review."""
    records_identified: int         # SEARCH step output
    records_from_databases: int     # PubMed + S2 + bioRxiv
    records_from_lab_kb: int
    duplicates_removed: int
    records_screened: int           # SCREEN step input
    records_excluded_screening: int
    full_text_assessed: int         # EXTRACT step input
    full_text_excluded: int
    full_text_exclusion_reasons: dict[str, int]
    studies_included: int           # Final included
    negative_results_found: int     # NR Module matches
```

#### Export Models — BibTeX, Markdown, AI Disclosure

```python
class ExportBibTeX(BaseModel):
    """BibTeX export data for cited sources."""
    entries: list[dict]             # Each: {key, type, fields}
    def render(self) -> str: ...

class ExportMarkdown(BaseModel):
    """Markdown export of a workflow report."""
    title: str
    sections: list[dict]            # {heading, content, level}
    ai_disclosure: str              # Auto-generated disclosure
    session_manifest_summary: str
    def render(self) -> str: ...
```

**AI Disclosure Template** (auto-generated for manuscripts):
> "This analysis was conducted using BioTeam-AI v{version}, a multi-agent research
> system. Literature search was performed on {date} across {databases}. All claims
> were scored using the RCMXT evidence confidence framework. LLM models used:
> {model_versions}. Full session manifest available at {manifest_url}. The authors
> take full responsibility for the scientific content and interpretation."

---

## Agent Inventory (18 LLM agents + 2 hybrid engines) *(v4: count corrected from "15")*

### Tier 1: Strategic (3 LLM agents)

| Agent | Model | Reports To | Key Function | Criticality |
|-------|-------|-----------|--------------|-------------|
| **Research Director** | Opus/Sonnet dual-mode | Director (Human) | Decompose, assign, synthesize, route | Critical (no degraded mode) |
| **Project Manager** | Haiku | Research Director | Task tracking, timeline, dashboard state | Optional (workflows still run without PM) |
| **Knowledge Manager** | Sonnet | Research Director | Semantic + episodic memory, literature, novelty | Critical (all workflows need memory) |

### Core Engines (2 hybrid: code + LLM)

| Engine | LLM Model | Key Function | Criticality |
|--------|-----------|--------------|-------------|
| **Ambiguity Resolution Engine** | Sonnet | Contradiction Mapper + RCMXT scoring | Optional in Phase 1, Critical in Phase 2+ |
| **Negative Results Module** | Sonnet | Shadow mining, preprint deltas, trial failures, lab KB | Optional (Lab KB is code-only in Phase 1) |

### Tier 2: Domain Experts (12 LLM agents)

| Agent | Model | Division | Key Function | Criticality |
|-------|-------|----------|-------------|-------------|
| **Experimental Designer** | Sonnet | Cross-cutting | Power analysis, control design, protocol specs | Optional |
| **Integrative Biologist** | Sonnet | Cross-cutting | Cross-omics interpretation, mechanism linking | Optional |
| **[1] Genomics & Epigenomics** | Sonnet | Wet-to-Dry | Variant calling, ChIP-seq, ATAC-seq | Optional |
| **[2] Transcriptomics & Single-Cell** | Sonnet | Wet-to-Dry | RNA-seq, scRNA-seq, cfRNA, DEGs | Optional |
| **[3] Proteomics & Metabolomics** | Sonnet | Wet-to-Dry | Mass spec, protein networks | Optional |
| **[4] Biostatistics** | Sonnet | Computation | Statistical methods, power analysis | Optional |
| **[5] Machine Learning & DL** | Sonnet | Computation | Predictive modeling, evaluation | Optional |
| **[6] Systems Biology & Networks** | Sonnet | Computation | GSEA, pathway analysis, GRNs | Optional |
| **[7] Structural Biology** | Sonnet | Computation | AlphaFold, docking, MD simulation | Optional |
| **[8] Scientific Communication** | Sonnet | Translation | Manuscripts, figures, reviewer responses | Optional |
| **[9] Grant Writing & Funding** | Opus | Translation | NIH/NASA/NSF proposals, specific aims | Optional |
| **[10] Data Engineering** | Haiku | Translation | Nextflow/Snakemake, Docker, HPC | Optional |

### Tier 3: QA (3 LLM agents — independent)

| Agent | Model | Reports To | Key Function | Criticality |
|-------|-------|-----------|-------------|-------------|
| **Statistical Rigor** | Sonnet | Director | MTC audit, effect sizes, overfitting | Optional |
| **Biological Plausibility** | Sonnet | Director | Pathway connectivity, artifact detection | Optional |
| **Reproducibility & Standards** | Haiku | Director | FAIR, MINSEQE/MIAME, code audit | Optional |

### RESOLVED: Singleton Agent Degradation *(v4 — was MAJOR M15)*

**Critical agents** (Research Director, Knowledge Manager): If they fail 3x, the entire workflow pauses and alerts the Director. No automatic rerouting — these are irreplaceable.

**Optional agents** (all Tier 2, Tier 3, PM): If unavailable, the workflow engine:
1. Logs the unavailability
2. Skips the agent's step (if step is optional in the workflow)
3. OR reroutes to the closest available specialist (Research Director decides)
4. Marks the workflow output as "degraded" with missing agent noted

---

## Core Innovation I: Ambiguity Resolution Engine

### Five-Category Contradiction Taxonomy

| Type | Name | Definition | Example |
|------|------|-----------|---------|
| 1 | Conditional Truth | Both correct under different conditions | Immune suppression (6-mo ISS) vs. activation (Twins Study, 1-yr) |
| 2 | Technical Artifact | Methodology difference, not biology | Salmon vs. STAR alignment → 30%+ DEG list divergence |
| 3 | Interpretive Framing | Same data, different conceptual lens | "Space anemia" vs. "adaptive erythropoietic regulation" |
| 4 | Statistical Noise | Small N + high dimensionality | p=0.049 published vs. p=0.06 in file drawer |
| 5 | Temporal Dynamics | Snapshot timing determines conclusion | Acute inflammation (day 1-3) → resolution (wk 2) → chronic (mo 6) |

### RCMXT Calibration Protocol *(v4.1: publication-grade metrics)*

**Phase A: Establish Inter-Expert Baseline**
1. Recruit 5 domain experts (lab colleagues, collaborators) — minimum 5 for reliable ICC
2. Write **annotation guidelines**: per-axis scoring rubric with 3 anchor examples (low/mid/high) each
3. Pilot round: 10 claims, refine guidelines based on disagreements, then main round
4. Each expert scores **150 well-characterized biological claims** across **3 domains** (spaceflight biology, cancer genomics, neuroscience — 50 per domain)
5. Agreement metrics (per axis):
   - **ICC(2,k)** (two-way random, average measures) — primary agreement metric
   - **Bland-Altman plots** — visualize systematic bias between rater pairs
   - **Lin's Concordance Correlation Coefficient (CCC)** — supplementary
   - **Mean Absolute Error (MAE)** — practical disagreement magnitude
   - **Cohen's weighted kappa** (after binning into low/mid/high) — categorical agreement
6. Expert disagreement adjudication: discussion round for claims with ICC < 0.5, then final independent re-score
7. This becomes the ceiling — LLM cannot be expected to exceed expert consensus

**Phase B: LLM Calibration**
1. Run RCMXT scorer on each of the 150 claims, 5 times (measure consistency)
2. Primary target: **ICC(2,1) ≥ 0.7** between LLM and expert consensus (per axis)
3. Secondary targets:
   - Intra-run std < 0.15 per axis
   - MAE < 0.15 per axis vs. expert consensus
   - Bland-Altman: no systematic bias > 0.1
4. If below threshold: adjust scoring prompt with calibration examples
5. **Cross-model comparison**: Run identical claims through GPT-4o and Gemini 2.0 (same prompts) — report ICC vs. experts for each LLM
6. **Prompt sensitivity analysis**: 3 prompt variations (rephrased rubric), measure score variance

**Phase C: X-Axis Empty-Data Handling**
- ~80-85% of literature is single-omics. X-axis must distinguish:
  1. Multi-omics data agrees → X = 0.7-1.0
  2. Multi-omics data contradicts → X = 0.0-0.3
  3. No multi-omics data available → X = NULL (not 0.5!)
- NULL X displayed as "—" in radar charts, excluded from composite score
- **Statistical analysis**: Compare 4-axis composite (X=NULL) vs. 5-axis composite distributions; test for systematic bias using Welch's t-test

**Phase D: Ablation Study (for publication)**
- **Sample size**: 150 claims (power analysis: 150 sufficient to detect medium effect size d=0.5 at α=0.05, power=0.80)
- Compare full RCMXT vs. each axis removed (5 ablations)
- **Baselines (6 total)**:
  1. GRADE framework scores (clinical evidence standard)
  2. Single-score LLM confidence (Claude, same prompt minus axis decomposition)
  3. GPT-4o single-score confidence
  4. BM25/TF-IDF evidence count (non-LLM statistical baseline)
  5. Majority vote across sources
  6. No scoring (random baseline)
- **Evaluation metric**: Downstream task performance — RCMXT-filtered evidence improves hypothesis ranking accuracy vs. unfiltered evidence (measured by expert agreement with final ranking)
- **Statistical tests**: Paired Wilcoxon signed-rank test per ablation, Bonferroni correction for 5+6=11 comparisons
- **Bootstrap 95% CI**: 1000 iterations for all reported metrics
- **Mutual information analysis**: Quantify unique information each axis contributes (justify 5 axes, not 3 or 7)

**Phase E: Production Monitoring (v4)**
- RCMXTMonitor runs on every score (see Distribution Monitoring above)
- Monthly holdout: re-score **20 known claims** (not 5), compare to reference using ICC
- Quarterly: re-calibrate if model version changes
- **Model version drift analysis**: When Claude model updates, run full 150-claim comparison and report delta

### Hybrid Implementation

```python
# Deterministic layer (no LLM)
def extract_study_metadata(paper: Paper) -> StudyMetadata:
    """Extract organism, cell_type, n, platform from structured fields."""

def count_independent_replications(claim: str, evidence: list[Evidence]) -> int:
    """Count distinct research groups. Only primary_literature + preprint sources."""

def check_omics_layers(claim: str, evidence: list[Evidence]) -> OmicsLayerStatus:
    """Check which omics layers support the claim."""

# LLM layer (Sonnet via Instructor)
async def classify_contradiction(
    evidence_a: Evidence, evidence_b: Evidence
) -> ContradictionType:
    """Instructor returns validated ContradictionType enum."""
    return await llm.complete_structured(
        messages=[{"role": "user", "content": f"Classify: {evidence_a} vs {evidence_b}"}],
        model_tier="sonnet",
        response_model=ContradictionClassification,
    )
```

---

## Core Innovation II: Negative Results Integration Module

### Four Data Sources

| Source | Maturity | Phase | Method |
|--------|----------|-------|--------|
| **Internal Lab KB** | Engineering | Phase 1 | CRUD + search. Director enters manually. |
| **Clinical Trial Failures** | Engineering | Phase 2 | ClinicalTrials.gov MCP query + LLM interpretation |
| **Shadow Literature** | R&D | Phase 3b | Constrained 30-phrase vocabulary + LLM context interpretation |
| **Preprint Deltas** | R&D | Phase 3b | bioRxiv/medRxiv API version history + text diff + LLM |

### Shadow Mining: Constrained Vocabulary

**Tier 1 — High Precision (expect >90% true positive):**
```
"we were unable to replicate", "failed to reproduce", "could not confirm",
"no statistically significant difference", "did not reach significance",
"contrary to our hypothesis", "negative result", "no effect was observed",
"the effect was not significant", "we found no evidence"
```

**Tier 2 — Moderate Precision (60-80% true positive, need LLM disambiguation):**
```
"contrary to expectations", "inconsistent with previous reports",
"results were inconclusive", "did not support the hypothesis",
"the association was not significant", "we observed no correlation",
"failed to detect", "below the detection limit",
"not reproducible across", "these findings contradict"
```

**Tier 3 — Context-Dependent (always require LLM interpretation):**
```
"limited by sample size", "the effect was modest",
"warrants further investigation", "preliminary and should be interpreted with caution",
"power was insufficient", "confounded by", "artifacts may explain",
"alternative explanation", "may be due to batch effects",
"sensitivity analysis revealed"
```

**Protocol:** Start Tier 1 only. Measure precision. If >0.85, add Tier 2. If combined >0.70, add Tier 3.

---

## Workflow Templates

### Direct Query
```
CLASSIFY (Research Director, Sonnet)
  → If simple: LOOKUP (Knowledge Manager) → ANSWER (1 Specialist) → RESPOND (SSE push)
  → If complex: ROUTE to W1-W6
```

### W1: Literature Review *(v4: Phase 1 = reduced, Phase 2 = full; v4.2: + PRISMA + CitationValidator)*

**Phase 1 (reduced — no Phase 2 dependencies):**
```
SCOPE → DECOMPOSE (Research Director, Opus)
  → SEARCH (Knowledge Manager, Sonnet + PubMed/Semantic Scholar/bioRxiv/medRxiv)
       ► Accepts seed_papers from WorkflowInstance (v4.2)
       ► PRISMAFlow.records_identified populated
  → SCREEN (Specialist, Sonnet)
       ► PRISMAFlow.records_screened, records_excluded populated
  → EXTRACT (Specialist, structured JSON output)
       ► Evidence.verbatim_quote captured for each finding (v4.2)
       ► PRISMAFlow.full_text_assessed, studies_included populated
  → NEGATIVE CHECK (NR Module: Internal Lab KB query only)
       ► PRISMAFlow.negative_results_found populated
  → SYNTHESIZE (Research Director, Opus)
       ► CitationValidator.validate() run on synthesis output (v4.2)
       ► If verification_rate < 1.0: flag unverified citations
  → NOVELTY CHECK (Knowledge Manager, Sonnet)
  → REPORT to Director via Dashboard (SSE push)
       ► Includes: PRISMAFlow, CitationReport, SessionManifest (v4.2)
       ► Export available: Markdown + BibTeX + AI Disclosure (v4.2)
  ⏸ HUMAN CHECKPOINT: after SYNTHESIZE (Director reviews before final report)
```

**Phase 2+ (full — adds contradiction mapping + RCMXT):**
```
SCOPE → DECOMPOSE → SEARCH → SCREEN → EXTRACT
  → CONTRADICTION MAP (Ambiguity Engine: code + Sonnet)
  → RCMXT SCORE (Ambiguity Engine: code + Sonnet)
  → NEGATIVE CHECK
  → SYNTHESIZE (+ CitationValidator) → NOVELTY CHECK → REPORT
  ↺ LOOP (max 3): contradictions → re-search with resolution variables
  ⏸ HUMAN CHECKPOINT: after SYNTHESIZE
```

### W2: Hypothesis Generation (Generate-Debate-Evolve)
```
CONTEXTUALIZE (Knowledge Manager + NR Module)
  → GENERATE (Teams 1-7 in parallel, Sonnet × 7)
  → NEGATIVE FILTER (NR Module)
  → DEBATE (QA Tier challenges each, Sonnet × 3)
  → RANK (Research Director, Opus: merit×0.30 + feasibility×0.25 + novelty×0.20
           + alignment×0.15 + data×0.10)
  → EVOLVE (Top 3 refined, cross-pollinated, Sonnet)
  → RCMXT PROFILE (Ambiguity Engine)
  → PRESENT to Director (SSE push)
  ↺ LOOP (max 3): Director feedback → refine → re-rank
  ⏸ HUMAN CHECKPOINT: after RANK
```

### W3: Data Analysis
```
INGEST (Data Eng, Haiku) → QC (BioStats, Sonnet + domain team)
  → PLAN (Research Director, Opus)
  ⏸ HUMAN CHECKPOINT: Director approves analysis plan
  → EXECUTE (Specialist: generate code → Code Sandbox)
  → INTEGRATE (Integrative Biologist if multi-omics, Sonnet)
  → VALIDATE (Statistical Rigor, Sonnet)
  → PLAUSIBILITY (Biological Plausibility, Sonnet)
  → INTERPRET (Systems Bio + Research Director)
  → CONTRADICTION CHECK (Ambiguity Engine vs. literature)
  → AUDIT (Reproducibility, Haiku: checklist)
  → REPORT to Director (SSE push)
  ↺ LOOP (max 3): QA findings → revise → re-validate
```

### W4: Manuscript Writing
```
OUTLINE (Research Director + Director)
  ⏸ HUMAN CHECKPOINT: Director approves outline
  → ASSEMBLE (Knowledge Manager)
  → DRAFT (parallel: SciComm + specialists, Sonnet)
  → FIGURES (SciComm, Sonnet)
  → STATISTICAL REVIEW (Statistical Rigor, Sonnet)
  → PLAUSIBILITY REVIEW (Biological Plausibility, Sonnet)
  → REPRODUCIBILITY CHECK (Reproducibility, Haiku)
  → REVISION (Research Director, Opus)
  → DIRECTOR REVIEW
  ↺ LOOP (max 5): each review cycle feeds back to drafting
```

### W5: Grant Proposal
```
OPPORTUNITY (Team 9 + Research Director, both Opus)
  → SPECIFIC AIMS (Research Director + Team 9, Opus)
  ⏸ HUMAN CHECKPOINT: Director approves specific aims
  → STRATEGY (parallel by Aim, specialists, Sonnet)
  → PRELIMINARY DATA (specialists + Knowledge Manager)
  → BUDGET (Team 9 + Project Manager, Opus + Haiku)
  → MOCK REVIEW (All 3 QA, Sonnet/Haiku)
  → REVISION → DIRECTOR REVIEW + SUBMIT
  ↺ LOOP (max 3): mock review → revise strategy
```

### W6: Ambiguity Resolution (standalone)
```
IDENTIFY CLAIM (any agent triggers)
  → EVIDENCE LANDSCAPE (Knowledge Manager, Sonnet)
  → CLASSIFY (Ambiguity Engine: code + Sonnet)
  → MINE NEGATIVES (NR Module)
  → RESOLUTION HYPOTHESES (Ambiguity Engine, Sonnet)
  → DISCRIMINATING EXPERIMENT (Experimental Designer, Sonnet)
  → PRESENT to Director with RCMXT profiles
```

---

## Issue Resolutions (v1 Review → v2, retained)

### Issue 1: Engines vs Agents — RESOLVED

Engines are **hybrid components**: deterministic code pipelines + LLM-powered interpretation steps.

| Component | Deterministic Code | LLM Call (Model) |
|-----------|-------------------|-------------------|
| **Contradiction Mapper** | Query DB for evidence, extract metadata | Classify type, generate resolution hypotheses (Sonnet) |
| **RCMXT Scorer** | Aggregate metadata, count replications, check omics | Score subjective axes (M, T), calibrate (Sonnet) |
| **Shadow Miner** | Constrained 30-phrase vocabulary matching | Interpret context, extract NegativeResult (Sonnet) |
| **Preprint Delta** | Text diff between versions | Interpret significance of changes (Sonnet) |
| **Trial Failure** | ClinicalTrials.gov API query + filtering | Interpret termination reasons (Sonnet) |
| **Internal Lab KB** | CRUD operations, search | None (purely structured data) |

### Issue 2: Division Leads — RESOLVED: Removed

Division Leads removed as agents. Research Director communicates directly with specialists. Divisions remain as organizational grouping for dashboard display.

### Issue 3: Code Execution — RESOLVED

```
Agent generates CodeBlock → Execution Router → Docker (local) / HPC (Phase 4) / Human Review
```

```python
class CodeBlock(BaseModel):
    language: Literal["python", "R"]
    code: str
    dependencies: list[str]
    expected_output: type[BaseModel]
    estimated_runtime: str
    execution_target: Literal["local", "hpc"]

class ExecutionResult(BaseModel):
    stdout: str
    stderr: str
    files_created: list[str]
    runtime_seconds: float
    exit_code: int
```

### Issue 4: Agent Communication — RESOLVED

```python
class AgentMessage(BaseModel):
    id: str
    from_agent: str
    to_agent: str
    workflow_id: str
    step: str
    payload: dict
    context_refs: list[str]
    timestamp: datetime
```

Transport: Phase 1 = sync + asyncio; Phase 2+ = + Celery/Redis.

Key rule: Agents never pass raw conversation history. They pass structured outputs via AgentMessage.

### Issue 5: Cost Controls — RESOLVED + Enhanced

**Model Tier Assignment:**

| Agent | Model | Est. Cost/Call |
|-------|-------|---------------|
| Research Director — routing | Sonnet | ~$0.05-0.10 |
| Research Director — synthesis | Opus | ~$0.50-1.00 |
| Knowledge Manager | Sonnet | ~$0.05-0.15 |
| Project Manager | Haiku | ~$0.01-0.03 |
| Specialists 1-8 | Sonnet | ~$0.05-0.15 |
| Grants (Team 9) | Opus | ~$0.50-1.00 |
| Data Engineering (Team 10) | Haiku | ~$0.01-0.05 |
| QA: Stat Rigor, Bio Plausibility | Sonnet | ~$0.05-0.15 |
| QA: Reproducibility | Haiku | ~$0.01-0.03 |
| Engine LLM calls | Sonnet | ~$0.03-0.10 |

**With prompt caching:** Repeated system prompts cost 0.1x → ~85% reduction on input tokens.

**Token Budget Per Workflow:**

| Workflow | Est. Calls | Est. Cost | Max Budget | Validation Gate |
|----------|-----------|-----------|------------|-----------------|
| Direct Query | 1-3 | $0.10-0.50 | $1 | — |
| W1 (reduced) | 6-8 | $0.50-2.00 | $5 | Phase 1 smoke test |
| W1 (full) | 8-12 | $1-3 | $5 | Phase 2 milestone |
| W2 | 15-25 | $3-8 | $15 | Phase 3a milestone |
| W3 | 10-18 | $2-5 | $10 | Phase 2 milestone |
| W4 | 20-35 | $5-15 | $25 | Phase 4 milestone |
| W5 | 25-40 | $8-20 | $30 | Phase 4 milestone |
| W6 | 6-10 | $1-3 | $5 | Phase 3a milestone |

**Cost controls:**
```python
class CostTracker:
    workflow_budgets: dict[str, float]
    session_budget: float = 50.0
    alert_threshold: float = 0.8

    def check_budget(self, workflow_id: str, estimated_cost: float) -> bool: ...
    def record_actual(self, workflow_id: str, step: str, actual_cost: float): ...
    def get_accuracy_report(self) -> CostAccuracyReport: ...
```

**Cost Validation Gate:** After each phase milestone, compare actual vs. estimated. If actual > 2x, adjust budgets and model tiers before proceeding.

### Issue 6: Role Overlaps — RESOLVED via RACI Matrix

*(RACI matrix unchanged from v2/v3 — stable)*

### Issue 7: Timeline — RESOLVED (18 weeks)

See updated Phased Roadmap below.

### Issue 8: Agent Prompt Engineering — RESOLVED

Agent spec YAML template per agent with: system_prompt, output_schema, tools, mcp_access, few_shot_examples, failure_modes, version.

### Issue 9: PubMed + Literature Access — RESOLVED *(v4: Biopython + Semantic Scholar)*

```python
# PubMed via Biopython (rate-limited, XML-parsed)
from Bio import Entrez, Medline
Entrez.email = os.getenv("NCBI_EMAIL", "your-email@example.com")
Entrez.api_key = os.getenv("NCBI_API_KEY")

# Semantic Scholar (citation graphs, semantic search)
from semanticscholar import SemanticScholar
sch = SemanticScholar(api_key=os.getenv("S2_API_KEY"))
```

Available integrations:
- **PubMed** (Biopython — Bio.Entrez) — primary literature
- **Semantic Scholar** (Python client) — citation graphs, semantic search, SPECTER2 embeddings *(NEW in v4)*
- **bioRxiv/medRxiv** (MCP + API) — preprints
- **ChEMBL** (MCP) — compound/drug data
- **Clinical Trials** (MCP) — trial data
- **ICD-10 Codes** (MCP) — diagnosis codes
- **Hugging Face** (MCP) — models, papers
- **Slack** (MCP) — notifications

### Issue 10: R&D vs Engineering — RESOLVED

Phase 3a (Engineering) / Phase 3b (R&D) split.

### Issue 11: Operational Details — RESOLVED

| Item | Solution |
|------|----------|
| API rate limiting | Token bucket per tier: Opus 40 RPM, Sonnet 80 RPM, Haiku 200 RPM |
| Background tasks | Phase 1: asyncio.gather. Phase 2+: Celery + Redis |
| Real-time | SSE via sse-starlette. Event schema defined (v4) |
| Error handling | 3-layer: Pydantic, retry with backoff (3x), escalate to Director |
| Prompt versioning | Git-tracked .md files in agents/prompts/ |
| Raw data | DataRegistry (v4) tracks metadata; files on filesystem |
| DB migration trigger | >10 concurrent users OR >100k episodic events |
| Graceful degradation | Agent fails 3x → mark unavailable; degradation modes per agent (v4) |
| Health checks | `/health` endpoint: LLM API connectivity, SQLite DB, ChromaDB, PubMed API (Biopython), CostTracker status |
| Backups | Daily SQLite + ChromaDB snapshots |
| API versioning | `/api/v1/` |
| Dev modes | `make dev-minimal` / `make dev-full` |
| Checkpointing | Per-agent checkpoints + idempotency tokens (v4) |

---

## Cold Start Protocol

### Quick Start Mode *(v4.2: NEW — addresses UX friction)*

Researchers should not be forced through a 3-hour setup before seeing any value.
Quick Start skips Steps 1-3 and goes directly to Direct Query with zero seeded knowledge.

```
Quick Start: Try Direct Query Immediately (~2 min)
├── System boots with empty ChromaDB + empty Lab KB
├── Director can immediately run Direct Query (uses live PubMed/S2/bioRxiv)
├── Results will lack memory context but demonstrate the system's capabilities
├── Dashboard shows "Cold Start incomplete" banner with link to full setup
└── Full Cold Start can be run later without losing Quick Start data
```

### Full Cold Start Protocol (~3 hr)

```
Step 1: Seed Knowledge Manager (~30 min)
├── Import researcher's publication list (Google Scholar/ORCID)
├── Fetch abstracts via PubMed (Biopython) + Semantic Scholar
├── Store in ChromaDB (literature collection, provenance-tagged)
└── Build initial topic graph from publication keywords

Step 2: Seed Internal Lab KB (~15 min, manual)
├── Dashboard wizard: "What experiments didn't work?"
├── Structured form: claim, outcome, conditions, category
├── Target: 10-20 entries
└── Stored with source_type="lab_kb"

Step 3: RCMXT Calibration (~2 hr, semi-automated)
├── Phase 1 calibration (simplified — LLM-only, no inter-expert baseline yet)
├── Load 50 benchmark claims (shipped with system)
├── Run scorer 5x per claim, measure consistency
├── Compare to reference scores (shipped with system)
└── Report calibration metrics. Auto-adjust if below threshold.
Note: Full inter-expert calibration (Phase A) requires human collaborators
      and is deferred to Phase 2. Phase 1 uses LLM-only calibration.

Step 4: Smoke Test (~10 min)
├── Run Direct Query: "What is spaceflight-induced anemia?"
├── Verify: response uses seeded knowledge
├── Run W1 stub: search + screen only (no full workflow)
├── Report: system operational, estimated costs
└── Cost Validation: record actual vs. estimated for W1 stub
```

---

## Tech Stack *(v4: updated)*

| Layer | Technology | Change in v4 |
|-------|-----------|-------------|
| **Frontend** | Next.js 15 + Tailwind + shadcn/ui | — |
| **Workflow Viz** | React Flow (XyFlow) | NEW |
| **Backend API** | FastAPI (Python 3.12+) | — |
| **LLM SDK** | **Anthropic Client SDK** (`pip install anthropic`) | Changed from Agent SDK |
| **Structured Output** | **Instructor** (`pip install instructor`) | NEW |
| **Prompt Caching** | Anthropic native cache_control | NEW |
| **Orchestration (Phase 1)** | **asyncio.gather** + Semaphore | Changed from TaskGroup |
| **Orchestration (Phase 2+)** | Celery + Redis | — |
| **Real-time** | SSE via **sse-starlette** | Made specific |
| **Vector DB** | ChromaDB (collections: literature, synthesis, lab_kb) | Separated collections |
| **State DB** | SQLite (WAL mode) | WAL specified |
| **Code Sandbox** | Docker containers | — |
| **Monitoring** | Langfuse (self-hosted) | — |
| **Literature** | **Biopython** (PubMed) + **Semantic Scholar** + bioRxiv/medRxiv | Specific libraries |
| **Protocol** | MCP | — |
| **Deployment** | **Docker Compose (local-only)** | Changed from hybrid Vercel |
| **Auth** | NextAuth.js + JWT (Phase 4) | Deferred |

---

## Project Structure *(v4: updated)*

```
AI_Scientist_team/
├── README.md
├── pyproject.toml
├── docker-compose.yml
├── docker-compose.dev.yml          # Minimal dev mode
├── .env.example
├── Makefile                         # make dev-minimal / make dev-full
│
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app + SSE hub + /health
│   │   ├── config.py               # Settings, model tiers, budgets
│   │   │
│   │   ├── llm/                    # LLM layer (v4: Anthropic SDK + Instructor)
│   │   │   ├── layer.py            # LLMLayer: complete_structured, complete_raw, complete_with_tools
│   │   │   ├── mock_layer.py       # MockLLMLayer for testing
│   │   │   ├── cache.py            # Prompt caching helpers
│   │   │   └── cost_estimator.py   # Pre-call cost estimation
│   │   │
│   │   ├── models/                 # Pydantic data models
│   │   │   ├── agent.py            # Agent, AgentOutput, AgentSpec
│   │   │   ├── task.py             # Task, Project
│   │   │   ├── workflow.py         # WorkflowInstance, WorkflowStep, StepCheckpoint (v4)
│   │   │   ├── memory.py           # MemoryItem, SemanticEntry, EpisodicEvent
│   │   │   ├── evidence.py         # Evidence, RCMXTScore, OmicsLayerStatus,
│   │   │   │                       #   ContradictionEntry, DataRegistry (v4: all defined)
│   │   │   ├── negative_result.py  # NegativeResult, FailedProtocol
│   │   │   ├── messages.py         # AgentMessage, ContextPackage, SSEEvent (v4)
│   │   │   ├── cost.py             # CostTracker, CostAccuracyReport
│   │   │   └── code_execution.py   # CodeBlock, ExecutionResult
│   │   │
│   │   ├── agents/
│   │   │   ├── base.py             # BaseAgent (uses LLMLayer, Instructor, retry)
│   │   │   ├── registry.py         # Agent registry + health + degradation modes (v4)
│   │   │   ├── prompts/            # Version-controlled prompt files
│   │   │   │   ├── research_director.md
│   │   │   │   ├── knowledge_manager.md
│   │   │   │   ├── project_manager.md
│   │   │   │   ├── experimental_designer.md
│   │   │   │   ├── integrative_biologist.md
│   │   │   │   ├── t01_genomics.md ... t10_data_eng.md
│   │   │   │   ├── qa_statistical_rigor.md
│   │   │   │   ├── qa_biological_plausibility.md
│   │   │   │   └── qa_reproducibility.md
│   │   │   ├── specs/              # Agent spec YAML files
│   │   │   ├── research_director.py
│   │   │   ├── project_manager.py
│   │   │   ├── knowledge_manager.py
│   │   │   ├── experimental_designer.py
│   │   │   ├── integrative_biologist.py
│   │   │   ├── teams/
│   │   │   │   ├── t01_genomics.py ... t10_data_eng.py
│   │   │   └── qa/
│   │   │       ├── statistical_rigor.py
│   │   │       ├── biological_plausibility.py
│   │   │       └── reproducibility_standards.py
│   │   │
│   │   ├── engines/                # Hybrid engines (code + LLM)
│   │   │   ├── ambiguity/
│   │   │   │   ├── contradiction_mapper.py
│   │   │   │   ├── rcmxt_scorer.py
│   │   │   │   ├── rcmxt_monitor.py    # (v4: distribution monitoring)
│   │   │   │   ├── resolution_engine.py
│   │   │   │   └── taxonomy.py
│   │   │   └── negative_results/
│   │   │       ├── shadow_miner.py
│   │   │       ├── preprint_delta.py
│   │   │       ├── trial_failure.py
│   │   │       └── internal_kb.py
│   │   │
│   │   ├── workflows/
│   │   │   ├── engine.py           # WorkflowEngine: state machine + transition table (v4)
│   │   │   ├── runners/
│   │   │   │   ├── async_runner.py  # Phase 1: asyncio.gather + Semaphore (v4)
│   │   │   │   └── celery_runner.py # Phase 2+: Celery
│   │   │   ├── direct_query.py
│   │   │   ├── w1_literature.py     # Phase 1: reduced. Phase 2: full.
│   │   │   ├── w2_hypothesis.py ... w6_ambiguity.py
│   │   │
│   │   ├── memory/
│   │   │   ├── semantic.py         # ChromaDB (3 collections: literature/synthesis/lab_kb)
│   │   │   ├── episodic.py         # SQLite WAL mode
│   │   │   └── literature.py       # Citation tracking + dedup by DOI/PMID (v4)
│   │   │
│   │   ├── integrations/
│   │   │   ├── pubmed.py           # Biopython (Bio.Entrez) (v4)
│   │   │   ├── semantic_scholar.py # Semantic Scholar API (v4: NEW)
│   │   │   └── scholar.py          # Google Scholar (optional)
│   │   │
│   │   ├── execution/
│   │   │   ├── router.py
│   │   │   ├── docker_runner.py
│   │   │   ├── hpc_runner.py       # Phase 4
│   │   │   └── containers/
│   │   │       ├── Dockerfile.rnaseq
│   │   │       ├── Dockerfile.singlecell
│   │   │       └── Dockerfile.genomics
│   │   │
│   │   ├── mcp/
│   │   │   └── registry.py
│   │   │
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── agents.py
│   │   │   │   ├── tasks.py
│   │   │   │   ├── workflows.py
│   │   │   │   ├── memory.py
│   │   │   │   ├── evidence.py
│   │   │   │   ├── dashboard.py
│   │   │   │   ├── direct_query.py
│   │   │   │   └── sse.py          # SSE via sse-starlette (v4)
│   │   │   └── health.py
│   │   │
│   │   ├── cold_start/
│   │   │   ├── seeder.py
│   │   │   ├── calibrator.py
│   │   │   ├── smoke_test.py
│   │   │   └── benchmarks/
│   │   │       ├── rcmxt_50_claims.json
│   │   │       ├── rcmxt_expert_scores.json
│   │   │       └── shadow_mining_phrases.json
│   │   │
│   │   ├── backup/
│   │   │   └── backup_manager.py
│   │   │
│   │   └── db/
│   │       ├── database.py         # SQLite WAL mode (v4)
│   │       └── migrations/
│   │
│   └── tests/
│       ├── test_agents/
│       ├── test_engines/
│       ├── test_workflows/
│       ├── test_execution/
│       ├── test_cold_start/
│       ├── test_llm/              # LLMLayer + MockLLMLayer tests (v4)
│       └── test_api/
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx           # Mission Control
│   │   │   ├── projects/          # Project Board
│   │   │   ├── lab-kb/            # Internal Lab KB
│   │   │   ├── teams/             # Phase 2
│   │   │   ├── quality/           # Phase 2
│   │   │   ├── evidence/          # Phase 3
│   │   │   ├── knowledge/         # Phase 4
│   │   │   └── analytics/         # Phase 4
│   │   ├── components/
│   │   │   ├── dashboard/
│   │   │   │   └── ActivityFeed.tsx
│   │   │   ├── agents/
│   │   │   │   ├── AgentGrid.tsx            # Clickable agent status grid
│   │   │   │   └── AgentDetailSheet.tsx     # (v4: NEW) Side panel for agent inspection
│   │   │   ├── workflows/
│   │   │   │   ├── WorkflowGraph.tsx        # React Flow visualization (v4: NEW)
│   │   │   │   ├── WorkflowDetailSheet.tsx  # (v4: NEW) Side panel for workflow inspection
│   │   │   │   ├── StepDetailPanel.tsx      # (v4: NEW) Expandable step output view
│   │   │   │   └── WorkflowIntervention.tsx # Inline intervention actions
│   │   │   ├── shared/
│   │   │   │   └── InstructionInput.tsx     # (v4: NEW) Reusable note injection component
│   │   │   ├── evidence/
│   │   │   ├── cost/
│   │   │   └── cold-start/
│   │   │       └── LabKBWizard.tsx
│   │   ├── hooks/
│   │   │   ├── useSSE.ts          # SSE subscription hook
│   │   │   └── useDetailSheet.ts  # (v4: NEW) Sheet open/close state + data fetch
│   │   └── lib/
│   └── package.json
│
├── scripts/
│   ├── backup.sh
│   └── cold_start.py
│
└── docs/
    ├── planning/
    │   ├── plan_v4.md             # This file
    │   ├── plan_v3.md             # Previous version
    │   ├── review_v3_critical.md  # All resolved issues
    │   ├── session_log.md         # Planning history
    │   ├── prompts_used.md        # Prompt archive
    │   ├── resources_guide.md     # Curated tool/library guide (v4: NEW)
    │   └── PRD.md                 # Product Requirements Document (v4: NEW)
    ├── architecture.md
    ├── workflow-engine.md
    ├── agent-specs/
    ├── workflow-specs/
    ├── benchmarks/
    └── proposal/
        └── BioTeam-AI_Proposal.docx
```

---

## Phased Development Roadmap (18 weeks engineering + parallel evaluation workstream)

### Phase 1: Foundation + First Value (Week 1-5)

**Week 1-2: Scaffolding + Data Models + LLM Layer**
- [ ] Project scaffolding (monorepo, FastAPI, Next.js, Docker Compose)
- [ ] Makefile with `dev-minimal` and `dev-full` modes
- [ ] LLM layer: `LLMLayer` + `MockLLMLayer` (Anthropic Client SDK + Instructor)
- [ ] Prompt caching strategy implementation
- [ ] All Pydantic models (agent, task, workflow, evidence, negative_result, messages, code_execution, DataRegistry)
- [ ] SQLite database (WAL mode) + Alembic migrations
- [ ] `/health` endpoint
- [ ] `/api/v1/` routing structure
- [ ] AgentMessage transport layer (sync + asyncio modes)
- [ ] Langfuse integration from day one

**Week 3-4: Core Agents + Workflow Engine**
- [ ] BaseAgent class (uses LLMLayer, Instructor validation, retry, Langfuse tracing)
- [ ] Agent spec YAML template + prompt markdown template
- [ ] Research Director agent (dual-mode: Sonnet routing + Opus synthesis)
- [ ] Knowledge Manager agent (Sonnet) — ChromaDB integration with 3 collections
- [ ] Project Manager agent (Haiku)
- [ ] PubMed integration (Biopython — Bio.Entrez)
- [ ] Semantic Scholar integration
- [ ] CostTracker implementation
- [ ] Workflow engine: state machine + transition table + AsyncWorkflowRunner
- [ ] Per-agent checkpointing with idempotency tokens
- [ ] Direct Query mode implementation
- [ ] SSE hub (sse-starlette) with event schema

**Week 5: First Specialists + Dashboard + Cold Start**
- [ ] Team 2 (Transcriptomics) — prompt + spec + tests
- [ ] Team 10 (Data Engineering) — prompt + spec + tests
- [ ] Internal Lab KB (NR Module, engineering portion)
- [ ] Dashboard: 3 core panels (Mission Control, Projects, Lab KB) — SSE-connected
- [ ] Drill-down: AgentDetailSheet (read-only) — click agent cell → side panel *(v4: NEW)*
- [ ] Drill-down: WorkflowDetailSheet (read-only + intervention actions) *(v4: NEW)*
- [ ] API: `GET /agents/{id}`, `GET /workflows/{id}`, `GET /workflows/{id}/steps/{step_id}` *(v4: NEW)*
- [ ] Cold Start protocol (seeder + calibrator + smoke test)
- [ ] W1: Literature Review (reduced — no contradiction map / RCMXT)
- [ ] Backup manager (daily SQLite + ChromaDB snapshots)
- [ ] **Milestone: Run Cold Start + first real literature review**
- [ ] **Cost Validation Gate: Compare W1 actual cost vs. $0.50-2.00 estimate**

### Phase 2: Ambiguity Engine + QA + Scale-Up (Week 6-9)

**Week 6: Infrastructure Scale-Up**
- [ ] Redis + Celery setup
- [ ] `CeleryWorkflowRunner` (same WorkflowStep definitions, different executor)
- [ ] Code Sandbox: Docker runner for local execution
- [ ] Dashboard: +Teams panel, +Quality panel

**Week 7-8: Ambiguity Engine**
- [ ] Contradiction Mapper (deterministic metadata extraction + Sonnet classification)
- [ ] RCMXT scorer (full implementation with X-axis NULL handling)
- [ ] RCMXT calibration: inter-expert baseline (Phase A) + LLM calibration (Phase B)
- [ ] RCMXTMonitor (distribution monitoring, score hedging detection)
- [ ] Resolution hypothesis generator
- [ ] Contradiction visualization component
- [ ] Clinical Trial Failure Miner (ClinicalTrials.gov MCP)
- [ ] W1: Literature Review (full — with contradiction map + RCMXT)

**Week 9: QA Tier + More Specialists**
- [ ] 3 QA agents (Statistical Rigor, Biological Plausibility, Reproducibility)
- [ ] Teams 4 (BioStats), 5 (ML/DL), 6 (Systems Bio)
- [ ] W3: Data Analysis workflow (end-to-end)
- [ ] Workflow Intervention UI component
- [ ] Drill-down Phase 2: Agent history, "Inject Note", "Modify Parameters", clickable feed *(v4: NEW)*
- [ ] API: `POST /workflows/{id}/intervene`, `POST /agents/{id}/query`, agent history *(v4: NEW)*
- [ ] **Milestone: Run first data analysis workflow with QA validation**
- [ ] **Cost Validation Gate: Compare W3 actual cost vs. $2-5 estimate**

### Phase 3a: Full Biology (Week 10-12) — Engineering

- [ ] Teams 1 (Genomics), 3 (Proteomics), 7 (Structural Bio)
- [ ] Experimental Designer agent
- [ ] Integrative Biologist agent
- [ ] W2: Hypothesis Generation with debate pattern (Celery for 7-agent parallel)
- [ ] W6: Ambiguity Resolution standalone workflow
- [ ] Dashboard: +Evidence Explorer panel + React Flow workflow viz
- [ ] **Milestone: Run first hypothesis generation with debate**
- [ ] **Cost Validation Gate: Compare W2 actual cost vs. $3-8 estimate**

### Phase 3b: Negative Results R&D (Week 13-14) — Research

- [ ] Shadow Literature Miner prototype
  - Start Tier 1 (10 phrases) on PMC Open Access
  - Engineering gate: precision >0.85 → add Tier 2 → combined >0.70 → add Tier 3
  - **Publication gate**: precision AND recall on 200+ labeled sentences (from eval workstream)
  - Baselines: NegBio, NegEx, GPT-4o zero-shot, keyword-only
  - If below engineering gate: ship Tier 1 only, defer rest
- [ ] Preprint Delta Analyzer prototype
  - Engineering gate: correctly identifies >60% of removed findings in 20 test cases
  - **Publication gate**: precision + recall on 100+ preprint pairs (from eval workstream)
  - Baseline: difflib text diff
  - If below engineering gate: defer, rely on Lab KB + Trial Failures
- [ ] RCMXT ablation study (5 ablations + **6 baselines** including GRADE, GPT-4o, Gemini, BM25)
- [ ] Mutual information analysis across 5 RCMXT axes
- [ ] Integrate successful prototypes
- [ ] **Milestone: NR Module evaluation report + RCMXT ablation results**

### Phase 4: Translation + Production (Week 15-18)

**Week 15-16: Translation Teams + HPC**
- [ ] Teams 8 (SciComm), 9 (Grants)
- [ ] W4: Manuscript Writing workflow
- [ ] W5: Grant Proposal workflow
- [ ] HPC runner (SSH + Slurm)
- [ ] Dashboard: +Knowledge Browser, +Analytics panel

**Week 17-18: Production Hardening**
- [ ] Auth system (NextAuth.js + JWT)
- [ ] Docker Compose full deployment
- [ ] Vercel deployment (optional, with polling fallback if SSE not supported)
- [ ] Comprehensive testing (unit + integration + E2E with Playwright)
- [ ] Error handling audit
- [ ] Security audit (RBAC, secrets, audit log)
- [ ] **Milestone: Full system demo on spaceflight anemia case study**
- [ ] **Final Cost Report: All workflows actual vs. estimated**

### Publication Evaluation Workstream (Parallel to Engineering) *(v4.1: NEW)*

Runs concurrently with engineering phases. **Does not block engineering milestones.**

**Week 1-2: Administrative Setup**
- [ ] File IRB determination request at Weill Cornell Medicine (for user study, Paper 4)
- [ ] Write RCMXT annotation guidelines: per-axis scoring rubric with 3 anchor examples (low/mid/high)
- [ ] Write contradiction taxonomy annotation guidelines: decision tree + 2 worked examples per type
- [ ] Identify and contact 5 domain expert candidates for RCMXT scoring

**Week 3-4: Corpus Building Begins**
- [ ] Begin curating 150 biological claims across 3 domains (spaceflight biology, cancer genomics, neuroscience)
- [ ] Begin curating contradiction corpus: target 150+ contradictions from PMC OA
- [ ] Begin labeling negative result sentences from PMC OA: target 200+
- [ ] Pilot annotation round: 10 claims + 10 contradictions with 2 annotators, refine guidelines

**Week 6-8: Expert Scoring (Async)**
- [ ] Distribute 150 claims to 5 experts with annotation guidelines (async, ~4-6 hours per expert)
- [ ] Collect expert scores, compute preliminary ICC per axis
- [ ] If ICC < 0.5 on any axis: discussion round, guideline refinement, re-score
- [ ] Preregister RCMXT calibration + ablation protocol on **OSF**

**Week 10-12: LLM Evaluation Begins**
- [ ] Run RCMXT LLM calibration on 150 claims × 5 runs
- [ ] Run cross-model comparison: GPT-4o + Gemini 2.0 on same 150 claims
- [ ] Run prompt sensitivity analysis: 3 prompt variations × 150 claims
- [ ] Compute all agreement metrics: ICC, Bland-Altman, Lin's CCC, MAE
- [ ] Contradiction taxonomy: 2 annotators classify 150+ contradictions, compute Cohen's kappa
- [ ] Card sorting study: 3 experts independently group 50 contradictions

**Week 14-16: Ablation + Baselines**
- [ ] Run RCMXT ablation study: 5 axis-removal + 6 baselines on 150 claims
- [ ] Run downstream task: RCMXT-filtered vs unfiltered evidence for hypothesis ranking
- [ ] Compute mutual information analysis across 5 axes
- [ ] Shadow Mining evaluation: 200+ labeled sentences, precision + recall per tier, 4 baselines
- [ ] Preprint Delta evaluation: 100+ preprint pairs, precision + recall

**Week 18-20: Paper Writing (Papers 2, 1)**
- [ ] Write Paper 2 (Contradiction Taxonomy) draft — target Bioinformatics
- [ ] Write Paper 1 (RCMXT) extended abstract — target NeurIPS AI4Science Workshop
- [ ] Post Paper 2 preprint on bioRxiv
- [ ] Submit Paper 2 to Bioinformatics

**Week 20-24: Paper Submissions**
- [ ] Submit Paper 1 extended abstract to NeurIPS AI4Science
- [ ] Write Paper 1 full manuscript — target Nature Methods
- [ ] Post Papers 1 + 3 preprints on bioRxiv
- [ ] Submit Paper 1 to Nature Methods
- [ ] Submit Paper 3 (NR Module) to PLOS ONE

**Week 24-30: User Study + Framework Paper**
- [ ] Recruit N ≥ 5 biology researchers for user study (IRB approved by now)
- [ ] Run task-based user study: same questions with/without BioTeam-AI
- [ ] Collect SUS scores, time measurements, blind quality ratings
- [ ] Run multi-agent ablation: 18-agent vs single Opus on 10 tasks
- [ ] Prepare 3 case studies (spaceflight, cancer genomics, neuroscience)
- [ ] Decision: Paper 5 standalone (if 300+ entries) or supplementary

**Week 30-36: Final Submissions**
- [ ] Write Paper 4 (Full Framework) — target Nature Methods
- [ ] Submit Paper 4 to Nature Methods
- [ ] If Paper 5 standalone: submit to Scientific Data with Figshare dataset DOI
- [ ] **Milestone: All 4-5 papers submitted or preprinted**

### Open Science Checklist *(v4.1: NEW)*

| Item | Repository | Timing |
|------|-----------|--------|
| System source code | GitHub (MIT license) | Pre-Paper 4 submission |
| RCMXT scoring code + prompts | GitHub + Zenodo DOI | Pre-Paper 1 submission |
| 150 benchmark claims + expert scores | Figshare | With Paper 1 |
| 150+ contradiction corpus | Figshare | With Paper 2 |
| 200+ negative result sentences | Figshare | With Paper 3 |
| Shadow mining vocabulary | GitHub | With Paper 3 |
| Annotation guidelines (all) | GitHub + paper supplementary | With each paper |
| OSF preregistration | OSF | Week 8 |
| Project website + interactive demo | GitHub Pages | Week 16 |
| Docker deployment package | Docker Hub | Pre-Paper 4 |

---

## RESOLVED: Deployment Strategy *(v4 — was BLOCKER B2)*

### The Problem (v3)

v3 specified hybrid deployment: FastAPI backend local + Next.js dashboard on Vercel + SSE for real-time. This is architecturally incompatible because:
- Vercel serverless functions have 10s/60s timeout
- SSE requires persistent HTTP connections — impossible on serverless
- Local backend needs public endpoint or tunnel for Vercel to reach it

### The Solution (v4)

**Phase 1-3: Docker Compose local-only.** Both backend and frontend run on localhost.

```yaml
# docker-compose.dev.yml (make dev-minimal)
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    volumes: ["./backend:/app", "./data:/data"]
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - DATABASE_URL=sqlite:///data/bioteam.db

  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
    depends_on: [backend]
```

**Phase 4 (optional): Vercel with polling fallback.**
- Frontend on Vercel uses polling (`/api/v1/workflows/{id}/status` every 3 seconds)
- SSE only works in local mode
- Backend needs ngrok or similar tunnel for Vercel to reach it
- Decision deferred until actual need for remote access arises

**Benefits:**
- Zero infrastructure complexity for Phase 1-3
- SSE works perfectly on localhost
- Docker Compose is the only deployment requirement
- Progressive: add Vercel when/if remote access is needed

### Infrastructure Requirements

- **Disk:** ~50GB (SQLite databases, ChromaDB collections, Docker containers/images, daily backups)
- **RAM:** 8GB minimum (ChromaDB in-memory, Docker containers, FastAPI/Next.js)
- **Python:** 3.12+
- **Node.js:** 20+ (Next.js 15 requirement)
- **Docker + Docker Compose:** Required for deployment

---

## Communication Pattern

```
Director ←→ Dashboard (SSE via sse-starlette) ←→ FastAPI (/api/v1/) ←→ Research Director
                                                          │
                                              ┌───────────┤
                                              │           │
                                         Direct Query  Full Workflow
                                         (1-3 calls)   (W1-W6)
                                              │           │
                              ┌───────────────┼───────────┼──────────┐
                              │               │           │          │
                         Specialists     Core Engines  QA Agents   Sandbox
                         (Sonnet/Haiku)  (code+Sonnet) (Sonnet/Haiku) (Docker)
                              │                                      │
                              └──────────────────────────────────────┘
                              via AgentMessage (provenance-tagged)
                              Phase 1: asyncio.gather + Semaphore
                              Phase 2+: + Celery/Redis
```

**Context injection per agent:**
```python
class ContextPackage(BaseModel):
    task_description: str
    relevant_memory: list[MemoryItem]       # From Knowledge Manager
    prior_step_outputs: list[AgentOutput]   # From previous workflow steps
    negative_results: list[NegativeResult]  # From NR Module
    rcmxt_context: list[RCMXTScore] | None  # If claim under investigation
    constraints: dict                        # Budget remaining, deadline, etc.
```

---

## Security

- OAuth 2.0 + JWT for API auth (Phase 4)
- RBAC: Director full access; agents scoped per tier/team
- All agent actions logged (Langfuse)
- Kill switch: Director halts any workflow
- MCP tool access scoped per agent (agent spec YAML)
- Secrets via .env
- Code sandbox: Docker containers with no network access
- Daily automated backups (SQLite + ChromaDB)
- API versioning (`/api/v1/`)
- Provenance tagging prevents evidence contamination

---

## Publication Strategy *(v4.1: publication-grade evaluation plan)*

### Differentiation (Extended)

| Feature | Elicit | Consensus | Scite.ai | ASReview | Google AI Co-Scientist | **BioTeam-AI** |
|---------|--------|-----------|----------|----------|----------------------|----------------|
| Contradiction detection | No | No | Citation context (supporting/contrasting) | No | Partial (debate) | **5-type taxonomy** |
| Multi-axis evidence scoring | No | Single score | No | No | No | **RCMXT (5 axes)** |
| Negative results integration | No | No | No | No | No | **4 data sources** |
| Multi-omics awareness | No | No | No | No | No | **X-axis + Integrative Biologist** |
| Independent QA layer | No | No | No | No | Yes (review) | **3 specialized QA agents** |
| Multi-agent orchestration | No | No | No | No | Yes (Gemini) | **18 agents + 2 engines** |
| Memory persistence | No | Limited | No | No | Unknown | **Episodic + Semantic** |
| Code execution sandbox | No | No | No | No | Unknown | **Docker containers** |

### Related Work Coverage (Required for Publication)

Papers must cite and compare to:
- **Evidence scoring**: GRADE framework, Cochrane risk-of-bias tool, SciScore
- **Citation analysis**: Scite.ai (citation statement classification), Semantic Scholar (SPECTER2)
- **Systematic review**: ASReview (active learning), DistillerSR, Covidence, Rayyan
- **AI research assistants**: Elicit, Consensus, SciSpace, Connected Papers
- **Multi-agent AI**: AutoGPT, MetaGPT, ChatDev, CAMEL, Sakana AI Scientist, Stanford Virtual Lab
- **Negation/negative results**: NegBio (NLM), NegEx algorithm, Journal of Negative Results in Biomedicine
- **Scientific disagreement**: Philosophy of science literature on types of disagreement, meta-analysis heterogeneity frameworks

### Five Publications: Detailed Plan

#### Paper 1: RCMXT Evidence Confidence Scoring

| Item | Detail |
|------|--------|
| **Title (working)** | "RCMXT: A Multi-Axis Evidence Confidence Framework for Biology Research" |
| **Target venue** | Nature Methods (primary), NeurIPS AI4Science Workshop (extended abstract first) |
| **Core contribution** | 5-axis scoring system replacing single-score confidence |
| **Evaluation design** | 150 claims × 3 domains × 5 experts + 6 baselines + 5 ablations |
| **Statistical methods** | ICC(2,k), Bland-Altman, Lin's CCC, MAE, bootstrap 95% CI, Wilcoxon + Bonferroni |
| **Required baselines** | GRADE scores, GPT-4o, Gemini 2.0, BM25, single-score LLM, no scoring |
| **Downstream task** | RCMXT-filtered evidence improves hypothesis ranking (expert-judged) |
| **Sensitivity analysis** | 3 prompt variations, temperature sweep, model version comparison |
| **Open science** | Code: GitHub + Zenodo DOI. Claims dataset: Figshare. Protocol: OSF preregistration |
| **Sample size justification** | Power analysis: N=150 detects d=0.5, α=0.05, power=0.80 |
| **Limitations to address** | LLM-as-scorer biases, domain specificity, X-axis sparsity, model dependency |
| **Realistic submission** | Week 20-24 |

#### Paper 2: Five-Category Contradiction Taxonomy

| Item | Detail |
|------|--------|
| **Title (working)** | "A Computational Taxonomy of Contradictions in Biological Literature" |
| **Target venue** | Bioinformatics (Application Note or full paper) |
| **Core contribution** | 5-type classification with hybrid detection (deterministic + LLM) |
| **Corpus required** | **150+ annotated contradictions** across 3 biology domains |
| **Annotation methodology** | Written guidelines with examples per type, 2 annotators, adjudication round |
| **Agreement metric** | Cohen's kappa (inter-annotator), per-class precision/recall/F1, confusion matrix |
| **Taxonomy validation** | Card sorting study: 3 experts independently group 50 contradictions → compare emergent categories to proposed 5 |
| **Required baselines** | GRADE inconsistency domain, keyword matching, random classifier |
| **Mutual exclusivity test** | Report % of contradictions that annotators assign to multiple categories |
| **Open science** | Annotated contradiction corpus released on Figshare |
| **Limitations to address** | Categories may not be exhaustive, English-language only, domain bias |
| **Realistic submission** | Week 18-22 |

#### Paper 3: Negative Results Integration Module

| Item | Detail |
|------|--------|
| **Title (working)** | "Mining the File Drawer: Computational Extraction of Negative Results from Biomedical Literature" |
| **Target venue** | PLOS ONE (primary), Quantitative Science Studies (alternative) |
| **Core contribution** | 4-source integration (Lab KB + clinical trials + shadow mining + preprint deltas) |
| **Shadow Mining evaluation** | **200+ labeled negative result sentences** from PMC OA. Report **precision AND recall** per tier |
| **Preprint Delta evaluation** | **100+ preprint pairs** with annotated changes. Report precision/recall for removed findings |
| **Required baselines** | NegBio, NegEx, keyword-only matching, GPT-4o zero-shot |
| **Downstream utility** | Case study: NR Module surfaced a negative result that changed a hypothesis or prevented wasted experiment |
| **Ethical considerations** | Address responsible interpretation of "shadow" negatives — original authors may disagree with interpretation |
| **Open science** | Labeled corpus on Figshare, shadow mining vocabulary on GitHub |
| **Limitations to address** | English-only, precision-recall trade-off, author intent ambiguity |
| **Realistic submission** | Week 22-26 |

#### Paper 4: Full BioTeam-AI Framework

| Item | Detail |
|------|--------|
| **Title (working)** | "BioTeam-AI: A Multi-Agent System with Biology-Aware Epistemology for Research Assistance" |
| **Target venue** | Nature Methods (primary), Cell Systems or Genome Biology (alternatives) |
| **Core contribution** | Full system with RCMXT + contradiction taxonomy + NR integration + multi-agent |
| **User study design** | N ≥ 5 biology researchers (not the developer), **IRB approved** |
| **User study protocol** | Task-based: same research questions with/without BioTeam-AI. Measure: time, completeness, accuracy, novelty. Post-task: System Usability Scale (SUS) + semi-structured interview |
| **Case studies** | **3 minimum**: spaceflight anemia (primary), cancer genomics, neuroscience or immunology |
| **Prospective validation** | At least 1 case where system identifies novel insight, subsequently validated |
| **Multi-agent ablation** | 18-agent system vs. single well-prompted Opus call on same tasks — measure quality difference |
| **System comparison** | BioTeam-AI vs. researcher using Elicit+ChatGPT vs. researcher working manually |
| **Cost-effectiveness** | Total weekly cost vs. hiring a research assistant |
| **Open science** | Full system open-source on GitHub, all prompts published, Docker deployment |
| **Limitations to address** | Single-developer bias, Claude-only vendor lock-in, English-only, evaluation on 3 domains |
| **Realistic submission** | Week 30-36 |

#### Paper 5: Spaceflight Biology Benchmark Dataset

| Item | Detail |
|------|--------|
| **Title (working)** | "SpaceBio-Bench: A Benchmark for Evaluating AI Evidence Assessment in Spaceflight Biology" |
| **Target venue** | Scientific Data (primary), or supplementary material in Papers 1-3 if < 200 entries |
| **Minimum dataset size** | **300+ entries**: 150 scored claims, 100+ contradictions, 50+ negative results |
| **Annotation methodology** | Written guidelines, 2+ annotators per entry, ICC/kappa reported |
| **Data format** | JSON + CSV, FAIR-compliant, Figshare/Zenodo with DOI |
| **NASA GeneLab integration** | Cross-reference with OSDR accession numbers where applicable |
| **Data dictionary** | Full schema documentation, provenance for each entry |
| **Maintenance plan** | Versioned releases (v1.0, v1.1...), community contribution guidelines |
| **Decision rule** | If < 200 entries by Week 28: release as supplementary material in Paper 1, not standalone |
| **Realistic submission** | Week 28-34 (only if threshold met) |

### Submission Order & Strategy

```
Week 8:  OSF preregistration (RCMXT calibration + ablation protocol)
Week 10: Begin expert scoring (async, parallel with engineering)
Week 16: Submit Paper 2 (Taxonomy) to Bioinformatics — smallest scope, fastest
Week 18: bioRxiv preprint for Paper 2
Week 20: Submit Paper 1 (RCMXT) extended abstract to NeurIPS AI4Science Workshop
Week 22: bioRxiv preprint for Papers 1 + 3
Week 24: Submit Paper 1 (RCMXT) full paper to Nature Methods
Week 26: Submit Paper 3 (NR Module) to PLOS ONE
Week 28: Decision on Paper 5 (benchmark: standalone vs supplementary)
Week 34: Submit Paper 4 (Framework) to Nature Methods — after user study
Week 36: Submit Paper 5 (Benchmark) to Scientific Data (if standalone)
```

### Preprint & Impact Strategy

- **bioRxiv first**: Papers 1-3 posted before journal submission (priority + community feedback)
- **GitHub release with Zenodo DOI** before preprints (citable code, increases adoption)
- **Project website** with interactive RCMXT demo (try on your own claims)
- **Social media**: Twitter/X + Bluesky threads for each preprint, tag #AIforScience #spaceflight #multiomics
- **Cross-citation cluster**: All 5 papers reference each other
- **Conference presentations**: ISMB/ECCB (bioinformatics), NeurIPS AI4Science (ML), NASA Human Research Program Investigators' Workshop (domain)

---

## Verification Plan

### Engineering Tests (Continuous)

1. **Unit tests**: Each agent, engine, workflow step, API endpoint, LLM layer
2. **Agent quality tests**: 10 domain-specific benchmark questions per agent
3. **Integration tests**: E2E W1-W6 + Direct Query with MockLLMLayer
4. **Workflow engine tests**: State transitions (all legal/illegal), loop detection, budget enforcement, checkpointing, parallel failure recovery
5. **Sandbox tests**: Code generation → execution → result parsing
6. **Cold start test**: Full protocol on clean system
7. **Health check test**: `/health` reports all dependency statuses (LLM API, SQLite, ChromaDB, PubMed, CostTracker)
8. **Provenance test**: Verify internal_synthesis cannot inflate R-axis scores
9. **Dashboard E2E**: Playwright for 3 core panels + progressive panels
10. **Smoke test**: Real literature review on "spaceflight-induced anemia"
11. **Performance targets**: Direct Query < 30s, W1 < 15 min (20-50 papers), Dashboard load < 2s, SSE latency < 500ms
12. **Cost validation gates**: Actual vs. estimated at each phase milestone

### Publication-Grade Evaluation (Parallel Workstream)

13. **RCMXT inter-expert agreement**: 150 claims × 5 experts × 3 domains → ICC(2,k) per axis, Bland-Altman plots, Lin's CCC, MAE. Target: ICC > 0.6 inter-expert
14. **RCMXT LLM calibration**: 150 claims × 5 runs → ICC(2,1) vs expert consensus per axis. Target: ICC ≥ 0.7. Cross-model: GPT-4o + Gemini 2.0 comparison
15. **RCMXT ablation**: 5 axis-removal + 6 baselines (GRADE, GPT-4o single-score, Gemini single-score, BM25, majority vote, no scoring). Downstream task: hypothesis ranking. Wilcoxon + Bonferroni. Bootstrap 95% CI (1000 iterations)
16. **RCMXT sensitivity**: 3 prompt variations × 150 claims. Temperature sweep (0.0, 0.3, 0.7, 1.0). Model version comparison when updates occur
17. **RCMXT mutual information**: Quantify unique contribution per axis (justify 5 not 3 or 7)
18. **RCMXT monitoring**: Verify hedging detection on synthetic biased scores + monthly 20-claim holdout
19. **Contradiction taxonomy**: 150+ annotated contradictions × 3 domains × 2 annotators → Cohen's kappa per type, per-class P/R/F1, confusion matrix, macro F1. Card sorting validation with 3 independent experts
20. **Shadow Mining**: 200+ labeled sentences from PMC OA → **precision AND recall** per tier. Baselines: NegBio, NegEx, GPT-4o zero-shot, keyword-only
21. **Preprint Delta**: 100+ preprint pairs → precision/recall for removed findings. Baseline: difflib text diff
22. **Multi-agent ablation** (Paper 4): 18-agent BioTeam-AI vs. single Opus call on same 10 research tasks → quality comparison rated by 3 independent experts
23. **User study** (Paper 4): N ≥ 5 researchers, task-based with/without BioTeam-AI. SUS score, time measurement, output quality blind-rated by external expert. **IRB required**
24. **Benchmark dataset validation** (Paper 5): 300+ entries with inter-annotator agreement reported (ICC for continuous, kappa for categorical). FAIR compliance checklist

---

## Known Technical Debt (deferred)

| Item | Phase | Notes |
|------|-------|-------|
| ChromaDB → Qdrant migration | Phase 4+ | When scaling requires it |
| Embedding model selection | Phase 2 | Currently using ChromaDB defaults |
| MODEL_MAP model IDs | Ongoing | Update when new model versions release |
| Multiple browser tab conflicts | Phase 4+ | Accept single-tab for now |
| Loop count vs. budget limit conflict | Phase 2 | Budget takes precedence |
| Multi-user / tenant_id | Phase 5+ | Explicitly single-user for now |
| Vercel production deployment | Phase 4 | Polling fallback if needed |

---

## Summary of All Resolved Issues (v1 → v4.2)

| Version | Issues Found | Issues Resolved |
|---------|-------------|-----------------|
| v1 review | 11 issues | 11 (in v2) |
| v2 multi-perspective | 21 changes | 21 (in v3) |
| v3 critical review | 34 unique (3B + 5C + 15M + 6m) | 3B + 5C + 8M (in v4); 7M + 6m as known debt |
| v4 researcher feedback | 22 unique (6C + 9H + 7M) | 6C + 7H implemented (in v4.2); 2H + 7M deferred |
| **Total** | **88 unique issues** | **61 resolved, 20 deferred, 7 accepted** |

---

## Implementation Status Snapshot (as of 2026-02-27)

### Completion by Phase

| Phase | Planned | Status | Notes |
|-------|---------|--------|-------|
| **Phase 1**: Foundation (Wk 1-5) | W1-reduced, 3 agents, 3 dashboard panels | ✅ Complete | All items shipped |
| **Phase 2**: Ambiguity Engine + QA (Wk 6-9) | Celery, code sandbox, ambiguity engine, 3 QA agents | ⊙ 70% | Celery/Redis and code sandbox deferred |
| **Phase 3a**: Full Biology (Wk 10-12) | 12 specialist agents, W2/W6 | ✅ Complete | All 12 specialists + W2/W6 implemented |
| **Phase 3b**: NR R&D (Wk 13-14) | Shadow mining, preprint delta, RCMXT ablation | ⊙ 30% | Lab KB done; advanced NLP tiers not built |
| **Phase 4**: Translation + Production (Wk 15-18) | W4/W5, auth, production hardening | ⊙ 50% | W4/W5 implemented; auth dev-only; no Docker prod |
| **Publication Workstream** | IRB, guidelines, expert scoring, 5 papers | ❌ 0% | Not started |

### Features Built Beyond Original Plan

| Feature | Status | Business Value |
|---------|--------|----------------|
| **W9 Bioinformatics workflow** | ✅ Implemented | Handles genomics/RNA-seq/proteomics analysis chains |
| **7 Bioinformatics API integrations** | ✅ Implemented | UniProt, Ensembl, STRING, GWAS, GTEx, g:Profiler, NCBI |
| **Open Peer Review Corpus** | ⊙ Disabled | W8 benchmark against eLife/PLOS open reviews |
| **MCP Connector infrastructure** | ✅ Implemented | PubMed, bioRxiv, ClinicalTrials, ChEMBL, ICD-10 MCP |
| **PTC (Programmatic Tool Calling)** | ⊙ Disabled | Multi-tool orchestration; toggled off by default |
| **Iterative Self-Refine loop** | ✅ Implemented | Quality scoring → refinement with budget cap |
| **Long-term step checkpointing** | ✅ Implemented | Rerun/skip/inject API for interrupted runs |
| **GitHub Actions CI** | ✅ Implemented | ruff + pytest, integration test auto-skip |
| **Digest email delivery** | ✅ Implemented | SMTP/Gmail scheduled digest report delivery |
| **Data integrity audit scheduler** | ✅ Implemented | Crossref-based citation verification on schedule |

### Technical Debt Added (not in original plan)

| Item | Risk | Mitigation |
|------|------|-----------|
| Code execution sandbox missing | W3/W9 cannot run real analysis | Add `docker_runner.py` next priority |
| Celery/Redis not implemented | Long workflows block event loop | asyncio.gather is fine at current scale |
| Open Peer Review Corpus disabled | W8 benchmark pipeline untested | Enable after adding coverage tests |
| MCP/PTC disabled by default | Integration coverage gaps | Enable + test in Phase 3b iteration |
| Frontend missing 5 planned panels | Researchers can't see team/QA/evidence data | Add in next frontend sprint |
| No production auth | Single-user only (acceptable for now) | Add JWT when sharing with lab colleagues |

### Updated Known Technical Debt

| Item | Phase | Notes |
|------|-------|-------|
| ChromaDB → Qdrant migration | Phase 4+ | When scaling requires it |
| Embedding model selection | Phase 2 | Currently using ChromaDB defaults |
| MODEL_MAP model IDs | Ongoing | ~~claude-sonnet-4-5-20250929~~ → claude-sonnet-4-6 ✅ (2026-02-27) |
| Multiple browser tab conflicts | Phase 4+ | Accept single-tab for now |
| Loop count vs. budget limit conflict | Phase 2 | Budget takes precedence |
| Multi-user / tenant_id | Phase 5+ | Explicitly single-user for now |
| Vercel production deployment | Phase 4 | Polling fallback if needed |
| Code execution sandbox | Phase 2 (overdue) | Highest priority unimplemented feature |
| Celery/Redis task queue | Phase 2 (deferred) | Asyncio.gather sufficient for now |
| Open Peer Review Corpus enable | Phase 6 | Needs test coverage before enabling |

### Next Session Work Order (Priority Stack)

1. **[Critical] Code execution sandbox** — `docker_runner.py` + Dockerfiles for rnaseq/singlecell/genomics. W3 and W9 cannot deliver real scientific value without this.
2. **[Critical] Publication workstream start** — Write RCMXT annotation guidelines + identify 5 domain expert candidates. Unblocks Paper 1.
3. **[High] W9 test coverage** — `test_w9_runner.py` needs full offline validation via MockLLMLayer
4. **[High] Open Peer Review Corpus enable** — Add tests for eLife XML parser + concern parser → set `peer_review_corpus_enabled = True` → run benchmark
5. **[Medium] Frontend Phase 2 panels** — Teams panel, Quality panel, Evidence Explorer
6. **[Medium] RCMXT calibration data** — Begin curating 150 biological claims across 3 domains
7. **[Low] Celery/Redis** — Only needed if asyncio.gather becomes a bottleneck at scale
