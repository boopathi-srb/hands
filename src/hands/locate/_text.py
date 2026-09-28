"""Text normalization shared by every matcher in this package.

All matching in `hands.locate` is case-insensitive and whitespace-collapsed unless a caller
explicitly asks for case sensitivity (TextVisible.case_sensitive).
"""

from __future__ import annotations

from hands.core.observation import Node

_LABEL_TRAILING_CHARACTERS = " :*\t"


def collapse_whitespace(text: str | None) -> str:
    """Collapse every run of whitespace to one space and strip the ends. None becomes ''."""
    if not text:
        return ""
    return " ".join(text.split())


def normalize_text(text: str | None) -> str:
    """Whitespace-collapsed, case-folded text used for case-insensitive comparisons."""
    return collapse_whitespace(text).casefold()


def normalize_label(text: str | None) -> str:
    """Like normalize_text, but also drops the trailing ':' and '*' that legacy forms put on labels."""
    return normalize_text(text).rstrip(_LABEL_TRAILING_CHARACTERS)


def display_text(node: Node) -> str:
    """What a person would read for this node: its accessible name, falling back to visible text."""
    return collapse_whitespace(node.name) or collapse_whitespace(node.text)


def node_matches_text_exactly(node: Node, wanted_text: str) -> bool:
    """True when the node's name or visible text equals `wanted_text` after normalization."""
    normalized_wanted = normalize_text(wanted_text)
    if not normalized_wanted:
        return False
    return normalized_wanted in (normalize_text(node.name), normalize_text(node.text))


def node_contains_text(node: Node, wanted_text: str) -> bool:
    """True when the node's name or visible text contains `wanted_text` after normalization."""
    normalized_wanted = normalize_text(wanted_text)
    if not normalized_wanted:
        return False
    return normalized_wanted in normalize_text(node.name) or normalized_wanted in normalize_text(
        node.text
    )
