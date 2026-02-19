# BioTeam-AI — Implementation Plan v3

## Context

JangKeun Kim (Weill Cornell Medicine) is building a personal AI Science Team for biology research. The system provides a dashboard for directing specialized AI agent teams through research workflows. This plan merges:

1. **BioTeam-AI Proposal** (BioTeam-AI_Proposal.docx) — Ambiguity Resolution Engine, RCMXT Evidence Scoring, Negative Results Integration Module
2. **Implementation planning session** — practical tech stack, 10 specialist teams, dashboard design
3. **v1 Critical Review** — 11 issues identified and resolved
4. **v2 Multi-Perspective Review** — 6 expert perspectives (Software Architect, Biology Domain, UX, DevOps, Academic, Cost/ROI) with 20+ actionable findings incorporated *(NEW in v3)*

Key differentiator: biology-aware epistemology that handles contradictions, negative results, and context-dependent truth.

### v2 → v3 Changelog

| # | Change | Source |
|---|--------|--------|
| 1 | Workflow engine promoted to dedicated architecture section | Architect #A |
| 2 | SSE-only real-time (WebSocket contradiction resolved) | Architect #B |
| 3 | Phase 1 uses asyncio, Celery/Redis deferred to Phase 2 | Architect #C |
| 4 | API versioning (`/api/v1/`) added | Architect #D |
| 5 | RCMXT calibration: inter-expert baseline + X-axis empty-data handling | Biology #A, #B |
| 6 | Shadow Mining: constrained 30-phrase vocabulary as starting point | Biology #C |
| 7 | medRxiv added alongside bioRxiv | Biology #D |
| 8 | Dashboard: 3 core panels at launch, progressive disclosure for rest | UX #A |
| 9 | Direct Query mode added (bypasses full workflow) | UX #B |
| 10 | Workflow intervention UI specified | UX #C |
| 11 | Cold Start protocol added | UX #D |
| 12 | `make dev-minimal` / `make dev-full` Makefile modes | DevOps #A |
| 13 | `/health` endpoint with dependency checks | DevOps #B |
| 14 | HPC runner moved from Phase 3a → Phase 4 | DevOps #C |
| 15 | Backup/restore strategy added | DevOps #D |
| 16 | Publication framing: generalizable framework + Elicit/Consensus differentiation | Academic #A, #C |
| 17 | RCMXT validation plan: ablation study + baselines | Academic #B |
| 18 | Benchmark dataset sharing plan | Academic #D |
| 19 | Opus cost optimization: Research Director dual-mode (route vs. synthesize) | Cost #B |
| 20 | Cost estimate validation gate at Phase 1 milestone | Cost #A, #C |
| 21 | LLM abstraction layer over Claude Agent SDK | Cost #D |

---

## Design Principles

1. **Biology ≠ SWE** — Context-dependent truth. Every claim gets an RCMXT confidence vector, not true/false.
2. **Multi-agent is not always better** (Google 180-experiment study) — Research Director decides single vs. multi-agent per task.
3. **QA must be structurally independent** — QA agents report directly to Director, never subordinate to teams they review.
4. **Memory is infrastructure** (NTT AI Constellation) — Episodic + semantic memory prevents rediscovery.
5. **Negative results are first-class data** — Publication bias hides 85% of failures; the system must mine them.
6. **Bidirectional iteration** — Every workflow loops back; no unidirectional pipelines.
7. **Schema-enforced outputs** — All agent outputs are structured JSON with Pydantic validation.
8. **Cost-aware execution** — Model tier selection per agent; token budgets per workflow.
9. **Code generation, not code execution** — Agents produce code + instructions; execution is delegated to sandboxes or human.
10. **Progressive complexity** — Start minimal (asyncio, SQLite, 3 panels), scale up infrastructure only when needed. *(NEW)*
11. **Ship research value early** — Every phase must deliver a usable standalone capability, not just "infrastructure." *(NEW)*

---

## Three-Tier Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DASHBOARD (Next.js)                           │
│  Phase 1: Mission Control │ Projects │ Lab KB                   │
│  Phase 2+: + Teams │ Quality │ Evidence │ Knowledge │ Analytics │
└────────────────────────────┬────────────────────────────────────┘
                             │ Server-Sent Events (SSE)
┌────────────────────────────┴────────────────────────────────────┐
│                    FASTAPI BACKEND                               │
│  REST API (/api/v1/) │ SSE Hub │ Background Tasks               │
│  Phase 1: asyncio    │ Phase 2+: Celery + Redis                 │
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
│       │                      │  Research Director answers         │
│       │                      │  simple questions in 1 turn        │
│       │                      │  without spawning a workflow.      │
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
│  │  │ Knowledge Mgr   │  Semantic: ChromaDB                 │      │
│  │  │ (Sonnet)         │  Episodic: SQLite/Postgres          │      │
│  │  │                  │  Literature: PubMed + bioRxiv/      │      │
│  │  │                  │             medRxiv APIs            │      │
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
│  [2] Transcrip   [5] ML/DL       [9] Grants                       │
│  [3] Proteomics  [6] Systems Bio  [10] Data Eng                   │
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
│  Phase 1: SQLite │ ChromaDB │ Langfuse │ asyncio                  │
│  Phase 2: + Redis │ Celery │ Docker Sandbox                       │
│  Phase 4: + HPC Runner │ PostgreSQL (optional)                    │
│  Always:  /health endpoint │ daily backups │ .env secrets          │
└────────────────────────────────────────────────────────────────────┘
```

---

## NEW: Direct Query Mode *(v3)*

Not every research question needs a full workflow. Direct Query mode handles simple, single-turn questions without spawning W1-W6.

```
┌──────────────────────────────────────────────────────────────┐
│                    DIRECT QUERY MODE                          │
│                                                               │
│  User asks: "Is gene TNFSF11 differentially expressed in     │
│  spaceflight cfRNA data?"                                     │
│                                                               │
│  Research Director (Sonnet-tier for routing):                 │
│  1. Classify: simple_query | needs_workflow                   │
│                                                               │
│  If simple_query:                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │ Knowledge    │ →  │ Specialist   │ →  │ Response     │     │
│  │ Manager      │    │ (1 agent)    │    │ (direct to   │     │
│  │ (memory +    │    │              │    │  dashboard)  │     │
│  │  literature) │    │              │    │              │     │
│  └─────────────┘    └──────────────┘    └──────────────┘     │
│  ~1-3 LLM calls, < $0.50, < 30 seconds                       │
│                                                               │
│  If needs_workflow:                                            │
│  → Route to appropriate W1-W6 with explanation to Director    │
│                                                               │
│  Classification heuristics:                                    │
│  - Single entity lookup → simple_query                        │
│  - "What is X?" / "Is X true?" → simple_query                │
│  - "Compare X across Y conditions" → needs_workflow (W1)      │
│  - "Analyze dataset Z" → needs_workflow (W3)                  │
│  - "Write section about X" → needs_workflow (W4)              │
└──────────────────────────────────────────────────────────────┘
```

---

## NEW: Workflow Engine Architecture *(v3)*

The workflow engine is the most complex component. It manages state transitions, checkpointing, parallel fan-out/fan-in, loop detection, budget enforcement, and human intervention points.

### State Machine Design

```
┌────────────────────────────────────────────────────────────────┐
│                    WORKFLOW ENGINE                               │
│                                                                  │
│  Core: Finite State Machine per workflow instance                │
│                                                                  │
│  WorkflowInstance {                                              │
│    id: str                                                       │
│    template: W1 | W2 | W3 | W4 | W5 | W6                       │
│    state: PENDING | RUNNING | PAUSED | WAITING_HUMAN |           │
│           COMPLETED | FAILED | CANCELLED | OVER_BUDGET           │
│    current_step: str                                             │
│    step_history: list[StepResult]    # For replay/audit          │
│    checkpoint: bytes | None          # Serialized state          │
│    loop_count: dict[str, int]        # Per-loop iteration count  │
│    max_loops: int = 3                # Prevent infinite loops    │
│    budget_remaining: float                                       │
│    created_at, updated_at: datetime                              │
│  }                                                               │
│                                                                  │
│  Step Definition:                                                │
│  WorkflowStep {                                                  │
│    id: str                          # e.g., "SEARCH"             │
│    agent_id: str | list[str]        # Single or parallel         │
│    input_mapper: Callable           # Prior outputs → input      │
│    output_schema: type[BaseModel]                                │
│    next_step: str | Callable        # Static or conditional      │
│    is_parallel: bool = False                                     │
│    is_human_checkpoint: bool = False # Pause for Director        │
│    is_loop_point: bool = False      # Can loop back here         │
│    loop_condition: Callable | None  # When to loop vs. proceed   │
│    estimated_cost: float                                         │
│  }                                                               │
│                                                                  │
│  Execution Modes (grows with infrastructure):                    │
│  ┌────────────────────────────────────────────────────────┐      │
│  │ Phase 1: AsyncWorkflowRunner                           │      │
│  │   - Python asyncio.TaskGroup for parallel steps        │      │
│  │   - In-process, single-worker                          │      │
│  │   - Checkpoints to SQLite                              │      │
│  │   - Sufficient for 1-3 concurrent workflows            │      │
│  ├────────────────────────────────────────────────────────┤      │
│  │ Phase 2+: CeleryWorkflowRunner                         │      │
│  │   - Celery chord() for parallel fan-out/fan-in         │      │
│  │   - Redis broker, multi-worker                         │      │
│  │   - Same WorkflowStep definitions, different executor  │      │
│  │   - Needed when: >3 concurrent workflows OR            │      │
│  │     W2 GENERATE step (7 agents truly parallel)         │      │
│  └────────────────────────────────────────────────────────┘      │
│                                                                  │
│  Budget Enforcement:                                             │
│  - Pre-step: estimate cost, check budget_remaining               │
│  - If insufficient: state → OVER_BUDGET, alert dashboard         │
│  - Director can: (a) approve overage, (b) cancel, (c) skip step │
│                                                                  │
│  Loop Detection:                                                 │
│  - Each loop_point tracks iteration count                        │
│  - If loop_count[step_id] >= max_loops: force proceed + warn     │
│  - Director can override max_loops from dashboard                │
│                                                                  │
│  Human Intervention (WAITING_HUMAN state):                       │
│  - Triggered at is_human_checkpoint steps                        │
│  - Also triggered by: OVER_BUDGET, agent failure, QA rejection   │
│  - Dashboard shows: current state, outputs so far, action menu   │
│  - Actions: approve, reject, modify parameters, skip, cancel     │
│  - Timeout: 24h default, then auto-pause with notification       │
└────────────────────────────────────────────────────────────────┘
```

### Workflow Intervention UI

```
┌────────────────────────────────────────────────────────────────┐
│  WORKFLOW INTERVENTION (Dashboard Panel)                        │
│                                                                 │
│  When workflow is WAITING_HUMAN or PAUSED:                      │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ W1: Literature Review — "Spaceflight Anemia"            │    │
│  │ Status: WAITING_HUMAN at step SYNTHESIZE                │    │
│  │ Budget: $2.40 / $5.00 used                              │    │
│  │ Loop: 1 of 3 (contradictions found → re-searching)      │    │
│  │                                                          │    │
│  │ Current outputs:                                         │    │
│  │  ├── SEARCH: 47 papers found                            │    │
│  │  ├── SCREEN: 23 relevant                                │    │
│  │  ├── EXTRACT: 23 structured summaries                   │    │
│  │  ├── CONTRADICTION MAP: 4 contradictions identified     │    │
│  │  └── RCMXT: 4 claims scored [click to expand]           │    │
│  │                                                          │    │
│  │ Actions:                                                 │    │
│  │  [Continue] [Modify Search Terms] [Skip QA] [Cancel]    │    │
│  │  [Inject Note: _______________]                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  Director can intervene at ANY step (not just checkpoints):     │
│  - Pause button: forces current step to complete, then pauses   │
│  - Inject context: adds a note to ContextPackage for next step  │
│  - Redirect: skip to a different step or re-route to new agent  │
└────────────────────────────────────────────────────────────────┘
```

---

## Issue Resolutions (v1 Review → v2, retained in v3)

### Issue 1: Engines vs Agents — RESOLVED

Engines are **hybrid components**: deterministic code pipelines + LLM-powered interpretation steps.

| Component | Deterministic Code | LLM Call (Model) |
|-----------|-------------------|-------------------|
| **Contradiction Mapper** | Query DB for evidence, extract metadata, structural comparison | Classify contradiction type, generate resolution hypotheses (Sonnet) |
| **RCMXT Scorer** | Aggregate study metadata, count replications, check omics layers | Score subjective axes (M, T), calibrate (Sonnet) |
| **Shadow Miner** | Constrained 30-phrase vocabulary matching *(v3: was regex)* | Interpret context, extract structured NegativeResult (Sonnet) |
| **Preprint Delta** | Text diff between versions | Interpret significance of changes (Sonnet) |
| **Trial Failure** | ClinicalTrials.gov API query + filtering | Interpret termination reasons, extract implications (Sonnet) |
| **Internal Lab KB** | CRUD operations, search | None (purely structured data) |

### Issue 2: Division Leads — RESOLVED: Removed

Division Leads are **removed as agents**. Research Director communicates directly with specialist teams. Divisions remain as organizational grouping (for dashboard display and configuration), not as routing agents. This reduces agent count from 18 to 15 active LLM agents.

### Issue 3: Code Execution — RESOLVED

**Strategy: Code Generation + Sandboxed Execution**

Specialist agents (Teams 1-7) **generate code**, not execute it. Execution is handled by a separate Code Sandbox layer.

```
Agent generates CodeBlock → Execution Router → Docker (local) / HPC (Phase 4) / Human Review
```

```python
class CodeBlock(BaseModel):
    language: Literal["python", "R"]
    code: str
    dependencies: list[str]           # ["scanpy", "DESeq2"]
    expected_output: type[BaseModel]
    estimated_runtime: str            # "5min" | "2hr"
    execution_target: Literal["local", "hpc"]

class ExecutionResult(BaseModel):
    stdout: str
    stderr: str
    files_created: list[str]
    runtime_seconds: float
    exit_code: int
```

**Execution targets:**
- **Local Docker**: Short jobs (< 10 min). Pre-built containers with common bio tools (scanpy, DESeq2, etc.)
- **HPC via SSH**: Long jobs (> 10 min). Submit to Cornell CAC via Slurm. *(Moved to Phase 4 in v3)*
- **Human Review**: Any destructive operation, file deletion, or external API call with side effects requires Director approval via dashboard.

### Issue 4: Agent-to-Agent Communication — RESOLVED

**Transport: Phase 1 in-process async, Phase 2+ Redis message broker**

```python
class AgentMessage(BaseModel):
    id: str                     # uuid
    from_agent: str
    to_agent: str
    workflow_id: str
    step: str
    payload: dict               # Structured data
    context_refs: list[str]     # Memory/task IDs
    timestamp: datetime
```

**Transport Modes:**

| Mode | When | Phase |
|------|------|-------|
| **Sync** | Direct function call within same process (single-agent mode) | 1+ |
| **Async** | `asyncio.TaskGroup` for parallel multi-agent tasks | 1+ |
| **Queued** | Celery task queue for truly parallel multi-worker execution | 2+ |

**Key rule:** Agents never pass raw conversation history to each other. They pass structured outputs via `AgentMessage`. The orchestrator (workflow engine) manages context injection — each agent receives only what it needs, not the full chain.

### Issue 5: Cost Controls — RESOLVED + Enhanced *(v3)*

**Model Tier Assignment (v3: Research Director dual-mode):**

| Agent | Model | Rationale | Est. Cost/Call |
|-------|-------|-----------|---------------|
| Research Director — **routing** | **Sonnet** | Simple classification: direct query vs. workflow, team assignment | ~$0.05-0.10 |
| Research Director — **synthesis** | **Opus** | Complex reasoning: cross-team synthesis, contradiction resolution, final reports | ~$0.50-1.00 |
| Knowledge Manager | **Sonnet** | Literature search, memory queries | ~$0.05-0.15 |
| Project Manager | **Haiku** | Simple status tracking, updates | ~$0.01-0.03 |
| Experimental Designer | **Sonnet** | Moderate reasoning | ~$0.05-0.15 |
| Integrative Biologist | **Sonnet** | Cross-omics interpretation | ~$0.05-0.15 |
| Specialist Teams 1-7 | **Sonnet** | Domain analysis | ~$0.05-0.15 |
| SciComm (Team 8) | **Sonnet** | Writing quality matters | ~$0.10-0.30 |
| Grants (Team 9) | **Opus** | High-stakes writing | ~$0.50-1.00 |
| Data Engineering (Team 10) | **Haiku** | Code generation, templates | ~$0.01-0.05 |
| QA: Statistical Rigor | **Sonnet** | Analytical reasoning | ~$0.05-0.15 |
| QA: Biological Plausibility | **Sonnet** | Domain reasoning | ~$0.05-0.15 |
| QA: Reproducibility | **Haiku** | Checklist-based validation | ~$0.01-0.03 |
| Engine LLM calls | **Sonnet** | Classification, extraction | ~$0.03-0.10 |

**Research Director Dual-Mode Logic:**
```python
class ResearchDirector:
    async def handle(self, input: UserRequest) -> AgentOutput:
        # Phase 1: Classify complexity (Sonnet-tier, cheap)
        classification = await self.classify(input, model="sonnet")

        if classification.type == "direct_query":
            # Route to single specialist, no workflow
            return await self.direct_query(input, classification.target_agent)

        elif classification.type == "simple_workflow":
            # Decompose + delegate, Sonnet sufficient
            return await self.orchestrate(input, model="sonnet")

        else:  # complex_synthesis, cross_team, contradiction_resolution
            # Full Opus reasoning required
            return await self.orchestrate(input, model="opus")
```

**Token Budget Per Workflow (v3: validation gate added):**

| Workflow | Est. LLM Calls | Est. Cost | Max Budget | Validation |
|----------|---------------|-----------|------------|------------|
| Direct Query | 1-3 | $0.10-0.50 | $1 | — |
| W1: Literature Review | 8-12 | $1-3 | $5 | **Validate at Phase 1 smoke test** |
| W2: Hypothesis Generation | 15-25 | $3-8 | $15 | Validate at Phase 3a milestone |
| W3: Data Analysis | 10-18 | $2-5 | $10 | Validate at Phase 2 milestone |
| W4: Manuscript Writing | 20-35 | $5-15 | $25 | Validate at Phase 4 milestone |
| W5: Grant Proposal | 25-40 | $8-20 | $30 | Validate at Phase 4 milestone |
| W6: Ambiguity Resolution | 6-10 | $1-3 | $5 | Validate at Phase 3a milestone |

**Cost Validation Gate (NEW in v3):** After each phase milestone smoke test, compare actual costs vs. estimates. If actual > 2x estimated, adjust budgets and model tier assignments before proceeding to next phase.

**Cost controls implemented in code:**
```python
class CostTracker:
    workflow_budgets: dict[str, float]     # Max $ per workflow type
    session_budget: float = 50.0           # Daily max $
    alert_threshold: float = 0.8           # Alert at 80% of budget

    def check_budget(self, workflow_id: str, estimated_cost: float) -> bool:
        """Returns False if over budget, triggers dashboard alert."""

    def record_actual(self, workflow_id: str, step: str, actual_cost: float):
        """Records actual cost per step for validation gate analysis."""

    def get_accuracy_report(self) -> CostAccuracyReport:
        """Compares estimated vs. actual across all completed workflows."""
```

**Caching strategy:**
- Knowledge Manager caches literature search results (TTL: 24h)
- RCMXT scores cached per claim (TTL: 7d, invalidated on new evidence)
- Agent prompt templates cached (no TTL, invalidated on version change)
- Identical queries within same workflow deduplicated

### Issue 6: Role Overlaps — RESOLVED via RACI Matrix

*(Unchanged from v2 — RACI matrix is stable)*

| Activity | Experimental Designer | Team 4 BioStats | QA Statistical Rigor |
|----------|----------------------|-----------------|---------------------|
| Power analysis for NEW experiment | **R** | C | I |
| Power analysis for EXISTING data | I | **R** | I |
| Statistical method selection | I | **R** | C |
| Multiple testing correction | I | **R** | **A** (audits) |
| Effect size assessment | I | **R** | **A** (audits) |
| Control group design | **R** | C | I |
| Confounder identification | **R** | C | I |
| Protocol specification | **R** | I | I |
| Pseudoreplication detection | I | C | **R** |
| Overfitting risk assessment | I | C | **R** |

| Activity | Knowledge Manager | Ambiguity Engine |
|----------|------------------|------------------|
| Literature search | **R** | I |
| Evidence aggregation | **R** | C |
| Contradiction classification | I | **R** |
| RCMXT scoring | Provides data (**R**) | Computes score (**R**) |
| Resolution hypotheses | I | **R** |
| Novelty checking | **R** | C |
| Memory storage | **R** | I |

### Issue 7: Timeline — RESOLVED (18 weeks, rebalanced in v3)

See updated Phased Roadmap below.

### Issue 8: Agent Prompt Engineering — RESOLVED

**Agent Specification Template** (every agent must define):

```yaml
# agent_spec.yaml — template for each agent
agent_id: "t02_transcriptomics"
display_name: "Transcriptomics & Single-Cell Specialist"
tier: 2
division: "wet_to_dry"
model: "sonnet"

system_prompt: |
  You are a transcriptomics and single-cell biology expert within the BioTeam-AI
  research team. Your role is to...
  [500-2000 words, stored in agents/prompts/t02_transcriptomics.md]

output_schema:
  type: "AnalysisOutput"
  fields:
    - finding: str           # Key biological finding
    - evidence: list[str]    # Supporting evidence
    - confidence: float      # 0.0-1.0
    - methods_used: list[str]
    - code_blocks: list[CodeBlock]  # Generated code if applicable
    - caveats: list[str]     # Limitations and assumptions
    - next_steps: list[str]  # Recommended follow-ups

tools:
  - knowledge_manager_query
  - literature_search
  - code_generate
  - request_execution
  - report_to_director

mcp_access:
  - bioRxiv
  - hugging_face

few_shot_examples:
  - input: "Analyze DEGs from cfRNA data at R+1 vs baseline"
    output: { ... example structured output ... }

failure_modes:
  - insufficient_data: "Request more data from Director"
  - ambiguous_question: "Ask Director for clarification"
  - out_of_scope: "Redirect to appropriate specialist team"

version: "1.0.0"
changelog:
  - "1.0.0: Initial agent specification"
```

### Issue 9: PubMed + medRxiv Access — RESOLVED *(v3: medRxiv added)*

```python
class PubMedClient:
    """Direct NCBI E-utilities integration."""
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    async def search(self, query: str, max_results: int = 20) -> list[Article]: ...
    async def fetch_abstract(self, pmid: str) -> str: ...
    async def fetch_full_text(self, pmcid: str) -> str | None: ...
```

Available MCP + custom integrations:
- **bioRxiv** (MCP — preprint search, feeds Shadow Mining)
- **medRxiv** (MCP — same API as bioRxiv, clinical/translational preprints) *(NEW in v3)*
- ChEMBL (MCP — compound/drug data)
- Clinical Trials (MCP — feeds Trial Failure Mining)
- ICD-10 Codes (MCP — diagnosis codes)
- Hugging Face (MCP — models, papers)
- Slack (MCP — notifications)
- **PubMed (custom — NCBI E-utilities)**
- **Google Scholar (custom — SerpAPI or Scholarly, optional)**

### Issue 10: R&D vs Engineering — RESOLVED

Phase 3 split into 3a (Engineering) and 3b (R&D). See updated roadmap.

### Issue 11: Missing Operational Details — RESOLVED + Enhanced *(v3)*

| Item | Solution |
|------|----------|
| **API rate limiting** | Token bucket per model tier: Opus 40 RPM, Sonnet 80 RPM, Haiku 200 RPM. Queue overflow → delayed retry |
| **Background tasks** | Phase 1: `asyncio.TaskGroup`. Phase 2+: Celery + Redis *(v3: phased)* |
| **Real-time dashboard** | **SSE-only** from FastAPI. No WebSocket. *(v3: contradiction resolved)* |
| **Error handling** | 3-layer: (1) Pydantic validation, (2) retry with backoff (max 3), (3) escalate to Director |
| **Prompt versioning** | Git-tracked markdown files in `agents/prompts/`. Spec YAML references version |
| **Raw data pipeline** | Data files stored on local filesystem or HPC. Agents reference by path, never inline. `DataRegistry` tracks metadata |
| **DB migration trigger** | SQLite until: >10 concurrent users OR >100k episodic events OR shared server deploy |
| **Graceful degradation** | Agent fails 3x → mark `unavailable`, Research Director reroutes or flags for human |
| **Health checks** | `/health` endpoint checks all dependencies, surfaces status on dashboard *(NEW in v3)* |
| **Backups** | Daily automated SQLite backup + ChromaDB snapshot to dated directory *(NEW in v3)* |
| **API versioning** | All endpoints under `/api/v1/`, enables independent frontend/backend evolution *(NEW in v3)* |
| **Dev modes** | `make dev-minimal` (FastAPI + SQLite) vs. `make dev-full` (all services) *(NEW in v3)* |

---

## Agent Inventory (15 LLM agents + 2 hybrid engines)

*(Unchanged from v2 — agent roster is stable)*

### Tier 1: Strategic (3 LLM agents)

| Agent | Model | Reports To | Key Function |
|-------|-------|-----------|--------------|
| **Research Director** | Opus/Sonnet dual-mode *(v3)* | Director (Human) | Decomposes questions, assigns teams, synthesizes, maintains research state graph |
| **Project Manager** | Haiku | Research Director | Task tracking, timeline, dashboard state, resource conflicts |
| **Knowledge Manager** | Sonnet | Research Director | Semantic + episodic memory, literature synthesis, novelty checking |

### Core Engines (2 hybrid: code + LLM)

| Engine | LLM Model | Key Function |
|--------|-----------|--------------|
| **Ambiguity Resolution Engine** | Sonnet | Contradiction Mapper + RCMXT scoring + 5-type taxonomy |
| **Negative Results Module** | Sonnet | Shadow mining, preprint deltas, trial failures, internal lab KB |

### Tier 2: Domain Experts (10 LLM agents)

| Agent | Model | Division | Key Function |
|-------|-------|----------|-------------|
| **Experimental Designer** | Sonnet | Cross-cutting | Power analysis for new experiments, control design, confounder ID, protocol specs |
| **Integrative Biologist** | Sonnet | Cross-cutting | Cross-omics interpretation, discordance hypotheses, mechanism linking |
| **[1] Genomics & Epigenomics** | Sonnet | Wet-to-Dry | Variant calling, ChIP-seq, ATAC-seq, methylation |
| **[2] Transcriptomics & Single-Cell** | Sonnet | Wet-to-Dry | RNA-seq, scRNA-seq, cfRNA, spatial, DEG analysis |
| **[3] Proteomics & Metabolomics** | Sonnet | Wet-to-Dry | Mass spec, protein networks, metabolic pathways |
| **[4] Biostatistics** | Sonnet | Computation | Statistical method selection, analysis execution, power analysis on existing data |
| **[5] Machine Learning & DL** | Sonnet | Computation | Predictive modeling, LLM fine-tuning, model evaluation |
| **[6] Systems Biology & Networks** | Sonnet | Computation | GSEA, pathway analysis, GRNs, dynamical modeling |
| **[7] Structural Biology** | Sonnet | Computation | AlphaFold, molecular docking, MD simulation |
| **[8] Scientific Communication** | Sonnet | Translation | Manuscripts, figures, reviewer responses |
| **[9] Grant Writing & Funding** | Opus | Translation | NIH/NASA/NSF proposals, specific aims, budget |
| **[10] Data Engineering** | Haiku | Translation | Nextflow/Snakemake, Docker, HPC, databases |

### Tier 3: QA (3 LLM agents — independent)

| Agent | Model | Reports To | Key Function |
|-------|-------|-----------|-------------|
| **Statistical Rigor** | Sonnet | Director | MTC audit, effect sizes, overfitting risk, pseudoreplication detection |
| **Biological Plausibility** | Sonnet | Director | Pathway connectivity, evolutionary conservation, artifact detection |
| **Reproducibility & Standards** | Haiku | Director | FAIR, MINSEQE/MIAME, code audit, figure standards (checklist-based) |

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

### RCMXT Evidence Confidence Scoring

Every biological claim receives a 5-axis vector `[R, C, M, X, T]` scored 0.0–1.0:

| Axis | Measures | High (→1.0) | Low (→0.0) |
|------|---------|-------------|------------|
| **R** (Reproducibility) | Independent replications | ≥3 labs confirmed | Single study |
| **C** (Condition Specificity) | Generalizability | Cross-species, cross-condition | One cell line, one condition |
| **M** (Methodological Robustness) | Study design quality | Blinded, powered, appropriate stats | n<5, no correction |
| **X** (Cross-Omics Consistency) | Multi-layer agreement | mRNA↑ + protein↑ + functional↑ | mRNA↑ but protein unchanged |
| **T** (Temporal Stability) | Evidence durability | Consistent across decades | Recent, unreplicated |

### RCMXT Calibration Protocol *(v3: enhanced)*

**Phase A: Establish Inter-Expert Baseline**
1. Recruit 3-5 domain experts (lab colleagues, collaborators)
2. Each scores the same 50 well-characterized biological claims on all 5 axes
3. Compute pairwise inter-expert agreement (Pearson r per axis)
4. This becomes the **ceiling** — LLM cannot be expected to exceed expert consensus

**Phase B: LLM Calibration**
1. Run RCMXT scorer on each of the 50 claims, 5 times (measure consistency)
2. Target: LLM-vs-expert Pearson r ≥ inter-expert r (or r > 0.7, whichever is lower)
3. Target: intra-run std < 0.15 per axis
4. If below threshold: adjust scoring prompt with calibration examples

**Phase C: X-Axis Empty-Data Handling *(NEW in v3)***
- Most published studies are single-omics (~80-85% of literature)
- X-axis scoring must distinguish three states:
  1. **Multi-omics data agrees** → X = 0.7-1.0
  2. **Multi-omics data contradicts** → X = 0.0-0.3
  3. **No multi-omics data available** → X = NULL (not 0.5!)
- NULL X scores displayed as "—" in radar charts, excluded from composite scores
- When aggregating RCMXT across claims: use 4-axis average for claims with NULL X

**Phase D: Ablation Study (for publication) *(NEW in v3)***
- Compare full RCMXT vs. each axis removed (5 ablations)
- Compare vs. baselines: single-score confidence, majority vote, no scoring
- Report: which axes contribute most to discrimination between reliable vs. unreliable claims
- This data feeds the methods paper (Nature Methods / NeurIPS target)

**Maintenance:** Re-calibrate quarterly as new evidence enters the system.

### Hybrid Implementation

```python
# Deterministic layer (no LLM)
def extract_study_metadata(paper: Paper) -> StudyMetadata:
    """Extract organism, cell_type, n, platform from structured fields."""

def count_independent_replications(claim: str, evidence: list[Evidence]) -> int:
    """Count distinct research groups confirming the claim."""

def check_omics_layers(claim: str, evidence: list[Evidence]) -> OmicsLayerStatus:
    """Check which omics layers support the claim. Returns availability + agreement."""

class OmicsLayerStatus(BaseModel):
    layers_available: list[Literal["genomic", "transcriptomic", "proteomic", "metabolomic", "functional"]]
    layers_agreeing: list[str]
    layers_contradicting: list[str]
    multi_omics_available: bool   # True if ≥2 layers present

# LLM layer (Sonnet)
async def classify_contradiction(evidence_a: Evidence, evidence_b: Evidence) -> ContradictionType:
    """LLM classifies which of 5 taxonomy types applies."""

async def generate_resolution_hypothesis(matrix: ContradictionMatrix) -> list[ResolutionHypothesis]:
    """LLM proposes explanations for the contradiction."""
```

---

## Core Innovation II: Negative Results Integration Module

### Four Data Sources (with maturity levels)

| Source | Maturity | Phase | Method |
|--------|----------|-------|--------|
| **Internal Lab KB** | Engineering | Phase 1 | CRUD + search. Structured input from researcher. |
| **Clinical Trial Failures** | Engineering | Phase 2 | ClinicalTrials.gov MCP query + LLM interpretation |
| **Shadow Literature** | R&D | Phase 3b | **Constrained 30-phrase vocabulary** *(v3)* + LLM context interpretation on full-text (PMC OA only) |
| **Preprint Deltas** | R&D | Phase 3b | bioRxiv/medRxiv API version history + text diff + LLM interpretation |

### Shadow Mining: Constrained Vocabulary *(NEW in v3)*

Start with 30 high-precision phrases instead of broad regex. Expand based on precision/recall measurements.

**Tier 1 — High Precision (expect > 90% true positive):**
```
"we were unable to replicate"
"failed to reproduce"
"could not confirm"
"no statistically significant difference"
"did not reach significance"
"contrary to our hypothesis"
"negative result"
"no effect was observed"
"the effect was not significant"
"we found no evidence"
```

**Tier 2 — Moderate Precision (expect 60-80% true positive, need LLM disambiguation):**
```
"contrary to expectations"
"inconsistent with previous reports"
"results were inconclusive"
"did not support the hypothesis"
"the association was not significant"
"we observed no correlation"
"failed to detect"
"below the detection limit"
"not reproducible across"
"these findings contradict"
```

**Tier 3 — Context-Dependent (always require LLM interpretation):**
```
"limited by sample size"
"the effect was modest"
"warrants further investigation"
"preliminary and should be interpreted with caution"
"power was insufficient"
"confounded by"
"artifacts may explain"
"alternative explanation"
"may be due to batch effects"
"sensitivity analysis revealed"
```

**Protocol:** Start with Tier 1 only. Measure precision. If > 0.85, add Tier 2. If combined > 0.70, add Tier 3 with mandatory LLM disambiguation.

### MVP (Phase 1): Internal Lab KB Only

```python
class NegativeResult(BaseModel):
    id: str
    claim: str                          # What was attempted
    outcome: str                        # What happened
    conditions: dict                    # Under what conditions
    source: Literal["internal", "clinical_trial", "shadow", "preprint_delta"]
    confidence: float                   # 0.0-1.0
    n_attempts: int
    failure_category: Literal["protocol", "reagent", "analysis", "biological"]
    implications: list[str]
    added_by: str                       # "human" or agent_id
    created_at: datetime
    tags: list[str]                     # For searchability
```

---

## Workflow Templates

### Direct Query (NEW in v3)
```
CLASSIFY (Research Director, Sonnet)
  → If simple: LOOKUP (Knowledge Manager, Sonnet)
    → ANSWER (Specialist, Sonnet — 1 agent only)
    → RESPOND to Director via Dashboard (SSE push)
  → If complex: ROUTE to W1-W6
```

### W1: Literature Review
```
SCOPE → DECOMPOSE (Research Director, Opus)
  → SEARCH (Knowledge Manager, Sonnet + PubMed/bioRxiv/medRxiv APIs)
  → SCREEN (Specialist, Sonnet)
  → EXTRACT (Specialist, structured JSON output)
  → CONTRADICTION MAP (Ambiguity Engine: code + Sonnet)
  → RCMXT SCORE (Ambiguity Engine: code + Sonnet)
  → NEGATIVE CHECK (NR Module: Internal Lab KB query)
  → SYNTHESIZE (Research Director, Opus)
  → NOVELTY CHECK (Knowledge Manager, Sonnet)
  → REPORT to Director via Dashboard (SSE push)
  ↺ LOOP (max 3): contradictions → re-search with resolution variables
  ⏸ HUMAN CHECKPOINT: after SYNTHESIZE (Director reviews before final report)
```

### W2: Hypothesis Generation (Generate-Debate-Evolve)
```
CONTEXTUALIZE (Knowledge Manager + NR Module)
  → GENERATE (Teams 1-7 in parallel, Sonnet × 7)
  → NEGATIVE FILTER (NR Module)
  → DEBATE (QA Tier challenges each, Sonnet × 3)
  → RANK (Research Director, Opus: merit×0.30 + feasibility×0.25 + novelty×0.20 + alignment×0.15 + data×0.10)
  → EVOLVE (Top 3 refined, cross-pollinated, Sonnet)
  → RCMXT PROFILE (Ambiguity Engine)
  → PRESENT to Director (SSE push)
  ↺ LOOP (max 3): Director feedback → refine → re-rank
  ⏸ HUMAN CHECKPOINT: after RANK (Director selects top hypotheses before EVOLVE)
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
OUTLINE (Research Director + Director) → ASSEMBLE (Knowledge Manager)
  ⏸ HUMAN CHECKPOINT: Director approves outline
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

## NEW: Cold Start Protocol *(v3)*

The system must deliver value on first run. Empty memory stores and uncalibrated scoring make the first experience underwhelming. This protocol seeds the system before the first real workflow.

```
┌─────────────────────────────────────────────────────────────────┐
│                    COLD START PROTOCOL                            │
│                    (Run once at first deployment)                 │
│                                                                  │
│  Step 1: Seed Knowledge Manager (~30 min)                        │
│  ├── Import researcher's publication list (Google Scholar/ORCID) │
│  ├── Fetch abstracts for all publications via PubMed             │
│  ├── Store in semantic memory (ChromaDB)                         │
│  └── Build initial topic graph from publication keywords          │
│                                                                  │
│  Step 2: Seed Internal Lab KB (~15 min, manual)                  │
│  ├── Dashboard wizard: "What experiments didn't work?"            │
│  ├── Structured form: claim, outcome, conditions, category       │
│  ├── Target: 10-20 entries from researcher's experience          │
│  └── These feed the Negative Results Module immediately          │
│                                                                  │
│  Step 3: RCMXT Calibration (~2 hr, semi-automated)              │
│  ├── Load 50 pre-curated benchmark claims (shipped with system)  │
│  │   └── 25 spaceflight biology + 25 general molecular biology   │
│  ├── Run scorer 5x per claim                                    │
│  ├── Compare to expert reference scores (shipped with system)    │
│  ├── Report calibration metrics                                  │
│  └── If below threshold: auto-adjust with top-5 calibration      │
│       examples added to scoring prompt                            │
│                                                                  │
│  Step 4: Smoke Test (~10 min)                                    │
│  ├── Run Direct Query: "What is spaceflight-induced anemia?"     │
│  ├── Verify: response uses seeded knowledge                      │
│  ├── Run W1 stub: Literature search only (no full workflow)      │
│  └── Report: system operational, estimated costs                 │
│                                                                  │
│  Deliverable: Cold Start Report                                  │
│  ├── Knowledge base: N publications seeded, N topics extracted   │
│  ├── Lab KB: N negative results entered                          │
│  ├── RCMXT calibration: Pearson r per axis, pass/fail            │
│  └── Smoke test: response quality, cost, latency                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## NEW: LLM Abstraction Layer *(v3)*

To reduce Claude Agent SDK vendor lock-in, a thin adapter wraps the SDK. All agents call through the adapter, never the SDK directly.

```python
# backend/app/llm/adapter.py
from abc import ABC, abstractmethod

class LLMAdapter(ABC):
    """Thin abstraction over LLM provider. All agents use this interface."""

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        model_tier: Literal["opus", "sonnet", "haiku"],
        output_schema: type[BaseModel] | None = None,
        tools: list[Tool] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse: ...

    @abstractmethod
    async def complete_with_tools(
        self,
        messages: list[Message],
        model_tier: Literal["opus", "sonnet", "haiku"],
        tools: list[Tool],
        max_iterations: int = 10,
    ) -> AgentOutput: ...

class ClaudeAdapter(LLMAdapter):
    """Primary implementation using Claude Agent SDK."""
    # Maps model_tier to actual model IDs
    MODEL_MAP = {
        "opus": "claude-opus-4-6",
        "sonnet": "claude-sonnet-4-5-20250929",
        "haiku": "claude-haiku-4-5-20251001",
    }

# Future (if needed):
# class OpenAIAdapter(LLMAdapter): ...
# class LocalAdapter(LLMAdapter): ...  # For testing
```

**Benefits:**
- All agent code uses `LLMAdapter`, not Claude SDK directly
- Model tier names (`opus`, `sonnet`, `haiku`) are abstracted from version IDs
- Easy to swap model versions (just update `MODEL_MAP`)
- Enables mock adapter for testing (no real API calls)
- If Claude pricing changes dramatically, alternative providers can be evaluated

**Scope limit:** This is a thin adapter, not a full multi-provider framework. Claude remains the primary and recommended provider.

---

## Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Frontend** | Next.js 15 + Tailwind CSS + shadcn/ui | Dashboard, SSR |
| **Backend API** | FastAPI (Python) | Async, Pydantic, AI ecosystem |
| **LLM Runtime** | LLMAdapter → Claude Agent SDK *(v3: abstracted)* | Claude-only, native MCP, swappable |
| **Orchestration (Phase 1)** | Python asyncio.TaskGroup *(v3: simplified)* | In-process, no extra infra |
| **Orchestration (Phase 2+)** | Celery + Redis | Async job queue, parallel agent execution |
| **Real-time** | Server-Sent Events (SSE) only *(v3: no WebSocket)* | Dashboard live updates, simpler |
| **Vector DB** | ChromaDB (dev) → Qdrant (prod) | Semantic memory |
| **State DB** | SQLite (dev) → PostgreSQL (prod) | Tasks, episodic memory, NR KB |
| **Code Sandbox** | Docker containers | Isolated bioinformatics code execution |
| **Monitoring** | Langfuse (self-hosted) | Agent tracing, cost tracking |
| **Protocol** | MCP | Tool integration standard |
| **Auth** | NextAuth.js + JWT | Hybrid deployment security |
| **Deploy** | Docker Compose (local) + Vercel (dashboard) | Hybrid |
| **Literature** | NCBI E-utilities + bioRxiv/medRxiv API *(v3: +medRxiv)* | PubMed + preprints |

---

## Project Structure

```
AI_Scientist_team/
├── README.md
├── pyproject.toml
├── docker-compose.yml
├── .env.example
├── Makefile                           # make dev-minimal / make dev-full (v3)
│
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI app + SSE + /health endpoint
│   │   ├── config.py                 # Settings, model tiers, budgets
│   │   ├── cost_tracker.py           # Token/cost accounting + validation gate
│   │   │
│   │   ├── llm/                      # LLM abstraction layer (v3)
│   │   │   ├── adapter.py            # LLMAdapter ABC + ClaudeAdapter
│   │   │   ├── mock_adapter.py       # For testing (no API calls)
│   │   │   └── cost_estimator.py     # Pre-call cost estimation
│   │   │
│   │   ├── models/                   # Pydantic data models
│   │   │   ├── agent.py             # Agent, Team, Division
│   │   │   ├── task.py              # Task, Project
│   │   │   ├── workflow.py          # WorkflowInstance, WorkflowStep (v3: expanded)
│   │   │   ├── memory.py           # Semantic/Episodic memory
│   │   │   ├── evidence.py         # RCMXT, ContradictionMatrix, OmicsLayerStatus (v3)
│   │   │   ├── negative_result.py  # NegativeResult, FailedProtocol
│   │   │   ├── messages.py         # AgentMessage, ContextPackage
│   │   │   └── code_execution.py   # CodeBlock, ExecutionResult
│   │   │
│   │   ├── agents/
│   │   │   ├── base.py             # BaseAgent (uses LLMAdapter, schema validation, retry)
│   │   │   ├── registry.py         # Agent registry + health status
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
│   │   │   │   ├── research_director.yaml ... qa_reproducibility.yaml
│   │   │   ├── research_director.py   # Dual-mode: Sonnet routing + Opus synthesis (v3)
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
│   │   ├── engines/                 # Hybrid engines (code + LLM)
│   │   │   ├── ambiguity/
│   │   │   │   ├── contradiction_mapper.py
│   │   │   │   ├── rcmxt_scorer.py
│   │   │   │   ├── resolution_engine.py
│   │   │   │   └── taxonomy.py
│   │   │   └── negative_results/
│   │   │       ├── shadow_miner.py  # Constrained vocabulary approach (v3)
│   │   │       ├── preprint_delta.py
│   │   │       ├── trial_failure.py
│   │   │       └── internal_kb.py
│   │   │
│   │   ├── workflows/
│   │   │   ├── engine.py           # WorkflowEngine: state machine (v3: detailed)
│   │   │   ├── runners/            # Execution backends (v3)
│   │   │   │   ├── async_runner.py  # Phase 1: asyncio.TaskGroup
│   │   │   │   └── celery_runner.py # Phase 2+: Celery
│   │   │   ├── direct_query.py     # Direct Query mode (v3)
│   │   │   ├── w1_literature.py ... w6_ambiguity.py
│   │   │
│   │   ├── memory/
│   │   │   ├── semantic.py         # ChromaDB
│   │   │   ├── episodic.py         # SQLite/Postgres event log
│   │   │   └── literature.py       # Citation tracking
│   │   │
│   │   ├── integrations/           # External API clients
│   │   │   ├── pubmed.py           # NCBI E-utilities
│   │   │   └── scholar.py          # Google Scholar (optional)
│   │   │
│   │   ├── execution/              # Code sandbox
│   │   │   ├── router.py           # Route to Docker/HPC/human
│   │   │   ├── docker_runner.py    # Local Docker execution
│   │   │   ├── hpc_runner.py       # SSH + Slurm submission (Phase 4)
│   │   │   └── containers/         # Dockerfiles for bio tools
│   │   │       ├── Dockerfile.rnaseq
│   │   │       ├── Dockerfile.singlecell
│   │   │       └── Dockerfile.genomics
│   │   │
│   │   ├── mcp/
│   │   │   └── registry.py        # Tool registry per agent
│   │   │
│   │   ├── api/
│   │   │   ├── v1/                # API versioning (v3)
│   │   │   │   ├── agents.py
│   │   │   │   ├── tasks.py
│   │   │   │   ├── workflows.py
│   │   │   │   ├── memory.py
│   │   │   │   ├── evidence.py
│   │   │   │   ├── dashboard.py
│   │   │   │   ├── direct_query.py  # Direct Query endpoint (v3)
│   │   │   │   └── sse.py
│   │   │   └── health.py          # /health endpoint (v3)
│   │   │
│   │   ├── cold_start/            # Cold Start protocol (v3)
│   │   │   ├── seeder.py          # Knowledge + Lab KB seeding
│   │   │   ├── calibrator.py      # RCMXT calibration runner
│   │   │   ├── smoke_test.py      # Automated smoke test
│   │   │   └── benchmarks/        # Shipped calibration data
│   │   │       ├── rcmxt_50_claims.json
│   │   │       ├── rcmxt_expert_scores.json
│   │   │       └── shadow_mining_phrases.json
│   │   │
│   │   ├── backup/                # Backup/restore (v3)
│   │   │   └── backup_manager.py  # Daily SQLite + ChromaDB snapshots
│   │   │
│   │   └── db/
│   │       ├── database.py
│   │       └── migrations/        # Alembic
│   │
│   └── tests/
│       ├── test_agents/
│       ├── test_engines/
│       ├── test_workflows/
│       ├── test_execution/
│       ├── test_cold_start/       # Cold start tests (v3)
│       ├── test_llm/              # Adapter + mock tests (v3)
│       └── test_api/
│
├── frontend/                       # Next.js Dashboard
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx           # Mission Control (Phase 1 core panel)
│   │   │   ├── projects/          # Project Board (Phase 1 core panel)
│   │   │   ├── lab-kb/            # Internal Lab KB (Phase 1 core panel)
│   │   │   ├── teams/             # Team roster (Phase 2 — progressive)
│   │   │   ├── quality/           # QA dashboard (Phase 2 — progressive)
│   │   │   ├── evidence/          # RCMXT explorer (Phase 3 — progressive)
│   │   │   ├── knowledge/         # Knowledge browser (Phase 4 — progressive)
│   │   │   └── analytics/         # Cost + productivity (Phase 4 — progressive)
│   │   ├── components/
│   │   │   ├── dashboard/
│   │   │   ├── agents/
│   │   │   ├── tasks/
│   │   │   ├── workflows/
│   │   │   │   └── WorkflowIntervention.tsx  # Intervention UI (v3)
│   │   │   ├── evidence/          # RCMXT radar charts, contradiction viz
│   │   │   ├── cost/              # Cost tracking widgets
│   │   │   └── cold-start/        # Cold start wizard (v3)
│   │   │       └── LabKBWizard.tsx
│   │   ├── hooks/
│   │   │   └── useSSE.ts          # SSE subscription hook
│   │   └── lib/
│   └── package.json
│
├── scripts/                        # Utility scripts (v3)
│   ├── backup.sh                  # Daily backup cron script
│   └── cold_start.py              # CLI runner for cold start protocol
│
└── docs/
    ├── architecture.md
    ├── workflow-engine.md          # Detailed engine design (v3)
    ├── agent-specs/
    ├── workflow-specs/
    ├── benchmarks/                 # For publication (v3)
    │   ├── rcmxt_calibration_results.md
    │   └── shadow_mining_evaluation.md
    └── proposal/
        └── BioTeam-AI_Proposal.docx
```

---

## Phased Development Roadmap (18 weeks, rebalanced)

### Phase 1: Foundation + First Value (Week 1-5)

**Week 1-2: Scaffolding + Data Models + LLM Layer**
- [ ] Project scaffolding (monorepo, FastAPI, Next.js, Docker Compose)
- [ ] Makefile with `dev-minimal` (FastAPI + SQLite) and `dev-full` modes
- [ ] LLM abstraction layer (`LLMAdapter` + `ClaudeAdapter` + `MockAdapter`)
- [ ] All Pydantic models (agent, task, workflow, evidence, negative_result, messages, code_execution)
- [ ] SQLite database + Alembic migrations
- [ ] `/health` endpoint
- [ ] `/api/v1/` routing structure
- [ ] CostTracker implementation (with `record_actual` + `get_accuracy_report`)
- [ ] AgentMessage transport layer (sync + asyncio modes only — no Redis yet)
- [ ] Backup manager (daily SQLite copy + ChromaDB snapshot)

**Week 3-4: Core Agents + Workflow Engine**
- [ ] BaseAgent class (uses LLMAdapter, schema validation, retry logic, Langfuse tracing)
- [ ] Agent spec YAML template + prompt markdown template
- [ ] Research Director agent (dual-mode: Sonnet routing + Opus synthesis)
- [ ] Knowledge Manager agent (Sonnet) — ChromaDB integration
- [ ] Project Manager agent (Haiku)
- [ ] PubMed integration (NCBI E-utilities client)
- [ ] Workflow engine: `WorkflowInstance` state machine + `AsyncWorkflowRunner`
- [ ] Direct Query mode implementation

**Week 5: First Specialists + Dashboard + Cold Start**
- [ ] Team 2 (Transcriptomics) — prompt + spec + tests
- [ ] Team 10 (Data Engineering) — prompt + spec + tests
- [ ] RCMXT scoring engine (deterministic + LLM layers + X-axis NULL handling)
- [ ] Internal Lab KB (NR Module, engineering portion)
- [ ] Dashboard: 3 core panels (Mission Control, Projects, Lab KB) — SSE-connected
- [ ] Cold Start protocol (seeder + calibrator + smoke test)
- [ ] W1: Literature Review workflow (end-to-end)
- [ ] **Milestone: Run Cold Start + first real literature review**
- [ ] **Cost Validation Gate: Compare W1 actual cost vs. $1-3 estimate. Adjust budgets if actual > 2x.**

### Phase 2: Ambiguity Engine + QA + Scale-Up (Week 6-9)

**Week 6: Infrastructure Scale-Up**
- [ ] Redis + Celery setup
- [ ] `CeleryWorkflowRunner` (same WorkflowStep definitions, different executor)
- [ ] Code Sandbox: Docker runner for local execution
- [ ] Dashboard: +Teams panel, +Quality panel (progressive disclosure)

**Week 7-8: Ambiguity Engine**
- [ ] Contradiction Mapper (deterministic metadata extraction + Sonnet classification)
- [ ] RCMXT calibration: inter-expert baseline (Phase A) + LLM calibration (Phase B)
- [ ] Resolution hypothesis generator
- [ ] Contradiction visualization component (frontend)
- [ ] Clinical Trial Failure Miner (ClinicalTrials.gov MCP)

**Week 9: QA Tier + More Specialists**
- [ ] 3 QA agents (Statistical Rigor, Biological Plausibility, Reproducibility)
- [ ] Teams 4 (BioStats), 5 (ML/DL), 6 (Systems Bio)
- [ ] W3: Data Analysis workflow (end-to-end)
- [ ] Workflow Intervention UI component
- [ ] **Milestone: Run first data analysis workflow with QA validation**
- [ ] **Cost Validation Gate: Compare W3 actual cost vs. $2-5 estimate.**

### Phase 3a: Full Biology (Week 10-12) — Engineering

- [ ] Teams 1 (Genomics), 3 (Proteomics), 7 (Structural Bio)
- [ ] Experimental Designer agent
- [ ] Integrative Biologist agent
- [ ] W2: Hypothesis Generation with debate pattern (uses Celery for 7-agent parallel)
- [ ] W6: Ambiguity Resolution standalone workflow
- [ ] Dashboard: +Evidence Explorer panel
- [ ] **Milestone: Run first hypothesis generation with debate**
- [ ] **Cost Validation Gate: Compare W2 actual cost vs. $3-8 estimate.**

### Phase 3b: Negative Results R&D (Week 13-14) — Research

- [ ] Shadow Literature Miner prototype
  - Start with Tier 1 constrained vocabulary (10 phrases) on PMC Open Access
  - Success criteria: precision > 0.85 on Tier 1; if pass, add Tier 2, target combined precision > 0.70
  - If below threshold: ship Tier 1 only (high-precision, low-recall), defer Tier 2-3
- [ ] Preprint Delta Analyzer prototype (bioRxiv/medRxiv version history)
  - Success criteria: correctly identifies > 60% of removed figures/conclusions in 20 test cases
  - If below threshold: defer, rely on Internal Lab KB + Trial Failures
- [ ] RCMXT ablation study (for publication): 5 ablations + 3 baselines
- [ ] Integrate successful prototypes into NR Module
- [ ] **Milestone: NR Module evaluation report + RCMXT ablation results**

### Phase 4: Translation + Production (Week 15-18)

**Week 15-16: Translation Teams + HPC**
- [ ] Teams 8 (SciComm), 9 (Grants)
- [ ] W4: Manuscript Writing workflow
- [ ] W5: Grant Proposal workflow
- [ ] HPC runner (SSH + Slurm) — *(moved from Phase 3a in v3)*
- [ ] Dashboard: +Knowledge Browser, +Analytics panel

**Week 17-18: Production Hardening**
- [ ] Auth system (NextAuth.js + JWT)
- [ ] Docker Compose full deployment
- [ ] Vercel deployment for dashboard (hybrid mode)
- [ ] Comprehensive testing (unit + integration + E2E with Playwright)
- [ ] Error handling audit (all failure modes documented)
- [ ] Security audit (RBAC, secrets, audit log)
- [ ] **Milestone: Full system demo on spaceflight anemia case study**
- [ ] **Final Cost Report: All workflows actual vs. estimated, cumulative spend**

---

## Communication Pattern

```
Director ←→ Dashboard (SSE) ←→ FastAPI (/api/v1/) ←→ Research Director
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
                                    (via AgentMessage)
                                    Phase 1: asyncio
                                    Phase 2+: + Celery/Redis
```

**Transport rules:**
1. Direct Query → sync function call (Research Director + 1 specialist)
2. Single-agent workflow step → sync function call (no overhead)
3. Multi-agent parallel → asyncio.TaskGroup (Phase 1) / Celery (Phase 2+)
4. Long-running workflow → Celery task chain with checkpointing (Phase 2+)
5. Dashboard updates → SSE push on every workflow step completion
6. Large data → file path reference, never inline in AgentMessage

**Context injection:** Each agent receives a `ContextPackage` assembled by the workflow engine:
```python
class ContextPackage(BaseModel):
    """What an agent receives at invocation."""
    task_description: str
    relevant_memory: list[MemoryItem]      # From Knowledge Manager
    prior_step_outputs: list[AgentOutput]  # From previous workflow steps
    negative_results: list[NegativeResult] # Relevant NR Module results
    rcmxt_context: list[RCMXTScore] | None # If claim under investigation
    constraints: dict                       # Budget remaining, deadline, etc.
```

---

## Security

- OAuth 2.0 + JWT for API auth
- RBAC: Director full access; agents scoped per tier/team
- All agent actions logged with audit trail (Langfuse)
- Kill switch: Director halts any workflow from dashboard
- MCP tool access scoped per agent (defined in agent spec YAML)
- Secrets via .env, never hardcoded
- Code sandbox: Docker containers with no network access (except HPC runner)
- Hybrid deploy: sensitive data stays local, dashboard accessible via Vercel
- Daily automated backups of SQLite + ChromaDB *(NEW in v3)*
- API versioning prevents accidental breaking changes *(NEW in v3)*

---

## NEW: Publication Strategy *(v3)*

### Framing

Position as **"a generalizable framework for biology-aware multi-agent research assistance"** — not "a personal tool." The architecture (RCMXT, contradiction taxonomy, NR module) is transferable to any biology research group.

### Differentiation from Existing Tools

| Feature | Elicit | Consensus | Google AI Co-Scientist | **BioTeam-AI** |
|---------|--------|-----------|----------------------|----------------|
| Literature search | Yes | Yes | Yes | Yes |
| Claim extraction | Yes | Yes | Partial | Yes |
| Contradiction detection | No | No | Partial (debate) | **5-type taxonomy** |
| Multi-axis evidence scoring | No | Single score | No | **RCMXT (5 axes)** |
| Negative results integration | No | No | No | **4 data sources** |
| Multi-omics awareness | No | No | No | **X-axis + Integrative Biologist** |
| Hypothesis generation | No | No | Yes (Generate-Debate-Evolve) | Yes (adapted) |
| QA layer (independent) | No | No | Yes (review) | **3 specialized QA agents** |
| Code generation for analysis | No | No | Partial | **Full pipeline + sandbox** |

### Publishable Contributions

| Contribution | Target Venue | Data Required | Phase |
|-------------|-------------|---------------|-------|
| RCMXT scoring system + ablation study | Nature Methods / NeurIPS | 50 calibration claims, ablation results | 3b |
| 5-category contradiction taxonomy | Bioinformatics | 20 curated contradictions from spaceflight biology | 3a |
| Negative Results Integration Module | PLOS ONE / F1000 | Shadow mining precision/recall, trial failure analysis | 3b |
| Full system: BioTeam-AI framework | Nature Methods / Science | Spaceflight anemia end-to-end case study | 4 |
| Benchmark dataset: spaceflight biology contradictions | Scientific Data | 20 contradictions + 15 negative results + 10 multi-omics tasks | 4 |

### Benchmark Dataset Sharing Plan *(NEW in v3)*

All calibration and evaluation data will be published as a companion dataset:
- **RCMXT Calibration Set**: 50 claims + expert scores + LLM scores + ablation results
- **Contradiction Benchmark**: 20 spaceflight biology contradictions with taxonomy labels
- **Negative Results Corpus**: 15 curated negative results from spaceflight research
- **Multi-Omics Integration Tasks**: 10 cross-omics interpretation challenges

Format: JSON + README, hosted on Zenodo (DOI) and linked from paper.

---

## Verification Plan *(v3: expanded)*

1. **Unit tests**: Each agent, engine, workflow step, API endpoint, transport layer, LLM adapter
2. **Agent quality tests**: Each agent answers 10 domain-specific benchmark questions; evaluate output quality
3. **RCMXT calibration**: 50 benchmark claims, inter-expert baseline, LLM-vs-expert r ≥ inter-expert r, intra-run std < 0.15, X-axis NULL handling verified *(v3: enhanced)*
4. **RCMXT ablation**: 5 axis-removal ablations + 3 baselines, report per-axis contribution *(NEW in v3)*
5. **Engine tests**: Ambiguity Engine on 20 curated contradictions; NR Module on 15 known negative results
6. **Shadow Mining tests**: Tier 1 precision > 0.85, Tier 1+2 combined precision > 0.70 *(v3: tiered)*
7. **Integration tests**: End-to-end W1-W6 + Direct Query workflow execution with mock LLM responses
8. **Cost validation gates**: Actual vs. estimated cost comparison at each phase milestone *(NEW in v3)*
9. **Sandbox tests**: Code generation → execution → result parsing pipeline
10. **Workflow engine tests**: State transitions, loop detection (max_loops), budget enforcement (OVER_BUDGET state), human checkpoint (WAITING_HUMAN state), parallel fan-out/fan-in *(NEW in v3)*
11. **Cold start test**: Full cold start protocol on clean system, verify seeded data quality *(NEW in v3)*
12. **Health check test**: `/health` endpoint correctly reports all dependency statuses *(NEW in v3)*
13. **Dashboard E2E**: Playwright tests for 3 core panels (Phase 1) + progressive panels (Phase 2-4)
14. **Smoke test**: Real literature review on "spaceflight-induced anemia" through full pipeline
15. **Spaceflight Biology Benchmark**: 20 contradictions + 15 negative results + 10 multi-omics tasks
