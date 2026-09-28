"""Synthetic input via Quartz CGEvents: the fallback when an element has no AX action.

All coordinates here are SCREEN coordinates (top-left origin, points), because that is what CGEvent
expects. Callers convert from window-relative bounds first. Every method returns an ActResult.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Literal, Protocol

from hands.core.actions import ActResult
from hands.core.log import get_logger, log_failure

logger = get_logger(__name__)

MouseButton = Literal["left", "right"]

# ANSI virtual key codes (HIToolbox/Events.h). Stable across macOS releases.
NAMED_KEY_CODES: dict[str, int] = {
    "enter": 36,
    "return": 36,
    "tab": 48,
    "space": 49,
    "backspace": 51,
    "delete": 51,
    "escape": 53,
    "esc": 53,
    "forwarddelete": 117,
    "home": 115,
    "end": 119,
    "pageup": 116,
    "pagedown": 121,
    "arrowleft": 123,
    "left": 123,
    "arrowright": 124,
    "right": 124,
    "arrowdown": 125,
    "down": 125,
    "arrowup": 126,
    "up": 126,
    "f1": 122,
    "f2": 120,
    "f3": 99,
    "f4": 118,
    "f5": 96,
    "f6": 97,
    "f7": 98,
    "f8": 100,
    "f9": 101,
    "f10": 109,
    "f11": 103,
    "f12": 111,
}

CHARACTER_KEY_CODES: dict[str, int] = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19,
    "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28,
    "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "l": 37, "j": 38,
    "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44, "n": 45, "m": 46, ".": 47,
    "`": 50,
}  # fmt: skip

MODIFIER_FLAGS: dict[str, int] = {
    "shift": 1 << 17,
    "control": 1 << 18,
    "ctrl": 1 << 18,
    "alt": 1 << 19,
    "option": 1 << 19,
    "meta": 1 << 20,
    "cmd": 1 << 20,
    "command": 1 << 20,
}

UNICODE_ONLY_KEY_CODE = 0
"""Key code used when posting arbitrary unicode text; the text itself rides on the event."""


@dataclass(frozen=True)
class KeyCombo:
    key_code: int
    flags: int


def parse_key_combo(key: str) -> KeyCombo | None:
    """Parse 'Enter', 'ArrowDown', 'a', 'Cmd+A', 'Shift+Tab'. None if the key is unknown.

    A lone uppercase letter ('A') implies Shift; with explicit modifiers ('Cmd+A') the case is ignored.
    """
    parts = [part.strip() for part in key.split("+")]
    if any(not part for part in parts):
        return None
    *modifier_names, key_name = parts
    flags = 0
    for modifier_name in modifier_names:
        modifier_flag = MODIFIER_FLAGS.get(modifier_name.lower())
        if modifier_flag is None:
            return None
        flags |= modifier_flag
    lowered = key_name.lower()
    key_code = NAMED_KEY_CODES.get(lowered, CHARACTER_KEY_CODES.get(lowered))
    if key_code is None:
        return None
    is_lone_uppercase_letter = not modifier_names and len(key_name) == 1 and key_name.isupper()
    if is_lone_uppercase_letter:
        flags |= MODIFIER_FLAGS["shift"]
    return KeyCombo(key_code=key_code, flags=flags)


def scroll_lines(direction: Literal["up", "down"], amount: int) -> int:
    """CGEvent wheel delta: positive scrolls content up (toward the top), negative down."""
    return amount if direction == "up" else -amount


class EventPoster(Protocol):
    def move(self, x: float, y: float) -> ActResult: ...

    def mouse_button(self, x: float, y: float, button: MouseButton, down: bool) -> ActResult: ...

    def click(
        self, x: float, y: float, button: MouseButton = "left", click_count: int = 1
    ) -> ActResult: ...

    def key(self, key: str, down: bool | None = None) -> ActResult:
        """Press a key combo; down=True/False sends only that half (for live-view passthrough)."""
        ...

    def type_text(self, text: str) -> ActResult: ...

    def scroll(self, x: float, y: float, lines: int) -> ActResult: ...


def _load_quartz() -> ModuleType | None:
    try:
        return importlib.import_module("Quartz")
    except ImportError as import_error:
        log_failure(logger, "_load_quartz", f"cannot import Quartz: {import_error}")
        return None


class QuartzEventPoster:
    """EventPoster over CGEventPost(kCGHIDEventTap, ...). `quartz_module` is injectable for tests."""

    def __init__(self, quartz_module: ModuleType | None = None) -> None:
        self._quartz_module = quartz_module
        self._module_loaded = quartz_module is not None

    def _quartz(self) -> ModuleType | None:
        if not self._module_loaded:
            self._quartz_module = _load_quartz()
            self._module_loaded = True
        return self._quartz_module

    def _post(self, function_name: str, event: Any, **inputs: Any) -> ActResult:
        quartz = self._quartz()
        if quartz is None or event is None:
            log_failure(logger, function_name, "could not create CGEvent", **inputs)
            return ActResult(ok=False, error=f"{function_name}: could not create CGEvent")
        quartz.CGEventPost(quartz.kCGHIDEventTap, event)
        return ActResult(ok=True)

    def _unavailable(self, function_name: str, **inputs: Any) -> ActResult:
        log_failure(logger, function_name, "Quartz is unavailable", **inputs)
        return ActResult(ok=False, error=f"{function_name}: Quartz is unavailable")

    def move(self, x: float, y: float) -> ActResult:
        quartz = self._quartz()
        if quartz is None:
            return self._unavailable("move", x=x, y=y)
        event = quartz.CGEventCreateMouseEvent(
            None, quartz.kCGEventMouseMoved, quartz.CGPointMake(x, y), quartz.kCGMouseButtonLeft
        )
        return self._post("move", event, x=x, y=y)

    def _mouse_event(
        self, x: float, y: float, button: MouseButton, down: bool, click_count: int
    ) -> Any:
        quartz = self._quartz()
        if quartz is None:
            return None
        if button == "left":
            event_type = quartz.kCGEventLeftMouseDown if down else quartz.kCGEventLeftMouseUp
            button_code = quartz.kCGMouseButtonLeft
        else:
            event_type = quartz.kCGEventRightMouseDown if down else quartz.kCGEventRightMouseUp
            button_code = quartz.kCGMouseButtonRight
        event = quartz.CGEventCreateMouseEvent(
            None, event_type, quartz.CGPointMake(x, y), button_code
        )
        if event is not None:
            quartz.CGEventSetIntegerValueField(event, quartz.kCGMouseEventClickState, click_count)
        return event

    def mouse_button(self, x: float, y: float, button: MouseButton, down: bool) -> ActResult:
        event = self._mouse_event(x, y, button, down, click_count=1)
        return self._post("mouse_button", event, x=x, y=y, button=button, down=down)

    def click(
        self, x: float, y: float, button: MouseButton = "left", click_count: int = 1
    ) -> ActResult:
        for click_index in range(1, click_count + 1):
            for down in (True, False):
                event = self._mouse_event(x, y, button, down, click_index)
                result = self._post(
                    "click", event, x=x, y=y, button=button, click_count=click_count
                )
                if not result.ok:
                    return result
        return ActResult(ok=True)

    def _keyboard_event(self, key_code: int, down: bool, flags: int) -> Any:
        quartz = self._quartz()
        if quartz is None:
            return None
        event = quartz.CGEventCreateKeyboardEvent(None, key_code, down)
        if event is not None and flags:
            quartz.CGEventSetFlags(event, flags)
        return event

    def key(self, key: str, down: bool | None = None) -> ActResult:
        combo = parse_key_combo(key)
        if combo is None:
            log_failure(logger, "key", "unknown key name", key=key)
            return ActResult(ok=False, error=f"unknown key: {key}")
        phases = (True, False) if down is None else (down,)
        for phase_down in phases:
            result = self._post(
                "key", self._keyboard_event(combo.key_code, phase_down, combo.flags), key=key
            )
            if not result.ok:
                return result
        return ActResult(ok=True)

    def _unicode_event(self, character: str, down: bool) -> Any:
        quartz = self._quartz()
        if quartz is None:
            return None
        event = quartz.CGEventCreateKeyboardEvent(None, UNICODE_ONLY_KEY_CODE, down)
        if event is not None:
            quartz.CGEventKeyboardSetUnicodeString(event, len(character), character)
        return event

    def type_text(self, text: str) -> ActResult:
        for character in text:
            for down in (True, False):
                result = self._post(
                    "type_text", self._unicode_event(character, down), text_length=len(text)
                )
                if not result.ok:
                    return result
        return ActResult(ok=True)

    def scroll(self, x: float, y: float, lines: int) -> ActResult:
        move_result = self.move(x, y)
        if not move_result.ok:
            return move_result
        quartz = self._quartz()
        if quartz is None:
            return self._unavailable("scroll", x=x, y=y, lines=lines)
        event = quartz.CGEventCreateScrollWheelEvent(None, quartz.kCGScrollEventUnitLine, 1, lines)
        return self._post("scroll", event, x=x, y=y, lines=lines)
