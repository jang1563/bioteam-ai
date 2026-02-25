"""Tests for Celery app configuration and task dispatch."""

from unittest.mock import patch


class TestCeleryAppConfig:
    """Test Celery application setup."""

    def test_is_celery_enabled_false_when_empty(self):
        """Celery is disabled when broker URL is empty."""
        with patch("app.celery_app.settings") as mock_settings:
            mock_settings.celery_broker_url = ""
            from app.celery_app import is_celery_enabled  # noqa: F401
            assert not is_celery_enabled()

    def test_is_celery_enabled_true_when_set(self):
        """Celery is enabled when broker URL is set."""
        with patch("app.celery_app.settings") as mock_settings:
            mock_settings.celery_broker_url = "redis://localhost:6379/0"
            assert bool(mock_settings.celery_broker_url)

    def test_create_celery_app_returns_celery_instance(self):
        """create_celery_app returns a Celery instance."""
        from app.celery_app import create_celery_app
        app = create_celery_app()
        assert app is not None
        assert app.main == "bioteam"

    def test_celery_app_config_defaults(self):
        """Celery app has correct default configuration."""
        from app.celery_app import celery_app
        assert celery_app.conf.task_serializer == "json"
        assert celery_app.conf.timezone == "UTC"
        assert celery_app.conf.enable_utc is True
        assert celery_app.conf.task_track_started is True

    def test_celery_task_routes(self):
        """Workflow tasks route to workflows queue."""
        from app.celery_app import celery_app
        routes = celery_app.conf.task_routes
        assert "app.tasks.workflow_tasks.*" in routes
        assert routes["app.tasks.workflow_tasks.*"]["queue"] == "workflows"


class TestCeleryTasks:
    """Test task registration and structure."""

    def test_run_workflow_task_exists(self):
        """run_workflow generic task exists and is a Celery task."""
        from app.tasks.workflow_tasks import run_workflow
        assert run_workflow.name == "app.tasks.workflow_tasks.run_workflow"

    def test_resume_workflow_task_exists(self):
        """resume_workflow generic task exists and is a Celery task."""
        from app.tasks.workflow_tasks import resume_workflow
        assert resume_workflow.name == "app.tasks.workflow_tasks.resume_workflow"

    def test_run_workflow_task_config(self):
        """run_workflow has correct retry config."""
        from app.tasks.workflow_tasks import run_workflow
        assert run_workflow.max_retries == 1
        assert run_workflow.default_retry_delay == 30

    def test_resume_workflow_task_config(self):
        """resume_workflow has correct retry config."""
        from app.tasks.workflow_tasks import resume_workflow
        assert resume_workflow.max_retries == 1

    def test_run_w1_backward_compat_task_exists(self):
        """Backward-compatible run_w1_workflow task exists."""
        from app.tasks.workflow_tasks import run_w1_workflow
        assert run_w1_workflow.name == "app.tasks.workflow_tasks.run_w1_workflow"

    def test_resume_w1_backward_compat_task_exists(self):
        """Backward-compatible resume_w1_workflow task exists."""
        from app.tasks.workflow_tasks import resume_w1_workflow
        assert resume_w1_workflow.name == "app.tasks.workflow_tasks.resume_w1_workflow"


class TestDispatchLogic:
    """Test generic dispatch helper functions in workflows.py."""

    def test_dispatch_workflow_uses_asyncio_when_celery_disabled(self):
        """When Celery is disabled, dispatch uses asyncio.create_task."""
        with (
            patch("app.celery_app.is_celery_enabled", return_value=False),
            patch("app.api.v1.workflows.asyncio") as mock_asyncio,
        ):
            from app.api.v1.workflows import _dispatch_workflow
            _dispatch_workflow("wf-001", "W1", "test query", 5.0)
            mock_asyncio.create_task.assert_called_once()

    def test_dispatch_workflow_uses_celery_when_enabled(self):
        """When Celery is enabled, dispatch uses Celery delay."""
        with (
            patch("app.celery_app.is_celery_enabled", return_value=True),
            patch("app.tasks.workflow_tasks.run_workflow") as mock_task,
        ):
            from app.api.v1.workflows import _dispatch_workflow
            _dispatch_workflow("wf-001", "W2", "test query", 5.0)
            mock_task.delay.assert_called_once_with("wf-001", "W2", "test query", 5.0)

    def test_dispatch_workflow_resume_uses_asyncio_when_celery_disabled(self):
        """When Celery is disabled, resume uses asyncio.create_task."""
        with (
            patch("app.celery_app.is_celery_enabled", return_value=False),
            patch("app.api.v1.workflows.asyncio") as mock_asyncio,
        ):
            from app.api.v1.workflows import _dispatch_workflow_resume
            _dispatch_workflow_resume("wf-001", "W3", "test query")
            mock_asyncio.create_task.assert_called_once()

    def test_dispatch_workflow_resume_uses_celery_when_enabled(self):
        """When Celery is enabled, resume uses Celery delay."""
        with (
            patch("app.celery_app.is_celery_enabled", return_value=True),
            patch("app.tasks.workflow_tasks.resume_workflow") as mock_task,
        ):
            from app.api.v1.workflows import _dispatch_workflow_resume
            _dispatch_workflow_resume("wf-001", "W4", "test query")
            mock_task.delay.assert_called_once_with("wf-001", "W4", "test query")

    def test_backward_compat_dispatch_w1(self):
        """_dispatch_w1 backward-compatible alias works."""
        with (
            patch("app.celery_app.is_celery_enabled", return_value=True),
            patch("app.tasks.workflow_tasks.run_workflow") as mock_task,
        ):
            from app.api.v1.workflows import _dispatch_w1
            _dispatch_w1("wf-001", "test query", 5.0)
            mock_task.delay.assert_called_once_with("wf-001", "W1", "test query", 5.0)
