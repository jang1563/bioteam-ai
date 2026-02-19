# BioTeam-AI Plan v3 — Critical Review Results

**Date:** 2026-02-16
**Reviewers:** 3 parallel analysis agents (Internal Consistency, Implementation Feasibility, Edge Cases & Failure Modes)
**Total Issues Found:** 53 raw, 34 unique after deduplication

---

## BLOCKERS (Must resolve before implementation)

### B1: Claude Agent SDK Is The Wrong Tool [BLOCKER]

**Source:** Feasibility Review #1, #9

The plan specifies "Claude Agent SDK (Python)" as the agent runtime and wraps it in an `LLMAdapter` abstraction. This is architecturally wrong.

**The Problem:**
- The Claude Agent SDK is a wrapper around the Claude Code CLI, not a direct API client
- It spawns a Claude Code subprocess and communicates via JSON over stdio
- It provides built-in file-system tools (Read, Write, Edit, Bash) designed for coding agents
- Each `query()` call creates an autonomous session — you cannot control it step-by-step
- The `LLMAdapter` methods (`complete()`, `complete_with_tools()`) don't map to the SDK's interface
- Requires Node.js + npm as hidden dependencies in the Python backend
- Cost estimates are based on single API calls, but the Agent SDK runs multi-turn sessions internally

**The Fix:**
Use the **Anthropic Client SDK** (`pip install anthropic`) with `client.messages.create()`:
- Direct HTTP API calls with full control
- Native structured output support via `response_format`
- Tool use with manual agentic loop (~30 lines of code)
- Pure Python, no Node.js dependency
- Cost per call is predictable (single API roundtrip)

**Impact:** Affects LLMAdapter design, BaseAgent class, cost estimates, Docker deployment, all agent implementations.

---

### B2: SSE Through Vercel Is Not Viable [BLOCKER]

**Source:** Feasibility Review #4

The deployment plan: FastAPI backend local + Next.js dashboard on Vercel. SSE for real-time updates.

**The Problem:**
- Vercel serverless functions have 10s timeout (Hobby) / 60s timeout (Pro)
- SSE requires persistent HTTP connections — impossible on serverless
- Local FastAPI backend needs public endpoint or tunnel (ngrok) for Vercel to reach it — not mentioned
- Next.js page navigation kills SSE connections without app-level management

**Options:**
1. **Host frontend locally** alongside FastAPI via Docker Compose (eliminate Vercel)
2. **Use polling** instead of SSE — `/api/v1/workflows/{id}/status` every 2-5 seconds
3. **Hybrid:** Local development = SSE (both services on localhost), production = polling through Vercel

**Impact:** Affects dashboard architecture, deployment strategy, `useSSE.ts` hook.

---

### B3: Phase 1 W1 "End-to-End" Depends on Phase 2 Components [BLOCKER]

**Source:** Consistency Review #1, #11, #12

The Phase 1 milestone says "Run first real literature review through the system" (end-to-end W1). But W1 includes:
- CONTRADICTION MAP → requires Contradiction Mapper (Phase 2, Week 7-8)
- RCMXT SCORE → RCMXT scoring engine is Phase 1, but calibration (inter-expert baseline) is Phase 2
- Cold Start Step 3 (RCMXT calibration) also depends on Phase 2 calibration protocol

**The Fix:**
Define "Phase 1 W1" as a reduced workflow:
```
SCOPE → DECOMPOSE → SEARCH → SCREEN → EXTRACT → NEGATIVE CHECK → SYNTHESIZE → NOVELTY CHECK → REPORT
(Skip: CONTRADICTION MAP, RCMXT SCORE, and the contradiction-triggered loop)
```
Cold Start Step 3 should use a simplified "Phase 1 calibration" (LLM-only, no inter-expert baseline).

**Impact:** Affects Phase 1 milestone definition, Cold Start protocol, W1 workflow template.

---

## CRITICAL (Undermine core value proposition)

### C1: Circular Reasoning Amplification

Agent A's synthesis stored in ChromaDB → Agent B retrieves as "evidence" → stored again → single source amplified to multi-source confirmation. No mechanism to distinguish primary literature from system-generated interpretations.

**Mitigation:** Provenance tagging (`source_type` field: `primary_literature` vs. `internal_synthesis`), separate ChromaDB collections, R-axis excludes system-generated sources from replication count.

### C2: RCMXT Score Hedging (All-0.5 Syndrome)

LLM converges on safe mid-range scores. Calibration only runs on 50 frozen benchmarks, production drift undetected.

**Mitigation:** Runtime score distribution monitor (flag if any axis std < 0.10), entropy check, production holdout sampling.

### C3: Workflow Engine State Transitions Undefined

8 states listed but no transition table. Which transitions are legal? What does each user action (approve, reject, skip) produce? Unimplementable without this.

**Mitigation:** Add explicit state transition diagram with guard conditions.

### C4: Checkpoint Granularity Ambiguous

Crash during parallel step (4 of 7 agents done) — restart all 7 or resume from 4? Atomic write strategy undefined.

**Mitigation:** Per-agent checkpointing, SQLite WAL mode, idempotency tokens.

### C5: `DataRegistry` and `Evidence` Types Undefined

Referenced throughout code but never defined as Pydantic models. Fundamental data types for the entire pipeline.

**Mitigation:** Add to models directory, define schemas, assign to Week 1-2.

---

## MAJOR (Design changes needed — 15 issues)

| # | Issue | Mitigation |
|---|-------|-----------|
| M1 | Agent count: "15" but tables sum to 18 | Fix count or remove 3 agents |
| M2 | asyncio.TaskGroup cancels all on any failure | Use `gather(return_exceptions=True)` + Semaphore |
| M3 | Direct Query classification: 3-type vs 2-type mismatch | Unify taxonomy, define Pydantic schema |
| M4 | `input_mapper: Callable` has no type signature | Define as `(list[StepResult]) -> ContextPackage` |
| M5 | ChromaDB duplicate entries across workflows | Content-addressed dedup via DOI/PMID hash |
| M6 | Shadow Mining: Introduction citations vs. Results findings | Section-aware parsing, restrict Tier 1 to Results/Discussion |
| M7 | Contradiction Mapper Type-1 collapse | Forced ranking with justification, per-type calibration |
| M8 | SSE event schema undefined | Define event types + payload structure |
| M9 | Model update invalidates RCMXT calibration | Version pinning + auto-recalibration trigger |
| M10 | Budget exhaustion at penultimate step | Reserve synthesis cost upfront |
| M11 | Page refresh loses SSE state | REST endpoint for full state + localStorage hydration |
| M12 | W6 trigger mechanism undefined | Add `trigger_workflow` to AgentMessage or API endpoint |
| M13 | ContextPackage assembly logic undefined | Specify relevance criteria per field |
| M14 | Week 1-2 scope: 10-16 days in 10 days | Defer backup manager + CostTracker to Week 3 |
| M15 | Singleton agent failure = system-wide outage | Classify agents as critical vs. optional, degraded modes |

---

## MINOR (6 issues, defer to Phase 2+)

| # | Issue |
|---|-------|
| m1 | ChromaDB → Qdrant migration unscheduled |
| m2 | Embedding model unspecified |
| m3 | MODEL_MAP uses incorrect model IDs |
| m4 | Multiple browser tab conflicts |
| m5 | Loop count vs. budget limit conflict |
| m6 | Deep single-user assumptions (accept explicitly or add tenant_id) |

---

## Recommended Priority for v4 Plan Update

1. **Resolve all 3 Blockers** (B1, B2, B3) — these change the architecture
2. **Address 5 Criticals** (C1-C5) — these affect core system integrity
3. **Incorporate top Majors** (M1-M8 minimum) — these prevent implementation confusion
4. **Document remaining Majors and Minors** as known technical debt with phase assignments
