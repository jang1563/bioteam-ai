"""BioTeam-AI configuration — settings, model tiers, budgets."""

from pydantic_settings import BaseSettings
from typing import Literal


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

    # Database
    database_url: str = "sqlite:///data/bioteam.db"

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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
