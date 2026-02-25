"""BioTeam-AI configuration — settings, model tiers, budgets."""

from typing import Literal

from pydantic_settings import BaseSettings

# Claude model ID mapping
MODEL_MAP: dict[str, str] = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-5-20250929",
    "haiku": "claude-haiku-4-5-20251001",
}

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

    # Data Integrity Audit
    integrity_audit_enabled: bool = True
    integrity_audit_interval_hours: float = 24.0
    crossref_email: str = ""  # For Crossref polite pool (higher rate limits)

    # Email / SMTP (for digest report delivery)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""  # Gmail address
    smtp_password: str = ""  # Gmail App Password
    digest_recipients: str = ""  # Comma-separated email addresses

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
