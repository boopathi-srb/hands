"""MacDesktopSurface: the core `Surface` protocol over the macOS Accessibility API.

It produces the same `Observation` model as the browser surface (roles, names, labels, container and
structural paths, bounds), so TargetSpecs and Conditions from `hands.core` resolve unchanged. See
`tree.py` for how AX maps onto that model and for the coordinate convention (window-relative bounds).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from hands.core.actions import Action, ActResult, ActTarget, NodeRef, OpenAction, Point
from hands.core.log import get_logger, log_failure
from hands.core.observation import Observation
from hands.core.ports import SurfaceKind
from hands.surfaces.desktop_macos.actuator import AxActuator, ResolvedTarget
from hands.surfaces.desktop_macos.apps import AppController, MacAppController
from hands.surfaces.desktop_macos.ax import (
    Attr,
    AxBackend,
    AxElement,
    AxPoint,
    AxSize,
    PyObjcAxBackend,
)
from hands.surfaces.desktop_macos.capture import ScreencaptureCli, WindowCapturer
from hands.surfaces.desktop_macos.events import EventPoster, QuartzEventPoster
from hands.surfaces.desktop_macos.live_view import CaptureTarget, ScreenLiveView
from hands.surfaces.desktop_macos.tree import (
    TreeLimits,
    TreeSnapshot,
    build_tree_snapshot,
    content_signature,
    empty_snapshot,
)

logger = get_logger(__name__)

PERMISSION_HELP = (
    "Accessibility permission is not granted to this process (AXIsProcessTrusted() is false). "
    "Open System Settings > Privacy & Security > Accessibility and enable the app that runs Python "
    "(Terminal, iTerm, VS Code, or whichever terminal launched `uv run`), then restart that app. "
    "Screenshots additionally need System Settings > Privacy & Security > Screen Recording."
)

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


@dataclass(frozen=True)
class SurfaceTimings:
    settle_timeout_s: float = 3.0
    settle_poll_s: float = 0.2
    launch_timeout_s: float = 15.0
    launch_poll_s: float = 0.25


def permission_error() -> ActResult:
    return ActResult(ok=False, error=PERMISSION_HELP)


class MacDesktopSurface:
    """One running macOS app, perceived through AX and driven by AX actions (CGEvent as fallback)."""

    kind: SurfaceKind = "desktop"

    def __init__(
        self,
        bundle_id: str | None = None,
        *,
        backend: AxBackend | None = None,
        events: EventPoster | None = None,
        apps: AppController | None = None,
        capturer: WindowCapturer | None = None,
        limits: TreeLimits | None = None,
        timings: SurfaceTimings | None = None,
        sleep: Sleep = asyncio.sleep,
        clock: Clock = time.monotonic,
    ) -> None:
        self._bundle_id = bundle_id
        self._backend: AxBackend = backend or PyObjcAxBackend()
        self._events: EventPoster = events or QuartzEventPoster()
        self._apps: AppController = apps or MacAppController()
        self._capturer: WindowCapturer = capturer or ScreencaptureCli()
        self._limits = limits or TreeLimits()
        self._timings = timings or SurfaceTimings()
        self._sleep = sleep
        self._clock = clock
        self._pid: int | None = None
        self._snapshot: TreeSnapshot | None = None
        self._live_view: ScreenLiveView | None = None
        self.launched_by_surface = False
        self._actuator = AxActuator(self._backend, self._events, self._activate_app, sleep)

    # ---------------------------------------------------- state

    @property
    def bundle_id(self) -> str | None:
        return self._bundle_id

    @property
    def pid(self) -> int | None:
        return self._pid

    @property
    def last_snapshot(self) -> TreeSnapshot | None:
        return self._snapshot

    def permission_granted(self) -> bool:
        return self._backend.is_process_trusted()

    def _activate_app(self) -> ActResult:
        if self._pid is None:
            return ActResult(ok=False, error="no app attached")
        return self._apps.activate(self._pid)

    def _resolve_pid(self) -> int | None:
        if self._pid is None and self._bundle_id is not None:
            self._pid = self._apps.find_pid(self._bundle_id)
        return self._pid

    # ---------------------------------------------------- launch / attach

    async def launch(self, bundle_id: str) -> ActResult:
        """Open (or activate) the app by bundle id and wait until its process has a window."""
        if not self.permission_granted():
            log_failure(logger, "launch", "accessibility permission missing", bundle_id=bundle_id)
            return permission_error()
        already_running = self._apps.find_pid(bundle_id) is not None
        opened = await self._apps.launch(bundle_id)
        if not opened.ok:
            return opened
        pid = await self._wait_for_pid(bundle_id)
        if pid is None:
            log_failure(logger, "launch", "process did not appear", bundle_id=bundle_id)
            return ActResult(
                ok=False,
                error=f"{bundle_id} did not start within {self._timings.launch_timeout_s}s",
            )
        self._bundle_id, self._pid, self._snapshot = bundle_id, pid, None
        self.launched_by_surface = self.launched_by_surface or not already_running
        if not await self._wait_for_window(pid):
            logger.warning(
                "launch: %s (pid %d) has no window yet; observing an empty app", bundle_id, pid
            )
        return ActResult(ok=True)

    async def _poll_until(self, probe: Callable[[], bool]) -> bool:
        deadline = self._clock() + self._timings.launch_timeout_s
        while not probe():
            if self._clock() >= deadline:
                return False
            await self._sleep(self._timings.launch_poll_s)
        return True

    async def _wait_for_pid(self, bundle_id: str) -> int | None:
        found = await self._poll_until(lambda: self._apps.find_pid(bundle_id) is not None)
        return self._apps.find_pid(bundle_id) if found else None

    async def _wait_for_window(self, pid: int) -> bool:
        app_element = self._backend.application_element(pid)
        if not app_element.ok:
            return False
        return await self._poll_until(
            lambda: bool(self._backend.attribute(app_element.value, Attr.WINDOWS).value)
        )

    async def quit_app(self) -> ActResult:
        """Quit the attached app (used by evidence tooling to clean up an app it launched)."""
        if self._bundle_id is None:
            return ActResult(ok=True)
        return self._apps.terminate(self._bundle_id)

    # ---------------------------------------------------- observe

    async def observe(self, include_screenshot: bool = True) -> Observation:
        snapshot = await self._settled_snapshot()
        self._snapshot = snapshot
        screenshot_png = await self._capture_primary_window() if include_screenshot else None
        return Observation(
            observed_at=datetime.now(UTC),
            location=snapshot.location,
            nodes=snapshot.nodes,
            dialogs=snapshot.dialogs,
            fingerprint=snapshot.fingerprint,
            screenshot_png=screenshot_png,
        )

    def _application_element(self, function_name: str) -> AxElement | None:
        pid = self._resolve_pid()
        if pid is None:
            log_failure(logger, function_name, "no running app attached", bundle_id=self._bundle_id)
            return None
        if not self.permission_granted():
            log_failure(
                logger, function_name, "accessibility permission missing", bundle_id=self._bundle_id
            )
            return None
        app_element = self._backend.application_element(pid)
        return app_element.value if app_element.ok else None

    async def take_snapshot(self) -> TreeSnapshot:
        """One unsettled tree walk (in a worker thread: AX calls are blocking IPC)."""
        bundle_id = self._bundle_id or ""
        app_element = self._application_element("take_snapshot")
        if app_element is None:
            return empty_snapshot(bundle_id)
        return await asyncio.to_thread(
            build_tree_snapshot, self._backend, app_element, bundle_id, self._limits
        )

    async def _settled_snapshot(self) -> TreeSnapshot:
        """Poll until two consecutive walks have identical content, or the settle timeout passes."""
        deadline = self._clock() + self._timings.settle_timeout_s
        previous = await self.take_snapshot()
        while True:
            await self._sleep(self._timings.settle_poll_s)
            current = await self.take_snapshot()
            if content_signature(current.nodes) == content_signature(previous.nodes):
                return current
            if self._clock() >= deadline:
                logger.warning(
                    "observe: %s did not settle within %ss",
                    self._bundle_id,
                    self._timings.settle_timeout_s,
                )
                return current
            previous = current

    async def _capture_primary_window(self) -> bytes | None:
        target = await self.capture_target()
        if target is None:
            return None
        return (await self._capturer.capture_window(target.window_id)).png

    def _current_window_frame(self) -> tuple[AxPoint, AxSize] | None:
        """Fresh focused-window frame (the window may have moved since the last observe)."""
        app_element = self._application_element("_current_window_frame")
        if app_element is None:
            return None
        window = self._backend.attribute(app_element, Attr.FOCUSED_WINDOW).value
        if window is None:
            return None
        frame = self._backend.attributes(window, (Attr.POSITION, Attr.SIZE)).value or {}
        origin, size = frame.get(Attr.POSITION), frame.get(Attr.SIZE)
        if not isinstance(origin, AxPoint) or not isinstance(size, AxSize):
            return None
        return origin, size

    async def capture_target(self) -> CaptureTarget | None:
        """The focused window's CGWindowID and screen origin, for screenshots and the live view."""
        frame = self._current_window_frame()
        if frame is None or self._pid is None:
            return None
        origin, size = frame
        window_id = self._apps.window_id_for(self._pid, origin, size)
        return CaptureTarget(window_id=window_id, origin=origin) if window_id is not None else None

    # ---------------------------------------------------- act

    async def act(self, target: ActTarget, action: Action) -> ActResult:
        """Perform one action. Never raises: unexpected errors become ActResult(ok=False)."""
        try:
            return await self._dispatch(target, action)
        except Exception as unexpected_error:  # noqa: BLE001 - protocol boundary: act() must not raise
            log_failure(
                logger,
                "act",
                f"unexpected error: {unexpected_error!r}",
                action_kind=action.kind,
                target=target,
            )
            return ActResult(ok=False, error=f"{action.kind} failed: {unexpected_error}")

    async def _dispatch(self, target: ActTarget, action: Action) -> ActResult:
        if isinstance(action, OpenAction):
            return await self.launch(action.entry_point)
        if not self.permission_granted():
            log_failure(logger, "act", "accessibility permission missing", action_kind=action.kind)
            return permission_error()
        resolved = self.resolve_target(target, default_to_window_center=action.kind == "scroll")
        if isinstance(resolved, ActResult):
            return resolved
        if action.kind == "click":
            return await self._actuator.click(resolved)
        if action.kind == "type":
            return await self._actuator.type_text(resolved, action.text, action.clear_first)
        if action.kind == "press":
            return await self._actuator.press(resolved, action.key)
        if action.kind == "select":
            return await self._actuator.select(resolved, action.option)
        return await self._actuator.scroll(resolved, action.direction, action.amount)

    def resolve_target(
        self, target: ActTarget, default_to_window_center: bool = False
    ) -> ResolvedTarget | ActResult:
        """NodeRef -> live element + screen center; Point (window-relative) -> screen point; None -> nothing."""
        if isinstance(target, NodeRef):
            return self._resolve_ref(target.ref)
        if isinstance(target, Point):
            return self._resolve_point(target.x, target.y, f"point ({target.x}, {target.y})")
        if default_to_window_center:
            return self._resolve_window_center()
        return ResolvedTarget(element=None, screen_point=None, description="focused element")

    def _resolve_ref(self, ref: str) -> ResolvedTarget | ActResult:
        entry = self._snapshot.entries_by_ref.get(ref) if self._snapshot else None
        if self._snapshot is None or entry is None:
            log_failure(logger, "_resolve_ref", "ref not in the latest observation", ref=ref)
            return ActResult(
                ok=False, error=f"unknown ref {ref!r}: observe() first and use a ref from it"
            )
        return ResolvedTarget(
            element=entry.element,
            screen_point=self._snapshot.screen_center(ref),
            description=f"ref {ref}",
        )

    def _resolve_point(self, x: float, y: float, description: str) -> ResolvedTarget | ActResult:
        window = self._snapshot.primary_window if self._snapshot else None
        if window is None:
            log_failure(
                logger, "_resolve_point", "no observed window to anchor the point", x=x, y=y
            )
            return ActResult(
                ok=False, error="no observed window: observe() before acting on a point"
            )
        return ResolvedTarget(
            element=None,
            screen_point=AxPoint(window.origin.x + x, window.origin.y + y),
            description=description,
        )

    def _resolve_window_center(self) -> ResolvedTarget | ActResult:
        window = self._snapshot.primary_window if self._snapshot else None
        if window is None:
            return self._resolve_point(0.0, 0.0, "window center")
        return self._resolve_point(window.size.width / 2, window.size.height / 2, "window center")

    # ---------------------------------------------------- lifecycle

    async def close(self) -> None:
        """Stop the live view and forget state. The app itself is left running (see quit_app)."""
        if self._live_view is not None:
            await self._live_view.stop()
        self._snapshot = None

    def live_view(self) -> ScreenLiveView | None:
        if self._live_view is None:
            self._live_view = ScreenLiveView(self.capture_target, self._capturer, self._events)
        return self._live_view
