"""FakeLiveView: records operator input, emits frames, and drives its FakeSurface like a human would."""

from __future__ import annotations

from surface_test_helpers import act_on, find_node

from hands.core.actions import ClickAction, OpenAction
from hands.core.ports import KeyEvent, LiveViewTransport, PointerEvent
from hands.surfaces.fake import FakeLiveView, blank_png, coreone_fake


async def _collecting_start(live_view: FakeLiveView) -> list[bytes]:
    frames: list[bytes] = []

    async def collect(frame: bytes) -> None:
        frames.append(frame)

    await live_view.start(collect)
    return frames


def test_fake_live_view_satisfies_protocol() -> None:
    assert isinstance(FakeLiveView(), LiveViewTransport)


async def test_emit_frame_only_while_started() -> None:
    live_view = FakeLiveView()
    assert await live_view.emit_frame() is False

    frames = await _collecting_start(live_view)
    assert await live_view.emit_frame() is True
    assert await live_view.emit_frame(b"custom") is True
    await live_view.stop()

    assert frames == [blank_png(1280, 800), b"custom"]
    assert live_view.frames_emitted == 2
    assert await live_view.emit_frame() is False and not live_view.running


async def test_unbound_live_view_only_records() -> None:
    live_view = FakeLiveView()
    await live_view.inject_pointer(PointerEvent(type="click", x=1, y=2))
    await live_view.inject_key(KeyEvent(type="char", key="a", text="a"))
    assert len(live_view.pointer_events) == 1 and len(live_view.key_events) == 1


async def test_injected_click_and_keys_drive_the_surface_as_human() -> None:
    surface = coreone_fake(password="pw")
    await surface.act(None, OpenAction(entry_point="http://coreone.test/t/lakeside/login"))
    login = await surface.observe()
    user_box = find_node(login, "textbox", label="User ID").bounds
    assert user_box is not None
    live_view = surface.live_view()
    await _collecting_start(live_view)

    await live_view.inject_pointer(PointerEvent(type="click", x=user_box.center_x, y=user_box.center_y))
    for event in [
        KeyEvent(type="down", key="t"), KeyEvent(type="up", key="t"),  # down/up style
        KeyEvent(type="down", key="e"), KeyEvent(type="char", key="e", text="e"), KeyEvent(type="up", key="e"),
        KeyEvent(type="char", key="l", text="l"),  # char-only style
        KeyEvent(type="down", key="Shift"), KeyEvent(type="up", key="Shift"),  # modifiers type nothing
    ]:
        await live_view.inject_key(event)

    assert surface.value_of("User ID") == "tel"
    human_acts = [record for record in surface.actions if record.source == "human"]
    assert [record.action.kind for record in human_acts] == ["click", "type", "type", "type", "press"]


async def test_injected_enter_presses_the_focused_field() -> None:
    surface = coreone_fake(password="pw")
    await surface.act(None, OpenAction(entry_point="http://coreone.test/t/lakeside/login"))
    await act_on(surface, ClickAction(), "textbox", label="Password")
    live_view = surface.live_view()

    for character in "pw":
        await live_view.inject_key(KeyEvent(type="char", key=character, text=character))
    await act_on(surface, ClickAction(), "textbox", label="User ID")
    for character in "teller1":
        await live_view.inject_key(KeyEvent(type="char", key=character, text=character))
    await act_on(surface, ClickAction(), "textbox", label="Password")
    await live_view.inject_key(KeyEvent(type="down", key="Enter"))

    assert surface.current_screen == "main"


async def test_pointer_move_and_down_are_recorded_only_and_wheel_scrolls() -> None:
    surface = coreone_fake()
    live_view = surface.live_view()
    await live_view.inject_pointer(PointerEvent(type="move", x=5, y=5))
    await live_view.inject_pointer(PointerEvent(type="down", x=5, y=5))
    await live_view.inject_pointer(PointerEvent(type="wheel", x=5, y=5, delta_y=-120))

    assert len(live_view.pointer_events) == 3
    assert [(record.action.kind, record.source) for record in surface.actions] == [("scroll", "human")]


async def test_surface_close_stops_live_view() -> None:
    surface = coreone_fake()
    live_view = surface.live_view()
    await _collecting_start(live_view)
    await surface.close()
    assert not live_view.running
