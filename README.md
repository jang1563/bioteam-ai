# BioTeam-AI

[![CI](https://github.com/jang1563/bioteam-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/jang1563/bioteam-ai/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)

BioTeam-AI is a research prototype for inspectable, biology-specific manuscript
support. It combines a FastAPI backend, a Next.js dashboard, typed report
contracts, human checkpoints, and multi-agent workflow orchestration.

The project is designed as decision support. It does not replace scientific
judgment, peer review, statistical review, or source verification.

## Current scope

| Surface | Maturity | Public evidence |
|---|---|---|
| Manuscript session and report contracts | Tested core | Offline API and model tests |
| Reviewer-risk and submission-check aggregation | Frozen integration examples | [Case studies](docs/case_studies/) |
| Story framing and RCMXT claim maps | Guided research support | Typed schemas and workflow tests |
| External integrations and live LLM evaluations | Optional / experimental | Explicit opt-in tests |

See the [research overview](docs/research_overview.md) and
[reproducible evidence index](docs/reproducible_evidence.md) for the supported
interpretation boundary.

## Public release boundary

This repository contains source code, configuration templates, offline tests,
and small synthetic fixtures. It intentionally excludes:

- private planning, application, and session artifacts;
- generated evaluation outputs and full biomedical abstracts;
- cached third-party benchmark questions or passages;
- Hugging Face dataset payloads that have not completed redistribution and
  label-quality review.

`ContradictBio-338` and `ContradictBio-1138` are currently
`not_published_pending_license`. Their private working copies are not part of
this MIT-licensed code release. See [Data release status](docs/data_release_status.md).

The machine-readable boundary is
[`release/public_release_manifest.json`](release/public_release_manifest.json),
and CI checks both the current tree and reachable Git history.

## Quick start

Prerequisites:

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- Node.js 22+
- npm

Backend:

```bash
git clone https://github.com/jang1563/bioteam-ai.git
cd bioteam-ai
uv sync --dev
cp .env.example .env

cd backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --loop asyncio
```

Frontend, in another terminal:

```bash
cd frontend
npm ci
npm run dev
```

The dashboard is served at `http://localhost:3000`; the API is served at
`http://localhost:8000`.

Most offline tests do not require an API key. Live LLM and network integration
paths require the corresponding environment variables documented in
[`.env.example`](.env.example).

ChromaDB is embedded locally and temporarily pinned below 1.0 because the
current 1.x line has an unpatched server advisory. Do not expose a Chroma HTTP
server. Existing v0.1.0 users should read the
[migration note](SECURITY.md#chromadb-deployment-boundary).

## Verify a clean checkout

These are the default CI gates:

```bash
uv sync --dev
uv run ruff check backend/
uv run python scripts/check_public_manifest.py
uv run python scripts/check_public_history.py
uv run pytest backend/tests/ \
  -m "not integration and not benchmark_slow and not benchmark" \
  -x -q --tb=short

cd frontend
npm ci
npm run lint
npm run build
```

Tests marked `integration`, `benchmark_slow`, or `benchmark` can use network
services, external data, paid model APIs, or long-running evaluations and are
therefore opt-in.

## Architecture

```text
Next.js dashboard
       |
FastAPI REST + SSE
       |
Typed agents and W1-W11 workflow runners
       |
SQLite / ChromaDB / optional external integrations
```

Key implementation paths:

- `backend/app/agents/`: agent registry and domain-specific agents
- `backend/app/workflows/`: workflow definitions and runners
- `backend/app/engines/`: evidence, integrity, narrative, and review engines
- `backend/app/models/`: typed API and report contracts
- `backend/tests/`: offline, integration, and benchmark-oriented tests
- `frontend/src/`: dashboard routes and components

## Evidence and limitations

- [Research overview](docs/research_overview.md)
- [Reproducible evidence](docs/reproducible_evidence.md)
- [Reviewer-risk frozen example](docs/case_studies/reviewer_risks_microgravity.md)
- [Submission-check frozen example](docs/case_studies/submission_checks_microgravity.md)
- [Data release status](docs/data_release_status.md)

Frozen examples verify output shape, provenance plumbing, and workflow
aggregation. They are not blinded external validation. Historical model
evaluation summaries that depend on held data are not presented here as
independently reproducible public benchmarks.

## Security and responsible use

Do not submit sensitive manuscripts or credentials to an externally hosted
instance without reviewing its storage, logging, and model-provider settings.
See [SECURITY.md](SECURITY.md) for private vulnerability reporting guidance.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Changes should keep the offline CI path
green and preserve the public release boundary.

## License and citation

The repository's source code is licensed under the [MIT License](LICENSE).
Excluded datasets and third-party materials are not relicensed by this
repository.

Citation metadata is available in [CITATION.cff](CITATION.cff).
