# BioTeam-AI

**Personal AI Science Team for Biology Research**

[Live Demo](https://jang1563.github.io/bioteam-ai/) | [Project Summary (PDF)](https://jang1563.github.io/bioteam-ai/summary.html)

A multi-agent research automation system that orchestrates specialized AI agents for literature review, hypothesis generation, data analysis, and manuscript drafting — designed for solo biology researchers and small lab groups.

Built with Claude (Anthropic) as the LLM backbone, integrating 6 academic data sources with a real-time dashboard. 23 AI agents · 10 workflow templates · Docker code execution sandbox · RCMXT evidence calibration · Preprint version tracking.

---

## Why This Exists

Biology researchers spend ~30% of their time on literature review and synthesis. This system automates the repetitive parts:

- **Research Digest**: Monitors 6 sources (PubMed, bioRxiv, arXiv, GitHub, HuggingFace, Semantic Scholar), deduplicates across sources, scores relevance, and generates AI summaries — replacing ~2 hours of manual work with a 20-second pipeline at $0.005/run.
- **Direct Query**: Ask research questions and get structured, evidence-graded answers with citation chains.
- **Contradiction Detection**: Identifies conflicting findings across papers using a 5-category taxonomy.
- **Negative Results Integration**: 85% of negative results go unpublished. The Lab Knowledge Base captures and surfaces them.
- **RCMXT Calibration**: Score biological claims on 5 axes (R/C/M/X/T). 15-claim seed corpus + LLM batch scoring + annotator IRR support for publication-ready benchmarks.
- **Preprint Delta Detector**: Track how bioRxiv/medRxiv papers evolve across revisions — diff abstracts, detect sample size changes, conclusion shifts, and method updates via LLM classification.

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Next.js Dashboard                        │
│  Mission Control · Digest · Query · Teams · Quality         │
│  Evidence · Peer Review · Integrity · Lab KB · Projects     │
│  Analytics · Drug Discovery · RCMXT Calibration            │
├──────────────────────┬─────────────────────────────────────┤
│    REST API (v1)     │         SSE (Real-time)             │
├──────────────────────┴─────────────────────────────────────┤
│                   FastAPI Backend                            │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────────┐    │
│  │ 23 Agents│  │ Engines  │  │ Integrations          │    │
│  │ Director │  │ RCMXT    │  │ PubMed  · bioRxiv     │    │
│  │ KM · PM  │  │ Ambiguity│  │ arXiv   · GitHub      │    │
│  │ T01-T10  │  │ Digest   │  │ HF      · S2          │    │
│  │ 3 QA     │  │ Integrity│  │ eLife Peer Review     │    │
│  └──────────┘  │ Preprint │  └───────────────────────┘    │
│                │ Delta    │                                  │
│  ┌──────────┐  └──────────┘  ┌───────────────────────┐    │
│  │ Workflows│  ┌──────────┐  │ Memory + Execution    │    │
│  │ W1-W10   │  │ Cost     │  │ ChromaDB · Docker     │    │
│  └──────────┘  │ Tracker  │  └───────────────────────┘    │
│                └──────────┘                                  │
├────────────────────────────────────────────────────────────┤
│                SQLite (WAL) + ChromaDB                      │
└────────────────────────────────────────────────────────────┘
```

### Agent System (23 agents)

**Strategic Layer**

| Agent | Role | Model |
|-------|------|-------|
| Research Director | Route queries, synthesize cross-domain findings | Sonnet / Opus |
| Knowledge Manager | Maintain lab knowledge base, detect contradictions | Sonnet |
| Project Manager | Track tasks, deadlines, resource allocation | Haiku |
| Ambiguity Engine | Detect conflicting claims, grade evidence quality | Sonnet |
| Digest Agent | Summarize multi-source paper batches into reports | Haiku |
| Claim Extractor | Extract structured claims with verbatim quotes | Haiku |
| Data Integrity Auditor | Audit workflow outputs for statistical errors | Sonnet |

**Domain Specialists (T01–T10)**

| Agent | Specialty |
|-------|-----------|
| T01 Genomics | Variant analysis, GWAS, population genetics |
| T02 Transcriptomics | RNA-seq, gene expression, pathway enrichment |
| T03 Proteomics | Mass spec, protein structure, PTM analysis |
| T04 Biostatistics | Experimental design, mixed models, power analysis |
| T05 ML/DL | Model selection, deep learning, feature engineering |
| T06 Systems Biology | Network analysis, flux balance, emergent properties |
| T07 Structural Biology | Protein folding, docking, cryo-EM interpretation |
| T08 Science Communication | Manuscript writing, grant narratives, figures |
| T09 Grant Writing | Specific aims, budget justification, reviewer anticipation |
| T10 Data Engineering | Pipeline design, format conversion, QC workflows |

**QA Tier (reports directly to Director)**

| Agent | Focus |
|-------|-------|
| QA Statistical Rigor | Flag underpowered comparisons, multiple testing issues |
| QA Biological Plausibility | Flag mechanistically implausible claims |
| QA Reproducibility | Flag protocol gaps and irreproducible methods |

### Evidence Scoring (RCMXT)

Every claim is scored on 5 axes, not a single confidence number:

- **R**eproducibility (0-1): Independent replication status
- **C**ondition Specificity (0-1): Context-dependent effect boundaries
- **M**ethodological Robustness (0-1): Study design rigor
- **X**-Omics Consistency (0-1, nullable): Cross-omics concordance
- **T**emporal Stability (0-1): Consistency over time

### Workflow Templates (W1–W10)

| # | Workflow | Steps | Key Capability |
|---|----------|-------|----------------|
| W1 | Literature Review | 8 | PRISMA flow · CitationValidator · RCMXT scoring |
| W2 | Hypothesis Generation | 12 | Multi-domain synthesis · novelty assessment |
| W3 | Data Analysis | 11 | Docker Python/R execution · statistical QA |
| W4 | Manuscript Writing | 10 | Section-by-section drafting · figure planning |
| W5 | Grant Proposal | 12 | Specific aims · budget · reviewer anticipation |
| W6 | Ambiguity Resolution | 6 | 5-category contradiction taxonomy |
| W7 | Data Integrity Audit | 8 | Statistical error detection · provenance tracing |
| W8 | Paper Review | 13 | Open peer review corpus · RCMXT-graded critique |
| W9 | Bioinformatics Pipeline | 10 | RNA-seq / scRNA-seq / network analysis · Docker |
| W10 | Drug Discovery | 11 | Target ID · compound screening · ADMET prediction |

## Tech Stack

**Backend**: Python 3.12 · FastAPI · SQLModel (SQLite) · ChromaDB · Anthropic SDK · Instructor

**Frontend**: Next.js 15 · React 19 · Tailwind CSS · shadcn/ui · Zustand · React Flow

**Integrations**: PubMed (Biopython) · Semantic Scholar · bioRxiv · arXiv · GitHub · HuggingFace · eLife Open Peer Review

**Infrastructure**: Docker Compose · Docker sandbox (code execution) · SSE (sse-starlette) · SQLite WAL mode

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- Anthropic API key

### Backend

```bash
# Clone and install
git clone https://github.com/jang1563/bioteam-ai.git
cd bioteam-ai

# Create virtual environment
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY

# Run
uvicorn app.main:app --app-dir backend --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev    # http://localhost:3000
```

### Docker (Full Stack)

```bash
docker compose up
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/agents` | List all 23 agents and status |
| `GET` | `/api/v1/agents/{id}` | Agent detail + execution history |
| `POST` | `/api/v1/direct-query` | Submit a research question |
| `GET` | `/api/v1/direct-query/stream` | SSE stream for query progress |
| `POST` | `/api/v1/auth/stream-token` | Issue short-lived HMAC SSE auth token |
| `POST` | `/api/v1/workflows` | Create a workflow (W1–W10) |
| `GET` | `/api/v1/workflows/{id}` | Workflow status + step results |
| `GET/POST` | `/api/v1/digest/topics` | Manage digest topic profiles |
| `POST` | `/api/v1/digest/topics/{id}/run` | Trigger paper fetch + summarize |
| `GET` | `/api/v1/digest/reports` | Get AI-generated digest reports |
| `GET/POST` | `/api/v1/negative-results` | Lab knowledge base CRUD |
| `GET` | `/api/v1/contradictions` | View detected contradictions |
| `GET` | `/api/v1/integrity` | Data integrity audit results |
| `POST` | `/api/v1/cold-start/run` | Initialize system with seed data |
| `POST` | `/api/v1/rcmxt/score` | Score a biological claim on RCMXT axes (single) |
| `POST` | `/api/v1/rcmxt/batch` | Batch-score multiple claims with axis summary |
| `GET` | `/api/v1/rcmxt/corpus-stats` | RCMXT seed corpus stats (15 claims, 3 domains) |
| `POST` | `/api/v1/preprint-delta/compare` | Compare v1 vs latest of a bioRxiv/medRxiv preprint |
| `POST` | `/api/v1/preprint-delta/batch` | Batch compare up to 10 DOIs |
| `GET` | `/api/v1/analytics/overview` | System activity + workflow + cost summary |

## Research Digest Pipeline

The automated literature monitoring system:

```
TopicProfile (queries + sources)
    │
    ├── PubMed ──────┐
    ├── bioRxiv ─────┤
    ├── arXiv ───────┤
    ├── GitHub ──────┼── Fetch (~160 entries, parallel)
    ├── HuggingFace ─┤
    └── Semantic S. ──┘
            │
     Deduplicate (DOI / arXiv ID / title)
            │
     Score Relevance (regex word-boundary matching)
            │
     Persist Top 100 → SQLite
            │
     Summarize Top 30 → DigestAgent (Haiku)
            │
     DigestReport (summary + highlights + trends)
```

**Cost**: ~$0.005 per run (Haiku model). All 6 APIs are free.

### Real Run Output (Feb 25, 2026)

Single run with topic "AI in Biology Research" — 3 queries across PubMed + arXiv:

```
39 entries fetched (9 PubMed, 30 arXiv)
6 highlights generated with real paper URLs
Pipeline time: ~23 seconds
LLM cost: $0.026
```

**Sample highlight from real data:**
> **scKGBERT: a knowledge-enhanced foundation model for single-cell transcriptomics** (PubMed)
> Foundation model integrating 41M single-cell RNA-seq profiles with 8.9M protein-protein
> interactions using Gaussian attention for superior biomarker identification.

All papers link to real PubMed/arXiv URLs with full abstracts, authors, and relevance scores.

## Testing

```bash
# Core suite (1950 tests, excludes benchmarks and live-API integration tests)
.venv/bin/pytest backend/tests/ --ignore=backend/tests/benchmarks \
    --ignore=backend/tests/test_integrations -q

# Specific modules
.venv/bin/pytest backend/tests/test_digest/ -q        # Digest pipeline
.venv/bin/pytest backend/tests/test_api/ -q            # API endpoints
.venv/bin/pytest backend/tests/test_security/ -q       # Auth + fuzzing
.venv/bin/pytest backend/tests/test_workflows/ -q      # W1-W10 runners
.venv/bin/pytest backend/tests/test_execution/ -q      # Docker sandbox + checkpoint
.venv/bin/pytest backend/tests/test_engines/ -q        # RCMXT · preprint delta · integrity

# Optional: benchmarks (RCMXT calibration, live model calls)
.venv/bin/pytest backend/tests/benchmarks/ -q

# Frontend build check
cd frontend && npm run build
```

**Current status:** 1950 passed · 0 failed · 21 skipped

## BioReview-Bench

W8 Paper Review is evaluated against **BioReview-Bench**, an open benchmark derived from eLife's public peer review corpus (29 articles with full decision letters).

**Benchmark methodology**: Ground truth concerns are extracted from eLife decision letters via LLM (Haiku). W8-generated review text is matched against ground truth using keyword + cosine similarity (ConcernMatcher). The W8 pipeline runs via `article_data` injection (eLife XML body text), bypassing PDF parsing.

| Split | Articles | Mean Recall | Mean Major Recall | Mean Precision |
|-------|----------|-------------|-------------------|----------------|
| Pilot (5 curated) | 5 | 70.3% | 64.3% | 32.3% |
| **Corpus (eLife)** | **29** | **39.6%** | **41.7%** | **16.0%** |

**Corpus distribution**: 22/29 articles achieved >0% recall; 12/29 achieved ≥50% recall; 3/29 achieved 100% recall. Major revision papers (where reviewers raised more serious concerns) tend to score higher recall (mean ~55%) vs. minor revision papers (~35%), reflecting W8's stronger performance on prominent methodological and statistical issues.

**Corpus collection**: `backend/scripts/collect_elife_corpus.py` — bulk-collects eLife articles with decision letters + full body text (JATS XML via CDN). Currently 29 articles across biology, immunology, cell biology, and evolutionary biology.

**Run benchmark**:
```bash
# Collect corpus (requires no API key — eLife is open access)
uv run python backend/scripts/collect_elife_corpus.py --max 50

# Run W8 on all corpus articles + evaluate
uv run python backend/scripts/run_w8_benchmark.py --source corpus --run-w8 --use-llm --max 50

# Report only (uses cached W8 results)
uv run python backend/scripts/run_w8_benchmark.py --source corpus
```

## Cost Analysis

| Scenario | Monthly Cost |
|----------|-------------|
| 1 topic, daily digest | $0.15 |
| 3 topics, daily | $0.45 |
| 5 topics (3 daily + 2 weekly) | $0.49 |
| 10 topics, daily | $1.50 |

All external APIs (PubMed, bioRxiv, arXiv, GitHub, HuggingFace, Semantic Scholar) are free. Infrastructure is local (SQLite + ChromaDB). Budget cap: $50/session.

## Project Structure

```
bioteam-ai/
├── backend/
│   ├── app/
│   │   ├── agents/          # 23 AI agents (specs/ YAML + registry + prompts)
│   │   ├── api/v1/          # REST endpoints (13 route files)
│   │   ├── cold_start/      # Seed data + RCMXT 150-claim benchmark
│   │   ├── cost/            # LLM cost tracking + budget enforcement
│   │   ├── db/              # SQLite WAL + Alembic migrations
│   │   ├── digest/          # Multi-source paper pipeline (6 sources)
│   │   ├── engines/         # RCMXT · preprint-delta · contradiction · integrity · citation
│   │   ├── execution/       # DockerCodeRunner + container Dockerfiles
│   │   ├── integrations/    # PubMed · S2 · bioRxiv · arXiv · GitHub · HF · eLife
│   │   ├── llm/             # Anthropic layer + circuit breaker + mock for testing
│   │   ├── memory/          # ChromaDB semantic memory (3 collections)
│   │   ├── middleware/      # Auth (Bearer + HMAC stream tokens) · rate limiting
│   │   ├── models/          # Pydantic/SQLModel schemas (evidence · workflow · agent)
│   │   ├── security/        # Stream token signing + fuzzing tests
│   │   └── workflows/       # W1-W10 pipeline runners + note processor
│   └── tests/               # 1950 tests across 25 categories (0 failures)
├── frontend/
│   └── src/
│       ├── app/             # 18 Next.js pages: / · /digest · /query · /teams
│       │                    #   /quality · /evidence · /peer-review · /integrity
│       │                    #   /lab-kb · /projects · /settings · /rcmxt
│       │                    #   /analytics · /drug-discovery · /agents
│       ├── components/      # Dashboard UI (shadcn/ui + React Flow)
│       ├── hooks/           # React hooks (agents, workflows, digest, SSE)
│       ├── lib/             # API client with auth + retry
│       ├── stores/          # Zustand state
│       └── types/           # TypeScript API types
├── docs/
│   ├── planning/            # PRD · implementation plan v4.2 · resources guide
│   ├── annotation/          # RCMXT annotation guidelines + 15-claim seed corpus CSV
│   └── publication/         # Paper 1 draft: RCMXT calibration + IRR methodology
├── docker-compose.yml       # Full stack deployment
└── pyproject.toml           # Python project config (Python 3.12+)
```

## Security

- **Auth**: Bearer token via `BIOTEAM_API_KEY` (empty = dev mode). Production requires `APP_ENV=production` + non-empty key.
- **SSE/Stream Auth**: Frontend issues a short-lived HMAC-signed token via `POST /api/v1/auth/stream-token` (TTL 120s). Passed as `?token=...` for EventSource. Raw API key in SSE query param rejected (hardened Feb 2026).
- **Rate Limiting**: Token bucket — 60 rpm global, 10 rpm expensive endpoints
- **CORS**: Config-driven via `CORS_ORIGINS` env var
- **Circuit Breaker**: 5 failures → 60s cooldown → single probe (HALF_OPEN state)
- **Input Validation**: Pydantic + Literal types for all API inputs
- **Citation Post-Validation**: Direct Query answers scanned for DOI/PMID patterns and author-year references (e.g., "Smith et al. 2023"); unverified citations flagged in `ungrounded_citations`
- **Docker Sandbox**: Agent-generated code runs in isolated containers (no network, read-only FS, memory/CPU caps, `--user nobody`)
- **Fuzzing**: 106 security tests (SQL injection, XSS, oversized payloads)

## License

MIT License. See [LICENSE](LICENSE).
