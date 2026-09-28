"""Window screenshots via the `screencapture` CLI (needs Screen Recording permission for other apps).

`screencapture -l <windowid> -x -o` captures one window, silently, without its shadow. The CLI is
used instead of CGWindowListCreateImage because that API is obsoleted on macOS 15+.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from hands.core.log import get_logger, log_failure
from hands.surfaces.desktop_macos.process import CommandRunner, run_command

logger = get_logger(__name__)

CAPTURE_TIMEOUT_S = 10.0
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class CaptureResult:
    png: bytes | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.png is not None


class WindowCapturer(Protocol):
    async def capture_window(self, window_id: int) -> CaptureResult: ...


def screencapture_argv(window_id: int, output_path: str) -> list[str]:
    return ["screencapture", "-l", str(window_id), "-x", "-o", "-t", "png", output_path]


def read_png(path: Path) -> CaptureResult:
    """Read a PNG file and check its signature. Missing/empty/non-PNG files are errors."""
    if not path.exists():
        return CaptureResult(error=f"no file written at {path}")
    png_bytes = path.read_bytes()
    if not png_bytes.startswith(PNG_SIGNATURE):
        return CaptureResult(error=f"file at {path} is not a PNG ({len(png_bytes)} bytes)")
    return CaptureResult(png=png_bytes)


class ScreencaptureCli:
    """WindowCapturer over `screencapture`. The command runner is injectable for tests."""

    def __init__(self, command_runner: CommandRunner = run_command) -> None:
        self._command_runner = command_runner

    async def capture_window(self, window_id: int) -> CaptureResult:
        file_descriptor, temp_name = tempfile.mkstemp(prefix="hands_window_", suffix=".png")
        os.close(file_descriptor)
        temp_path = Path(temp_name)
        temp_path.unlink()
        command_result = await self._command_runner(
            screencapture_argv(window_id, str(temp_path)), CAPTURE_TIMEOUT_S
        )
        if not command_result.ok:
            detail = (
                command_result.error
                or command_result.stderr.strip()
                or f"exit {command_result.returncode}"
            )
            log_failure(logger, "capture_window", detail, window_id=window_id)
            return CaptureResult(error=f"screencapture failed: {detail}")
        capture = read_png(temp_path)
        temp_path.unlink(missing_ok=True)
        if not capture.ok:
            log_failure(logger, "capture_window", capture.error or "unknown", window_id=window_id)
        return capture
