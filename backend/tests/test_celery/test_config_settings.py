"""Tests for Celery-related configuration settings."""

from unittest.mock import patch


class TestCelerySettings:
    """Test Celery settings in config.py."""

    def test_celery_settings_defaults(self):
        """Default Celery settings are empty (disabled)."""
        from app.config import Settings
        s = Settings()
        assert s.celery_broker_url == ""
        assert s.celery_result_backend == ""
        assert s.celery_worker_concurrency == 4
        assert s.celery_task_time_limit == 3600

    def test_celery_settings_from_env(self):
        """Celery settings can be loaded from environment."""
        env = {
            "CELERY_BROKER_URL": "redis://redis:6379/0",
            "CELERY_RESULT_BACKEND": "redis://redis:6379/1",
            "CELERY_WORKER_CONCURRENCY": "8",
            "CELERY_TASK_TIME_LIMIT": "7200",
        }
        with patch.dict("os.environ", env):
            from app.config import Settings
            s = Settings()
            assert s.celery_broker_url == "redis://redis:6379/0"
            assert s.celery_result_backend == "redis://redis:6379/1"
            assert s.celery_worker_concurrency == 8
            assert s.celery_task_time_limit == 7200

    def test_is_celery_enabled_depends_on_broker_url(self):
        """is_celery_enabled returns True only when broker URL is non-empty."""
        with patch("app.celery_app.settings") as mock_settings:
            mock_settings.celery_broker_url = ""
            from app.celery_app import is_celery_enabled  # noqa: F401
            assert not is_celery_enabled()

            mock_settings.celery_broker_url = "redis://localhost:6379/0"
            assert is_celery_enabled()
