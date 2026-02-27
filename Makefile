# BioTeam-AI Makefile

.PHONY: help dev-minimal dev-full dev-local stop test test-llm test-agents test-workflows test-digest test-celery test-e2e lint format db-init db-migrate db-reset cold-start backup celery-worker clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# === Development Modes ===

dev-local: ## Run backend locally (no Docker, fastest iteration)
	uv run uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload

dev-minimal: ## Docker: backend + frontend only (no Langfuse)
	docker compose -f docker-compose.dev.yml up --build

dev-full: ## Docker: all services including Langfuse
	docker compose up --build

stop: ## Stop all Docker services
	docker compose down
	docker compose -f docker-compose.dev.yml down

# === Testing ===

test: ## Run all tests
	uv run pytest backend/tests/ -q --tb=short

test-llm: ## Run LLM layer tests only
	uv run pytest backend/tests/test_llm/ -v

test-agents: ## Run agent tests only
	uv run pytest backend/tests/test_agents/ -v

test-workflows: ## Run workflow tests only
	uv run pytest backend/tests/test_workflows/ -v

test-digest: ## Run digest pipeline tests only
	uv run pytest backend/tests/test_digest/ -v

test-celery: ## Run Celery integration tests
	uv run pytest backend/tests/test_celery/ -v

test-e2e: ## Run E2E Playwright tests (frontend)
	cd frontend && npx playwright test

# === Code Quality ===

lint: ## Run ruff linter
	uv run ruff check backend/

format: ## Format code with ruff
	uv run ruff format backend/

lint-fix: ## Auto-fix lint issues
	uv run ruff check backend/ --fix

# === Database ===

db-init: ## Initialize database with Alembic
	cd backend && uv run alembic upgrade head

db-migrate: ## Create new migration
	cd backend && uv run alembic revision --autogenerate -m "$(msg)"

db-reset: ## Reset database (WARNING: deletes all data)
	rm -f data/bioteam.db && cd backend && uv run alembic upgrade head

# === Celery ===

celery-worker: ## Start Celery worker (requires Redis)
	cd backend && uv run celery -A app.celery_app worker --loglevel=info --concurrency=4 -Q default,workflows

# === Cold Start ===

cold-start: ## Run Cold Start protocol
	uv run pytest backend/tests/test_cold_start/ -q

# === Backup ===

backup: ## Run manual backup
	cd backend && uv run python scripts/run_backup.py

# === Cleanup ===

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
