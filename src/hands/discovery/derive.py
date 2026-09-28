"""Pure heuristics the recorder uses to generalize one discovery run into a reusable capability.

- parameterize_text:     literal run values of declared inputs become `{{input}}` placeholders
- canonical_path:        URL path with input values -> ':input', tenant id -> ':tenant', ids -> ':id'
- derive_postcondition:  location change, else a distinctive new text, else nothing
- infer_value_type:      decimal / integer / date / string from an extracted sample
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

from hands.core.artifact import ValueType
from hands.core.conditions import Condition, LocationMatches, TextVisible
from hands.core.observation import Location, Node, Observation
from hands.discovery.render import (
    CONTAINER_ROLES,
    INTERACTIVE_ROLES,
    SECRET_MASK,
    node_display_name,
)
from hands.locate import evaluate, is_volatile_text

MIN_ANCHOR_CHARS = 3
MAX_ANCHOR_CHARS = 60
HEADING_ROLES = frozenset({"heading", "title"})
TEXT_ROLES = frozenset({"text", "statictext", "paragraph", "label", "cell", "columnheader", "caption"})

_DECIMAL = re.compile(
    r"^[-+]?[$€£¥]?\s?(\d{1,3}(,\d{3})+(\.\d+)?|\d+\.\d+|\d{1,3}(,\d{3})+)$"
)
_INTEGER = re.compile(r"^[-+]?(0|[1-9]\d*)$")
_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})$")
_PLACEHOLDER_OPEN = "{{"


# ---------------------------------------------------------------- parameterization


def _placeholder(name: str) -> str:
    return f"{{{{{name}}}}}"


def _values_longest_first(input_values: Mapping[str, str]) -> list[tuple[str, str]]:
    usable = [(name, value) for name, value in input_values.items() if value and value.strip()]
    return sorted(usable, key=lambda pair: len(pair[1]), reverse=True)


def parameterize_text(text: str, input_values: Mapping[str, str]) -> str:
    """Exact input value -> placeholder; in URL-like text, path segments equal to a value too."""
    stripped = text.strip()
    for name, value in _values_longest_first(input_values):
        if stripped == value.strip():
            return _placeholder(name)
    if "/" in text:
        return _parameterize_url(text, input_values)
    return text


def _parameterize_url(url: str, input_values: Mapping[str, str]) -> str:
    parts = urlsplit(url)
    segments = [
        _segment_placeholder(segment, input_values) or segment for segment in parts.path.split("/")
    ]
    return urlunsplit(parts._replace(path="/".join(segments)))


def _segment_placeholder(segment: str, input_values: Mapping[str, str]) -> str | None:
    for name, value in _values_longest_first(input_values):
        if segment == value.strip():
            return _placeholder(name)
    return None


def canonical_path(
    location: Location, input_values: Mapping[str, str], tenant_id: str | None = None
) -> str | None:
    """Location pattern for a URL location; None for desktop windows (titles are not paths)."""
    if location.kind != "url":
        return None
    path = urlsplit(location.value).path or "/"
    return "/".join(_canonical_segment(segment, input_values, tenant_id) for segment in path.split("/"))


def _canonical_segment(segment: str, input_values: Mapping[str, str], tenant_id: str | None) -> str:
    if not segment:
        return segment
    for name, value in _values_longest_first(input_values):
        if segment == value.strip():
            return f":{name}"
    if tenant_id and segment == tenant_id:
        return ":tenant"
    if is_volatile_text(segment):
        return ":id"
    return segment


# ---------------------------------------------------------------- postconditions


def derive_postcondition(
    before: Observation,
    after: Observation | None,
    input_values: Mapping[str, str],
    tenant_id: str | None = None,
) -> Condition | None:
    """What proves the action worked: the location moved, else a new distinctive text, else None."""
    if after is None:
        return None
    before_path = canonical_path(before.location, input_values, tenant_id)
    after_path = canonical_path(after.location, input_values, tenant_id)
    if after_path is not None and after_path != before_path:
        return LocationMatches(pattern=after_path)
    new_text = distinctive_new_text(before, after, input_values)
    return TextVisible(pattern=new_text) if new_text else None


def distinctive_new_text(
    before: Observation, after: Observation, input_values: Mapping[str, str]
) -> str | None:
    """Best short label that is visible after and not before. Headings first, never data or inputs."""
    ranked: list[tuple[int, int, str]] = []
    for order, node in enumerate(after.nodes):
        text = node_display_name(node)
        rank = _anchor_rank(node)
        if rank is None or not is_stable_label(text, input_values):
            continue
        ranked.append((rank, order, text))
    for _rank, _order, text in sorted(ranked):
        condition = TextVisible(pattern=text)
        if not evaluate(condition, before).met and evaluate(condition, after).met:
            return text
    return None


def is_stable_label(text: str, input_values: Mapping[str, str]) -> bool:
    """UI chrome rather than data: short, not volatile, no input value, no mask, no placeholder."""
    if not MIN_ANCHOR_CHARS <= len(text) <= MAX_ANCHOR_CHARS:
        return False
    if is_volatile_text(text) or SECRET_MASK in text or _PLACEHOLDER_OPEN in text:
        return False
    return not any(value.strip() and value.strip() in text for value in input_values.values())


def _anchor_rank(node: Node) -> int | None:
    role = node.role.casefold()
    if role in HEADING_ROLES:
        return 0
    if role in TEXT_ROLES:
        return 1
    if role in INTERACTIVE_ROLES or role in CONTAINER_ROLES:
        return None
    return 2


# ---------------------------------------------------------------- outputs


def infer_value_type(sample: str) -> ValueType:
    """decimal for amounts, integer for plain whole numbers, date for common date forms, else string."""
    stripped = sample.strip()
    if _DECIMAL.match(stripped):
        return "decimal"
    if _INTEGER.match(stripped):
        return "integer"
    if _DATE.match(stripped):
        return "date"
    return "string"


def uses_any_placeholder(text: str | None, names: Sequence[str]) -> bool:
    return bool(text) and any(_placeholder(name) in (text or "") for name in names)
