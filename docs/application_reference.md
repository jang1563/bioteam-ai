# BioTeam-AI — Application Reference

Quick reference for including this project in job applications.

---

## Links

| Resource | URL |
|----------|-----|
| GitHub Repo | https://github.com/jang1563/bioteam-ai |
| Live Demo | https://jang1563.github.io/bioteam-ai/ |
| Project Summary | https://jang1563.github.io/bioteam-ai/summary.html |
| PDF (local) | ~/Downloads/BioTeam-AI_ Personal AI Science Team for Biology Research.pdf |

---

## One-Liner Description

> Personal AI Science Team — a multi-agent system using Claude API that automates literature monitoring, hypothesis generation, and research synthesis for biology researchers.

## Elevator Pitch (3 sentences)

BioTeam-AI is an open-source multi-agent research automation system built on Anthropic's Claude API. It orchestrates 18 specialized LLM agents to monitor 6 academic data sources (PubMed, bioRxiv, arXiv, GitHub, HuggingFace, Semantic Scholar), automatically collecting, deduplicating, scoring, and summarizing the latest papers — replacing ~2 hours of manual literature review with a 23-second pipeline at $0.005/run. The system includes a real-time Next.js dashboard, 5-dimension reproducibility scoring (RCMXT), and 725+ automated tests.

---

## Key Numbers

| Metric | Value |
|--------|-------|
| LLM Agents | 18 across 3 tiers |
| Data Sources | 6 (PubMed, bioRxiv, arXiv, GitHub, HuggingFace, Semantic Scholar) |
| Automated Tests | 725+ (including 106 security/fuzzing) |
| Cost per Digest Run | $0.005 (Haiku) |
| Real Run Result | 39 papers fetched, 6 AI highlights, $0.026 |
| ROI vs Manual | 962x (cost), 300x (time) |
| Pipeline Speed | ~23 seconds per cycle |
| Source Files | 69 backend + 56 frontend |
| Test Coverage Categories | 18 |

---

## Tech Stack

**Backend**: Python 3.12, FastAPI, SQLModel (SQLite), ChromaDB, Anthropic Claude API (Haiku/Sonnet), Instructor, SSE

**Frontend**: Next.js 16, React 19, Tailwind CSS 4, shadcn/ui, Zustand, React Flow

**Integrations**: PubMed (Biopython), Semantic Scholar, bioRxiv, arXiv, GitHub, HuggingFace

**Infrastructure**: Docker Compose, SQLite WAL, sse-starlette

---

## Architecture Summary

```
Tier 1 — Directors (3): Research Director, Knowledge Manager, Project Manager
Tier 2 — Teams (10): Transcriptomics, Data Engineering, + 8 specialists
Tier 3 — Engines (5): Digest Engine, Ambiguity Engine, RCMXT Scoring, Citation Validator, Session Manifest
```

---

## Key Features (for resume/cover letter)

1. **Multi-Source Literature Digest** — Automated pipeline fetching from 6 academic sources with word-boundary relevance scoring, deduplication, and AI summarization
2. **RCMXT Evidence Scoring** — 5-axis evidence quality assessment (Reproducibility, Condition Specificity, Methodological Robustness, Cross-Omics Consistency, Temporal Stability)
3. **Ambiguity Detection Engine** — Identifies conflicting findings across papers with resolution workflows
4. **Real-Time Dashboard** — Next.js 16 with SSE activity feed, agent monitoring, workflow visualization
5. **Production Security** — Bearer auth, rate limiting (token bucket), circuit breaker, CORS hardening, 106 fuzzing tests
6. **Cost-Effective** — $0.005/run using Claude Haiku, 962x ROI vs manual review

---

## Relevance to Anthropic (AI for Science)

- **Direct Claude API expertise**: Built entire system on Anthropic SDK + Instructor, not a wrapper
- **Real scientific workflow**: Solves actual biology researcher pain points (literature overload)
- **Responsible AI patterns**: Evidence grounding, hallucination mitigation via RCMXT scoring, citation validation
- **Cost optimization**: Strategic model tier selection (Haiku for bulk, Sonnet for critical reasoning)
- **Production readiness**: Auth, rate limiting, circuit breaker, comprehensive test suite

---

## Suggested Application Phrasing

### For Resume / Project Section:

> **BioTeam-AI** — Open-source multi-agent research automation system (Python/FastAPI/Next.js)
> - Designed and built 18 LLM agents on Claude API for automated literature monitoring across 6 academic data sources
> - Reduced manual literature review time from 2 hours to 23 seconds per cycle at $0.005/run (962x ROI)
> - Implemented 5-dimension evidence scoring (RCMXT), real-time SSE dashboard, and 725+ automated tests
> - GitHub: github.com/jang1563/bioteam-ai | Live Demo: jang1563.github.io/bioteam-ai

### For Cover Letter:

> To demonstrate my understanding of AI applications in scientific research, I built BioTeam-AI — an open-source multi-agent system that uses Claude to automate literature monitoring across PubMed, bioRxiv, arXiv, and other sources. The system fetches, deduplicates, scores, and summarizes papers in 23 seconds at $0.005 per run, replacing hours of manual work. This project reflects my conviction that AI tools should be practical, cost-effective, and grounded in real scientific workflows. [GitHub: github.com/jang1563/bioteam-ai]

---

## Git History (for reference)

```
2d48b18 Add real data run results and fix missing arxiv dependency
7658465 Add GitHub Pages deployment, project summary, and repo metadata
795b9e5 Convert demo showcase from Korean to English
cdcc79a Update README with GitHub username
e3dc48a Add expert review fixes, README, LICENSE, and public release prep
a117f5d Add Research Digest, Ambiguity Engine, Direct Query streaming
e1b9a24 Add Tier 1 reproducibility: RCMXT scoring, citation validation
ca983fa Add W1 pipeline execution, Direct Query UI, workflow result display
f16f79b Add security hardening, a11y, error handling, fuzzing tests
335aac4 Add Next.js 16 dashboard frontend with full UI
fa2fa5a Add workflow list endpoint and negative results CRUD API
3ad48c4 Add security/stability hardening Phase A+B+C
2cf9a46 Initial commit: Week 5 backend complete (v0.5-week5)
```
