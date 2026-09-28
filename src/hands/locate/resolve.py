"""Resolve a TargetSpec against an Observation. Pure and surface-agnostic.

Candidates are tried in order; the first that yields at least one match wins and its index is the
`rank` (rank > 0 is a drift signal for replay). Matching is case-insensitive and whitespace-collapsed.

Candidate semantics
- role_name: node role equals `role`; node name (falling back to visible text when the name is empty)
  equals `name` when `exact`, else contains it.
- label: node.label equals `label`, or the nearest text node to the left (same row) or directly above,
  in the same container, equals it. Trailing ':' and '*' are ignored. With no `role`, only form fields
  (textbox, combobox, checkbox, ...) are eligible, so the label cell itself or its wrapping cell never match.
- text_anchor: anchor nodes are non-container nodes whose name/text equals `anchor_text` (falling back
  to contains). For 'inside' any node whose text contains the anchor is an anchor (rows aggregate their
  cells' text). Related nodes must share the anchor's container_path. The `ordinal`-th related node in
  reading order is chosen; an ordinal beyond the matches means this candidate does not match.
- structural: exact container_path and structural_path.
- visual_anchor: point = anchor center + (dx, dy); `node` is the smallest node in the anchor's container
  whose bounds contain the point, if any.

Ambiguity
- For text_anchor the ordinal is the declared disambiguator, so `ambiguous` is True only when the anchor
  text itself matched more than one anchor that produced related nodes.
- For every other kind, `ambiguous` is True when more than one node matched; the first in reading order
  is returned.
Disabled nodes still match; callers can inspect `Resolution.node.enabled`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal

from pydantic import BaseModel

from hands.core.actions import Point
from hands.core.observation import Node, Observation, Rect
from hands.core.targets import (
    Candidate,
    CandidateKind,
    LabelCandidate,
    RoleNameCandidate,
    StructuralCandidate,
    TargetSpec,
    TextAnchorCandidate,
    VisualAnchorCandidate,
)
from hands.locate._geometry import (
    area,
    center_point,
    contains_point,
    is_below,
    is_inside,
    is_right_of,
    is_same_row,
    reading_order,
    same_container,
)
from hands.locate._nodes import (
    explicit_or_adjacent_label,
    find_anchor_nodes,
    find_enclosing_anchor_nodes,
    is_form_field,
    role_is,
)
from hands.locate._text import display_text, normalize_label, normalize_text

Relation = Literal["right_of", "below", "same_row", "inside"]
RelationTest = Callable[[Rect, Rect], bool]

_RELATION_TESTS: dict[Relation, RelationTest] = {
    "right_of": is_right_of,
    "below": is_below,
    "same_row": is_same_row,
    "inside": is_inside,
}


class Resolution(BaseModel):
    """Which node (and/or point) a TargetSpec resolved to, and how."""

    node: Node | None
    point: Point | None
    rank: int
    candidate_kind: CandidateKind
    ambiguous: bool
    match_count: int


class CandidateMatch(BaseModel):
    """The outcome of one candidate before it is tagged with its rank."""

    node: Node | None
    point: Point | None
    ambiguous: bool
    match_count: int


def resolve_target(spec: TargetSpec, observation: Observation) -> Resolution | None:
    """Try candidates in order; return the first that matches, or None when none do."""
    for rank, candidate in enumerate(spec.candidates):
        candidate_match = resolve_candidate(candidate, observation)
        if candidate_match is not None:
            return Resolution(
                node=candidate_match.node,
                point=candidate_match.point,
                rank=rank,
                candidate_kind=candidate.kind,
                ambiguous=candidate_match.ambiguous,
                match_count=candidate_match.match_count,
            )
    return None


def resolve_candidate(candidate: Candidate, observation: Observation) -> CandidateMatch | None:
    """Resolve one candidate in isolation."""
    nodes = observation.nodes
    if isinstance(candidate, RoleNameCandidate):
        return _pick_first(_match_role_name(candidate, nodes))
    if isinstance(candidate, LabelCandidate):
        return _pick_first(_match_label(candidate, nodes))
    if isinstance(candidate, TextAnchorCandidate):
        return _resolve_text_anchor(candidate, nodes)
    if isinstance(candidate, StructuralCandidate):
        return _pick_first(_match_structural(candidate, nodes))
    return _resolve_visual_anchor(candidate, nodes)


def related_nodes(
    anchor: Node, relation: Relation, role: str | None, nodes: Sequence[Node]
) -> list[Node]:
    """Nodes in the anchor's container standing in `relation` to it, in reading order."""
    relation_test = _RELATION_TESTS[relation]
    anchor_bounds = anchor.bounds
    if anchor_bounds is None:
        return []
    related = [
        node
        for node in nodes
        if node.ref != anchor.ref
        and node.bounds is not None
        and same_container(anchor, node)
        and role_is(node, role)
        and relation_test(anchor_bounds, node.bounds)
    ]
    return reading_order(related)


def text_anchor_matches(
    candidate: TextAnchorCandidate, nodes: Sequence[Node]
) -> tuple[list[Node], int]:
    """All related nodes across every anchor (deduplicated, reading order) and how many anchors contributed."""
    contributions = _anchor_contributions(candidate, nodes)
    if candidate.relation == "inside":
        contributions = _innermost_contributions(contributions)
    matched_by_ref: dict[str, Node] = {}
    for _anchor, related in contributions:
        for node in related:
            matched_by_ref.setdefault(node.ref, node)
    return reading_order(list(matched_by_ref.values())), len(contributions)


def _anchor_contributions(
    candidate: TextAnchorCandidate, nodes: Sequence[Node]
) -> list[tuple[Node, list[Node]]]:
    contributions: list[tuple[Node, list[Node]]] = []
    for anchor in _anchors_for(candidate, nodes):
        related = related_nodes(anchor, candidate.relation, candidate.role, nodes)
        if related:
            contributions.append((anchor, related))
    return contributions


def _innermost_contributions(
    contributions: list[tuple[Node, list[Node]]],
) -> list[tuple[Node, list[Node]]]:
    """For 'inside', drop anchors that enclose another contributing anchor (a table enclosing the row)."""
    anchors = [anchor for anchor, _related in contributions]
    return [
        (anchor, related)
        for anchor, related in contributions
        if not any(_strictly_encloses(anchor, other) for other in anchors)
    ]


def _strictly_encloses(outer: Node, inner: Node) -> bool:
    if outer.ref == inner.ref or outer.bounds is None or inner.bounds is None:
        return False
    return is_inside(outer.bounds, inner.bounds)


def _anchors_for(candidate: TextAnchorCandidate, nodes: Sequence[Node]) -> list[Node]:
    if candidate.relation == "inside":
        return find_enclosing_anchor_nodes(candidate.anchor_text, nodes)
    return find_anchor_nodes(candidate.anchor_text, nodes)


def _match_role_name(candidate: RoleNameCandidate, nodes: Sequence[Node]) -> list[Node]:
    wanted_name = normalize_text(candidate.name)
    if not wanted_name:
        return []

    def name_matches(node: Node) -> bool:
        node_name = normalize_text(display_text(node))
        return node_name == wanted_name if candidate.exact else wanted_name in node_name

    return [node for node in nodes if role_is(node, candidate.role) and name_matches(node)]


def _match_label(candidate: LabelCandidate, nodes: Sequence[Node]) -> list[Node]:
    wanted_label = normalize_label(candidate.label)
    if not wanted_label:
        return []
    eligible = [node for node in nodes if _label_role_eligible(node, candidate.role)]
    return [
        node
        for node in eligible
        if normalize_label(explicit_or_adjacent_label(node, nodes)) == wanted_label
    ]


def _label_role_eligible(node: Node, role: str | None) -> bool:
    return is_form_field(node) if role is None else role_is(node, role)


def _match_structural(candidate: StructuralCandidate, nodes: Sequence[Node]) -> list[Node]:
    if not candidate.structural_path:
        return []
    return [
        node
        for node in nodes
        if node.container_path == tuple(candidate.container_path)
        and node.structural_path == candidate.structural_path
    ]


def _resolve_text_anchor(
    candidate: TextAnchorCandidate, nodes: Sequence[Node]
) -> CandidateMatch | None:
    matches, contributing_anchor_count = text_anchor_matches(candidate, nodes)
    if candidate.ordinal >= len(matches):
        return None
    chosen = matches[candidate.ordinal]
    return CandidateMatch(
        node=chosen,
        point=_node_center(chosen),
        ambiguous=contributing_anchor_count > 1,
        match_count=len(matches),
    )


def _resolve_visual_anchor(
    candidate: VisualAnchorCandidate, nodes: Sequence[Node]
) -> CandidateMatch | None:
    anchors = reading_order(
        [node for node in find_anchor_nodes(candidate.anchor_text, nodes) if node.bounds]
    )
    if not anchors:
        return None
    anchor = anchors[0]
    if anchor.bounds is None:
        return None
    anchor_center = center_point(anchor.bounds)
    target_point = Point(x=anchor_center.x + candidate.dx, y=anchor_center.y + candidate.dy)
    return CandidateMatch(
        node=node_at_point(target_point, anchor.container_path, nodes),
        point=target_point,
        ambiguous=len(anchors) > 1,
        match_count=len(anchors),
    )


def node_at_point(
    point: Point, container_path: tuple[str, ...], nodes: Sequence[Node]
) -> Node | None:
    """The smallest node in `container_path` whose bounds contain `point` (hit test)."""
    hits = [
        node
        for node in nodes
        if node.bounds is not None
        and node.container_path == container_path
        and contains_point(node.bounds, point)
    ]
    if not hits:
        return None
    return min(hits, key=lambda node: area(node.bounds) if node.bounds is not None else 0.0)


def _pick_first(matches: list[Node]) -> CandidateMatch | None:
    if not matches:
        return None
    ordered = reading_order(matches)
    chosen = ordered[0]
    return CandidateMatch(
        node=chosen,
        point=_node_center(chosen),
        ambiguous=len(ordered) > 1,
        match_count=len(ordered),
    )


def _node_center(node: Node) -> Point | None:
    return center_point(node.bounds) if node.bounds is not None else None
