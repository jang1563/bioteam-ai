# BioTeam-AI Makefile

.PHONY: help dev-minimal dev-full dev-local stop test test-llm test-agents test-workflows test-digest test-celery test-e2e lint format db-init db-migrate db-reset cold-start backup celery-worker clean sandbox-build sandbox-build-fast sandbox-test check-version

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

# === Code Execution Sandbox ===

SANDBOX_DIR := backend/app/execution/containers

sandbox-build: ## Build all 4 Docker sandbox images (slow: ~15-30 min for bioconductor)
	docker build -f $(SANDBOX_DIR)/Dockerfile.python_analysis -t bioteam-python-analysis $(SANDBOX_DIR)
	docker build -f $(SANDBOX_DIR)/Dockerfile.genomics       -t bioteam-genomics       $(SANDBOX_DIR)
	docker build -f $(SANDBOX_DIR)/Dockerfile.singlecell     -t bioteam-singlecell     $(SANDBOX_DIR)
	docker build -f $(SANDBOX_DIR)/Dockerfile.rnaseq         -t bioteam-rnaseq         $(SANDBOX_DIR)
	@echo "✓ All sandbox images built. Set DOCKER_IMAGE_PYTHON=bioteam-python-analysis in .env to use."

sandbox-build-fast: ## Build only the Python analysis image (fast: ~2-3 min)
	docker build -f $(SANDBOX_DIR)/Dockerfile.python_analysis -t bioteam-python-analysis $(SANDBOX_DIR)
	@echo "✓ Python analysis image built. Set DOCKER_IMAGE_PYTHON=bioteam-python-analysis in .env to use."

sandbox-test: ## Run live Docker sandbox integration tests (requires Docker daemon)
	uv run pytest backend/tests/test_execution/test_docker_runner.py --run-integration -v

# === Cold Start ===

cold-start: ## Run Cold Start protocol
	uv run pytest backend/tests/test_cold_start/ -q

# === Backup ===

backup: ## Run manual backup
	cd backend && uv run python scripts/run_backup.py

# === Version Check ===

check-version: ## Verify project version is consistent across pyproject.toml and backend
	@PY_VER=$$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])") && \
	APP_VER=$$(python -c "import sys; sys.path.insert(0,'backend'); from app import __version__; print(__version__)") && \
	if [ "$$PY_VER" != "$$APP_VER" ]; then \
		echo "ERROR: Version mismatch — pyproject.toml=$$PY_VER  app/__init__.py=$$APP_VER"; exit 1; \
	else \
		echo "OK: project version $$PY_VER consistent"; \
	fi

# === Cleanup ===

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
