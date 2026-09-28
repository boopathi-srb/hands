"""CdpLiveView: stream the live page to an operator and inject their input into the SAME session.

Frames come from `Page.startScreencast` (JPEG, quality 60, max 1280x800) on a dedicated CDP session;
each frame is acknowledged immediately so Chrome keeps sending, then handed to the frame handler as
JPEG bytes. `last_frame_metadata` exposes Chrome's frame metadata (device size, scroll offsets).

Input is replayed with `Input.dispatchMouseEvent` / `Input.dispatchKeyEvent` at page CSS pixel
coordinates (see keys.py for the key-event mapping). If a native JS dialog is open, the page cannot
receive input: Enter accepts and Escape dismisses the dialog, everything else is ignored and logged.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from hands.core.log import get_logger, log_failure
from hands.core.ports import FrameHandler, KeyEvent, PointerEvent
from hands.surfaces.browser.cdp import CdpCaller
from hands.surfaces.browser.guard import Guarded, run_guarded
from hands.surfaces.browser.keys import KeyTranslator, PointerTranslator
from hands.surfaces.browser.native_dialogs import NativeDialogKeeper
from hands.surfaces.browser.navigation import NavigationTracker

_LOGGER = get_logger(__name__)

SCREENCAST_PARAMS: dict[str, Any] = {"format": "jpeg", "quality": 60, "maxWidth": 1280, "maxHeight": 800,
                                     "everyNthFrame": 1}
INPUT_TIMEOUT_S = 5.0


class CdpLiveView:
    """LiveViewTransport over CDP. One instance per operator session; start() once, stop() once."""

    def __init__(self, page: Page, dialogs: NativeDialogKeeper, navigations: NavigationTracker | None = None) -> None:
        self._page = page
        self._dialogs = dialogs
        self._navigations = navigations
        self._cdp: CdpCaller | None = None
        self._on_frame: FrameHandler | None = None
        self._frame_deliveries: list[asyncio.Task[None]] = []
        self._keys = KeyTranslator()
        self._pointer = PointerTranslator()
        self.last_frame_metadata: dict[str, Any] | None = None
        self.frames_delivered = 0

    @property
    def running(self) -> bool:
        return self._cdp is not None

    async def start(self, on_frame: FrameHandler) -> None:
        if self._cdp is not None:
            log_failure(_LOGGER, "CdpLiveView.start", "already started", url=self._page.url)
            return
        session = await self._open_session()
        if session is None:
            return
        self._on_frame = on_frame
        self._cdp = session
        session.session.on("Page.screencastFrame", self._on_screencast_frame)
        started = await self._send_dialog_safe(session, "Page.startScreencast", SCREENCAST_PARAMS)
        if started.status in ("failed", "timeout") or (started.ok and started.value is None):
            await self.stop()

    async def stop(self) -> None:
        session, self._cdp = self._cdp, None
        self._on_frame = None
        if session is None:
            return
        await self._send_dialog_safe(session, "Page.stopScreencast", None)
        await run_guarded(session.detach(), self._dialogs, timeout_s=INPUT_TIMEOUT_S, operation="detach",
                          start_behind_open_dialog=True)
        for delivery in list(self._frame_deliveries):
            delivery.cancel()
        self._frame_deliveries.clear()

    async def inject_pointer(self, event: PointerEvent) -> None:
        if self._reject_input_during_dialog(f"pointer {event.type}"):
            return
        for params in self._pointer.translate(event, self._keys.modifiers):
            await self._dispatch("Input.dispatchMouseEvent", params)

    async def inject_key(self, event: KeyEvent) -> None:
        if self._dialogs.has_pending_dialog:
            await self._answer_dialog_with_key(event)
            return
        for params in self._keys.translate(event):
            await self._dispatch("Input.dispatchKeyEvent", params)

    # ------------------------------------------------------------ internals

    async def _open_session(self) -> CdpCaller | None:
        try:
            return CdpCaller(await self._page.context.new_cdp_session(self._page))
        except PlaywrightError as error:
            log_failure(_LOGGER, "CdpLiveView.start", f"could not open CDP session: {error}", url=self._page.url)
            return None

    async def _send_dialog_safe(
        self, session: CdpCaller, method: str, params: dict[str, Any] | None
    ) -> Guarded[dict[str, Any] | None]:
        """Renderer-bound commands wait behind an open JS dialog; park them instead of hanging."""
        return await run_guarded(session.send(method, params, expected_failure=method == "Page.stopScreencast"),
                                 self._dialogs, timeout_s=INPUT_TIMEOUT_S, operation=method,
                                 start_behind_open_dialog=True)

    def _on_screencast_frame(self, params: dict[str, Any]) -> None:
        delivery = asyncio.ensure_future(self._deliver_frame(params))
        self._frame_deliveries.append(delivery)
        delivery.add_done_callback(self._forget_delivery)

    async def _deliver_frame(self, params: dict[str, Any]) -> None:
        session, on_frame = self._cdp, self._on_frame
        if session is None or on_frame is None:
            return
        await session.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]}, expected_failure=True)
        self.last_frame_metadata = params.get("metadata")
        await on_frame(base64.b64decode(params["data"]))
        self.frames_delivered += 1

    def _forget_delivery(self, delivery: asyncio.Task[None]) -> None:
        if delivery in self._frame_deliveries:
            self._frame_deliveries.remove(delivery)
        if not delivery.cancelled() and delivery.exception() is not None:
            log_failure(_LOGGER, "CdpLiveView._deliver_frame", repr(delivery.exception()), url=self._page.url)

    async def _dispatch(self, method: str, params: dict[str, Any]) -> None:
        session = self._cdp
        if session is None:
            log_failure(_LOGGER, "CdpLiveView._dispatch", "live view is not started", method=method)
            return
        await run_guarded(session.send(method, params), self._dialogs, timeout_s=INPUT_TIMEOUT_S, operation=method)
        if self._navigations is not None:
            self._navigations.mark_action()  # human input may start navigations, like automated input

    async def _answer_dialog_with_key(self, event: KeyEvent) -> None:
        if event.type != "down":
            _LOGGER.debug("ignoring key %s %r while a native dialog is open", event.type, event.key)
            return
        if event.key in ("Enter", "Escape"):
            await self._dialogs.resolve(accept=event.key == "Enter")
            return
        self._reject_input_during_dialog(f"key {event.type} {event.key!r}")

    def _reject_input_during_dialog(self, description: str) -> bool:
        if not self._dialogs.has_pending_dialog:
            return False
        log_failure(_LOGGER, "CdpLiveView.inject", "native dialog is open; input cannot reach the page",
                    input=description)
        return True
