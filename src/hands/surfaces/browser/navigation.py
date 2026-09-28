"""Track in-flight navigations of every frame, so observe() never snapshots a half-navigated page.

Page-level 'networkidle' only follows the main frame. A form submitted inside a child frame
(POST -> 303 -> slow GET) leaves the old document in place until the redirect target commits, so a
naive observe sees the old page. The tracker listens to page events:

    request (navigation)   -> frame has a pending navigation (a redirect replaces it)
    framenavigated         -> the pending navigation committed; its document still has to load
    requestfinished        -> response fully received (used to spot navigations that never commit,
                              e.g. 204 or downloads)
    requestfailed          -> the pending navigation is gone (if it is still the frame's latest)
    framedetached          -> the frame is gone

`wait_for_navigations` then waits, bounded, until every pending navigation committed and its frame
fired 'load'. Actions call `mark_action()` so settle can give a just-clicked submit button a short
grace window to start its navigation.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Frame, Page, Request

from hands.core.log import get_logger
from hands.surfaces.browser.guard import DialogSignal, run_guarded

_LOGGER = get_logger(__name__)

POLL_INTERVAL_S = 0.03
NEVER_COMMITS_AFTER_FINISH_S = 1.0


@dataclass
class PendingNavigation:
    request: Request
    started_at: float
    committed: bool = False
    finished_at: float | None = None


class NavigationTracker:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._pending: dict[Frame, PendingNavigation] = {}
        self._last_action_at: float | None = None

    def attach(self, page: Page) -> None:
        page.on("request", self._on_request)
        page.on("requestfinished", self._on_request_finished)
        page.on("requestfailed", self._on_request_failed)
        page.on("framenavigated", self._on_frame_navigated)
        page.on("framedetached", self._on_frame_detached)

    # ------------------------------------------------------------ state

    def mark_action(self) -> None:
        self._last_action_at = self._clock()

    def seconds_since_action(self) -> float | None:
        return None if self._last_action_at is None else self._clock() - self._last_action_at

    @property
    def has_pending(self) -> bool:
        return bool(self._pending)

    def pending_items(self) -> list[tuple[Frame, PendingNavigation]]:
        return list(self._pending.items())

    def forget(self, frame: Frame, navigation: PendingNavigation) -> None:
        """Drop a navigation once handled, unless a newer one has replaced it meanwhile."""
        if self._pending.get(frame) is navigation:
            del self._pending[frame]

    def never_commits(self, navigation: PendingNavigation) -> bool:
        """Response fully received but no document committed (204, download): stop waiting for it."""
        if navigation.committed or navigation.finished_at is None:
            return False
        return self._clock() - navigation.finished_at > NEVER_COMMITS_AFTER_FINISH_S

    # ------------------------------------------------------------ page events

    def _on_request(self, request: Request) -> None:
        if request.is_navigation_request():
            self._pending[request.frame] = PendingNavigation(request=request, started_at=self._clock())

    def _on_request_finished(self, request: Request) -> None:
        navigation = self._navigation_for(request)
        if navigation is not None:
            navigation.finished_at = self._clock()

    def _on_request_failed(self, request: Request) -> None:
        navigation = self._navigation_for(request)
        if navigation is not None:
            _LOGGER.debug("navigation request failed: %s %s", request.method, request.url)
            self.forget(request.frame, navigation)

    def _on_frame_navigated(self, frame: Frame) -> None:
        navigation = self._pending.get(frame)
        if navigation is not None:
            navigation.committed = True

    def _on_frame_detached(self, frame: Frame) -> None:
        self._pending.pop(frame, None)

    def _navigation_for(self, request: Request) -> PendingNavigation | None:
        if not request.is_navigation_request():
            return None
        navigation = self._pending.get(request.frame)
        return navigation if navigation is not None and navigation.request is request else None


async def wait_for_navigations(tracker: NavigationTracker, dialogs: DialogSignal, max_wait_s: float) -> bool:
    """True when every pending navigation committed and loaded (or was abandoned) within `max_wait_s`.
    Returns early (True) when a native dialog opens: nothing can load until it is answered."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_wait_s
    while tracker.has_pending and loop.time() < deadline:
        if dialogs.has_pending_dialog:
            return True
        for frame, navigation in tracker.pending_items():
            if navigation.committed:
                remaining_s = max(deadline - loop.time(), 0.05)
                await run_guarded(_frame_loaded(frame, remaining_s), dialogs, timeout_s=remaining_s + 1,
                                  operation="settle.frame_load")
                tracker.forget(frame, navigation)
            elif tracker.never_commits(navigation):
                _LOGGER.debug("navigation to %s finished without committing a document", navigation.request.url)
                tracker.forget(frame, navigation)
        await asyncio.sleep(POLL_INTERVAL_S)
    if tracker.has_pending:
        urls = [navigation.request.url for _, navigation in tracker.pending_items()]
        _LOGGER.warning("wait_for_navigations: still navigating after %.1fs | inputs: urls=%r", max_wait_s, urls)
        return False
    return True


async def _frame_loaded(frame: Frame, timeout_s: float) -> bool:
    try:
        await frame.wait_for_load_state("load", timeout=timeout_s * 1000)
    except PlaywrightError as error:
        _LOGGER.debug("frame %r did not reach 'load': %s", frame.name, error)
        return False
    return True
