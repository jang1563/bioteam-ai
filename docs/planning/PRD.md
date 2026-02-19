# BioTeam-AI — Product Requirements Document (PRD)

**Version:** 1.0
**Date:** 2026-02-16
**Author:** JangKeun Kim, Weill Cornell Medicine
**Status:** Draft (Pre-Implementation)

---

## 1. Executive Summary

BioTeam-AI is a personal AI science team management system for biology research. It provides a dashboard-style interface where a solo researcher (the "Director") can assign research tasks to specialized AI agent teams, monitor progress in real-time, and receive structured, evidence-graded outputs.

**Core differentiator:** Biology-aware epistemology — the system handles contradictions, negative results, and context-dependent truth using a novel 5-axis evidence scoring system (RCMXT) and a 5-category contradiction taxonomy, unlike existing tools (Elicit, Consensus) that treat evidence as binary.

**Target user:** Solo biology researcher or small lab group needing systematic literature review, hypothesis generation, data analysis support, manuscript drafting, and grant writing assistance.

---

## 2. Problem Statement

### 2.1 Current Pain Points

1. **Information overload:** A single PubMed search for "spaceflight anemia" returns 200+ papers. Manually screening, extracting claims, and identifying contradictions takes weeks.
2. **Negative results invisibility:** ~85% of negative results go unpublished (Franco et al., 2014). Researchers waste time repeating failed experiments they never knew about.
3. **Contradiction blindness:** Contradictory findings in literature are rarely flagged. A claim like "spaceflight causes immune suppression" may be simultaneously true (6-month ISS) and false (1-year Twins Study) depending on conditions — but no tool surfaces this.
4. **Multi-omics integration gap:** Genomic, transcriptomic, proteomic, and metabolomic data often tell different stories. No existing tool systematically checks cross-omics consistency for a given claim.
5. **Repetitive research tasks:** Literature reviews, statistical checks, figure formatting, and grant boilerplate consume time that could be spent on creative research.

### 2.2 Why Existing Tools Fall Short

| Tool | Limitation for Biology Research |
|------|-------------------------------|
| **Elicit** | Single-score confidence, no contradiction detection, no negative results |
| **Consensus** | Claim extraction only, no multi-omics awareness, no workflow orchestration |
| **Google AI Co-Scientist** | Hypothesis generation only, no full research pipeline, Gemini-only |
| **ChatGPT/Claude (direct)** | No persistent memory, no structured evidence grading, no team coordination |
| **Sakana AI Scientist** | Automated paper writing, not research assistance; no human-in-the-loop |

---

## 3. Product Vision

### 3.1 Vision Statement

A personal AI science team that thinks like a biology lab — understanding that truth is conditional, negative results matter, and evidence must be graded across multiple dimensions.

### 3.2 Success Criteria

#### Engineering Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Literature review time | 80% reduction vs. manual | Time from query to structured report |
| Cost per workflow | Within 2x of budget estimate | Actual vs. estimated cost |
| User satisfaction | Director uses system weekly | Sustained usage over 3 months |

#### Publication-Grade Success Criteria *(v4.1)*

| Metric | Target | Measurement | Paper |
|--------|--------|-------------|-------|
| RCMXT inter-expert agreement | ICC(2,k) > 0.6 per axis | ICC on 150 claims × 5 experts × 3 domains | Paper 1 |
| RCMXT LLM-vs-expert agreement | ICC(2,1) ≥ 0.7 per axis | ICC on 150 claims, 5 runs per claim | Paper 1 |
| RCMXT downstream utility | RCMXT-filtered > unfiltered for hypothesis ranking | Expert-judged ranking accuracy, Wilcoxon test | Paper 1 |
| Contradiction detection | Cohen's kappa ≥ 0.7 (inter-annotator) | 150+ contradictions × 2 annotators × 3 domains | Paper 2 |
| Contradiction per-class F1 | Macro F1 ≥ 0.70 | Per-class precision/recall/F1 with bootstrap 95% CI | Paper 2 |
| Shadow Mining | Precision ≥ 0.85 AND recall ≥ 0.60 (Tier 1) | 200+ labeled sentences from PMC OA | Paper 3 |
| Negative results surfaced | Recall > 50% across all 4 sources combined | Labeled test set across 3 domains | Paper 3 |
| Hypothesis novelty | >30% rated "novel" by ≥ 2/3 independent experts | Blind evaluation | Paper 4 |
| User study SUS | SUS ≥ 68 (above average) | N ≥ 5 researchers, IRB approved | Paper 4 |
| Multi-agent vs single-agent | Statistically significant quality improvement | Paired comparison on 10 tasks, expert-rated | Paper 4 |

### 3.3 Non-Goals (Explicit Out of Scope)

- **Autonomous research:** The system assists, not replaces, the researcher. All significant decisions require Director approval.
- **Wet lab automation:** No robotic experiment execution. Code generation and analysis only.
- **Multi-user SaaS:** Single-user (Director) system. Multi-tenancy is a Phase 5+ consideration.
- **Real-time data streaming:** Operates on published data, not live instrument feeds.
- **Clinical decision support:** Not a diagnostic tool. No patient data handling.

---

## 4. User Personas

### 4.1 Primary: The Director (Solo Researcher)

- **Profile:** JangKeun Kim, PhD researcher at Weill Cornell Medicine
- **Domain:** Spaceflight biology, multi-omics, cfRNA, systems biology
- **Technical skill:** Comfortable with Python/R, bioinformatics pipelines, HPC
- **Pain points:** Information overload, contradiction management, negative result blindness
- **Workflow:** Asks research questions → reviews AI team outputs → makes decisions → publishes

### 4.2 Secondary: Lab Colleagues (Future)

- **Profile:** Other researchers who may contribute to Lab KB or review outputs
- **Interaction:** Input negative results, review RCMXT scores, validate contradiction classifications
- **Phase:** Deferred to Phase 4+ (initially single-user)

---

## 5. Functional Requirements

### 5.1 Core Capabilities (Phase 1 — MVP)

#### FR-1: Direct Query Mode
- **Description:** Ask simple research questions and get immediate answers without spawning a full workflow.
- **Input:** Natural language question (e.g., "Is gene TNFSF11 differentially expressed in spaceflight cfRNA?")
- **Output:** Structured response with sources, confidence indicator, and option to escalate to full workflow.
- **Performance:** < 30 seconds, < $0.50 per query, 1-3 LLM calls.

#### FR-2: Literature Review Workflow (W1 — Reduced)
- **Description:** Automated literature search, screening, extraction, and synthesis.
- **Steps:** SCOPE → DECOMPOSE → SEARCH → SCREEN → EXTRACT → NEGATIVE CHECK → SYNTHESIZE → NOVELTY CHECK → REPORT
- **Input:** Research question or topic.
- **Output:** Structured report with: papers found/screened/included, key findings, negative results from Lab KB, synthesis, novelty assessment.
- **Phase 1 scope:** No contradiction mapping or RCMXT scoring (deferred to Phase 2).
- **Human checkpoint:** After SYNTHESIZE, before final report.
- **Budget:** Max $5 per workflow.

#### FR-3: Internal Lab Knowledge Base
- **Description:** Structured repository for negative results, failed experiments, and lab-specific knowledge.
- **Input:** Manual entry via dashboard wizard (claim, outcome, conditions, category).
- **Output:** Searchable knowledge base that feeds into all workflows via Negative Results Module.
- **CRUD:** Create, read, update, delete negative result entries.

#### FR-4: Dashboard — Mission Control
- **Description:** Overview of system status, active workflows, recent results, and quick actions.
- **Panels (Phase 1):** Mission Control, Projects, Lab KB.
- **Real-time:** SSE-powered live updates on workflow progress.
- **Actions:** Start workflow, ask direct query, pause/resume/cancel workflow, enter negative result.
- **Drill-down (Phase 1):** Click any agent → slide-over panel showing status, capabilities, current task (read-only). Click any workflow → slide-over panel showing pipeline progress, step outputs, budget, intervention actions.
- **Drill-down (Phase 2):** Agent execution history, "Inject Note" for workflows, "Modify Parameters" at checkpoints, "Direct Query to Agent" button, activity feed items clickable.

#### FR-5: Cold Start Protocol
- **Description:** First-run setup that seeds the system with researcher's publications, Lab KB entries, and RCMXT calibration.
- **Steps:** (1) Import publications from ORCID/Google Scholar, (2) Lab KB wizard for negative results, (3) RCMXT calibration on 50 benchmark claims, (4) Smoke test.
- **Duration:** ~3 hours (Step 1: ~30min automated, Step 2: ~15min manual, Step 3: ~2hr automated, Step 4: ~10min automated).

#### FR-6: Health Monitoring
- **Description:** `/health` endpoint checking all dependencies.
- **Checks:** LLM API connectivity, database, ChromaDB, PubMed API, cost tracker status.
- **Dashboard display:** Green/yellow/red status indicators.

### 5.2 Extended Capabilities (Phase 2-3)

#### FR-7: RCMXT Evidence Scoring
- **Description:** Every biological claim receives a 5-axis confidence vector [R,C,M,X,T] scored 0.0-1.0.
- **Axes:** Reproducibility, Condition Specificity, Methodological Robustness, Cross-Omics Consistency, Temporal Stability.
- **Special handling:** X-axis returns NULL when multi-omics data is unavailable (not 0.5).
- **Visualization:** Radar charts, color-coded scores.
- **Calibration:** Inter-expert baseline on 150 claims × 3 domains; LLM target ICC(2,1) ≥ 0.7. Cross-model comparison with GPT-4o and Gemini 2.0.

#### FR-8: Contradiction Detection & Classification
- **Description:** Identifies contradictory claims in literature and classifies them into 5 types.
- **Taxonomy:** Conditional Truth, Technical Artifact, Interpretive Framing, Statistical Noise, Temporal Dynamics.
- **Output:** Contradiction matrix with type labels, resolution hypotheses, discriminating experiment suggestions.

#### FR-9: Full Workflow Suite (W2-W6)
- **W2 Hypothesis Generation:** Generate-Debate-Evolve pattern with 7 specialist teams.
- **W3 Data Analysis:** Code generation + sandboxed execution + QA validation.
- **W4 Manuscript Writing:** Parallel drafting + multi-round review.
- **W5 Grant Proposal:** NIH/NASA/NSF-specific formatting + mock review.
- **W6 Ambiguity Resolution:** Standalone contradiction investigation.

#### FR-10: QA Layer (Independent)
- **Description:** Three QA agents that review all outputs independently.
- **Agents:** Statistical Rigor, Biological Plausibility, Reproducibility & Standards.
- **Independence:** Report directly to Director, never subordinate to teams they review.

#### FR-11: Workflow Intervention
- **Description:** Director can pause, resume, redirect, inject notes, and skip steps in any workflow.
- **Trigger points:** Human checkpoints, budget overruns, QA rejections, agent failures.
- **Actions:** Continue, modify parameters, skip QA, cancel, inject note.

### 5.3 Advanced Capabilities (Phase 3b-4)

#### FR-12: Negative Results Mining
- **Shadow Literature Mining:** Constrained 30-phrase vocabulary matching in PMC Open Access papers.
- **Preprint Delta Analysis:** Track removed figures/conclusions between bioRxiv/medRxiv versions.
- **Clinical Trial Failure Mining:** ClinicalTrials.gov terminated/failed trial interpretation.

#### FR-13: Code Sandbox
- **Description:** Agents generate bioinformatics code; Docker containers execute it safely.
- **Languages:** Python, R.
- **Pre-built containers:** RNA-seq, single-cell, genomics.
- **Safety:** No network access from containers; Director approval for any external operations.

#### FR-14: Translation Workflows
- **Description:** Manuscript and grant writing support.
- **Model:** Opus-tier for grant writing (high-stakes), Sonnet for manuscripts.

---

## 6. Non-Functional Requirements

### 6.1 Performance

| Requirement | Target |
|-------------|--------|
| Direct Query response | < 30 seconds |
| W1 Literature Review | < 15 minutes (20-50 papers) |
| Dashboard load time | < 2 seconds |
| SSE event latency | < 500ms from backend to dashboard |
| Concurrent workflows | 1-3 (Phase 1), up to 10 (Phase 2+) |

### 6.2 Cost

| Requirement | Target |
|-------------|--------|
| Direct Query | < $0.50 |
| W1 Literature Review | < $5 |
| W2 Hypothesis Generation | < $15 |
| W3 Data Analysis | < $10 |
| W4 Manuscript Writing | < $25 |
| W5 Grant Proposal | < $30 |
| Daily session budget | $50 default (configurable) |
| Alert threshold | 80% of any budget |

### 6.3 Reliability

| Requirement | Target |
|-------------|--------|
| Agent failure recovery | Auto-retry 3x with backoff, then escalate to Director |
| Workflow crash recovery | Resume from last checkpoint (per-agent granularity) |
| Data persistence | Daily automated backups (SQLite + ChromaDB) |
| State consistency | SQLite WAL mode for atomic writes |

### 6.4 Security

| Requirement | Implementation |
|-------------|---------------|
| Authentication | OAuth 2.0 + JWT (Phase 4) |
| API key management | `.env` file, never hardcoded |
| Code sandbox isolation | Docker containers, no network access |
| Audit trail | All agent actions logged via Langfuse |
| Kill switch | Director can halt any workflow instantly |

### 6.5 Usability

| Requirement | Implementation |
|-------------|---------------|
| Onboarding | Cold Start protocol guides first-time setup |
| Progressive disclosure | 3 core panels at launch; additional panels unlock as features are built |
| Direct access | Direct Query mode for quick questions (no workflow overhead) |
| Intervention | Pause/resume/redirect any workflow at any time |

### 6.6 Scalability

| Requirement | Phase 1 | Phase 2+ |
|-------------|---------|----------|
| Orchestration | asyncio (in-process) | Celery + Redis (multi-worker) |
| Database | SQLite | PostgreSQL (optional) |
| Vector DB | ChromaDB | Qdrant (optional) |
| Concurrent workflows | 1-3 | 10+ |
| Migration trigger | >10 concurrent users OR >100k episodic events |

---

## 7. System Architecture

### 7.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    DASHBOARD (Next.js 15)                      │
│  Phase 1: Mission Control | Projects | Lab KB                  │
│  Phase 2+: + Teams | Quality | Evidence | Knowledge | Analytics│
└───────────────────────┬──────────────────────────────────────┘
                        │ SSE (real-time) + REST API
┌───────────────────────┴──────────────────────────────────────┐
│                    FASTAPI BACKEND                             │
│  /api/v1/ endpoints | SSE hub | Workflow engine               │
├──────────────────────────────────────────────────────────────┤
│  Tier 1: Strategic    │ Research Director, PM, Knowledge Mgr  │
│  Core Engines         │ Ambiguity Engine, Negative Results    │
│  Tier 2: Specialists  │ 10 domain teams + 2 cross-cutting    │
│  Tier 3: QA           │ Statistical, Biological, Reproducible│
├──────────────────────────────────────────────────────────────┤
│  Infrastructure: SQLite | ChromaDB | Langfuse | Docker        │
└──────────────────────────────────────────────────────────────┘
```

### 7.2 Agent Inventory (18 LLM agents + 2 hybrid engines)

| Tier | Count | Examples |
|------|-------|---------|
| Strategic | 3 | Research Director (Opus/Sonnet), Project Manager (Haiku), Knowledge Manager (Sonnet) |
| Core Engines | 2 | Ambiguity Resolution Engine, Negative Results Module |
| Domain Experts | 12 | 10 specialist teams + Experimental Designer + Integrative Biologist |
| QA (Independent) | 3 | Statistical Rigor, Biological Plausibility, Reproducibility |

### 7.3 Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15 + Tailwind CSS + shadcn/ui |
| Backend | FastAPI (Python 3.12+) |
| LLM | Anthropic Client SDK + Instructor (structured outputs) |
| Orchestration | asyncio (Phase 1) → Celery + Redis (Phase 2+) |
| Real-time | SSE via sse-starlette |
| Workflow Viz | React Flow |
| Vector DB | ChromaDB |
| State DB | SQLite (WAL mode) |
| Code Sandbox | Docker containers |
| Monitoring | Langfuse (self-hosted) |
| Literature APIs | PubMed (Biopython), Semantic Scholar, bioRxiv/medRxiv |
| MCP Tools | bioRxiv, medRxiv, ChEMBL, Clinical Trials, ICD-10, Hugging Face |
| Deployment | Docker Compose (local-only for Phase 1-3) |

---

## 8. Data Models (Key Entities)

### 8.1 Evidence & Scoring

```python
class RCMXTScore(BaseModel):
    claim: str
    R: float                    # Reproducibility (0.0-1.0)
    C: float                    # Condition Specificity
    M: float                    # Methodological Robustness
    X: float | None             # Cross-Omics (NULL if unavailable)
    T: float                    # Temporal Stability
    composite: float | None     # Average (4 or 5 axes depending on X)
    sources: list[str]          # Evidence source IDs
    provenance: Literal["primary_literature", "internal_synthesis"]
    scored_at: datetime
    scorer_version: str         # Prompt version for traceability
    model_version: str          # e.g., "claude-sonnet-4-5-20250929"

class ContradictionEntry(BaseModel):
    claim_a: str
    claim_b: str
    type: Literal["conditional_truth", "technical_artifact",
                  "interpretive_framing", "statistical_noise",
                  "temporal_dynamics"]
    resolution_hypotheses: list[str]
    rcmxt_a: RCMXTScore
    rcmxt_b: RCMXTScore

class NegativeResult(BaseModel):
    claim: str
    outcome: str
    conditions: dict
    source: Literal["internal", "clinical_trial", "shadow", "preprint_delta"]
    confidence: float
    failure_category: Literal["protocol", "reagent", "analysis", "biological"]
    implications: list[str]
```

### 8.2 Workflow

```python
class WorkflowInstance(BaseModel):
    id: str
    template: Literal["W1", "W2", "W3", "W4", "W5", "W6", "direct_query"]
    state: Literal["PENDING", "RUNNING", "PAUSED", "WAITING_HUMAN",
                   "COMPLETED", "FAILED", "CANCELLED", "OVER_BUDGET"]
    current_step: str
    step_history: list[StepResult]
    checkpoint: bytes | None
    budget_remaining: float
    loop_count: dict[str, int]
    max_loops: int = 3
    injected_notes: list[DirectorNote] = []
    created_at: datetime
    updated_at: datetime
```

### 8.3 Agent Communication

```python
class AgentMessage(BaseModel):
    from_agent: str
    to_agent: str
    workflow_id: str
    payload: dict               # Structured, schema-validated
    context_refs: list[str]     # Memory/evidence IDs

class ContextPackage(BaseModel):
    task_description: str
    relevant_memory: list[MemoryItem]
    prior_step_outputs: list[AgentOutput]
    negative_results: list[NegativeResult]
    rcmxt_context: list[RCMXTScore] | None  # If claim under investigation
    constraints: dict           # Budget, deadline, director_notes, etc.
```

---

## 9. Core Innovations

### 9.1 RCMXT Evidence Confidence Scoring

A 5-axis vector replacing single-score confidence systems. Each axis measures a distinct dimension of evidence reliability, enabling nuanced claims like "highly reproducible but single-omics" or "robust methodology but unreplicated."

**Key design decisions:**
- X-axis (Cross-Omics) uses NULL instead of 0.5 when multi-omics data is unavailable (~80% of literature)
- Calibrated against inter-expert baseline on 150 curated claims across 3 domains (spaceflight biology, cancer genomics, neuroscience)
- Runtime distribution monitoring prevents score hedging (all-0.5 syndrome)

### 9.2 Five-Category Contradiction Taxonomy

Unlike binary "agrees/disagrees," this taxonomy classifies WHY findings contradict — enabling targeted resolution strategies rather than simply flagging disagreements.

### 9.3 Negative Results Integration

Four data sources mine unpublished failures, addressing the 85% file-drawer problem:
1. Internal Lab KB (manual, Phase 1)
2. Clinical Trial Failures (API, Phase 2)
3. Shadow Literature Mining (NLP, Phase 3b)
4. Preprint Delta Analysis (diff, Phase 3b)

---

## 10. User Workflows

### 10.1 Daily Usage Pattern

```
Morning:
  1. Open Dashboard → Mission Control
  2. Check overnight workflow results
  3. Review items in WAITING_HUMAN state
  4. Approve/modify/cancel pending decisions

Research Session:
  5. Ask Direct Query for quick lookups
  6. Launch W1 Literature Review for new topic
  7. Monitor progress via SSE updates
  8. Intervene at human checkpoints

End of Day:
  9. Review completed workflows
  10. Add negative results to Lab KB
  11. Check cost summary
```

### 10.2 First-Time Setup

```
1. Run Cold Start Protocol (~3 hours)
   a. Import publications (automated)
   b. Enter 10-20 negative results (manual wizard)
   c. RCMXT calibration (automated)
   d. Smoke test (automated)
2. Review Cold Start Report
3. Run first Direct Query
4. Launch first W1 Literature Review
```

---

## 11. Phased Delivery Roadmap

### Phase 1: Foundation + First Value (Week 1-5)
**Deliverable:** Working Direct Query + W1 Literature Review (reduced) + Dashboard (3 panels) + Cold Start

### Phase 2: Ambiguity Engine + QA (Week 6-9)
**Deliverable:** RCMXT scoring + Contradiction detection + QA agents + W3 Data Analysis + Code Sandbox

### Phase 3a: Full Biology (Week 10-12)
**Deliverable:** All specialist teams + W2 Hypothesis Generation + W6 Ambiguity Resolution

### Phase 3b: Negative Results R&D (Week 13-14)
**Deliverable:** Shadow Mining prototype + Preprint Delta prototype + RCMXT ablation study

### Phase 4: Translation + Production (Week 15-18)
**Deliverable:** W4 Manuscript + W5 Grant + Auth + HPC + Full deployment

---

## 12. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM costs exceed budget | Medium | High | Per-workflow budget caps, model tier optimization, prompt caching (90% cost reduction) |
| RCMXT scores unreliable | Medium | High | Inter-expert calibration, distribution monitoring, ablation study |
| Shadow Mining low precision | High | Medium | Constrained vocabulary (start Tier 1 only), precision gate before expansion |
| Agent hallucinations | Medium | High | Pydantic schema enforcement, QA layer, provenance tracking |
| Circular reasoning in memory | Low | Critical | Source provenance tagging, separate collections, R-axis source filtering |
| Solo developer scope creep | Medium | High | Phase gates, "progressive complexity" principle, cost validation gates |
| API rate limiting | Low | Medium | Token bucket per model tier, queue overflow with delayed retry |
| Expert recruitment delay | Medium | High | Start recruiting Week 1; 5 experts needed for RCMXT calibration |
| IRB approval delay | Medium | Medium | File determination request Week 1; most institutions take 2-4 weeks |
| Insufficient sample sizes for publication | High | Critical | 150 claims, 150 contradictions, 200 NR sentences — begin corpus building Week 3 |
| Single-domain evaluation weakness | High | High | Evaluate across 3 domains (spaceflight, cancer, neuro) not just one |
| Model version changes during evaluation | Medium | Medium | Lock model version during evaluation runs; record model_version in all results |

---

## 13. Publication Plan *(v4.1: expanded)*

### Publication Pipeline

| # | Contribution | Target Venue | Submission | Key Metric |
|---|-------------|-------------|-----------|------------|
| 1 | RCMXT scoring + ablation | NeurIPS AI4Science → Nature Methods | Week 20/24 | ICC ≥ 0.7, 150 claims × 3 domains |
| 2 | 5-category contradiction taxonomy | Bioinformatics | Week 18 | Cohen's kappa ≥ 0.7, 150+ contradictions |
| 3 | Negative Results Integration | PLOS ONE | Week 26 | Precision ≥ 0.85, recall ≥ 0.60 |
| 4 | Full BioTeam-AI framework | Nature Methods | Week 34 | User study N ≥ 5, SUS ≥ 68 |
| 5 | Benchmark dataset | Scientific Data | Week 36 | 300+ entries, FAIR-compliant |

### Open Science Requirements

- All code: GitHub (MIT license) + Zenodo DOI
- All datasets: Figshare with DOI
- Annotation guidelines: published as supplementary material
- RCMXT calibration protocol: preregistered on OSF (Week 8)
- IRB determination: filed Week 1 at Weill Cornell Medicine

### Publication Evaluation Workstream

Runs **in parallel** with the 18-week engineering roadmap. See `plan_v4.md` for detailed week-by-week schedule. Key milestones:
- Week 8: OSF preregistration
- Week 10: Expert scoring begins
- Week 18: Paper 2 (Taxonomy) submitted
- Week 24: Paper 1 (RCMXT) submitted to Nature Methods
- Week 34: Paper 4 (Framework) submitted

---

## 14. Dependencies

### External Services
- Anthropic API (Claude models — Opus, Sonnet, Haiku)
- NCBI E-utilities (PubMed access, requires API key)
- Semantic Scholar API (citation data, optional API key)
- bioRxiv/medRxiv API (preprint access, no key required)
- ClinicalTrials.gov API (trial data, no key required)

### Infrastructure
- Python 3.12+
- Node.js 20+ (frontend)
- Docker + Docker Compose
- ~50GB disk (databases, containers, backups)

### Human Resources
- 1 developer (JangKeun Kim)
- 5 domain experts for RCMXT calibration (150 claims scoring, ~4-6 hours each)
- 2 annotators for contradiction corpus (150+ contradictions, ~8-10 hours each)
- 3 independent experts for card sorting validation (taxonomy, ~2 hours each)
- N ≥ 5 biology researchers for user study (Paper 4, ~2-3 hours each, IRB approved)
- 3 external experts for blind quality rating of system outputs (Paper 4, ~3 hours each)

---

## 15. Acceptance Criteria

### Phase 1 MVP (Engineering)

- [ ] Cold Start protocol runs successfully on clean system
- [ ] Direct Query returns structured answer with sources in < 30 seconds
- [ ] W1 Literature Review completes end-to-end on "spaceflight anemia" query
- [ ] Dashboard shows real-time workflow progress via SSE
- [ ] Lab KB supports CRUD for negative results
- [ ] Actual W1 cost is within 2x of $1-3 estimate
- [ ] `/health` endpoint reports all dependency statuses
- [ ] All agent outputs pass Pydantic schema validation
- [ ] Daily backup runs and is restorable

### Publication Readiness (Parallel Workstream)

- [ ] RCMXT annotation guidelines written, pilot-tested, and refined
- [ ] 150 benchmark claims curated across 3 biology domains
- [ ] 5 domain experts recruited and scoring completed
- [ ] RCMXT inter-expert ICC(2,k) > 0.6 per axis
- [ ] RCMXT LLM-vs-expert ICC(2,1) ≥ 0.7 per axis
- [ ] 150+ contradiction corpus annotated with Cohen's kappa ≥ 0.7
- [ ] 200+ negative result sentences labeled with precision AND recall reported
- [ ] OSF preregistration filed for RCMXT calibration + ablation
- [ ] IRB determination obtained from Weill Cornell Medicine
- [ ] All code and datasets on GitHub/Figshare with DOI
- [ ] At least Paper 2 (Taxonomy) submitted to Bioinformatics by Week 18

---

## Appendices

### A. Reference Materials
- See `docs/planning/resources_guide.md` for curated tool/library references
- See `docs/planning/plan_v4.md` for detailed implementation plan
- See `docs/planning/review_v3_critical.md` for resolved technical issues
- See `BioTeam-AI_Proposal.docx` for original research proposal

### B. Glossary
- **RCMXT:** Reproducibility, Condition specificity, Methodological robustness, Cross-omics consistency, Temporal stability
- **Director:** The human researcher who oversees the AI team
- **Research Director:** The AI agent that orchestrates other agents
- **Shadow Mining:** Extracting negative results from hedging language in published papers
- **Preprint Delta:** Changes between preprint versions that may indicate retracted claims
- **Cold Start:** First-run protocol that seeds the system with initial knowledge
