"""Bounds geometry: reading order and spatial relations between nodes in the same container."""

from __future__ import annotations

from collections.abc import Sequence

from hands.core.actions import Point
from hands.core.observation import Node, Rect

EDGE_TOLERANCE_PX = 1.0


def same_container(first: Node, second: Node) -> bool:
    return first.container_path == second.container_path


def center_point(bounds: Rect) -> Point:
    return Point(x=bounds.center_x, y=bounds.center_y)


def area(bounds: Rect) -> float:
    return bounds.width * bounds.height


def contains_point(bounds: Rect, point: Point) -> bool:
    within_x = bounds.x <= point.x <= bounds.x + bounds.width
    within_y = bounds.y <= point.y <= bounds.y + bounds.height
    return within_x and within_y


def is_same_row(anchor: Rect, candidate: Rect) -> bool:
    """Vertical centers within half the anchor height."""
    return abs(candidate.center_y - anchor.center_y) <= anchor.height / 2


def is_right_of(anchor: Rect, candidate: Rect) -> bool:
    starts_after_anchor = candidate.x >= anchor.x + anchor.width - EDGE_TOLERANCE_PX
    return starts_after_anchor and is_same_row(anchor, candidate)


def horizontal_overlap(first: Rect, second: Rect) -> float:
    overlap_start = max(first.x, second.x)
    overlap_end = min(first.x + first.width, second.x + second.width)
    return max(0.0, overlap_end - overlap_start)


def is_below(anchor: Rect, candidate: Rect) -> bool:
    starts_after_anchor = candidate.y >= anchor.y + anchor.height - EDGE_TOLERANCE_PX
    return starts_after_anchor and horizontal_overlap(anchor, candidate) > 0


def is_inside(anchor: Rect, candidate: Rect) -> bool:
    fits_horizontally = (
        anchor.x <= candidate.x and candidate.x + candidate.width <= anchor.x + anchor.width
    )
    fits_vertically = (
        anchor.y <= candidate.y and candidate.y + candidate.height <= anchor.y + anchor.height
    )
    return fits_horizontally and fits_vertically


def gap_to_the_left(anchor: Rect, target: Rect) -> float:
    """Horizontal gap from the anchor's right edge to the target's left edge (negative if overlapping)."""
    return target.x - (anchor.x + anchor.width)


def gap_above(anchor: Rect, target: Rect) -> float:
    """Vertical gap from the anchor's bottom edge to the target's top edge (negative if overlapping)."""
    return target.y - (anchor.y + anchor.height)


def reading_order(nodes: Sequence[Node]) -> list[Node]:
    """Top-to-bottom, left-to-right by bounds. Nodes without bounds follow, in their original order.

    Nodes are grouped into visual lines: a node joins the current line when its vertical center is
    within half of the line's first node height, so cells a pixel apart still read left-to-right.
    """
    positioned = [node for node in nodes if node.bounds is not None]
    unpositioned = [node for node in nodes if node.bounds is None]
    by_vertical_center = sorted(positioned, key=_vertical_center)
    ordered: list[Node] = []
    for line in _group_into_lines(by_vertical_center):
        ordered.extend(sorted(line, key=_left_edge))
    return ordered + unpositioned


def _group_into_lines(nodes_by_center: list[Node]) -> list[list[Node]]:
    lines: list[list[Node]] = []
    for node in nodes_by_center:
        if lines and _belongs_to_line(lines[-1][0], node):
            lines[-1].append(node)
        else:
            lines.append([node])
    return lines


def _belongs_to_line(line_leader: Node, node: Node) -> bool:
    if line_leader.bounds is None or node.bounds is None:
        return False
    return is_same_row(line_leader.bounds, node.bounds)


def _vertical_center(node: Node) -> float:
    return node.bounds.center_y if node.bounds is not None else 0.0


def _left_edge(node: Node) -> float:
    return node.bounds.x if node.bounds is not None else 0.0
