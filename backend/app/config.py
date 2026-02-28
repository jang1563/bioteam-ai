"""BioTeam-AI configuration — settings, model tiers, budgets."""

from typing import Literal

from pydantic_settings import BaseSettings

ModelTier = Literal["opus", "sonnet", "haiku"]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Keys
    anthropic_api_key: str = ""
    ncbi_api_key: str = ""
    ncbi_email: str = ""
    s2_api_key: str = ""
    bioteam_api_key: str = ""  # Empty = auth disabled (dev mode)

    # Database
    database_url: str = "sqlite:///data/bioteam.db"

    # CORS (comma-separated origins)
    cors_origins: str = "http://localhost:3000"

    # Langfuse (empty = disabled)
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3001"

    # Rate limits (requests per minute per model tier)
    rate_limit_opus: int = 40
    rate_limit_sonnet: int = 80
    rate_limit_haiku: int = 200

    # Cost budgets
    session_budget: float = 50.0
    budget_alert_threshold: float = 0.8

    # Workflow defaults
    default_max_loops: int = 3
    default_concurrency_limit: int = 5

    # LLM defaults
    default_max_tokens: int = 4096
    default_max_retries: int = 2
    default_temperature: float = 0.0  # v4.2: deterministic by default for reproducibility
    model_opus: str = "claude-opus-4-6"
    model_sonnet: str = "claude-sonnet-4-6"
    model_haiku: str = "claude-haiku-4-5-20251001"

    # Backup scheduling
    backup_enabled: bool = True
    backup_interval_hours: float = 24.0

    # Digest scheduling
    digest_enabled: bool = True
    digest_check_interval_minutes: float = 60.0
    github_token: str = ""  # Optional, for higher GitHub API rate limits

    # Iterative refinement (Self-Refine loop)
    refinement_enabled: bool = True
    refinement_max_iterations: int = 2
    refinement_quality_threshold: float = 0.7
    refinement_budget_cap: float = 1.0  # $ per refinement cycle
    refinement_min_improvement: float = 0.05  # Δscore threshold for diminishing returns
    refinement_scorer_model: str = "haiku"

    # Celery / Redis (Phase 2 task queue)
    celery_broker_url: str = ""  # Empty = Celery disabled (uses asyncio fallback)
    celery_result_backend: str = ""
    celery_worker_concurrency: int = 4
    celery_task_time_limit: int = 3600  # seconds

    # MCP Healthcare Connectors (Anthropic-hosted)
    mcp_enabled: bool = False  # Master toggle — False = zero change to existing behavior
    mcp_pubmed_url: str = "https://mcp.deepsense.ai/pubmed/mcp"
    mcp_biorxiv_url: str = "https://mcp.deepsense.ai/biorxiv/mcp"
    mcp_clinical_trials_url: str = "https://mcp.deepsense.ai/clinical_trials/mcp"
    mcp_chembl_url: str = "https://mcp.deepsense.ai/chembl/mcp"
    mcp_icd10_url: str = "https://mcp.deepsense.ai/icd10/mcp"
    mcp_preferred_sources: str = "pubmed,biorxiv"  # Comma-separated active sources

    # Code Execution Sandbox (Docker)
    docker_enabled: bool = True   # Set False to skip Docker sandbox (agents output code only)
    docker_timeout_seconds: int = 120   # Per-run timeout (max 600)
    docker_memory_limit: str = "512m"   # Container RAM cap
    docker_cpu_limit: str = "1.0"       # Container CPU cap
    docker_image_python: str = "python:3.12-slim"   # Override with bioteam-python-analysis for full packages
    docker_image_r: str = "r-base:4.4"              # Override with bioteam-rnaseq for Bioconductor

    # Programmatic Tool Calling (PTC)
    ptc_enabled: bool = False  # Enable PTC for multi-tool orchestration
    ptc_container_reuse: bool = True  # Reuse sandbox containers within a workflow

    # Tool Search / Deferred Loading
    deferred_tools_enabled: bool = False  # Enable deferred tool loading for context savings

    # Data Integrity Audit
    integrity_audit_enabled: bool = True
    integrity_audit_interval_hours: float = 24.0
    crossref_email: str = ""  # For Crossref polite pool (higher rate limits)

    # Long-term task checkpointing (Phase 1)
    checkpoint_enabled: bool = True  # Enable SQLite-backed step checkpoints for long runs
    checkpoint_dir: str = "data/runs"  # Directory for progress.json files
    budget_notify_threshold: float = 0.8  # Fraction of budget used → SSE warning
    step_rerun_enabled: bool = True  # Enable step rerun/skip/inject API endpoints

    # Bioinformatics API integrations (Phase 3)
    uniprot_enabled: bool = True   # UniProt REST v2
    ensembl_enabled: bool = True   # Ensembl REST + VEP
    stringdb_enabled: bool = True  # STRING DB v12
    gwas_enabled: bool = True      # GWAS Catalog REST
    gtex_enabled: bool = True      # GTEx Portal v2
    go_enrichment_enabled: bool = True  # g:Profiler (gprofiler-official)
    ncbi_extended_enabled: bool = True  # NCBI Gene/ClinVar (reuses ncbi_api_key)
    peer_review_corpus_enabled: bool = False  # eLife/PLOS open peer review corpus (Phase 6)
    # API rate limit delays (seconds between requests)
    ensembl_rate_limit_delay: float = 0.1   # Ensembl: 15 req/sec max
    uniprot_rate_limit_delay: float = 0.1   # UniProt: 10 req/sec max
    stringdb_rate_limit_delay: float = 0.5  # STRING DB: conservative

    # Email / SMTP (for digest report delivery)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""  # Gmail address
    smtp_password: str = ""  # Gmail App Password
    digest_recipients: str = ""  # Comma-separated email addresses

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()


def get_model_map() -> dict[str, str]:
    """Resolve model map from settings (env-overridable)."""
    return {
        "opus": settings.model_opus,
        "sonnet": settings.model_sonnet,
        "haiku": settings.model_haiku,
    }


# Backward-compatible module-level mapping
MODEL_MAP: dict[str, str] = get_model_map()
