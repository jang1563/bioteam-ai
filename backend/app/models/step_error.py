"""StepErrorReport — structured error classification for W9 troubleshooting.

Error types:
  TRANSIENT     → auto-retry (network timeout, 503, rate limit)
  RECOVERABLE   → retry after param adjustment (token limit, input too large)
  USER_INPUT    → needs user action (file missing, API key absent, bad format)
  SKIP_SAFE     → step can be skipped (optional enrichment, non-critical)
  FATAL         → must abort (DB corruption, required agent unavailable)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

ErrorType = Literal["TRANSIENT", "RECOVERABLE", "USER_INPUT", "SKIP_SAFE", "FATAL"]
SuggestedAction = Literal[
    "RETRY", "RETRY_WITH_PARAMS", "SKIP", "USER_PROVIDE_INPUT", "ABORT"
]


class StepErrorReport(BaseModel):
    """Structured error report for a failed workflow step."""

    step_id: str
    agent_id: str = ""
    error_type: ErrorType
    error_message: str
    technical_detail: str = ""  # Full stack trace (not shown to user by default)
    recovery_suggestions: list[str] = Field(default_factory=list)
    retry_count: int = 0
    suggested_action: SuggestedAction = "RETRY"
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def classify(
        cls,
        step_id: str,
        agent_id: str,
        exception: Exception,
        retry_count: int = 0,
    ) -> "StepErrorReport":
        """Classify an exception into a StepErrorReport.

        Heuristics:
        - httpx.TimeoutException, ConnectionError → TRANSIENT
        - httpx status 429 (rate limit), 503 → TRANSIENT
        - httpx status 400 (bad request), missing file → USER_INPUT
        - httpx status 404 for optional data → SKIP_SAFE
        - ValidationError for non-critical steps → SKIP_SAFE
        - RuntimeError / critical system errors → FATAL
        - Everything else → RECOVERABLE
        """
        import traceback

        import httpx

        err_str = str(exception)
        tech_detail = traceback.format_exc()
        error_type: ErrorType
        suggestions: list[str]
        action: SuggestedAction

        if isinstance(exception, (httpx.TimeoutException, httpx.ConnectError)):
            error_type = "TRANSIENT"
            suggestions = [
                "Check network connectivity and retry.",
                "You can restart the workflow shortly.",
            ]
            action = "RETRY"
        elif isinstance(exception, httpx.HTTPStatusError):
            status = exception.response.status_code
            if status in (429, 503, 502, 504):
                error_type = "TRANSIENT"
                suggestions = ["Retrying automatically in a moment.", "The API server is temporarily unstable."]
                action = "RETRY"
            elif status == 400:
                error_type = "USER_INPUT"
                suggestions = ["Check the input data format.", "Review the API request parameters."]
                action = "USER_PROVIDE_INPUT"
            elif status == 404:
                error_type = "SKIP_SAFE"
                suggestions = ["Data not found. This step can be skipped."]
                action = "SKIP"
            elif status == 401:
                error_type = "USER_INPUT"
                suggestions = ["API key is missing or invalid. Check your environment variables."]
                action = "USER_PROVIDE_INPUT"
            else:
                error_type = "RECOVERABLE"
                suggestions = ["Adjust parameters and retry."]
                action = "RETRY_WITH_PARAMS"
        elif isinstance(exception, FileNotFoundError):
            error_type = "USER_INPUT"
            suggestions = [
                f"File not found: {err_str}",
                "Check data_manifest_path or provide a valid file path.",
            ]
            action = "USER_PROVIDE_INPUT"
        elif isinstance(exception, MemoryError):
            error_type = "FATAL"
            suggestions = ["Out of memory. Reduce input data size or increase server memory."]
            action = "ABORT"
        elif "max_tokens" in err_str.lower() or "context_length" in err_str.lower():
            error_type = "RECOVERABLE"
            suggestions = [
                "Input too long. Reduce gene list size or number of papers.",
                "Consider splitting the step into smaller chunks.",
            ]
            action = "RETRY_WITH_PARAMS"
        else:
            error_type = "RECOVERABLE"
            suggestions = ["Adjust parameters and retry."]
            action = "RETRY_WITH_PARAMS"

        return cls(
            step_id=step_id,
            agent_id=agent_id,
            error_type=error_type,
            error_message=err_str,
            technical_detail=tech_detail,
            recovery_suggestions=suggestions,
            retry_count=retry_count,
            suggested_action=action,
        )
