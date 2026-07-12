# Contributing to BioTeam-AI

Thank you for your interest in contributing to BioTeam-AI! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/<your-username>/bioteam-ai.git`
3. Create a feature branch: `git checkout -b feat/your-feature`
4. Set up your environment (see below)

## Development Setup

### Backend

```bash
# Install dependencies (requires uv)
uv sync --dev

# Copy environment template
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY at minimum

# Start the backend (--loop asyncio is REQUIRED for ChromaDB)
cd backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --loop asyncio
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Docker

```bash
# Minimal (backend + frontend)
docker compose -f docker-compose.dev.yml up

# Full stack (includes Redis, Celery, Langfuse)
docker compose up
```

## Running Tests

```bash
# Backend offline suite
uv run pytest backend/tests/ \
    -m "not integration and not benchmark_slow and not benchmark" \
    -x -q --tb=short

# Public release boundary
uv run python scripts/check_public_manifest.py
uv run python scripts/check_public_history.py

# Frontend lint + build
cd frontend && npm run lint && npm run build

# E2E tests (requires backend running)
cd frontend && npx playwright test
```

## Code Style

- **Python**: Enforced by [ruff](https://docs.astral.sh/ruff/) — `line-length=120`, target Python 3.12
- **TypeScript**: ESLint with Next.js config
- **Formatting**: Run `make format` before committing

```bash
# Lint
make lint

# Auto-fix
make lint-fix
```

## Pull Request Process

1. Ensure all tests pass (`make test`)
2. Ensure linting passes (`make lint`)
3. Update documentation if your change affects public APIs or behavior
4. Write a clear PR description explaining **what** and **why**
5. Keep PRs focused — one feature or fix per PR

## Commit Messages

Follow conventional commit style:

```
feat: add new endpoint for batch RCMXT scoring
fix: handle ChromaDB connection timeout gracefully
test: add W9 adapter integration tests
docs: update API endpoint table in README
refactor: extract shared eval utilities into eval_common.py
```

## Architecture Notes

Before making changes, review:

- [Research Overview](docs/research_overview.md) — Public scope, maturity, and claim boundaries
- [Reproducible Evidence](docs/reproducible_evidence.md) — Quality gates and validation paths
- [Data Release Status](docs/data_release_status.md) — Public/private artifact boundary
- [Annotation Guidelines](docs/annotation/) — RCMXT scoring and contradiction taxonomy

### Key Conventions

- **pytest-asyncio**: All async tests must use `@pytest.mark.asyncio`
- **AgentOutput**: Access via `out.output` (dict) and `out.summary` (str)
- **ContextPackage**: `task_description` is required; there is no `query` field
- **SSE events**: Use `"workflow.step_started"` / `"workflow.step_completed"` naming
- **ChromaDB**: Always use `--loop asyncio` with uvicorn (ChromaDB crashes with uvloop)

## Reporting Issues

Use [GitHub Issues](https://github.com/jang1563/bioteam-ai/issues) with the provided templates. Include:

- Steps to reproduce
- Expected vs. actual behavior
- Python/Node versions and OS
- Relevant log output

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).

Dataset payloads and third-party benchmark materials are not relicensed by a
code contribution.
