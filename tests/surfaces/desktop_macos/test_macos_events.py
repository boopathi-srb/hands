"""CGEvent poster against a stub Quartz module: nothing is posted to the real event stream."""

from typing import Any

import pytest

from hands.surfaces.desktop_macos import events as events_module
from hands.surfaces.desktop_macos.events import (
    MODIFIER_FLAGS,
    KeyCombo,
    QuartzEventPoster,
    parse_key_combo,
    scroll_lines,
)


class StubQuartz:
    kCGHIDEventTap = 0
    kCGEventMouseMoved = 5
    kCGEventLeftMouseDown = 1
    kCGEventLeftMouseUp = 2
    kCGEventRightMouseDown = 3
    kCGEventRightMouseUp = 4
    kCGMouseButtonLeft = 0
    kCGMouseButtonRight = 1
    kCGMouseEventClickState = 1
    kCGScrollEventUnitLine = 1

    def __init__(self, create_fails: bool = False) -> None:
        self.posted: list[dict[str, Any]] = []
        self.create_fails = create_fails

    def CGPointMake(self, x: float, y: float) -> tuple[float, float]:
        return (x, y)

    def CGEventCreateMouseEvent(
        self, source: None, event_type: int, point: tuple[float, float], button: int
    ) -> dict[str, Any] | None:
        return (
            None
            if self.create_fails
            else {"kind": "mouse", "type": event_type, "point": point, "button": button}
        )

    def CGEventSetIntegerValueField(self, event: dict[str, Any], field: int, value: int) -> None:
        event["click_state"] = value

    def CGEventCreateKeyboardEvent(
        self, source: None, key_code: int, down: bool
    ) -> dict[str, Any] | None:
        return None if self.create_fails else {"kind": "key", "code": key_code, "down": down}

    def CGEventSetFlags(self, event: dict[str, Any], flags: int) -> None:
        event["flags"] = flags

    def CGEventKeyboardSetUnicodeString(
        self, event: dict[str, Any], length: int, text: str
    ) -> None:
        event["text"] = text

    def CGEventCreateScrollWheelEvent(
        self, source: None, units: int, wheel_count: int, lines: int
    ) -> dict[str, Any]:
        return {"kind": "scroll", "lines": lines}

    def CGEventPost(self, tap: int, event: dict[str, Any]) -> None:
        self.posted.append(event)


@pytest.fixture
def quartz() -> StubQuartz:
    return StubQuartz()


@pytest.fixture
def poster(quartz: StubQuartz) -> QuartzEventPoster:
    return QuartzEventPoster(quartz_module=quartz)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("Enter", KeyCombo(36, 0)),
        ("ArrowDown", KeyCombo(125, 0)),
        ("Tab", KeyCombo(48, 0)),
        ("a", KeyCombo(0, 0)),
        ("A", KeyCombo(0, MODIFIER_FLAGS["shift"])),
        ("Cmd+A", KeyCombo(0, MODIFIER_FLAGS["cmd"])),
        ("Shift+Tab", KeyCombo(48, MODIFIER_FLAGS["shift"])),
        ("Ctrl+Alt+Delete", KeyCombo(51, MODIFIER_FLAGS["ctrl"] | MODIFIER_FLAGS["alt"])),
        ("5", KeyCombo(23, 0)),
    ],
)
def test_parse_key_combo(key: str, expected: KeyCombo) -> None:
    assert parse_key_combo(key) == expected


@pytest.mark.parametrize("key", ["", "Foo", "Hyper+A", "Cmd+", "+", "Cmd++"])
def test_parse_key_combo_rejects_unknown(key: str) -> None:
    assert parse_key_combo(key) is None


def test_scroll_lines() -> None:
    assert scroll_lines("up", 3) == 3
    assert scroll_lines("down", 3) == -3


def test_move_posts_mouse_moved(poster: QuartzEventPoster, quartz: StubQuartz) -> None:
    assert poster.move(10, 20).ok
    assert quartz.posted == [{"kind": "mouse", "type": 5, "point": (10, 20), "button": 0}]


def test_click_posts_down_and_up(poster: QuartzEventPoster, quartz: StubQuartz) -> None:
    assert poster.click(1, 2).ok
    assert [(event["type"], event["click_state"]) for event in quartz.posted] == [(1, 1), (2, 1)]


def test_double_click_sets_click_state(poster: QuartzEventPoster, quartz: StubQuartz) -> None:
    assert poster.click(1, 2, click_count=2).ok
    assert [event["click_state"] for event in quartz.posted] == [1, 1, 2, 2]


def test_right_mouse_button_half(poster: QuartzEventPoster, quartz: StubQuartz) -> None:
    assert poster.mouse_button(1, 2, "right", down=True).ok
    assert quartz.posted[0]["type"] == 3 and quartz.posted[0]["button"] == 1


def test_key_posts_down_up_with_flags(poster: QuartzEventPoster, quartz: StubQuartz) -> None:
    assert poster.key("Cmd+A").ok
    assert [(event["code"], event["down"], event["flags"]) for event in quartz.posted] == [
        (0, True, MODIFIER_FLAGS["cmd"]),
        (0, False, MODIFIER_FLAGS["cmd"]),
    ]


def test_key_single_phase(poster: QuartzEventPoster, quartz: StubQuartz) -> None:
    assert poster.key("Enter", down=False).ok
    assert quartz.posted == [{"kind": "key", "code": 36, "down": False}]


def test_unknown_key_is_an_error(poster: QuartzEventPoster, quartz: StubQuartz) -> None:
    result = poster.key("Hyperdrive")
    assert not result.ok and "unknown key" in (result.error or "")
    assert quartz.posted == []


def test_type_text_posts_unicode_per_character(
    poster: QuartzEventPoster, quartz: StubQuartz
) -> None:
    assert poster.type_text("hé").ok
    assert [(event["text"], event["down"]) for event in quartz.posted] == [
        ("h", True),
        ("h", False),
        ("é", True),
        ("é", False),
    ]
    quartz.posted.clear()
    assert poster.type_text("").ok and quartz.posted == []


def test_scroll_moves_then_scrolls(poster: QuartzEventPoster, quartz: StubQuartz) -> None:
    assert poster.scroll(5, 6, -3).ok
    assert [event["kind"] for event in quartz.posted] == ["mouse", "scroll"]
    assert quartz.posted[1]["lines"] == -3


def test_event_creation_failure_is_reported() -> None:
    poster = QuartzEventPoster(quartz_module=StubQuartz(create_fails=True))  # type: ignore[arg-type]
    assert not poster.click(1, 1).ok
    assert not poster.key("Enter").ok
    assert not poster.type_text("x").ok
    assert not poster.move(1, 1).ok
    assert not poster.scroll(1, 1, 1).ok


def test_quartz_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(events_module, "_load_quartz", lambda: None)
    poster = QuartzEventPoster()
    assert not poster.move(1, 1).ok
    assert not poster.click(1, 1).ok
    assert not poster.mouse_button(1, 1, "left", True).ok
    assert not poster.key("Enter").ok
    assert not poster.type_text("x").ok
    assert not poster.scroll(1, 1, 1).ok


def test_load_quartz_handles_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_import(name: str) -> None:
        raise ImportError(name)

    monkeypatch.setattr(events_module.importlib, "import_module", failing_import)
    assert events_module._load_quartz() is None
