"""Surface adapters: the only place where UI technology leaks.

- `hands.surfaces.fake`            in-memory scripted state machine for tests (no browser, no OS).
- `hands.surfaces.browser`         Playwright + CDP accessibility extraction (the only playwright importer).
- `hands.surfaces.desktop_macos`   macOS AX API surface.

This module holds the few helpers every surface shares, so observations from different surfaces
fingerprint identically. It must stay free of any automation library import.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from hands.core.observation import Node
from hands.core.ports import KeyEvent

FINGERPRINT_LENGTH = 16


def structural_fingerprint(nodes: Sequence[Node]) -> str:
    """Hash of the sorted (container_path, structural_path, role) triples of the given nodes.

    Text, values, refs, and bounds are deliberately excluded, so the fingerprint changes when the
    screen's structure changes (drift) but not when data on it changes.
    """
    structural_keys = sorted(
        "|".join(("/".join(node.container_path), node.structural_path, node.role)) for node in nodes
    )
    digest = hashlib.sha256("\n".join(structural_keys).encode("utf-8")).hexdigest()
    return digest[:FINGERPRINT_LENGTH]


def collapse_whitespace(text: str | None) -> str:
    """Collapse every whitespace run to one space and trim. None becomes ''."""
    if not text:
        return ""
    return " ".join(text.split())


class TypedTextTracker:
    """Decides which injected key events insert text, shared by every live-view transport.

    Operator consoles differ: some send (down, up) per key, some (down, char, up), some only char.
    Printable text is inserted on 'down' and the matching 'char' that follows is skipped, so each
    character is typed exactly once in all three styles. Named keys (Enter, Tab, ...) and control
    characters never produce text here; transports press them as keys instead.
    """

    def __init__(self) -> None:
        self._inserted_by_down: str | None = None

    def text_for_down(self, event: KeyEvent, command_modifier: bool) -> str | None:
        """Text a key-down should insert, or None. Ctrl/Meta chords never insert text."""
        candidate = event.text if event.text is not None else (event.key if len(event.key) == 1 else None)
        text = candidate if _is_printable(candidate) and not command_modifier else None
        self._inserted_by_down = text
        return text

    def text_for_char(self, event: KeyEvent, command_modifier: bool) -> str | None:
        """Text a char event should insert, or None when its key-down already inserted it."""
        candidate = event.text if event.text is not None else event.key
        if command_modifier or not _is_printable(candidate):
            return None
        if candidate == self._inserted_by_down:
            self._inserted_by_down = None
            return None
        return candidate

    def on_up(self, event: KeyEvent) -> None:
        self._inserted_by_down = None


def _is_printable(text: str | None) -> bool:
    return bool(text) and text is not None and text.isprintable()
