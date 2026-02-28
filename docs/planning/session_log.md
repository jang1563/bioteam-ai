# BioTeam-AI — Planning Session Log

**Project:** BioTeam-AI (Personal AI Science Team for Biology Research)
**Owner:** JangKeun Kim, Weill Cornell Medicine
**Start Date:** 2026-02-16

---

## Session 1: Initial Planning (2026-02-16)

### Phase 1: Research & Requirements (Session 1a)

**User Request (Korean):**
- Build a personal AI Science Team with dashboard interface
- Review existing similar tools
- Focus on productivity, security, usability, scalability
- Multi-agent development with useful guides/prompts

**Research Conducted:**
- Existing AI team tools: CrewAI, AutoGen, LangGraph, MetaGPT, Sakana AI Scientist, Stanford Virtual Lab, Google AI Co-Scientist, NTT AI Constellation
- Claude Agent SDK, MCP protocol, security best practices
- Current project directory: empty (only .claude/settings.local.json)

**Key Decisions:**
- Claude-only LLM strategy
- English output (despite Korean prompts)
- Hybrid deployment (backend local, dashboard cloud)
- 10 biology sub-specializations
- Company-style organizational structure

### Phase 2: Organizational Design (Session 1b)

**Deliverables:**
- 10 biology expert specializations aligned with JangKeun's research
- Cross-functional roles (PI Agent, Scientific Critic, Knowledge Manager, etc.)
- Communication patterns (hub-and-spoke, event-driven)
- 5 workflow templates (Literature Review, Hypothesis Generation, Data Analysis, Manuscript Writing, Grant Proposal)
- Dashboard design with 6 panels

### Phase 3: BioTeam-AI Proposal Integration (Session 1c)

**Input:** BioTeam-AI_Proposal.docx — JangKeun's working paper defining:
- Ambiguity Resolution Engine (5-category contradiction taxonomy)
- RCMXT Evidence Confidence Scoring (5-axis vector)
- Negative Results Integration Module (4 data sources)
- Three-tier architecture (Strategic / Domain Expert / QA)
- Space anemia case study

### Phase 4: Plan v1 → v1 Review (Session 1d)

**Plan v1:** Merged proposal innovations with practical implementation plan.

**v1 Critical Review identified 11 issues:**
1. Engines vs Agents identity crisis
2. Division Leads undefined
3. Code execution gap
4. Agent-to-agent communication unspecified
5. Cost controls missing
6. Role overlaps (Exp Designer vs BioStats vs QA)
7. Timeline too aggressive (10 weeks)
8. Agent prompt engineering underspecified
9. PubMed access missing
10. Core innovations are research-hard (R&D vs Engineering)
11. Missing operational details (rate limiting, job queue, error handling, etc.)

### Phase 5: Plan v2 (Session 1e)

All 11 issues resolved. Key additions:
- Hybrid engine model (code + LLM) with explicit separation table
- Division Leads removed (18 → 15 agents)
- Code execution pipeline (CodeBlock → Docker/HPC/Human)
- AgentMessage + 3 transport modes (sync/async/queued)
- Model tier assignments with cost estimates
- RACI matrix for role overlaps
- 18-week timeline (extended from 10)
- Agent spec YAML template
- PubMed via NCBI E-utilities
- Phase 3a (Engineering) / 3b (R&D) split

### Phase 6: Multi-Perspective Review → Plan v3 (Session 1f)

**6 Expert Perspectives Applied:**
1. Software Architect — workflow engine design, SSE vs WebSocket, Phase 1 simplification
2. Biology Domain Expert — RCMXT calibration, X-axis handling, Shadow Mining precision
3. Solo Researcher UX — dashboard progressive disclosure, Direct Query, Cold Start
4. DevOps/Operations — dev modes, health checks, HPC timing, backups
5. Academic/Publication — framing, differentiation, ablation study, benchmark sharing
6. Cost/ROI — Research Director dual-mode, cost validation gates, SDK abstraction

**21 changes incorporated into v3.** See v2→v3 changelog in plan.

### Phase 7: v3 Critical Review (Session 1g)

**3 parallel deep analyses:**
1. Internal Consistency Review
2. Implementation Feasibility Review
3. Edge Cases & Failure Modes Review

**Results:** 53 raw issues → 34 unique after deduplication
- 3 BLOCKERS (must resolve before coding)
- 5 CRITICAL (undermine core value)
- 15 MAJOR (design changes needed)
- 6 MINOR (defer to Phase 2+)

**Top 3 Blockers:**
1. Claude Agent SDK is wrong tool → use Anthropic Client SDK
2. SSE + Vercel serverless incompatible → local-only or polling
3. Phase 1 W1 depends on Phase 2 components → define reduced "Phase 1 W1"

---

## Files Created

| File | Location | Description |
|------|----------|-------------|
| Plan v3 | `docs/planning/plan_v3.md` | Current implementation plan (935 lines) |
| v3 Critical Review | `docs/planning/review_v3_critical.md` | All issues from 3-perspective review |
| Session Log | `docs/planning/session_log.md` | This file — full planning history |
| Prompts Used | `docs/planning/prompts_used.md` | Key prompts from planning session |
| Original Proposal | `BioTeam-AI_Proposal.docx` | JangKeun's working paper |
| Claude Plan File | `.claude/plans/effervescent-riding-lynx.md` | Active plan (same as plan_v3.md) |

### Phase 8: Resource Research + Plan v4 + PRD (Session 1h)

**User Request:** v4 plan update, search for public resources/prompts/guardrails, write PRD.

**Resource Research (3 parallel agents):**
- 30+ curated resources across 8 categories
- Key discoveries:
  - Anthropic's own multi-agent system blog validates Opus lead + Sonnet workers pattern
  - Instructor library for Pydantic-validated structured outputs + auto-retry
  - Prompt caching: 90% cost reduction on repeated system prompts
  - Semantic Scholar API (citation graphs, SPECTER2 embeddings) alongside PubMed
  - sse-starlette for production SSE; React Flow for workflow visualization
  - Biopython for PubMed access (rate-limited, XML-parsed)
  - GRADE evidence framework maps to RCMXT calibration methodology
  - ScienceAgentBench (ICLR 2025) as evaluation benchmark

**v4 Plan Update — All 3 Blockers + 5 Criticals Resolved:**
- B1: Anthropic Client SDK + Instructor (not Agent SDK)
- B2: Docker Compose local-only deployment (Vercel deferred to Phase 4)
- B3: Phase 1 W1 reduced (skip contradiction map + RCMXT)
- C1: Provenance tagging (source_type field on Evidence) prevents circular reasoning
- C2: RCMXTMonitor detects score hedging (std < 0.10, entropy check, monthly holdout)
- C3: Explicit state transition table with guard conditions (13 legal transitions)
- C4: Per-agent checkpointing with idempotency tokens + SQLite WAL
- C5: DataRegistry + Evidence types defined as Pydantic models
- Also resolved 8 of 15 Major issues (M1-M5, M8, M14, M15)

**PRD Written:** Product Requirements Document covering problem statement, functional/non-functional requirements, architecture, data models, workflows, phased roadmap, risks.

**Deliverables:**
- `docs/planning/plan_v4.md` — Updated implementation plan
- `docs/planning/PRD.md` — Product Requirements Document
- `docs/planning/resources_guide.md` — Curated resource guide (30+ resources)

---

## Files Created

| File | Location | Description |
|------|----------|-------------|
| Plan v4.2 | `docs/planning/plan_v4.md` | Current implementation plan (v4.2) |
| Plan v3 | `docs/planning/plan_v3.md` | Previous implementation plan |
| PRD | `docs/planning/PRD.md` | Product Requirements Document |
| Resources Guide | `docs/planning/resources_guide.md` | Curated tools/libraries guide |
| v3 Critical Review | `docs/planning/review_v3_critical.md` | All issues from 3-perspective review |
| Session Log | `docs/planning/session_log.md` | This file — full planning history |
| Prompts Used | `docs/planning/prompts_used.md` | Key prompts from planning session |
| Original Proposal | `BioTeam-AI_Proposal.docx` | JangKeun's working paper |
| Citation Validator | `backend/app/engines/citation_validator.py` | Deterministic citation verification (v4.2) |

---

### Phase 9: Interactive Demo + E2E Test + PRD Cross-Validation (Session 2a)

**Deliverables:**
- Interactive HTML demo with drill-down (Sheet panels for agents + workflows)
- 8 bugs found and fixed in E2E user test
- Full PRD ↔ Plan v4 cross-validation: 6 gaps found (all MINOR), all resolved

### Phase 10: Publication Readiness Review + v4.1 Update (Session 2b)

**Publication readiness audit** across 5 proposed papers identified 10 critical blockers:
1. Wrong agreement metric (Pearson r → ICC required)
2. Sample sizes too small (50/20/15 → 150/150/200)
3. No annotation guidelines
4. No user study design
5. Single domain only → need 3 domains
6. No GRADE framework comparison
7. No cross-LLM comparison (GPT-4o, Gemini)
8. No downstream task evaluation
9. No open-source commitment
10. Timeline 40-60% too aggressive for publication

**v4.1 updates applied:**
- RCMXT Calibration Protocol: ICC(2,k), Bland-Altman, Lin's CCC, MAE, 150 claims × 3 domains × 5 experts, cross-model comparison, prompt sensitivity, 6 baselines
- Publication Strategy: 5 papers with detailed evaluation designs, submission order, preprint strategy
- Verification Plan: split into Engineering Tests (12) + Publication-Grade Evaluation (12)
- Publication Evaluation Workstream: 36-week parallel schedule (Week 1-36)
- Open Science Checklist: code, data, guidelines, OSF preregistration, Figshare DOIs
- PRD Success Criteria: split into Engineering + Publication-Grade
- PRD Risks: +5 publication-related risks
- PRD Human Resources: expanded (experts, annotators, user study participants)
- PRD Acceptance Criteria: +11 publication readiness items

### Phase 11: Pre-Phase 1 Final Review + Day 0 Implementation (Session 2c)

**Final Review (3 parallel deep analyses):**
- **Phase 1 Readiness Review**: Score 6/10. 8 missing pieces identified, 6 technical ambiguities found.
- **Cross-Document Consistency**: 14 inconsistencies found (2 BLOCKERS, 12 MINOR). Both blockers fixed.
- **Environment Audit**: Docker daemon verified, Python 3.13 available, all packages needed identified.

**Blockers Fixed:**
1. PRD Paper 1/2 numbering swapped in Publication Pipeline table → corrected
2. PRD RCMXT calibration says "50 claims" should be "150" → corrected

**Day 0 Implementation Completed (7 tasks):**

1. **Development Environment**: conda env `bioteam-ai` (Python 3.12), 30+ packages installed, git init, .gitignore, .env.example
2. **Project Scaffolding**: Full directory structure (40+ dirs), pyproject.toml, docker-compose.yml + docker-compose.dev.yml, Makefile (dev-local/dev-minimal/dev-full/test/lint)
3. **Async/Sync Spike**: All 4 tests passed — AsyncAnthropic + Instructor + prompt caching all work with `await`. **Decision: async throughout.**
4. **ORM Decision**: **SQLModel** chosen (Pydantic v2 + SQLAlchemy). 9 SQL tables defined (Evidence, ContradictionEntry, DataRegistry, NegativeResult, WorkflowInstance, StepCheckpoint, AgentMessage, EpisodicEvent, CostRecord, Project, Task). SQLite WAL mode verified.
5. **BaseAgent + AgentOutput**: Abstract base class with Langfuse @observe decorator, 3-retry API-level error handling, cost estimation. AgentOutput model defined (the key gap from review). AgentRegistry with health tracking + degradation modes.
6. **Agent Spec YAML**: Schema defined, 3 examples created (research_director, knowledge_manager, project_manager). System prompts for all 3 strategic agents.
7. **ChromaDB + Benchmarks**: Embedded mode (no separate Docker service). SemanticMemory class with 3 collections + DOI dedup. 50 benchmark claims JSON created (25 spaceflight biology, 25 general biology, 17 with X=null).

**Deliverables:**
- FastAPI app running with `/health` endpoint (/health returns all 5 checks)
- All Pydantic models importable, all SQL tables creatable
- LLMLayer + MockLLMLayer fully functional
- Ready for Week 1 coding

### Phase 12: Week 1 Review + Researcher Feedback → v4.2 Update (Session 3)

**Week 1 Review:**
- Day 0 completed ~85% of Week 1-2 plan items
- Proposed compressed Phase 1 (3-4 weeks instead of 5)

**Researcher Feedback Analysis (3 parallel deep analyses):**
1. **Trust & Verification** (skeptical postdoc perspective) — 10 issues
2. **Workflow & UX Friction** (PI running a lab perspective) — 14 issues
3. **Publication & Scientific Rigor** (journal editor/reviewer perspective) — 14 issues

**Results:** 38 total → 22 unique after dedup → 6 CRITICAL, 9 HIGH, 7 MEDIUM

**v4.2 Code Changes Implemented (16 changes across 8 files):**

| File | Changes |
|------|---------|
| `backend/app/config.py` | + `default_temperature: float = 0.0` |
| `backend/app/llm/layer.py` | Complete rewrite: + `LLMResponse` dataclass, temperature parameter, tuple returns, `_extract_metadata()`, `create_with_completion` |
| `backend/app/llm/mock_layer.py` | Updated for tuple returns, + `_mock_meta()`, `.model` attribute |
| `backend/app/models/evidence.py` | + `verbatim_quote`, + `PRISMAFlow`, + `SessionManifest`, + `ExportBibTeX`, + `ExportMarkdown`, ContradictionEntry `type` → `types: list[str]` |
| `backend/app/models/negative_result.py` | + `verified_by`, + `verification_status`, + `VerificationStatus` Literal |
| `backend/app/models/workflow.py` | + `seed_papers`, + `DirectorNoteAction` Literal, DirectorNote `action` + `metadata` fields |
| `backend/app/agents/base.py` | `build_output()` + `llm_response` parameter, auto-propagates model_version |
| `backend/app/memory/semantic.py` | + `search_literature()`, + `search_all()` |
| `backend/app/engines/citation_validator.py` | **NEW FILE**: CitationValidator, CitationReport, CitationIssue |

**Plan Updates:**
- Title: v4 → v4.2
- Context: +line 7 (researcher feedback)
- Design Principles: +#13 (Reproducibility by default), +#14 (Trust through transparency)
- v4→v4.2 Changelog: 16 new entries (#25-#40)
- Data Models: +Reproducibility & Trust Models section (LLMResponse, CitationValidator, SessionManifest, PRISMAFlow, Export, AI Disclosure)
- W1 workflow: annotated with v4.2 additions per step
- Cold Start: +Quick Start Mode
- Summary table: updated totals (88 issues, 61 resolved)

---

### Phase 13: Full System Implementation (Sessions 4-N, up to 2026-02-27)

**What was built beyond the original plan:**

All 9 workflows (W1-W9) and all 18+ agents were implemented ahead of schedule. Additionally, the following features were built beyond the original v4.2 plan scope:

| Feature | Notes |
|---------|-------|
| **W9 Bioinformatics workflow** | 10-step pipeline: SCOPE→DECOMPOSE→FETCH_DATA→QC→PREPROCESS→ANALYZE→INTEGRATE→INTERPRET→QA→REPORT |
| **Bioinformatics API integrations** | UniProt REST v2, Ensembl REST+VEP, STRING DB v12, GWAS Catalog, GTEx Portal v2, g:Profiler, NCBI Gene/ClinVar |
| **Open Peer Review Corpus (Phase 6)** | eLife XML parser, OpenPeerReviewEntry SQLModel table, ConcernParser (Haiku-based), W8 benchmark runner |
| **MCP Connector infrastructure** | PubMed, bioRxiv, ClinicalTrials.gov, ChEMBL, ICD-10 MCP servers (master toggle `mcp_enabled`) |
| **PTC (Programmatic Tool Calling)** | Multi-tool orchestration framework, `ptc_enabled` config flag |
| **Deferred tool loading** | Context-saving tool search/load system |
| **Iterative refinement loop** | Self-Refine with quality threshold, max iterations, budget cap |
| **Long-term checkpointing** | SQLite-backed step checkpoints, step rerun/skip/inject API endpoints |
| **GitHub Actions CI** | `ci.yml` with ruff + pytest, integration test marker auto-skip |
| **Digest email delivery** | SMTP/Gmail digest report delivery, digest recipients config |
| **Data integrity audit scheduler** | Crossref API verification, audit interval scheduling |
| **Rate limiting** | Token bucket per-tier (Haiku: 200 rpm, Sonnet: 80, Opus: 40) |

**Implementation Status vs. Original Plan:**

| Phase | Original Plan | Status |
|-------|--------------|--------|
| Phase 1: Foundation | Week 1-5 | ✅ Complete |
| Phase 2: Ambiguity Engine + QA | Week 6-9 (incl. Celery/Redis) | ⊙ Partial — asyncio only, Celery deferred |
| Phase 3a: Full Biology | Week 10-12 | ✅ Complete (all 12 specialists) |
| Phase 3b: Negative Results R&D | Week 13-14 | ⊙ Partial — Lab KB done, shadow mining/preprint delta incomplete |
| Phase 4: Translation + Production | Week 15-18 | ⊙ Partial — W4/W5 implemented, production hardening TODO |
| Publication Workstream | Parallel, Week 1-36 | ❌ Not started |

**Key gaps remaining from original plan:**
1. Code execution sandbox (Docker containers for Python/R/Nextflow) — agents generate code but cannot execute it
2. Celery/Redis task queue — all orchestration runs via asyncio.gather only
3. Advanced shadow mining (NLP tier beyond 30-phrase vocabulary) — engineering gate not reached
4. Preprint delta full automation — basic comparison only
5. RCMXT calibration with 5 domain experts — no expert annotations collected
6. IRB determination + user study protocol — not filed
7. Production auth (NextAuth.js + JWT) — dev mode only (API key)
8. Frontend missing: Teams panel, Quality panel, Evidence Explorer, Knowledge Browser, Analytics
9. Docker Compose production deployment + security audit
10. Open Peer Review Corpus integration disabled by default (`peer_review_corpus_enabled = False`)

---

### Phase 14: Code Quality + CI Stabilization (Session: 2026-02-27)

**Goals:** Stabilize the existing codebase before next feature phase.

**Work completed (commit `b9b5bd6`):**

| Task | Detail |
|------|--------|
| **Ruff clean** | 93 issues fixed (88 auto + 7 manual). F841/E741/F821 manually fixed in resume.py, ncbi_extended.py, w8_paper_review.py, w9_bioinformatics.py, test_mcp_connector.py, digest_report.py |
| **digest.py import fix** | Ruff `--fix` incorrectly removed `SCHEDULE_LOOKBACK_DAYS` import (used at line 295); restored manually |
| **Dynamic agent count** | `registry._expected_count = len(agent_defs)` — decoupled test from hardcoded `23` |
| **Integration test markers** | `pytest.mark.integration` + conftest `--run-integration` flag for auto-skip |
| **CI improvement** | `--ignore` per-file approach → `-m "not integration"` unified filter |
| **Model version update** | `claude-sonnet-4-5-20250929` → `claude-sonnet-4-6` in config.py, .env.example, tracker.py |

---

## Next Steps (Updated 2026-02-27)

### Immediate Priority: W9 + Open Peer Review Corpus Stabilization

The most recently added features (W9, Open Peer Review Corpus) have the least test coverage. Stabilize before moving to new features:

1. **W9 Bioinformatics tests** — `test_w9_runner.py` exists but needs validation with MockLLMLayer; ensure all 10 steps pass offline
2. **Open Peer Review Corpus tests** — eLife XML parser, concern parser, benchmark runner need integration test coverage
3. **Enable `peer_review_corpus_enabled = True`** in config once stable, add to health check

### Near-Term: Code Execution Sandbox (Phase 2 Blocker)

The code sandbox is the biggest missing feature from the original plan. Agents can generate Python/R code but cannot execute it:

1. `backend/app/execution/docker_runner.py` — implement `DockerCodeRunner` for Python/R/Nextflow
2. `Dockerfile.rnaseq`, `Dockerfile.singlecell`, `Dockerfile.genomics` — base images
3. W3 (Data Analysis) and W9 (Bioinformatics) depend on this for real scientific value

### Publication Workstream Start (0% progress, critical for papers)

The publication workstream has not started. To unblock Paper 1 (RCMXT):

1. Write RCMXT annotation guidelines (per-axis rubric with 3 anchor examples per axis)
2. Identify 5 domain expert candidates (lab colleagues at Weill Cornell Medicine)
3. Begin curating 150 biological claims (50 spaceflight × 50 cancer genomics × 50 neuroscience)
4. File IRB determination at Weill Cornell Medicine (for user study, Paper 4)
5. Preregister calibration protocol on OSF (Week 8 target)

### Next Feature: Frontend Phase 2 Panels

The frontend currently has 3 panels (Mission Control, Projects, Lab KB). Phase 2 panels add research value:

1. **Teams panel** — per-team status, active agent list, recent outputs
2. **Quality panel** — QA agent review results, RCMXT scores, contradiction flags
3. **Evidence Explorer** — browse extracted claims with provenance and RCMXT scores

### Deferred (Phase 4):

- Celery/Redis task queue (asyncio.gather sufficient for current scale)
- HPC runner (SSH + Slurm)
- PostgreSQL migration
- OAuth 2.0 / NextAuth.js (dev mode auth sufficient for personal use)
- Vercel cloud deployment

---

## Key Architectural Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| LLM Provider | Claude-only | Consistency, MCP native support |
| LLM SDK | **Anthropic Client SDK** + **Instructor** | Direct API control, structured outputs, predictable cost |
| Structured Output | **Instructor** (Pydantic validation + auto-retry) | Handles LLM output validation elegantly |
| Backend | FastAPI (Python 3.12+) | Async, Pydantic, AI ecosystem |
| Frontend | Next.js 15 + Tailwind + shadcn/ui | Dashboard SSR |
| Workflow Viz | **React Flow** (XyFlow) | Interactive node-based workflow graphs |
| Deployment | **Docker Compose (local-only)** Phase 1-3, Vercel optional Phase 4 | SSE works on localhost; no infra complexity |
| Phase 1 Orchestration | **asyncio.gather** + Semaphore | Partial failure support, concurrency control |
| Phase 2+ Orchestration | Celery + Redis | Scale when needed |
| Real-time | SSE via **sse-starlette** | Production-ready, W3C spec compliant |
| Vector DB | ChromaDB (3 collections: literature/synthesis/lab_kb) | Provenance-separated semantic memory |
| State DB | SQLite (**WAL mode**) | Atomic writes for checkpointing |
| Agent Count | **18 LLM agents** + 2 hybrid engines | Corrected from "15" |
| Model Tiers | Opus (Director synthesis, Grants), Sonnet (most agents), Haiku (PM, Data Eng, Reproducibility) | Cost optimization |
| Prompt Caching | Anthropic native cache_control | 90% cost reduction on system prompts |
| Literature APIs | **Biopython** (PubMed) + **Semantic Scholar** + bioRxiv/medRxiv | Rich coverage |
| Code Execution | Agents generate, Docker sandbox executes | Safety + isolation |
| QA Independence | QA tier reports to human Director, not to teams | Structural objectivity |
| Provenance | source_type on all Evidence (primary_literature / internal_synthesis / lab_kb) | Prevents circular reasoning |
| Monitoring | **Langfuse** (from day one) | Agent tracing, cost tracking |
| Async pattern | **AsyncAnthropic** + async Instructor | Validated in Day 0 spike — all 4 tests passed |
| ORM | **SQLModel** (Pydantic v2 + SQLAlchemy) | One model class for API schema + DB table |
| ChromaDB mode | **Embedded** (no separate service) | Sufficient for Phase 1-3, simplifies deployment |
| Langfuse integration | **@observe decorator** on BaseAgent.execute() | Simplest, most reliable pattern |
| Agent spec format | **YAML** (id, tier, model_tier, tools, mcp_access, etc.) | Human-readable, git-trackable |
