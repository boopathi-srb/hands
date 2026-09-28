"""CDP wrapper, geometry fetching and settle helpers with mocked Playwright objects (no browser)."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from playwright.async_api import Error as PlaywrightError

from hands.core.observation import Rect
from hands.surfaces.browser.ax_extract import ExtractedNode, TextPart
from hands.surfaces.browser.cdp import CdpCaller
from hands.surfaces.browser.settle import SettleConfig, dom_signature, wait_for_settle
from hands.surfaces.browser.snapshot import attach_geometry, fetch_border_box, fetch_line_boxes

SQUARE = [0, 0, 10, 0, 10, 10, 0, 10]


class FakeCdpSession:
    """Answers DOM.getBoxModel / DOM.getContentQuads from a table; unknown ids raise like Chrome does."""

    def __init__(self, boxes: dict[int, list[float]] | None = None,
                 quads: dict[int, list[list[float]]] | None = None) -> None:
        self.boxes = boxes or {}
        self.quads = quads or {}
        self.sent: list[tuple[str, dict[str, Any]]] = []
        self.detached = False

    async def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        self.sent.append((method, params))
        node_id = params.get("backendNodeId")
        if method == "DOM.getBoxModel" and node_id in self.boxes:
            return {"model": {"border": self.boxes[node_id]}}
        if method == "DOM.getContentQuads" and node_id in self.quads:
            return {"quads": self.quads[node_id]}
        if method == "Page.getFrameTree":
            return {"frameTree": {"frame": {"id": "TOP"}}}
        raise PlaywrightError("Could not compute box model.")

    async def detach(self) -> None:
        if self.detached:
            raise PlaywrightError("already detached")
        self.detached = True


def _caller(session: FakeCdpSession) -> CdpCaller:
    return CdpCaller(session)  # type: ignore[arg-type]


# ---------------------------------------------------------------- CdpCaller


async def test_cdp_caller_returns_result() -> None:
    session = FakeCdpSession()
    assert await _caller(session).send("Page.getFrameTree") == {"frameTree": {"frame": {"id": "TOP"}}}
    assert session.sent == [("Page.getFrameTree", {})]


async def test_cdp_caller_turns_errors_into_none_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    caller = _caller(FakeCdpSession())
    with caplog.at_level(logging.DEBUG):
        assert await caller.send("DOM.getBoxModel", {"backendNodeId": 1}) is None
        assert await caller.send("DOM.getBoxModel", {"backendNodeId": 2}, expected_failure=True) is None
    levels = [record.levelno for record in caplog.records if "DOM.getBoxModel" in record.getMessage()]
    assert levels == [logging.ERROR, logging.DEBUG]


async def test_cdp_caller_detach_errors_are_logged_not_raised() -> None:
    session = FakeCdpSession()
    caller = _caller(session)
    await caller.detach()
    await caller.detach()
    assert session.detached and caller.session is session


# ---------------------------------------------------------------- geometry fetching


async def test_fetch_border_box() -> None:
    caller = _caller(FakeCdpSession(boxes={7: SQUARE}))
    assert await fetch_border_box(caller, 7) == Rect(x=0, y=0, width=10, height=10)
    assert await fetch_border_box(caller, 8) is None
    assert await fetch_border_box(caller, None) is None


async def test_fetch_line_boxes_drops_zero_width_and_failures() -> None:
    zero_width = [5, 0, 5, 0, 5, 10, 5, 10]
    caller = _caller(FakeCdpSession(quads={3: [SQUARE, zero_width, [1, 2]]}))
    assert await fetch_line_boxes(caller, TextPart("abc", 3)) == [Rect(x=0, y=0, width=10, height=10)]
    assert await fetch_line_boxes(caller, TextPart("gone", 4)) == []


async def test_attach_geometry_sets_element_bounds_and_text_lines() -> None:
    cell = ExtractedNode(role="cell", chrome_name="", container_path=(), frame_id="F", parent=None,
                         backend_node_id=1, text_parts=[TextPart("Balance", 2)])
    run = ExtractedNode(role="text", chrome_name="", container_path=(), frame_id="F", parent=None,
                        backend_node_id=3, text_parts=[TextPart("Total", 3)])
    hidden = ExtractedNode(role="button", chrome_name="", container_path=(), frame_id="F", parent=None,
                           backend_node_id=9)
    caller = _caller(FakeCdpSession(boxes={1: SQUARE}, quads={2: [SQUARE], 3: [SQUARE]}))

    await attach_geometry(caller, [cell, run, hidden])

    assert cell.bounds == Rect(x=0, y=0, width=10, height=10)
    assert cell.text_parts[0].line_boxes == [Rect(x=0, y=0, width=10, height=10)]
    assert run.bounds is None and run.text_parts[0].line_boxes  # runs get bounds from their lines later
    assert hidden.bounds is None


async def test_attach_geometry_with_no_nodes() -> None:
    session = FakeCdpSession()
    await attach_geometry(_caller(session), [])
    assert session.sent == []


# ---------------------------------------------------------------- settle


class FakeFrame:
    def __init__(self, name: str, signature: str | None) -> None:
        self.name = name
        self._signature = signature

    async def evaluate(self, script: str) -> str:
        if self._signature is None:
            raise PlaywrightError("Execution context was destroyed")
        return self._signature


class FakePage:
    def __init__(self, frames: list[FakeFrame]) -> None:
        self.frames = frames
        self.url = "http://example.test/"
        self.load_state_waits = 0

    async def wait_for_load_state(self, state: str, timeout: float) -> None:
        self.load_state_waits += 1


class OpenDialogSignal:
    has_pending_dialog = True

    async def wait_for_dialog(self) -> None:
        return

    def park(self, task: Any) -> None:
        task.cancel()


class NoDialogSignal:
    has_pending_dialog = False

    async def wait_for_dialog(self) -> None:
        import asyncio

        await asyncio.Event().wait()

    def park(self, task: Any) -> None:
        return


async def test_dom_signature_per_frame_marks_unavailable_frames() -> None:
    page = FakePage([FakeFrame("", "complete:10:500"), FakeFrame("content", None)])
    assert await dom_signature(page) == ("=complete:10:500", "content=unavailable")  # type: ignore[arg-type]


async def test_dom_signature_of_page_without_frames() -> None:
    assert await dom_signature(FakePage([])) == ()  # type: ignore[arg-type]


async def test_settle_returns_immediately_while_a_native_dialog_is_open() -> None:
    page = FakePage([FakeFrame("", "x")])
    await wait_for_settle(page, OpenDialogSignal(), SettleConfig())  # type: ignore[arg-type]
    assert page.load_state_waits == 0


async def test_settle_waits_for_network_then_a_quiet_dom() -> None:
    page = FakePage([FakeFrame("", "complete:3:40")])
    config = SettleConfig(dom_quiet_interval_ms=1, dom_quiet_max_ms=500)
    await wait_for_settle(page, NoDialogSignal(), config)  # type: ignore[arg-type]
    assert page.load_state_waits == 1
