"""ScreenLiveView: the desktop analogue of the browser's CDP screencast.

The browser surface streams frames with `Page.startScreencast` and injects operator input with
`Input.dispatch*Event` into the same page. On macOS the equivalent is: poll the app's window with
`screencapture -l <windowid>` (~2 fps, only emitting changed frames) and inject operator input as
CGEvents into the same running app. The operator therefore drives the exact session the automation
was using, which is what the control-lease hand-off needs.

Coordinates: incoming PointerEvents are WINDOW-RELATIVE points, the same frame as `Node.bounds`.
Frames are captured at the display's backing scale (2x on Retina), so a console mapping clicks on the
image must divide image pixels by (image width / window width in points).
"""

from __future__ import annotations

import asyncio
import hashlib
import io
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from hands.core.actions import ActResult
from hands.core.log import get_logger, log_failure
from hands.core.ports import FrameHandler, KeyEvent, PointerEvent
from hands.surfaces.desktop_macos.ax import AxPoint
from hands.surfaces.desktop_macos.capture import WindowCapturer
from hands.surfaces.desktop_macos.events import EventPoster, MouseButton

logger = get_logger(__name__)

FrameFormat = Literal["png", "jpeg"]
DEFAULT_FRAMES_PER_SECOND = 2.0
WHEEL_PIXELS_PER_LINE = 40.0
JPEG_QUALITY = 70


@dataclass(frozen=True)
class CaptureTarget:
    """Which window to stream and where it is on screen (for input coordinate conversion)."""

    window_id: int
    origin: AxPoint


CaptureTargetProvider = Callable[[], Awaitable[CaptureTarget | None]]
Sleep = Callable[[float], Awaitable[None]]


def encode_frame(png_bytes: bytes, image_format: FrameFormat) -> bytes | None:
    """PNG passes through; JPEG is re-encoded with Pillow (smaller frames for the console)."""
    if image_format == "png":
        return png_bytes
    from PIL import Image, UnidentifiedImageError

    try:
        image = Image.open(io.BytesIO(png_bytes))
        output = io.BytesIO()
        image.convert("RGB").save(output, format="JPEG", quality=JPEG_QUALITY)
    except (UnidentifiedImageError, OSError) as encode_error:
        log_failure(
            logger, "encode_frame", f"cannot re-encode frame: {encode_error}", size=len(png_bytes)
        )
        return None
    return output.getvalue()


def wheel_lines(delta_y: float) -> int:
    """Browser-style wheel delta (positive = scroll down) to CGEvent lines (negative = down)."""
    if delta_y == 0:
        return 0
    magnitude = max(1, round(abs(delta_y) / WHEEL_PIXELS_PER_LINE))
    return -magnitude if delta_y > 0 else magnitude


def pointer_button(button: Literal["left", "right", "none"]) -> MouseButton:
    return "right" if button == "right" else "left"


class ScreenLiveView:
    """LiveViewTransport over window screenshots and CGEvent injection."""

    def __init__(
        self,
        target_provider: CaptureTargetProvider,
        capturer: WindowCapturer,
        events: EventPoster,
        frames_per_second: float = DEFAULT_FRAMES_PER_SECOND,
        image_format: FrameFormat = "png",
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._target_provider = target_provider
        self._capturer = capturer
        self._events = events
        self._frame_interval_s = 1.0 / frames_per_second
        self._image_format = image_format
        self._sleep = sleep
        self._task: asyncio.Task[None] | None = None
        self._last_frame_digest: str | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self, on_frame: FrameHandler) -> None:
        if self.running:
            return
        self._last_frame_digest = None
        self._task = asyncio.create_task(self._frame_loop(on_frame))

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def capture_frame(self) -> bytes | None:
        """One encoded frame of the target window, or None when it cannot be captured."""
        target = await self._target_provider()
        if target is None:
            return None
        capture = await self._capturer.capture_window(target.window_id)
        if capture.png is None:
            return None
        return encode_frame(capture.png, self._image_format)

    async def next_changed_frame(self) -> bytes | None:
        """Capture a frame and return it only if it differs from the last emitted one."""
        frame = await self.capture_frame()
        if frame is None:
            return None
        digest = hashlib.sha256(frame).hexdigest()
        if digest == self._last_frame_digest:
            return None
        self._last_frame_digest = digest
        return frame

    async def _frame_loop(self, on_frame: FrameHandler) -> None:
        while True:
            frame = await self.next_changed_frame()
            if frame is not None:
                await self._deliver(on_frame, frame)
            await self._sleep(self._frame_interval_s)

    async def _deliver(self, on_frame: FrameHandler, frame: bytes) -> None:
        """Hand a frame to the consumer; a failing consumer is logged, not allowed to kill the stream."""
        try:
            await on_frame(frame)
        except Exception as handler_error:  # noqa: BLE001 - consumer boundary: keep streaming
            log_failure(
                logger,
                "_deliver",
                f"frame handler raised: {handler_error!r}",
                frame_size=len(frame),
            )

    # ---------------------------------------------------- input injection

    async def _screen_point(self, x: float, y: float) -> AxPoint | None:
        target = await self._target_provider()
        if target is None:
            log_failure(logger, "_screen_point", "no live window to inject into", x=x, y=y)
            return None
        return AxPoint(target.origin.x + x, target.origin.y + y)

    def _post_pointer(self, event: PointerEvent, point: AxPoint) -> ActResult:
        button = pointer_button(event.button)
        if event.type == "move":
            return self._events.move(point.x, point.y)
        if event.type in ("down", "up"):
            return self._events.mouse_button(point.x, point.y, button, down=event.type == "down")
        if event.type == "click":
            return self._events.click(point.x, point.y, button)
        return self._events.scroll(point.x, point.y, wheel_lines(event.delta_y))

    async def inject_pointer(self, event: PointerEvent) -> None:
        point = await self._screen_point(event.x, event.y)
        if point is None:
            return
        result = self._post_pointer(event, point)
        if not result.ok:
            log_failure(
                logger, "inject_pointer", result.error or "event post failed", event_type=event.type
            )

    async def inject_key(self, event: KeyEvent) -> None:
        if event.type == "char":
            result = self._events.type_text(event.text or event.key)
        else:
            result = self._events.key(event.key, down=event.type == "down")
        if not result.ok:
            # the key itself is not logged: operator keystrokes may be secrets
            log_failure(
                logger, "inject_key", result.error or "event post failed", event_type=event.type
            )
