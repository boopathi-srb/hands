"""Turn extracted nodes (with geometry attached) into their final form. Pure.

Order matters: merge inline text runs -> resolve text and names -> structural paths -> labels.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from hands.core.observation import Rect
from hands.surfaces import collapse_whitespace
from hands.surfaces.browser.ax_extract import ExtractedNode, TextPart
from hands.surfaces.browser.geometry import (
    LEFT_OF_TOLERANCE_PX,
    can_merge_runs,
    horizontal_gap,
    in_same_row,
    join_fragments,
    union_rects,
)
from hands.surfaces.browser.roles import (
    LABEL_SOURCE_ROLES,
    LABELABLE_ROLES,
    NAME_FROM_OWN_TEXT_ROLES,
    is_text_sink,
)


def assemble_nodes(extracted: Sequence[ExtractedNode]) -> list[ExtractedNode]:
    """Run every finishing pass and return the surviving nodes in document order."""
    survivors = merge_text_runs(extracted)
    resolve_texts(survivors)
    assign_structural_paths(survivors)
    infer_labels(survivors)
    return survivors


# ---------------------------------------------------------------- text runs


def merge_text_runs(nodes: Sequence[ExtractedNode]) -> list[ExtractedNode]:
    """Glue adjacent inline runs ('No member found for number ' + '99999' + '.') into one text node."""
    survivors: list[ExtractedNode] = []
    for node in nodes:
        target = surviving_node(node.merge_candidate) if node.is_text_run else None
        if target is not None and can_merge_runs(last_line_of(target), first_line_of(node)):
            target.text_parts.extend(node.text_parts)
            node.merged_into = target
            continue
        survivors.append(node)
    return survivors


def surviving_node(node: ExtractedNode | None) -> ExtractedNode | None:
    while node is not None and node.merged_into is not None:
        node = node.merged_into
    return node


def first_line_of(node: ExtractedNode) -> Rect | None:
    visible_parts = _visible_parts(node.text_parts)
    return visible_parts[0].line_boxes[0] if visible_parts else None


def last_line_of(node: ExtractedNode) -> Rect | None:
    visible_parts = _visible_parts(node.text_parts)
    return visible_parts[-1].line_boxes[-1] if visible_parts else None


def text_bounds(node: ExtractedNode) -> Rect | None:
    """Union of the node's own text line boxes; falls back to the node box."""
    line_boxes = [box for part in node.text_parts for box in part.line_boxes]
    return union_rects(line_boxes) or node.bounds


def _visible_parts(parts: Sequence[TextPart]) -> list[TextPart]:
    return [part for part in parts if part.text.strip() and part.line_boxes]


# ---------------------------------------------------------------- text and names


def resolve_texts(nodes: Sequence[ExtractedNode]) -> None:
    for node in nodes:
        node.text = join_fragments(
            [(part.text, _first_box(part), _last_box(part)) for part in node.text_parts]
        )
        node.name = resolved_name(node)
        if node.is_text_run:
            node.bounds = text_bounds(node)


def resolved_name(node: ExtractedNode) -> str:
    if node.is_text_run or node.role in NAME_FROM_OWN_TEXT_ROLES:
        return node.text
    chrome_name = collapse_whitespace(node.chrome_name)
    if chrome_name:
        return chrome_name
    return node.text if is_text_sink(node.role) else ""


def _first_box(part: TextPart) -> Rect | None:
    return part.line_boxes[0] if part.line_boxes else None


def _last_box(part: TextPart) -> Rect | None:
    return part.line_boxes[-1] if part.line_boxes else None


# ---------------------------------------------------------------- structural paths


def assign_structural_paths(nodes: Sequence[ExtractedNode]) -> None:
    """'table[1]/row[3]/cell[2]': 1-based index among kept siblings with the same role, per frame."""
    sibling_counts: dict[tuple[str, int, str], int] = {}
    for node in nodes:
        parent = node.parent
        count_key = (node.frame_id, id(parent) if parent is not None else 0, node.role)
        position = sibling_counts.get(count_key, 0) + 1
        sibling_counts[count_key] = position
        segment = f"{node.role}[{position}]"
        node.structural_path = f"{parent.structural_path}/{segment}" if parent is not None else segment


# ---------------------------------------------------------------- labels


def infer_labels(nodes: Sequence[ExtractedNode]) -> None:
    """Label = <label>/aria-labelledby name, else nearest text to the left in the same row."""
    label_sources = [node for node in nodes if node.role in LABEL_SOURCE_ROLES and node.text]
    for control in nodes:
        if control.role in LABELABLE_ROLES:
            control.label = label_for(control, label_sources)


def label_for(control: ExtractedNode, label_sources: Sequence[ExtractedNode]) -> str | None:
    if control.name_from_label and control.name:
        return control.name
    if control.bounds is None:
        return None
    nearest_text, nearest_gap = None, math.inf
    for source in label_sources:
        source_box = text_bounds(source)
        if source.frame_id != control.frame_id or source_box is None:
            continue
        gap = horizontal_gap(source_box, control.bounds)
        if in_same_row(source_box, control.bounds) and -LEFT_OF_TOLERANCE_PX <= gap < nearest_gap:
            nearest_text, nearest_gap = source.text, gap
    return nearest_text
