# BioTeam-AI

**Personal AI Science Team for Biology Research**

[Live Demo](https://jang1563.github.io/bioteam-ai/) | [Project Summary (PDF)](https://jang1563.github.io/bioteam-ai/summary.html)

A multi-agent research automation system that orchestrates specialized AI agents for literature review, hypothesis generation, data analysis, and manuscript drafting — designed for solo biology researchers and small lab groups.

Built with Claude (Anthropic) as the LLM backbone, integrating 6 academic data sources with a real-time dashboard.

---

## Why This Exists

Biology researchers spend ~30% of their time on literature review and synthesis. This system automates the repetitive parts:

- **Research Digest**: Monitors 6 sources (PubMed, bioRxiv, arXiv, GitHub, HuggingFace, Semantic Scholar), deduplicates across sources, scores relevance, and generates AI summaries — replacing ~2 hours of manual work with a 20-second pipeline at $0.005/run.
- **Direct Query**: Ask research questions and get structured, evidence-graded answers with citation chains.
- **Contradiction Detection**: Identifies conflicting findings across papers using a 5-category taxonomy.
- **Negative Results Integration**: 85% of negative results go unpublished. The Lab Knowledge Base captures and surfaces them.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Next.js Dashboard                     │
│         Mission Control · Digest · Query · Lab KB        │
├──────────────────────┬──────────────────────────────────┤
│    REST API (v1)     │         SSE (Real-time)          │
├──────────────────────┴──────────────────────────────────┤
│                   FastAPI Backend                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐   │
│  │ Agents   │  │ Engines  │  │ Integrations         │   │
│  │ Director │  │ RCMXT    │  │ PubMed  · bioRxiv    │   │
│  │ KM · PM  │  │ Ambiguity│  │ arXiv   · GitHub     │   │
│  │ T02 · T10│  │ Digest   │  │ HF      · S2         │   │
│  └──────────┘  └──────────┘  └──────────────────────┘   │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐   │
│  │ Workflows│  │ Cost     │  │ Memory               │   │
│  │ W1-W8    │  │ Tracker  │  │ ChromaDB (3 coll.)   │   │
│  └──────────┘  └──────────┘  └──────────────────────┘   │
├─────────────────────────────────────────────────────────┤
│                SQLite (WAL) + ChromaDB                    │
└─────────────────────────────────────────────────────────┘
```

### Agent System

| Agent | Role | Model |
|-------|------|-------|
| Research Director | Route queries, synthesize cross-domain findings | Sonnet / Opus |
| Knowledge Manager | Maintain lab knowledge base, detect contradictions | Sonnet |
| Project Manager | Track tasks, deadlines, resource allocation | Haiku |
| Transcriptomics (T02) | RNA-seq analysis, gene expression, pathway enrichment | Sonnet |
| Data Engineering (T10) | Pipeline design, format conversion, QC workflows | Haiku |
| Ambiguity Engine | Detect conflicting claims, grade evidence quality | Sonnet |
| Digest Agent | Summarize multi-source paper batches into reports | Haiku |

### Evidence Scoring (RCMXT)

Every claim is scored on 5 axes, not a single confidence number:

- **R**eproducibility (0-1): Independent replication status
- **C**ondition Specificity (0-1): Context-dependent effect boundaries
- **M**ethodological Robustness (0-1): Study design rigor
- **X**-Omics Consistency (0-1, nullable): Cross-omics concordance
- **T**emporal Stability (0-1): Consistency over time

## Tech Stack

**Backend**: Python 3.12 · FastAPI · SQLModel (SQLite) · ChromaDB · Anthropic SDK · Instructor

**Frontend**: Next.js 16 · React 19 · Tailwind CSS 4 · shadcn/ui · Zustand · React Flow

**Integrations**: PubMed (Biopython) · Semantic Scholar · bioRxiv · arXiv · GitHub · HuggingFace

**Infrastructure**: Docker Compose · SSE (sse-starlette) · SQLite WAL mode

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
| `GET` | `/api/v1/agents` | List all agents and status |
| `POST` | `/api/v1/direct-query` | Submit a research question |
| `GET` | `/api/v1/direct-query/stream` | SSE stream for query progress |
| `POST` | `/api/v1/auth/stream-token` | Issue short-lived SSE auth token |
| `POST` | `/api/v1/workflows` | Create a workflow (W1-W8) |
| `GET/POST` | `/api/v1/digest/topics` | Manage digest topic profiles |
| `POST` | `/api/v1/digest/topics/{id}/run` | Trigger paper fetch + summarize |
| `GET` | `/api/v1/digest/reports` | Get AI-generated digest reports |
| `GET/POST` | `/api/v1/negative-results` | Lab knowledge base CRUD |
| `GET` | `/api/v1/contradictions` | View detected contradictions |
| `POST` | `/api/v1/cold-start/run` | Initialize system with seed data |

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
# Core suite (1500+ tests, excludes benchmarks and live-API integration tests)
uv run pytest backend/tests/ --ignore=backend/tests/benchmarks \
    --ignore=backend/tests/test_integrations/test_semantic_scholar.py -q

# Specific modules
uv run pytest backend/tests/test_digest/ -q        # Digest pipeline
uv run pytest backend/tests/test_api/ -q            # API endpoints
uv run pytest backend/tests/test_security/ -q       # Auth + fuzzing
uv run pytest backend/tests/test_workflows/ -q      # W1-W8 runners

# Optional benchmarks (requires: uv sync --group benchmarks)
uv run pytest backend/tests/benchmarks/ -q

# Frontend build
cd frontend && npm run build
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
│   │   ├── agents/          # 22 AI agents + specs + prompts
│   │   ├── api/v1/          # REST endpoints (11 route files)
│   │   ├── cost/            # LLM cost tracking + budgets
│   │   ├── db/              # SQLite + migrations
│   │   ├── digest/          # Multi-source paper pipeline
│   │   ├── engines/         # RCMXT, contradiction, integrity, PDF, W8 report
│   │   ├── integrations/    # 8 external API clients + MCP connectors
│   │   ├── llm/             # Anthropic layer + mock for testing
│   │   ├── memory/          # ChromaDB semantic memory
│   │   ├── middleware/      # Auth, rate limiting
│   │   ├── models/          # Pydantic/SQLModel schemas
│   │   ├── security/        # Stream token signing
│   │   └── workflows/       # W1-W8 pipeline runners
│   └── tests/               # 1500+ tests across 20 categories
├── frontend/
│   └── src/
│       ├── app/             # Next.js pages (/, /digest, /query, /lab-kb, /settings)
│       ├── components/      # Dashboard UI (shadcn/ui)
│       ├── hooks/           # React hooks (agents, workflows, digest, SSE)
│       ├── lib/             # API client with auth + retry
│       ├── stores/          # Zustand state
│       └── types/           # TypeScript API types
├── docs/planning/           # PRD, implementation plan, resources guide
├── docker-compose.yml       # Full stack deployment
└── pyproject.toml           # Python project config
```

## Security

- **Auth**: Bearer token via `BIOTEAM_API_KEY` (empty = dev mode)
- **SSE/Stream Auth**: Frontend issues a short-lived HMAC-signed token via `POST /api/v1/auth/stream-token` (TTL 120s) and passes it as `?token=...` for EventSource. On disconnect, the client re-issues a fresh token before reconnecting (exponential backoff).
- **Rate Limiting**: Token bucket — 60 rpm global, 10 rpm expensive endpoints
- **CORS**: Config-driven via `CORS_ORIGINS` env var
- **Circuit Breaker**: 5 failures → 60s cooldown → probe
- **Input Validation**: Pydantic + Literal types for all API inputs
- **Citation Post-Validation**: Direct Query answers are scanned for DOI/PMID patterns; any citation not found in retrieved sources is flagged in `ungrounded_citations`
- **Fuzzing**: 106 security tests (SQL injection, XSS, oversized payloads)

## License

MIT License. See [LICENSE](LICENSE).
