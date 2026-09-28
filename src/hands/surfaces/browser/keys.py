"""Operator input -> CDP `Input.dispatchKeyEvent` / `Input.dispatchMouseEvent` parameters. Pure.

Key events
- 'down' of a printable key inserts its text (CDP keyDown with `text`); the 'char' that a console may
  send right after is de-duplicated by TypedTextTracker, so (down, up), (down, char, up) and (char)
  sequences all type each character exactly once.
- Named keys (Enter, Tab, Backspace, arrows, ...) are sent with their Windows virtual key codes, which
  Chrome needs for editing commands. Enter carries '\\r' so it submits forms like a real key press.
- Modifier keys (Shift, Control, Alt, Meta) are tracked across events and applied as the CDP
  `modifiers` bitmask to later key and mouse events. Ctrl/Meta chords never insert text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hands.core.ports import KeyEvent, PointerEvent
from hands.surfaces import TypedTextTracker

MODIFIER_BITS: dict[str, int] = {"Alt": 1, "Control": 2, "Meta": 4, "Shift": 8}
COMMAND_MODIFIER_MASK = MODIFIER_BITS["Control"] | MODIFIER_BITS["Meta"]
_BUTTON_BITS: dict[str, int] = {"left": 1, "right": 2, "none": 0}


@dataclass(frozen=True)
class KeyDefinition:
    key: str
    code: str
    key_code: int
    text: str | None = None


NAMED_KEYS: dict[str, KeyDefinition] = {
    definition.key: definition
    for definition in (
        KeyDefinition("Enter", "Enter", 13, "\r"),
        KeyDefinition("Tab", "Tab", 9),
        KeyDefinition("Backspace", "Backspace", 8),
        KeyDefinition("Delete", "Delete", 46),
        KeyDefinition("Escape", "Escape", 27),
        KeyDefinition("ArrowLeft", "ArrowLeft", 37),
        KeyDefinition("ArrowUp", "ArrowUp", 38),
        KeyDefinition("ArrowRight", "ArrowRight", 39),
        KeyDefinition("ArrowDown", "ArrowDown", 40),
        KeyDefinition("Home", "Home", 36),
        KeyDefinition("End", "End", 35),
        KeyDefinition("PageUp", "PageUp", 33),
        KeyDefinition("PageDown", "PageDown", 34),
        KeyDefinition("Insert", "Insert", 45),
        KeyDefinition("Shift", "ShiftLeft", 16),
        KeyDefinition("Control", "ControlLeft", 17),
        KeyDefinition("Alt", "AltLeft", 18),
        KeyDefinition("Meta", "MetaLeft", 91),
        KeyDefinition(" ", "Space", 32, " "),
    )
}


def key_definition(key: str) -> KeyDefinition:
    """Definition for a named key or a single character; unknown names get key code 0."""
    named = NAMED_KEYS.get(key)
    if named is not None:
        return named
    if len(key) == 1 and key.isalpha() and key.isascii():
        return KeyDefinition(key, f"Key{key.upper()}", ord(key.upper()), key)
    if len(key) == 1 and key.isdigit():
        return KeyDefinition(key, f"Digit{key}", ord(key), key)
    return KeyDefinition(key, "", 0, key if len(key) == 1 else None)


class KeyTranslator:
    """Stateful KeyEvent -> list of CDP dispatchKeyEvent params (one live view = one translator)."""

    def __init__(self) -> None:
        self._modifiers = 0
        self._typed_text = TypedTextTracker()

    @property
    def modifiers(self) -> int:
        return self._modifiers

    def translate(self, event: KeyEvent) -> list[dict[str, Any]]:
        if event.type == "down":
            return [self._key_down(event)]
        if event.type == "up":
            return [self._key_up(event)]
        return self._char(event)

    def _key_down(self, event: KeyEvent) -> dict[str, Any]:
        self._set_modifier(event.key, pressed=True)
        definition = key_definition(event.key)
        command_chord = bool(self._modifiers & COMMAND_MODIFIER_MASK)
        typed = self._typed_text.text_for_down(event, command_modifier=command_chord)
        named_text = definition.text if event.key in NAMED_KEYS and not command_chord else None
        text = typed or named_text
        params = self._key_params("keyDown" if text else "rawKeyDown", definition)
        if text:
            params.update({"text": text, "unmodifiedText": text})
        return params

    def _key_up(self, event: KeyEvent) -> dict[str, Any]:
        self._typed_text.on_up(event)
        self._set_modifier(event.key, pressed=False)
        return self._key_params("keyUp", key_definition(event.key))

    def _char(self, event: KeyEvent) -> list[dict[str, Any]]:
        command_chord = bool(self._modifiers & COMMAND_MODIFIER_MASK)
        text = self._typed_text.text_for_char(event, command_modifier=command_chord)
        if text is None:
            return []
        return [{"type": "char", "text": text, "unmodifiedText": text, "key": event.key,
                 "modifiers": self._modifiers}]

    def _key_params(self, event_type: str, definition: KeyDefinition) -> dict[str, Any]:
        return {
            "type": event_type,
            "key": definition.key,
            "code": definition.code,
            "windowsVirtualKeyCode": definition.key_code,
            "nativeVirtualKeyCode": definition.key_code,
            "modifiers": self._modifiers,
        }

    def _set_modifier(self, key: str, pressed: bool) -> None:
        bit = MODIFIER_BITS.get(key, 0)
        self._modifiers = self._modifiers | bit if pressed else self._modifiers & ~bit


class PointerTranslator:
    """Stateful PointerEvent -> list of CDP dispatchMouseEvent params. Coordinates are page CSS
    pixels, the same space as Node.bounds (the screencast is captured at viewport scale 1)."""

    def __init__(self) -> None:
        self._pressed_buttons = 0

    def translate(self, event: PointerEvent, modifiers: int = 0) -> list[dict[str, Any]]:
        if event.type == "click":
            pressed = self._button_params("mousePressed", event, modifiers, pressing=True)
            released = self._button_params("mouseReleased", event, modifiers, pressing=False)
            return [self._move_params(event, modifiers), pressed, released]
        if event.type == "down":
            return [self._button_params("mousePressed", event, modifiers, pressing=True)]
        if event.type == "up":
            return [self._button_params("mouseReleased", event, modifiers, pressing=False)]
        if event.type == "wheel":
            return [{"type": "mouseWheel", "x": event.x, "y": event.y, "deltaX": 0, "deltaY": event.delta_y,
                     "modifiers": modifiers}]
        return [self._move_params(event, modifiers)]

    def _move_params(self, event: PointerEvent, modifiers: int) -> dict[str, Any]:
        return {"type": "mouseMoved", "x": event.x, "y": event.y, "button": "none",
                "buttons": self._pressed_buttons, "modifiers": modifiers}

    def _button_params(self, event_type: str, event: PointerEvent, modifiers: int, pressing: bool) -> dict[str, Any]:
        bit = _BUTTON_BITS[event.button]
        self._pressed_buttons = self._pressed_buttons | bit if pressing else self._pressed_buttons & ~bit
        return {"type": event_type, "x": event.x, "y": event.y, "button": event.button, "clickCount": 1,
                "buttons": self._pressed_buttons, "modifiers": modifiers}
