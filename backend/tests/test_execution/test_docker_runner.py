"""Tests for DockerCodeRunner — all offline (no actual Docker required).

Tests that require a live Docker daemon are marked @pytest.mark.integration
and skipped in CI unless --run-integration is passed.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.execution.docker_runner import DockerCodeRunner, execute_code
from app.models.code_execution import CodeBlock, ExecutionResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> DockerCodeRunner:
    return DockerCodeRunner(timeout=30)


@pytest.fixture()
def python_block() -> CodeBlock:
    return CodeBlock(language="python", code="print('hello world')")


@pytest.fixture()
def r_block() -> CodeBlock:
    return CodeBlock(language="R", code='cat("hello from R\\n")')


# ---------------------------------------------------------------------------
# is_available()
# ---------------------------------------------------------------------------


class TestIsAvailable:
    def test_returns_false_when_docker_not_on_path(self, runner: DockerCodeRunner) -> None:
        with patch("shutil.which", return_value=None):
            assert runner.is_available() is False

    def test_returns_false_when_docker_info_fails(self, runner: DockerCodeRunner) -> None:
        with patch("shutil.which", return_value="/usr/bin/docker"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1)
                assert runner.is_available() is False

    def test_returns_false_when_subprocess_raises(self, runner: DockerCodeRunner) -> None:
        with patch("shutil.which", return_value="/usr/bin/docker"):
            with patch("subprocess.run", side_effect=Exception("daemon not running")):
                assert runner.is_available() is False

    def test_returns_true_when_docker_responds(self, runner: DockerCodeRunner) -> None:
        with patch("shutil.which", return_value="/usr/bin/docker"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                assert runner.is_available() is True


# ---------------------------------------------------------------------------
# run() — Docker unavailable path
# ---------------------------------------------------------------------------


class TestRunWhenDockerUnavailable:
    @pytest.mark.asyncio
    async def test_returns_error_result_when_docker_missing(
        self, runner: DockerCodeRunner, python_block: CodeBlock
    ) -> None:
        with patch.object(runner, "is_available", return_value=False):
            result = await runner.run(python_block)
        assert result.exit_code == -1
        assert "Docker" in result.stderr

    @pytest.mark.asyncio
    async def test_never_raises_when_docker_missing(
        self, runner: DockerCodeRunner, python_block: CodeBlock
    ) -> None:
        with patch.object(runner, "is_available", return_value=False):
            result = await runner.run(python_block)
        assert isinstance(result, ExecutionResult)

    @pytest.mark.asyncio
    async def test_unsupported_language_returns_error(self, runner: DockerCodeRunner) -> None:
        block = CodeBlock(language="python", code="x=1")
        block.language = "julia"  # type: ignore[assignment]
        with patch.object(runner, "is_available", return_value=True):
            result = await runner.run(block)
        assert result.exit_code == -1
        assert "Unsupported" in result.stderr


# ---------------------------------------------------------------------------
# run() — Mock subprocess (Docker "available" but subprocess mocked)
# ---------------------------------------------------------------------------


def _make_mock_proc(
    stdout: bytes = b"",
    stderr: bytes = b"",
    returncode: int = 0,
) -> MagicMock:
    """Build a mock asyncio.subprocess.Process."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    proc.wait = AsyncMock()
    return proc


class TestRunWithMockedSubprocess:
    @pytest.mark.asyncio
    async def test_successful_python_execution(
        self, runner: DockerCodeRunner, python_block: CodeBlock
    ) -> None:
        mock_proc = _make_mock_proc(stdout=b"hello world\n")

        with patch.object(runner, "is_available", return_value=True):
            with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                result = await runner.run(python_block)

        assert result.exit_code == 0
        assert "hello world" in result.stdout
        assert result.runtime_seconds >= 0

    @pytest.mark.asyncio
    async def test_failed_execution_captured_in_stderr(
        self, runner: DockerCodeRunner, python_block: CodeBlock
    ) -> None:
        mock_proc = _make_mock_proc(stderr=b"Traceback: NameError", returncode=1)

        with patch.object(runner, "is_available", return_value=True):
            with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                result = await runner.run(python_block)

        assert result.exit_code == 1
        assert "NameError" in result.stderr

    @pytest.mark.asyncio
    async def test_r_block_uses_rscript_command(
        self, runner: DockerCodeRunner, r_block: CodeBlock
    ) -> None:
        mock_proc = _make_mock_proc(stdout=b"hello from R\n")

        with patch.object(runner, "is_available", return_value=True):
            with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
                await runner.run(r_block)

        args = mock_exec.call_args[0]
        assert "Rscript" in args

    @pytest.mark.asyncio
    async def test_timeout_returns_exit_code_124(
        self, runner: DockerCodeRunner, python_block: CodeBlock
    ) -> None:
        mock_proc = _make_mock_proc()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch.object(runner, "is_available", return_value=True):
            with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                result = await runner.run(python_block)

        assert result.exit_code == 124
        assert "timed out" in result.stderr.lower()

    @pytest.mark.asyncio
    async def test_unexpected_error_does_not_raise(
        self, runner: DockerCodeRunner, python_block: CodeBlock
    ) -> None:
        with patch.object(runner, "is_available", return_value=True):
            with patch(
                "asyncio.create_subprocess_exec",
                side_effect=RuntimeError("docker socket error"),
            ):
                result = await runner.run(python_block)

        assert result.exit_code == -1
        assert isinstance(result, ExecutionResult)

    @pytest.mark.asyncio
    async def test_large_output_truncated(
        self, runner: DockerCodeRunner, python_block: CodeBlock
    ) -> None:
        large_output = b"x" * (300 * 1024)  # 300 KB > 256 KB cap
        mock_proc = _make_mock_proc(stdout=large_output)

        with patch.object(runner, "is_available", return_value=True):
            with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                result = await runner.run(python_block)

        assert "truncated" in result.stdout


# ---------------------------------------------------------------------------
# _build_docker_cmd — security flags
# ---------------------------------------------------------------------------


class TestBuildDockerCmd:
    def test_network_none_flag(self, runner: DockerCodeRunner) -> None:
        cmd = runner._build_docker_cmd("python:3.12-slim", "python /workspace/script.py", "/tmp/x")
        assert "--network" in cmd
        assert "none" in cmd

    def test_read_only_flag(self, runner: DockerCodeRunner) -> None:
        cmd = runner._build_docker_cmd("python:3.12-slim", "python /workspace/script.py", "/tmp/x")
        assert "--read-only" in cmd

    def test_memory_flag(self, runner: DockerCodeRunner) -> None:
        cmd = runner._build_docker_cmd("python:3.12-slim", "python /workspace/script.py", "/tmp/x")
        assert "--memory" in cmd
        assert _DEFAULT_MEMORY in cmd

    def test_user_nobody(self, runner: DockerCodeRunner) -> None:
        cmd = runner._build_docker_cmd("python:3.12-slim", "python /workspace/script.py", "/tmp/x")
        assert "--user" in cmd
        assert "nobody" in cmd

    def test_no_new_privileges(self, runner: DockerCodeRunner) -> None:
        cmd = runner._build_docker_cmd("python:3.12-slim", "python /workspace/script.py", "/tmp/x")
        assert "--no-new-privileges" in cmd

    def test_rm_flag(self, runner: DockerCodeRunner) -> None:
        cmd = runner._build_docker_cmd("python:3.12-slim", "python /workspace/script.py", "/tmp/x")
        assert "--rm" in cmd

    def test_workspace_volume_mounted(self, runner: DockerCodeRunner) -> None:
        cmd = runner._build_docker_cmd("python:3.12-slim", "python /workspace/script.py", "/tmp/testdir")
        volume_args = [cmd[i + 1] for i, x in enumerate(cmd) if x == "-v"]
        assert any("/tmp/testdir:/workspace:ro" in v for v in volume_args)

    def test_custom_image_used(self, runner: DockerCodeRunner) -> None:
        cmd = runner._build_docker_cmd("bioteam-rnaseq", "Rscript /workspace/script.R", "/tmp/x")
        assert "bioteam-rnaseq" in cmd


_DEFAULT_MEMORY = "512m"


# ---------------------------------------------------------------------------
# Image override via config
# ---------------------------------------------------------------------------


class TestImageConfig:
    def test_custom_python_image_used(self) -> None:
        runner = DockerCodeRunner(image_python="bioteam-python-analysis")
        from app.execution.docker_runner import _LANG_CONFIG
        default_python_image = _LANG_CONFIG["python"][0]
        # Override should differ from default
        assert runner._image_override.get("python") == "bioteam-python-analysis"
        assert runner._image_override.get("python") != default_python_image

    def test_custom_r_image_used(self) -> None:
        runner = DockerCodeRunner(image_r="bioteam-rnaseq")
        assert runner._image_override.get("R") == "bioteam-rnaseq"

    def test_no_override_uses_default(self) -> None:
        runner = DockerCodeRunner()
        assert "python" not in runner._image_override
        assert "R" not in runner._image_override


# ---------------------------------------------------------------------------
# execute_code convenience wrapper
# ---------------------------------------------------------------------------


class TestExecuteCode:
    @pytest.mark.asyncio
    async def test_execute_code_returns_execution_result(self) -> None:
        block = CodeBlock(language="python", code="print('ok')")

        with patch("app.execution.docker_runner.get_runner") as mock_get:
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=ExecutionResult(stdout="ok\n", exit_code=0))
            mock_get.return_value = mock_runner

            result = await execute_code(block)

        assert result.exit_code == 0
        assert "ok" in result.stdout


# ---------------------------------------------------------------------------
# Integration tests (live Docker required)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_python_hello_world() -> None:
    """Run a trivial Python script in a real Docker container."""
    runner = DockerCodeRunner(timeout=60)
    if not runner.is_available():
        pytest.skip("Docker daemon not running")

    block = CodeBlock(language="python", code="print('bioteam-sandbox-ok')")
    result = await runner.run(block)

    assert result.exit_code == 0, f"stderr: {result.stderr}"
    assert "bioteam-sandbox-ok" in result.stdout


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_python_no_network() -> None:
    """Confirm container cannot reach the internet."""
    runner = DockerCodeRunner(timeout=30)
    if not runner.is_available():
        pytest.skip("Docker daemon not running")

    code = "import urllib.request; urllib.request.urlopen('http://example.com', timeout=5)"
    block = CodeBlock(language="python", code=code)
    result = await runner.run(block)

    # Should fail — network is disabled
    assert result.exit_code != 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_timeout_enforcement() -> None:
    """Confirm timeout kills the container."""
    runner = DockerCodeRunner(timeout=3)
    if not runner.is_available():
        pytest.skip("Docker daemon not running")

    block = CodeBlock(language="python", code="import time; time.sleep(30)")
    result = await runner.run(block)

    assert result.exit_code == 124
    assert "timed out" in result.stderr.lower()
