"""Geometric label inference for native forms.

Many native forms (like the legacy web target) place a static text label next to a field with no
programmatic link. When AXTitleUIElement is absent, the nearest static text to the left on the same
line, or directly above, becomes the field's label. Pure function over Nodes, so it is shared logic
with nothing AX-specific in it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from hands.core.observation import Node, Rect

LABELABLE_ROLES = frozenset({"textbox", "combobox", "checkbox", "slider", "spinbutton", "switch"})


@dataclass(frozen=True)
class LabelGeometry:
    """Tolerances in points for adjacency."""

    max_left_gap: float = 250.0
    max_above_gap: float = 40.0
    edge_slack: float = 4.0


def _vertically_aligned(label_bounds: Rect, field_bounds: Rect) -> bool:
    return (
        abs(label_bounds.center_y - field_bounds.center_y)
        <= max(field_bounds.height, label_bounds.height) / 2
    )


def _horizontally_overlapping(label_bounds: Rect, field_bounds: Rect) -> bool:
    return (
        label_bounds.x < field_bounds.x + field_bounds.width
        and field_bounds.x < label_bounds.x + label_bounds.width
    )


def left_gap(label_bounds: Rect, field_bounds: Rect, geometry: LabelGeometry) -> float | None:
    """Distance from a label's right edge to the field's left edge, if the label sits left on the same line."""
    gap = field_bounds.x - (label_bounds.x + label_bounds.width)
    if gap < -geometry.edge_slack or gap > geometry.max_left_gap:
        return None
    return gap if _vertically_aligned(label_bounds, field_bounds) else None


def above_gap(label_bounds: Rect, field_bounds: Rect, geometry: LabelGeometry) -> float | None:
    """Distance from a label's bottom edge to the field's top edge, if the label sits directly above."""
    gap = field_bounds.y - (label_bounds.y + label_bounds.height)
    if gap < -geometry.edge_slack or gap > geometry.max_above_gap:
        return None
    return gap if _horizontally_overlapping(label_bounds, field_bounds) else None


def _nearest_label(field: Node, text_nodes: list[Node], geometry: LabelGeometry) -> str | None:
    if field.bounds is None:
        return None
    field_bounds = field.bounds
    left_candidates = [
        (gap, text_node.text)
        for text_node in text_nodes
        if text_node.bounds is not None
        and (gap := left_gap(text_node.bounds, field_bounds, geometry)) is not None
    ]
    if left_candidates:
        return min(left_candidates, key=lambda candidate: candidate[0])[1]
    above_candidates = [
        (gap, text_node.text)
        for text_node in text_nodes
        if text_node.bounds is not None
        and (gap := above_gap(text_node.bounds, field_bounds, geometry)) is not None
    ]
    if above_candidates:
        return min(above_candidates, key=lambda candidate: candidate[0])[1]
    return None


def assign_geometric_labels(nodes: list[Node], geometry: LabelGeometry | None = None) -> list[Node]:
    """Return nodes with `label` filled for unlabeled form controls from adjacent static text.

    Only text in the same container (window or sheet) is considered. Order is preserved.
    """
    active_geometry = geometry or LabelGeometry()
    text_nodes_by_container: dict[tuple[str, ...], list[Node]] = defaultdict(list)
    for node in nodes:
        if node.role == "text" and node.text:
            text_nodes_by_container[node.container_path].append(node)
    labeled_nodes: list[Node] = []
    for node in nodes:
        if node.role in LABELABLE_ROLES and not node.label:
            inferred_label = _nearest_label(
                node, text_nodes_by_container[node.container_path], active_geometry
            )
            if inferred_label:
                node = node.model_copy(update={"label": inferred_label})
        labeled_nodes.append(node)
    return labeled_nodes
