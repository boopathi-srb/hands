"""Helpers shared by all surfaces: fingerprint, whitespace collapsing, typed-text de-duplication."""

from __future__ import annotations

from hands.core.observation import Node
from hands.core.ports import KeyEvent
from hands.surfaces import TypedTextTracker, collapse_whitespace, structural_fingerprint


def _node(role: str, path: str, container: tuple[str, ...] = (), **extra: object) -> Node:
    return Node(ref="n1", role=role, structural_path=path, container_path=container, **extra)  # type: ignore[arg-type]


def test_fingerprint_of_empty_list_is_stable() -> None:
    assert structural_fingerprint([]) == structural_fingerprint([])
    assert len(structural_fingerprint([])) == 16


def test_fingerprint_ignores_order_text_values_refs_and_bounds() -> None:
    first = [_node("cell", "table[1]/row[1]/cell[1]", text="a"), _node("button", "button[1]", name="Go")]
    second = [_node("button", "button[1]", name="Submit", value="x"), _node("cell", "table[1]/row[1]/cell[1]")]
    assert structural_fingerprint(first) == structural_fingerprint(second)


def test_fingerprint_changes_with_structure_role_or_container() -> None:
    base = structural_fingerprint([_node("cell", "table[1]/row[1]/cell[1]")])
    assert structural_fingerprint([_node("cell", "table[1]/row[2]/cell[1]")]) != base
    assert structural_fingerprint([_node("columnheader", "table[1]/row[1]/cell[1]")]) != base
    assert structural_fingerprint([_node("cell", "table[1]/row[1]/cell[1]", ("frame:content",))]) != base


def test_collapse_whitespace_edge_cases() -> None:
    assert collapse_whitespace(None) == ""
    assert collapse_whitespace("") == ""
    assert collapse_whitespace("  \n\t ") == ""
    assert collapse_whitespace("  Member \n  Number  ") == "Member Number"


def test_typed_text_down_up_style_types_on_down() -> None:
    tracker = TypedTextTracker()
    assert tracker.text_for_down(KeyEvent(type="down", key="a"), command_modifier=False) == "a"
    tracker.on_up(KeyEvent(type="up", key="a"))


def test_typed_text_down_char_style_skips_duplicate_char() -> None:
    tracker = TypedTextTracker()
    assert tracker.text_for_down(KeyEvent(type="down", key="a"), command_modifier=False) == "a"
    assert tracker.text_for_char(KeyEvent(type="char", key="a", text="a"), command_modifier=False) is None
    # a second, different char (e.g. from an IME) is still typed
    assert tracker.text_for_char(KeyEvent(type="char", key="b", text="b"), command_modifier=False) == "b"


def test_typed_text_char_only_style() -> None:
    tracker = TypedTextTracker()
    assert tracker.text_for_char(KeyEvent(type="char", key="x", text="x"), command_modifier=False) == "x"
    assert tracker.text_for_char(KeyEvent(type="char", key="y"), command_modifier=False) == "y"


def test_typed_text_ignores_named_keys_control_chars_and_chords() -> None:
    tracker = TypedTextTracker()
    assert tracker.text_for_down(KeyEvent(type="down", key="Enter"), command_modifier=False) is None
    assert tracker.text_for_down(KeyEvent(type="down", key="Enter", text="\r"), command_modifier=False) is None
    assert tracker.text_for_char(KeyEvent(type="char", key="Enter", text="\r"), command_modifier=False) is None
    assert tracker.text_for_down(KeyEvent(type="down", key="a"), command_modifier=True) is None
    assert tracker.text_for_char(KeyEvent(type="char", key="a", text="a"), command_modifier=True) is None
    assert tracker.text_for_char(KeyEvent(type="char", key="", text=""), command_modifier=False) is None


def test_typed_text_explicit_text_wins_over_key() -> None:
    tracker = TypedTextTracker()
    assert tracker.text_for_down(KeyEvent(type="down", key="a", text="A"), command_modifier=False) == "A"
