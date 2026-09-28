"""Process-level app control: find, launch, activate, quit, and map an AX window to a CGWindowID."""

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from types import ModuleType
from typing import Any, Protocol

from hands.core.actions import ActResult
from hands.core.log import get_logger, log_failure
from hands.surfaces.desktop_macos.ax import AxPoint, AxSize
from hands.surfaces.desktop_macos.process import CommandRunner, run_command

logger = get_logger(__name__)

LAUNCH_COMMAND_TIMEOUT_S = 15.0
WINDOW_MATCH_TOLERANCE = 4.0
NORMAL_WINDOW_LAYER = 0


class AppController(Protocol):
    def find_pid(self, bundle_id: str) -> int | None: ...

    async def launch(self, bundle_id: str) -> ActResult: ...

    def activate(self, pid: int) -> ActResult: ...

    def terminate(self, bundle_id: str) -> ActResult: ...

    def window_id_for(self, pid: int, origin: AxPoint, size: AxSize) -> int | None: ...


def _import_optional(module_name: str) -> ModuleType | None:
    try:
        return importlib.import_module(module_name)
    except ImportError as import_error:
        log_failure(
            logger, "_import_optional", f"cannot import: {import_error}", module_name=module_name
        )
        return None


def window_frame_distance(window_info: Mapping[str, Any], origin: AxPoint, size: AxSize) -> float:
    """Sum of absolute differences between a CGWindow's bounds and an AX window frame."""
    bounds = window_info.get("kCGWindowBounds") or {}
    return (
        abs(float(bounds.get("X", 0.0)) - origin.x)
        + abs(float(bounds.get("Y", 0.0)) - origin.y)
        + abs(float(bounds.get("Width", 0.0)) - size.width)
        + abs(float(bounds.get("Height", 0.0)) - size.height)
    )


def pick_window_id(
    window_infos: Sequence[Mapping[str, Any]], pid: int, origin: AxPoint, size: AxSize
) -> int | None:
    """Choose the CGWindowID owned by pid whose bounds best match the AX frame.

    Bounds matching (not titles) is used because window titles in the CG list need Screen Recording
    permission. Falls back to the pid's first normal-layer window when nothing matches closely.
    """
    owned_windows = [
        info
        for info in window_infos
        if info.get("kCGWindowOwnerPID") == pid
        and info.get("kCGWindowLayer", NORMAL_WINDOW_LAYER) == NORMAL_WINDOW_LAYER
    ]
    if not owned_windows:
        return None
    best_match = min(owned_windows, key=lambda info: window_frame_distance(info, origin, size))
    if window_frame_distance(best_match, origin, size) <= WINDOW_MATCH_TOLERANCE:
        return int(best_match["kCGWindowNumber"])
    return int(owned_windows[0]["kCGWindowNumber"])


class MacAppController:
    """AppController over AppKit (NSRunningApplication), Quartz window lists and `open -b`."""

    def __init__(
        self,
        appkit_module: ModuleType | None = None,
        quartz_module: ModuleType | None = None,
        command_runner: CommandRunner = run_command,
    ) -> None:
        self._appkit = appkit_module
        self._quartz = quartz_module
        self._command_runner = command_runner

    def _appkit_module(self) -> ModuleType | None:
        if self._appkit is None:
            self._appkit = _import_optional("AppKit")
        return self._appkit

    def _quartz_module(self) -> ModuleType | None:
        if self._quartz is None:
            self._quartz = _import_optional("Quartz")
        return self._quartz

    def _running_applications(self, bundle_id: str) -> list[Any]:
        appkit = self._appkit_module()
        if appkit is None:
            return []
        running = appkit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id)
        return list(running or [])

    def find_pid(self, bundle_id: str) -> int | None:
        running = self._running_applications(bundle_id)
        return int(running[0].processIdentifier()) if running else None

    async def launch(self, bundle_id: str) -> ActResult:
        """`open -b <bundle_id>` launches the app, or activates it when already running."""
        result = await self._command_runner(["open", "-b", bundle_id], LAUNCH_COMMAND_TIMEOUT_S)
        if not result.ok:
            detail = result.error or result.stderr.strip() or f"exit code {result.returncode}"
            log_failure(logger, "launch", detail, bundle_id=bundle_id)
            return ActResult(ok=False, error=f"could not open {bundle_id}: {detail}")
        return ActResult(ok=True)

    def activate(self, pid: int) -> ActResult:
        appkit = self._appkit_module()
        if appkit is None:
            return ActResult(ok=False, error="AppKit unavailable")
        application = appkit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        if application is None:
            log_failure(logger, "activate", "no running application", pid=pid)
            return ActResult(ok=False, error=f"no running application with pid {pid}")
        if not application.activateWithOptions_(appkit.NSApplicationActivateIgnoringOtherApps):
            log_failure(logger, "activate", "activateWithOptions_ returned False", pid=pid)
            return ActResult(ok=False, error=f"could not activate pid {pid}")
        return ActResult(ok=True)

    def terminate(self, bundle_id: str) -> ActResult:
        running = self._running_applications(bundle_id)
        if not running:
            return ActResult(ok=True)
        if not all(application.terminate() for application in running):
            log_failure(logger, "terminate", "terminate() returned False", bundle_id=bundle_id)
            return ActResult(ok=False, error=f"could not quit {bundle_id}")
        return ActResult(ok=True)

    def window_id_for(self, pid: int, origin: AxPoint, size: AxSize) -> int | None:
        quartz = self._quartz_module()
        if quartz is None:
            return None
        options = (
            quartz.kCGWindowListOptionOnScreenOnly | quartz.kCGWindowListExcludeDesktopElements
        )
        window_infos = quartz.CGWindowListCopyWindowInfo(options, quartz.kCGNullWindowID) or []
        window_id = pick_window_id(list(window_infos), pid, origin, size)
        if window_id is None:
            log_failure(logger, "window_id_for", "no on-screen window for pid", pid=pid)
        return window_id
