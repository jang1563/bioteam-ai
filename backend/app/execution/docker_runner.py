"""Docker sandbox for agent-generated code execution.

Executes Python / R / shell code in an isolated Docker container with
resource limits, no network access, and a timeout. Falls back gracefully
(returns ExecutionResult with error) when Docker is unavailable.

Security constraints applied to every container run:
  --network none      no internet access
  --read-only         root filesystem read-only
  --tmpfs /tmp        writable scratch space (RAM-backed, dropped on exit)
  --memory 512m       RAM cap per run
  --cpus 1.0          CPU cap
  --user nobody       drop root privileges
  --rm                auto-remove on exit
  --no-new-privileges prevent privilege escalation

Image selection (config.docker_image_python / docker_image_r):
  - Default: python:3.12-slim / r-base:4.4
  - Bioinformatics: see containers/Dockerfile.* for custom images
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import time
from pathlib import Path

from app.models.code_execution import CodeBlock, ExecutionResult

logger = logging.getLogger(__name__)

# Default timeouts and resource limits
_DEFAULT_TIMEOUT_SECONDS = 120
_MAX_TIMEOUT_SECONDS = 600
_MEMORY_LIMIT = "512m"
_CPU_LIMIT = "1.0"
_OUTPUT_MAX_BYTES = 256 * 1024  # 256 KB stdout/stderr cap

# Language → (image, interpreter command template)
_LANG_CONFIG: dict[str, tuple[str, str]] = {
    "python": ("python:3.12-slim", "python /workspace/script.py"),
    "R": ("r-base:4.4", "Rscript /workspace/script.R"),
    "shell": ("python:3.12-slim", "bash /workspace/script.sh"),
}

_SCRIPT_EXTENSIONS = {
    "python": ".py",
    "R": ".R",
    "shell": ".sh",
}


class DockerCodeRunner:
    """Execute agent-generated code in a Docker sandbox.

    Usage:
        runner = DockerCodeRunner()
        if not runner.is_available():
            # Docker daemon not running — skip execution
            return ExecutionResult(stderr="Docker unavailable", exit_code=-1)

        block = CodeBlock(language="python", code="print('hello')")
        result = await runner.run(block)
        print(result.stdout)   # "hello\\n"
    """

    def __init__(
        self,
        timeout: int = _DEFAULT_TIMEOUT_SECONDS,
        memory: str = _MEMORY_LIMIT,
        cpus: str = _CPU_LIMIT,
        image_python: str | None = None,
        image_r: str | None = None,
    ) -> None:
        self._timeout = min(timeout, _MAX_TIMEOUT_SECONDS)
        self._memory = memory
        self._cpus = cpus
        self._image_override: dict[str, str] = {}
        if image_python:
            self._image_override["python"] = image_python
        if image_r:
            self._image_override["R"] = image_r

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if the Docker CLI is on PATH and the daemon responds."""
        if not shutil.which("docker"):
            return False
        try:
            import subprocess
            result = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    async def run(self, block: CodeBlock) -> ExecutionResult:
        """Execute *block* inside a Docker container and return the result.

        Always returns an ExecutionResult — never raises. Failures are
        surfaced via stderr and exit_code != 0.
        """
        if not self.is_available():
            return ExecutionResult(
                stderr="Docker daemon is not running or docker CLI not found. "
                       "Install Docker Desktop and start the daemon.",
                exit_code=-1,
            )

        lang = block.language
        if lang not in _LANG_CONFIG:
            return ExecutionResult(
                stderr=f"Unsupported language: {lang!r}. Supported: {list(_LANG_CONFIG)}",
                exit_code=-1,
            )

        default_image, cmd_template = _LANG_CONFIG[lang]
        image = self._image_override.get(lang, default_image)

        try:
            return await self._run_in_container(block, image, cmd_template)
        except asyncio.TimeoutError:
            return ExecutionResult(
                stderr=f"Execution timed out after {self._timeout}s.",
                exit_code=124,  # standard timeout exit code
                runtime_seconds=float(self._timeout),
            )
        except Exception as e:
            logger.warning("DockerCodeRunner unexpected error: %s", e)
            return ExecutionResult(stderr=f"Runner error: {e}", exit_code=-1)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_in_container(
        self,
        block: CodeBlock,
        image: str,
        cmd_template: str,
    ) -> ExecutionResult:
        """Write script to temp dir, launch container, collect output."""
        ext = _SCRIPT_EXTENSIONS.get(block.language, ".py")

        with tempfile.TemporaryDirectory(prefix="bioteam_sandbox_") as tmpdir:
            script_path = Path(tmpdir) / f"script{ext}"
            script_path.write_text(block.code, encoding="utf-8")

            docker_cmd = self._build_docker_cmd(image, cmd_template, tmpdir)

            start = time.monotonic()
            proc = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_raw, stderr_raw = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise

            elapsed = time.monotonic() - start
            exit_code = proc.returncode or 0

        stdout = stdout_raw.decode("utf-8", errors="replace")[:_OUTPUT_MAX_BYTES]
        stderr = stderr_raw.decode("utf-8", errors="replace")[:_OUTPUT_MAX_BYTES]

        if len(stdout_raw) >= _OUTPUT_MAX_BYTES:
            stdout += "\n[...output truncated at 256 KB...]"

        return ExecutionResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            runtime_seconds=round(elapsed, 3),
        )

    def _build_docker_cmd(
        self,
        image: str,
        cmd_template: str,
        host_tmpdir: str,
    ) -> list[str]:
        """Build the docker run command list."""
        return [
            "docker", "run",
            "--rm",
            "--network", "none",
            "--read-only",
            "--tmpfs", "/tmp:size=128m",
            "--memory", self._memory,
            "--cpus", self._cpus,
            "--no-new-privileges",
            "--user", "nobody",
            "-v", f"{host_tmpdir}:/workspace:ro",
            image,
            *cmd_template.split(),
        ]


# ---------------------------------------------------------------------------
# Convenience function used by workflow runners
# ---------------------------------------------------------------------------

_default_runner: DockerCodeRunner | None = None


def get_runner() -> DockerCodeRunner:
    """Return the shared DockerCodeRunner instance (lazy init)."""
    global _default_runner
    if _default_runner is None:
        _default_runner = DockerCodeRunner()
    return _default_runner


async def execute_code(block: CodeBlock, timeout: int = _DEFAULT_TIMEOUT_SECONDS) -> ExecutionResult:
    """Top-level convenience wrapper for workflow runners.

    Returns ExecutionResult. Never raises.
    """
    runner = get_runner()
    if timeout != _DEFAULT_TIMEOUT_SECONDS:
        runner = DockerCodeRunner(timeout=timeout)
    return await runner.run(block)
