"""Geometry helpers over page-level rectangles. Pure.

CDP `DOM.getBoxModel` / `DOM.getContentQuads` already return coordinates relative to the main frame's
viewport, including the offsets of every (same-process) frame and iframe above the node, so nothing
here adds frame offsets. That is verified by the nested-frameset integration test.
"""

from __future__ import annotations

from collections.abc import Sequence

from hands.core.observation import Rect
from hands.surfaces import collapse_whitespace

TOUCHING_GAP_PX = 1.5  # runs closer than this are glued with no space ('99999' + '.')
SAME_LINE_MAX_GAP_PX = 12.0  # runs further apart on one line are separate texts
LEFT_OF_TOLERANCE_PX = 2.0


def quad_to_rect(quad: Sequence[float]) -> Rect | None:
    """CDP quad [x1, y1, ..., x4, y4] -> axis-aligned Rect; None for malformed quads."""
    if len(quad) != 8:
        return None
    xs, ys = quad[0::2], quad[1::2]
    return Rect(x=min(xs), y=min(ys), width=max(xs) - min(xs), height=max(ys) - min(ys))


def union_rects(rects: Sequence[Rect]) -> Rect | None:
    if not rects:
        return None
    left = min(rect.x for rect in rects)
    top = min(rect.y for rect in rects)
    right = max(rect.x + rect.width for rect in rects)
    bottom = max(rect.y + rect.height for rect in rects)
    return Rect(x=left, y=top, width=right - left, height=bottom - top)


def on_same_line(first: Rect, second: Rect) -> bool:
    """Vertical overlap of at least half the shorter box."""
    overlap = min(first.y + first.height, second.y + second.height) - max(first.y, second.y)
    shorter = min(first.height, second.height)
    return shorter > 0 and overlap >= shorter / 2


def in_same_row(first: Rect, second: Rect) -> bool:
    """Vertical centers within half the taller box of each other (table-row alignment)."""
    return abs(first.center_y - second.center_y) <= max(first.height, second.height) / 2


def horizontal_gap(left_box: Rect, right_box: Rect) -> float:
    return right_box.x - (left_box.x + left_box.width)


def contains_point(rect: Rect, x: float, y: float) -> bool:
    return rect.x <= x <= rect.x + rect.width and rect.y <= y <= rect.y + rect.height


def text_separator(before: Rect | None, after: Rect | None) -> str:
    """'' when two text fragments touch on one line, else ' '."""
    if before is None or after is None:
        return " "
    touching = on_same_line(before, after) and -TOUCHING_GAP_PX <= horizontal_gap(before, after) <= TOUCHING_GAP_PX
    return "" if touching else " "


def can_merge_runs(before_last_line: Rect | None, after_first_line: Rect | None) -> bool:
    """Two adjacent text runs form one text when they sit on one line, close together."""
    if before_last_line is None or after_first_line is None:
        return False
    gap = horizontal_gap(before_last_line, after_first_line)
    return on_same_line(before_last_line, after_first_line) and -TOUCHING_GAP_PX <= gap <= SAME_LINE_MAX_GAP_PX


def join_fragments(fragments: Sequence[tuple[str, Rect | None, Rect | None]]) -> str:
    """Join (text, first_line_box, last_line_box) fragments into whitespace-collapsed text.

    Fragments that already carry whitespace at the seam, or touch geometrically, are glued directly;
    otherwise a single space separates them (block boundaries, table-cell internals).
    """
    joined = ""
    previous_last_line: Rect | None = None
    for index, (text, first_line, last_line) in enumerate(fragments):
        needs_separator = index > 0 and not (joined[-1:].isspace() or text[:1].isspace())
        if needs_separator:
            joined += text_separator(previous_last_line, first_line)
        joined += text
        previous_last_line = last_line or previous_last_line
    return collapse_whitespace(joined)
