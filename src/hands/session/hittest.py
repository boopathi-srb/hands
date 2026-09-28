"""Map a screen point to the accessibility node under it, using an Observation's node bounds."""

from __future__ import annotations

from hands.core.observation import Node, Observation, Rect


def rect_contains(bounds: Rect, x: float, y: float) -> bool:
    """True when (x, y) lies inside `bounds` (edges inclusive) and the rect has a positive area."""
    if bounds.width <= 0 or bounds.height <= 0:
        return False
    inside_x = bounds.x <= x <= bounds.x + bounds.width
    inside_y = bounds.y <= y <= bounds.y + bounds.height
    return inside_x and inside_y


def node_at(observation: Observation | None, x: float, y: float) -> Node | None:
    """The innermost (smallest-area) node whose bounds contain the point, or None.

    Ties keep reading order, so the first node listed wins.
    """
    if observation is None:
        return None
    containing = [
        node
        for node in observation.nodes
        if node.bounds is not None and rect_contains(node.bounds, x, y)
    ]
    return min(containing, key=_area, default=None)


def _area(node: Node) -> float:
    bounds = node.bounds
    return 0.0 if bounds is None else bounds.width * bounds.height
