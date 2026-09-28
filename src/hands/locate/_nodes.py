"""Node classification and the two geometric lookups shared by resolve and candidates:
finding anchor nodes by text, and finding the adjacent label text of a form field."""

from __future__ import annotations

from collections.abc import Sequence

from hands.core.observation import Node, Rect
from hands.locate._geometry import (
    gap_above,
    gap_to_the_left,
    horizontal_overlap,
    is_same_row,
    same_container,
)
from hands.locate._text import (
    collapse_whitespace,
    display_text,
    node_contains_text,
    node_matches_text_exactly,
)

INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "link",
        "textbox",
        "searchbox",
        "combobox",
        "listbox",
        "checkbox",
        "radio",
        "menuitem",
        "option",
        "tab",
        "spinbutton",
        "slider",
        "switch",
    }
)

FORM_FIELD_ROLES = frozenset(
    {
        "textbox",
        "searchbox",
        "combobox",
        "listbox",
        "checkbox",
        "radio",
        "spinbutton",
        "slider",
        "switch",
    }
)

CONTAINER_ROLES = frozenset(
    {
        "table",
        "grid",
        "row",
        "rowgroup",
        "list",
        "dialog",
        "alertdialog",
        "document",
        "form",
        "group",
        "region",
        "main",
        "navigation",
        "frame",
        "window",
        "pane",
    }
)

MAX_LEFT_LABEL_GAP_PX = 400.0
MIN_ABOVE_LABEL_GAP_ALLOWANCE_PX = 30.0
ABOVE_TIE_BREAK_PX = 0.001


def role_is(node: Node, role: str | None) -> bool:
    """True when `role` is None (no filter) or equals the node's role, case-insensitively."""
    return role is None or node.role.casefold() == role.casefold()


def is_interactive(node: Node) -> bool:
    return node.role.casefold() in INTERACTIVE_ROLES


def is_form_field(node: Node) -> bool:
    return node.role.casefold() in FORM_FIELD_ROLES


def is_container(node: Node) -> bool:
    return node.role.casefold() in CONTAINER_ROLES


def is_text_node(node: Node) -> bool:
    """A readable, non-interactive leaf such as a table cell, static text, or heading."""
    return not is_interactive(node) and not is_container(node) and bool(display_text(node))


def find_anchor_nodes(anchor_text: str, nodes: Sequence[Node]) -> list[Node]:
    """Non-container nodes whose name or text equals the anchor; if none, those that contain it."""
    leaf_nodes = [node for node in nodes if not is_container(node)]
    exact_matches = [node for node in leaf_nodes if node_matches_text_exactly(node, anchor_text)]
    if exact_matches:
        return exact_matches
    return [node for node in leaf_nodes if node_contains_text(node, anchor_text)]


def find_enclosing_anchor_nodes(anchor_text: str, nodes: Sequence[Node]) -> list[Node]:
    """Any node (containers included) whose name or text contains the anchor, for 'inside' relations."""
    return [node for node in nodes if node_contains_text(node, anchor_text)]


def adjacent_label_node(target: Node, nodes: Sequence[Node]) -> Node | None:
    """The nearest text node to the left in the same row, else directly above, in the same container.

    Left wins over above at equal distance because legacy table forms put labels in the previous cell.
    """
    if target.bounds is None:
        return None
    left_neighbours = _text_neighbours_left(target, target.bounds, nodes)
    above_neighbours = _text_neighbours_above(target, target.bounds, nodes)
    ranked = sorted(left_neighbours + above_neighbours, key=lambda pair: pair[0])
    return ranked[0][1] if ranked else None


def adjacent_label_text(target: Node, nodes: Sequence[Node]) -> str:
    label_node = adjacent_label_node(target, nodes)
    return display_text(label_node) if label_node is not None else ""


def explicit_or_adjacent_label(target: Node, nodes: Sequence[Node]) -> str:
    """The node's own label when set, else the adjacent label text ('' when neither exists)."""
    return collapse_whitespace(target.label) or adjacent_label_text(target, nodes)


def _label_eligible(target: Node, other: Node) -> bool:
    return (
        other.ref != target.ref
        and other.bounds is not None
        and same_container(target, other)
        and is_text_node(other)
    )


def _text_neighbours_left(
    target: Node, target_bounds: Rect, nodes: Sequence[Node]
) -> list[tuple[float, Node]]:
    neighbours: list[tuple[float, Node]] = []
    for other in nodes:
        if not _label_eligible(target, other) or other.bounds is None:
            continue
        gap = gap_to_the_left(other.bounds, target_bounds)
        if 0 <= gap <= MAX_LEFT_LABEL_GAP_PX and is_same_row(target_bounds, other.bounds):
            neighbours.append((gap, other))
    return neighbours


def _text_neighbours_above(
    target: Node, target_bounds: Rect, nodes: Sequence[Node]
) -> list[tuple[float, Node]]:
    max_gap = max(2 * target_bounds.height, MIN_ABOVE_LABEL_GAP_ALLOWANCE_PX)
    neighbours: list[tuple[float, Node]] = []
    for other in nodes:
        if not _label_eligible(target, other) or other.bounds is None:
            continue
        gap = gap_above(other.bounds, target_bounds)
        if 0 <= gap <= max_gap and horizontal_overlap(target_bounds, other.bounds) > 0:
            neighbours.append((gap + ABOVE_TIE_BREAK_PX, other))
    return neighbours
