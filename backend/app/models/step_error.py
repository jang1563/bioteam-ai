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
                "네트워크 연결을 확인하고 재시도하세요.",
                "잠시 후 워크플로우를 재시작할 수 있습니다.",
            ]
            action = "RETRY"
        elif isinstance(exception, httpx.HTTPStatusError):
            status = exception.response.status_code
            if status in (429, 503, 502, 504):
                error_type = "TRANSIENT"
                suggestions = ["잠시 후 자동 재시도합니다.", "API 서버가 일시적으로 불안정합니다."]
                action = "RETRY"
            elif status == 400:
                error_type = "USER_INPUT"
                suggestions = ["입력 데이터 형식을 확인하세요.", "API 요청 파라미터를 점검하세요."]
                action = "USER_PROVIDE_INPUT"
            elif status == 404:
                error_type = "SKIP_SAFE"
                suggestions = ["데이터를 찾을 수 없습니다. 이 단계를 건너뛸 수 있습니다."]
                action = "SKIP"
            elif status == 401:
                error_type = "USER_INPUT"
                suggestions = ["API 키가 없거나 올바르지 않습니다. 환경변수를 확인하세요."]
                action = "USER_PROVIDE_INPUT"
            else:
                error_type = "RECOVERABLE"
                suggestions = ["파라미터를 조정하여 재시도하세요."]
                action = "RETRY_WITH_PARAMS"
        elif isinstance(exception, FileNotFoundError):
            error_type = "USER_INPUT"
            suggestions = [
                f"파일을 찾을 수 없습니다: {err_str}",
                "data_manifest_path를 확인하거나 올바른 파일 경로를 제공하세요.",
            ]
            action = "USER_PROVIDE_INPUT"
        elif isinstance(exception, MemoryError):
            error_type = "FATAL"
            suggestions = ["메모리 부족. 입력 데이터 크기를 줄이거나 서버 메모리를 늘려주세요."]
            action = "ABORT"
        elif "max_tokens" in err_str.lower() or "context_length" in err_str.lower():
            error_type = "RECOVERABLE"
            suggestions = [
                "입력이 너무 깁니다. 유전자 목록이나 논문 수를 줄여보세요.",
                "단계를 더 작은 청크로 분할하는 것을 고려하세요.",
            ]
            action = "RETRY_WITH_PARAMS"
        else:
            error_type = "RECOVERABLE"
            suggestions = ["파라미터를 조정하여 재시도하세요."]
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
