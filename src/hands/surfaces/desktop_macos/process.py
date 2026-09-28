"""Async subprocess runner with a typed result (used for `open -b` and `screencapture`)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from hands.core.log import get_logger, log_failure

logger = get_logger(__name__)


@dataclass(frozen=True)
class CommandResult:
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.returncode == 0


CommandRunner = Callable[[Sequence[str], float], Awaitable[CommandResult]]


async def run_command(argv: Sequence[str], timeout_s: float) -> CommandResult:
    """Run a command without a shell. Never raises; failures come back in CommandResult.error."""
    try:
        process = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except OSError as start_error:
        log_failure(logger, "run_command", f"could not start: {start_error}", argv=list(argv))
        return CommandResult(returncode=None, error=f"could not start {argv[0]}: {start_error}")
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
    except TimeoutError:
        process.kill()
        await process.wait()
        log_failure(logger, "run_command", f"timed out after {timeout_s}s", argv=list(argv))
        return CommandResult(returncode=None, error=f"{argv[0]} timed out after {timeout_s}s")
    result = CommandResult(
        returncode=process.returncode,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )
    if result.returncode != 0:
        log_failure(
            logger,
            "run_command",
            f"exit code {result.returncode}: {result.stderr.strip()}",
            argv=list(argv),
        )
    return result
