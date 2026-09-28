"""NavigationTracker and settle helpers with mocked Playwright requests/frames (no browser)."""

from __future__ import annotations

import asyncio
from typing import Any

from playwright.async_api import Error as PlaywrightError

from hands.surfaces.browser.navigation import NavigationTracker, wait_for_navigations
from hands.surfaces.browser.settle import all_frames_complete


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class FakeFrame:
    def __init__(self, name: str, load_error: bool = False) -> None:
        self.name = name
        self.load_waits = 0
        self._load_error = load_error

    async def wait_for_load_state(self, state: str, timeout: float) -> None:
        self.load_waits += 1
        if self._load_error:
            raise PlaywrightError("frame was detached")


class FakeRequest:
    def __init__(self, frame: FakeFrame, url: str = "http://x/", navigation: bool = True) -> None:
        self.frame = frame
        self.url = url
        self.method = "GET"
        self._navigation = navigation

    def is_navigation_request(self) -> bool:
        return self._navigation


class NoDialog:
    has_pending_dialog = False

    async def wait_for_dialog(self) -> None:
        await asyncio.Event().wait()

    def park(self, task: Any) -> None:
        return


class OpenDialog(NoDialog):
    has_pending_dialog = True


def _tracker() -> tuple[NavigationTracker, FakeClock]:
    clock = FakeClock()
    return NavigationTracker(clock=clock), clock


# ---------------------------------------------------------------- event bookkeeping


def test_only_navigation_requests_are_tracked() -> None:
    tracker, _ = _tracker()
    content = FakeFrame("content")
    tracker._on_request(FakeRequest(content, navigation=False))  # type: ignore[arg-type]
    assert not tracker.has_pending

    tracker._on_request(FakeRequest(content))  # type: ignore[arg-type]
    assert [frame for frame, _ in tracker.pending_items()] == [content]


def test_redirect_replaces_pending_request_and_stale_failures_are_ignored() -> None:
    tracker, _ = _tracker()
    content = FakeFrame("content")
    post, redirected_get = FakeRequest(content, "http://x/search"), FakeRequest(content, "http://x/member/1")
    tracker._on_request(post)  # type: ignore[arg-type]
    tracker._on_request(redirected_get)  # type: ignore[arg-type]
    tracker._on_request_failed(post)  # type: ignore[arg-type]

    assert tracker.pending_items()[0][1].request is redirected_get
    tracker._on_request_failed(redirected_get)  # type: ignore[arg-type]
    assert not tracker.has_pending


def test_commit_and_detach() -> None:
    tracker, _ = _tracker()
    content, other = FakeFrame("content"), FakeFrame("other")
    tracker._on_request(FakeRequest(content))  # type: ignore[arg-type]
    tracker._on_frame_navigated(other)  # type: ignore[arg-type]
    tracker._on_frame_navigated(content)  # type: ignore[arg-type]
    assert tracker.pending_items()[0][1].committed

    tracker._on_frame_detached(content)  # type: ignore[arg-type]
    tracker._on_frame_detached(other)  # type: ignore[arg-type]
    assert not tracker.has_pending


def test_forget_keeps_a_newer_navigation() -> None:
    tracker, _ = _tracker()
    content = FakeFrame("content")
    tracker._on_request(FakeRequest(content))  # type: ignore[arg-type]
    older = tracker.pending_items()[0][1]
    tracker._on_request(FakeRequest(content, "http://x/newer"))  # type: ignore[arg-type]

    tracker.forget(content, older)  # type: ignore[arg-type]
    assert tracker.pending_items()[0][1].request.url == "http://x/newer"


def test_finished_navigation_that_never_commits_is_abandoned_after_a_while() -> None:
    tracker, clock = _tracker()
    content = FakeFrame("content")
    request = FakeRequest(content)
    tracker._on_request(request)  # type: ignore[arg-type]
    navigation = tracker.pending_items()[0][1]
    assert not tracker.never_commits(navigation)

    tracker._on_request_finished(request)  # type: ignore[arg-type]
    tracker._on_request_finished(FakeRequest(content, navigation=False))  # type: ignore[arg-type]
    assert not tracker.never_commits(navigation)
    clock.now += 2
    assert tracker.never_commits(navigation)


def test_seconds_since_action() -> None:
    tracker, clock = _tracker()
    assert tracker.seconds_since_action() is None
    tracker.mark_action()
    clock.now += 0.25
    assert tracker.seconds_since_action() == 0.25


# ---------------------------------------------------------------- waiting


async def test_wait_with_nothing_pending_returns_immediately() -> None:
    tracker, _ = _tracker()
    assert await wait_for_navigations(tracker, NoDialog(), max_wait_s=0.1)


async def test_wait_loads_committed_frames_and_forgets_them() -> None:
    tracker, _ = _tracker()
    content, detached = FakeFrame("content"), FakeFrame("gone", load_error=True)
    for frame in (content, detached):
        tracker._on_request(FakeRequest(frame))  # type: ignore[arg-type]
        tracker._on_frame_navigated(frame)  # type: ignore[arg-type]

    assert await wait_for_navigations(tracker, NoDialog(), max_wait_s=1)
    assert content.load_waits == 1 and detached.load_waits == 1 and not tracker.has_pending


async def test_wait_waits_for_a_late_commit() -> None:
    tracker, _ = _tracker()
    content = FakeFrame("content")
    tracker._on_request(FakeRequest(content))  # type: ignore[arg-type]
    asyncio.get_running_loop().call_later(0.1, tracker._on_frame_navigated, content)

    assert await wait_for_navigations(tracker, NoDialog(), max_wait_s=2)
    assert content.load_waits == 1


async def test_wait_gives_up_at_the_deadline() -> None:
    tracker, _ = _tracker()
    tracker._on_request(FakeRequest(FakeFrame("content"), "http://x/slow"))  # type: ignore[arg-type]
    assert not await wait_for_navigations(tracker, NoDialog(), max_wait_s=0.1)
    assert tracker.has_pending


async def test_wait_returns_early_when_a_native_dialog_is_open() -> None:
    tracker, _ = _tracker()
    tracker._on_request(FakeRequest(FakeFrame("content")))  # type: ignore[arg-type]
    assert await wait_for_navigations(tracker, OpenDialog(), max_wait_s=5)


# ---------------------------------------------------------------- readiness


def test_all_frames_complete() -> None:
    assert all_frames_complete(())
    assert all_frames_complete(("=complete:10:300", "content=complete:4:80"))
    assert not all_frames_complete(("=complete:10:300", "content=interactive:4:80"))
    assert not all_frames_complete(("content=unavailable",))
