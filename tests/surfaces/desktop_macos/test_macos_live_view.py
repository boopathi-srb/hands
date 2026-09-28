import asyncio

import pytest
from macos_ax_fakes import FakeCapturer, FakeEventPoster, tiny_png

from hands.core.ports import KeyEvent, LiveViewTransport, PointerEvent
from hands.surfaces.desktop_macos.ax import AxPoint
from hands.surfaces.desktop_macos.live_view import (
    CaptureTarget,
    ScreenLiveView,
    encode_frame,
    pointer_button,
    wheel_lines,
)

TARGET = CaptureTarget(window_id=7, origin=AxPoint(100, 50))


async def yielding_sleep(_seconds: float) -> None:
    await asyncio.sleep(0)


def make_view(
    capturer: FakeCapturer | None = None,
    events: FakeEventPoster | None = None,
    target: CaptureTarget | None = TARGET,
    image_format: str = "png",
) -> tuple[ScreenLiveView, FakeCapturer, FakeEventPoster]:
    active_capturer = capturer or FakeCapturer()
    active_events = events or FakeEventPoster()

    async def provider() -> CaptureTarget | None:
        return target

    view = ScreenLiveView(
        provider, active_capturer, active_events, image_format=image_format, sleep=yielding_sleep
    )  # type: ignore[arg-type]
    return view, active_capturer, active_events


def test_is_a_live_view_transport() -> None:
    assert isinstance(make_view()[0], LiveViewTransport)


def test_encode_frame_png_passthrough_and_jpeg() -> None:
    png = tiny_png()
    assert encode_frame(png, "png") is png
    jpeg = encode_frame(png, "jpeg")
    assert jpeg is not None and jpeg.startswith(b"\xff\xd8")
    assert encode_frame(b"not an image", "jpeg") is None


@pytest.mark.parametrize(("delta_y", "expected"), [(0, 0), (120, -3), (-120, 3), (10, -1), (-1, 1)])
def test_wheel_lines(delta_y: float, expected: int) -> None:
    assert wheel_lines(delta_y) == expected


def test_pointer_button() -> None:
    assert pointer_button("left") == "left"
    assert pointer_button("right") == "right"
    assert pointer_button("none") == "left"


async def test_capture_frame_and_missing_target() -> None:
    view, capturer, _ = make_view()
    assert await view.capture_frame() == tiny_png()
    assert capturer.captured_ids == [7]
    missing_view, _, _ = make_view(target=None)
    assert await missing_view.capture_frame() is None
    failing_view, _, _ = make_view(capturer=FakeCapturer(error="denied"))
    assert await failing_view.capture_frame() is None


async def test_next_changed_frame_skips_duplicates() -> None:
    red, blue = tiny_png((255, 0, 0)), tiny_png((0, 0, 255))
    view, _, _ = make_view(capturer=FakeCapturer(frames=[red, red, blue]))
    assert await view.next_changed_frame() == red
    assert await view.next_changed_frame() is None
    assert await view.next_changed_frame() == blue


async def test_start_streams_frames_until_stopped() -> None:
    red, blue = tiny_png((255, 0, 0)), tiny_png((0, 0, 255))
    view, _, _ = make_view(capturer=FakeCapturer(frames=[red, blue]), image_format="jpeg")
    received: list[bytes] = []

    async def on_frame(frame: bytes) -> None:
        received.append(frame)

    await view.start(on_frame)
    await view.start(on_frame)
    for _ in range(20):
        await asyncio.sleep(0)
    await view.stop()
    assert not view.running
    assert len(received) == 2
    assert all(frame.startswith(b"\xff\xd8") for frame in received)
    await view.stop()


async def test_failing_frame_handler_does_not_kill_stream() -> None:
    red, blue = tiny_png((255, 0, 0)), tiny_png((0, 0, 255))
    view, _, _ = make_view(capturer=FakeCapturer(frames=[red, blue]))
    calls: list[int] = []

    async def exploding(frame: bytes) -> None:
        calls.append(len(frame))
        raise ValueError("console went away")

    await view.start(exploding)
    for _ in range(20):
        await asyncio.sleep(0)
    assert view.running
    await view.stop()
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (PointerEvent(type="move", x=1, y=2), ("move", 101, 52)),
        (PointerEvent(type="down", x=1, y=2), ("mouse_button", 101, 52, "left", True)),
        (
            PointerEvent(type="up", x=1, y=2, button="right"),
            ("mouse_button", 101, 52, "right", False),
        ),
        (PointerEvent(type="click", x=1, y=2), ("click", 101, 52, "left")),
        (PointerEvent(type="wheel", x=1, y=2, button="none", delta_y=80), ("scroll", 101, 52, -2)),
    ],
)
async def test_inject_pointer_converts_window_points_to_screen(
    event: PointerEvent, expected: tuple
) -> None:
    view, _, events = make_view()
    await view.inject_pointer(event)
    assert events.calls == [expected]


async def test_inject_pointer_without_window_does_nothing() -> None:
    view, _, events = make_view(target=None)
    await view.inject_pointer(PointerEvent(type="click", x=1, y=2))
    assert events.calls == []


async def test_inject_pointer_failure_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    view, _, _ = make_view(events=FakeEventPoster(fail=True))
    await view.inject_pointer(PointerEvent(type="click", x=1, y=2))
    assert "inject_pointer failed" in caplog.text


async def test_inject_key_variants() -> None:
    view, _, events = make_view()
    await view.inject_key(KeyEvent(type="down", key="Enter"))
    await view.inject_key(KeyEvent(type="up", key="Enter"))
    await view.inject_key(KeyEvent(type="char", key="a", text="a"))
    await view.inject_key(KeyEvent(type="char", key="b"))
    assert events.calls == [
        ("key", "Enter", True),
        ("key", "Enter", False),
        ("type_text", "a"),
        ("type_text", "b"),
    ]


async def test_inject_key_failure_does_not_log_the_key(caplog: pytest.LogCaptureFixture) -> None:
    view, _, _ = make_view(events=FakeEventPoster(fail=True))
    await view.inject_key(KeyEvent(type="char", key="s3cr3t", text="s3cr3t"))
    assert "inject_key failed" in caplog.text
    assert "s3cr3t" not in caplog.text
