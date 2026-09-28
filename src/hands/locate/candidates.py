"""Turn a node the model acted on into a ranked, verified TargetSpec (used by the recorder).

Candidates are emitted in order of robustness: role_name, label, text_anchor, structural, and a final
visual_anchor fallback. Every non-visual candidate is kept only if resolving it on its own against the
same observation returns this exact node without ambiguity, so rank 0 always round-trips.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from typing import Literal

from hands.core.log import get_logger, log_failure
from hands.core.observation import Node, Observation, Rect
from hands.core.targets import (
    Candidate,
    LabelCandidate,
    RoleNameCandidate,
    StructuralCandidate,
    TargetSpec,
    TextAnchorCandidate,
    VisualAnchorCandidate,
)
from hands.locate._geometry import (
    gap_above,
    gap_to_the_left,
    horizontal_overlap,
    is_same_row,
    same_container,
)
from hands.locate._nodes import adjacent_label_text, find_anchor_nodes, is_form_field, is_text_node
from hands.locate._text import collapse_whitespace, display_text
from hands.locate.resolve import resolve_candidate, text_anchor_matches

_logger = get_logger(__name__)

ROLE_NAME_CONFIDENCE = 0.9
LABEL_CONFIDENCE = 0.85
TEXT_ANCHOR_CONFIDENCE = 0.7
STRUCTURAL_CONFIDENCE = 0.5
VISUAL_ANCHOR_CONFIDENCE = 0.3
FALLBACK_CONFIDENCE = 0.05
MIN_CONFIDENCE = 0.05

NAME_FROM_TEXT_PENALTY = 0.05
LONG_NAME_PENALTY = 0.1
LONG_NAME_CHARS = 40
ADJACENT_LABEL_PENALTY = 0.05
ORDINAL_PENALTY = 0.05

DEFAULT_MAX_CANDIDATES = 4

_VOLATILE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\d{4,}"),  # ids, member numbers, reference codes, years
    re.compile(r"\b\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}\b"),  # 09/28/2026, 2026-09-28, 28.09.26
    re.compile(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b",
        re.IGNORECASE,
    ),  # Sep 28
    re.compile(r"\b\d{1,2}:\d{2}\b"),  # times
    re.compile(r"[$€£¥]\s?\d"),  # currency amounts
    re.compile(r"\b\d{1,3}(,\d{3})*\.\d{2}\b"),  # 1,250.00 / 0.00
)

AnchorRelation = Literal["right_of", "below"]
AnchorOffer = tuple[float, Node, AnchorRelation]


# ---------------------------------------------------------------- public API


def is_volatile_text(text: str | None) -> bool:
    """True when text looks like data rather than UI chrome: 4+ digit runs, dates, times, amounts."""
    if not text:
        return False
    return any(pattern.search(text) for pattern in _VOLATILE_PATTERNS)


def generate_candidates(
    node: Node, observation: Observation, max_candidates: int = DEFAULT_MAX_CANDIDATES
) -> list[Candidate]:
    """Ranked candidates that each resolve back to `node`, plus a visual fallback when an anchor exists."""
    if max_candidates < 1:
        log_failure(
            _logger,
            "generate_candidates",
            "max_candidates must be >= 1",
            max_candidates=max_candidates,
        )
        return []
    if observation.node_by_ref(node.ref) != node:
        log_failure(
            _logger, "generate_candidates", "node is not part of the observation", ref=node.ref
        )
        return []
    robust_candidates = _verified_robust_candidates(node, observation)
    visual_candidate = _visual_anchor_candidate(node, observation)
    return _select_within_budget(robust_candidates, visual_candidate, max_candidates)


def build_target_spec(node: Node, observation: Observation, description: str) -> TargetSpec:
    """A TargetSpec for `node`. Falls back to a single low-confidence candidate flagged for review."""
    spec_description = collapse_whitespace(description) or _default_description(node)
    candidates = generate_candidates(node, observation)
    if not candidates:
        log_failure(
            _logger,
            "build_target_spec",
            "no verified candidate; emitting a low-confidence fallback for review",
            ref=node.ref,
            role=node.role,
        )
        candidates = [_fallback_candidate(node)]
    return TargetSpec(description=spec_description, candidates=candidates)


# ---------------------------------------------------------------- selection


def _verified_robust_candidates(node: Node, observation: Observation) -> list[Candidate]:
    builders: list[Callable[[Node, Observation], Candidate | None]] = [
        _role_name_candidate,
        _label_candidate,
        _text_anchor_candidate,
        _structural_candidate,
    ]
    built = [builder(node, observation) for builder in builders]
    return [candidate for candidate in built if candidate is not None]


def _select_within_budget(
    robust_candidates: list[Candidate], visual_candidate: Candidate | None, max_candidates: int
) -> list[Candidate]:
    """Keep the visual fallback last when there is room for it next to at least one robust candidate."""
    if visual_candidate is None:
        return robust_candidates[:max_candidates]
    if not robust_candidates:
        return [visual_candidate]
    if max_candidates == 1:
        return robust_candidates[:1]
    return [*robust_candidates[: max_candidates - 1], visual_candidate]


def resolves_uniquely_to(candidate: Candidate, node: Node, observation: Observation) -> bool:
    """True when the candidate alone resolves to exactly this node, without ambiguity."""
    candidate_match = resolve_candidate(candidate, observation)
    if candidate_match is None or candidate_match.node is None:
        return False
    return candidate_match.node.ref == node.ref and not candidate_match.ambiguous


def _keep_if_unique(candidate: Candidate, node: Node, observation: Observation) -> Candidate | None:
    return candidate if resolves_uniquely_to(candidate, node, observation) else None


def _confidence(base: float, penalty: float) -> float:
    return round(max(MIN_CONFIDENCE, min(1.0, base - penalty)), 3)


# ---------------------------------------------------------------- role_name


def _role_name_candidate(node: Node, observation: Observation) -> Candidate | None:
    name = display_text(node)
    if not name or is_volatile_text(name):
        return None
    penalty = NAME_FROM_TEXT_PENALTY if not collapse_whitespace(node.name) else 0.0
    penalty += LONG_NAME_PENALTY if len(name) > LONG_NAME_CHARS else 0.0
    candidate = RoleNameCandidate(
        role=node.role,
        name=name,
        exact=True,
        confidence=_confidence(ROLE_NAME_CONFIDENCE, penalty),
        reason=f"The only {node.role} named '{name}' on this screen; role and name survive layout changes.",
    )
    return _keep_if_unique(candidate, node, observation)


# ---------------------------------------------------------------- label


def _label_candidate(node: Node, observation: Observation) -> Candidate | None:
    if not is_form_field(node):
        return None
    explicit_label = collapse_whitespace(node.label)
    label_text = explicit_label or adjacent_label_text(node, observation.nodes)
    if not label_text or is_volatile_text(label_text):
        return None
    penalty = 0.0 if explicit_label else ADJACENT_LABEL_PENALTY
    source = "its associated label" if explicit_label else "the adjacent label cell"
    candidate = LabelCandidate(
        label=label_text,
        role=node.role,
        confidence=_confidence(LABEL_CONFIDENCE, penalty),
        reason=f"The {node.role} identified by {source} '{label_text}', which users read to find this field.",
    )
    return _keep_if_unique(candidate, node, observation)


# ---------------------------------------------------------------- text_anchor


def _text_anchor_candidate(node: Node, observation: Observation) -> Candidate | None:
    if node.bounds is None:
        return None
    for _distance, anchor, relation in _anchor_offers(node, node.bounds, observation.nodes):
        candidate = _anchored_candidate(node, anchor, relation, observation)
        if candidate is not None:
            return candidate
    return None


def _anchor_offers(node: Node, node_bounds: Rect, nodes: list[Node]) -> list[AnchorOffer]:
    """Stable text anchors to the left in the same row (right_of), then above in the same column (below)."""
    left_offers: list[AnchorOffer] = []
    above_offers: list[AnchorOffer] = []
    for other in nodes:
        if not _is_stable_anchor(node, other) or other.bounds is None:
            continue
        left_gap = gap_to_the_left(other.bounds, node_bounds)
        if left_gap >= 0 and is_same_row(other.bounds, node_bounds):
            left_offers.append((left_gap, other, "right_of"))
        above_gap = gap_above(other.bounds, node_bounds)
        if above_gap >= 0 and horizontal_overlap(other.bounds, node_bounds) > 0:
            above_offers.append((above_gap, other, "below"))
    return sorted(left_offers, key=_offer_distance) + sorted(above_offers, key=_offer_distance)


def _offer_distance(offer: AnchorOffer) -> float:
    return offer[0]


def _is_stable_anchor(node: Node, other: Node) -> bool:
    return (
        other.ref != node.ref
        and other.bounds is not None
        and same_container(node, other)
        and is_text_node(other)
        and not is_volatile_text(display_text(other))
    )


def _anchored_candidate(
    node: Node, anchor: Node, relation: AnchorRelation, observation: Observation
) -> Candidate | None:
    anchor_text = display_text(anchor)
    probe = _text_anchor(anchor_text, relation, node.role, ordinal=0)
    matches, _anchor_count = text_anchor_matches(probe, observation.nodes)
    ordinal = next((index for index, match in enumerate(matches) if match.ref == node.ref), None)
    if ordinal is None:
        return None
    return _keep_if_unique(
        _text_anchor(anchor_text, relation, node.role, ordinal), node, observation
    )


def _text_anchor(
    anchor_text: str, relation: AnchorRelation, role: str, ordinal: int
) -> TextAnchorCandidate:
    position = "nearest" if ordinal == 0 else f"number {ordinal + 1}"
    relation_words = relation.replace("_", " ")
    return TextAnchorCandidate(
        anchor_text=anchor_text,
        relation=relation,
        role=role,
        ordinal=ordinal,
        confidence=_confidence(TEXT_ANCHOR_CONFIDENCE, ORDINAL_PENALTY * ordinal),
        reason=(
            f"The {position} {role} {relation_words} the stable text '{anchor_text}', "
            "which identifies this row or column even when values change."
        ),
    )


# ---------------------------------------------------------------- structural


def _structural_candidate(node: Node, observation: Observation) -> Candidate | None:
    if not node.structural_path:
        return None
    container = "/".join(node.container_path) or "the top level"
    candidate = StructuralCandidate(
        container_path=node.container_path,
        structural_path=node.structural_path,
        confidence=STRUCTURAL_CONFIDENCE,
        reason=f"Position '{node.structural_path}' in {container}; stable while this legacy layout is unchanged.",
    )
    return _keep_if_unique(candidate, node, observation)


# ---------------------------------------------------------------- visual_anchor


def _visual_anchor_candidate(node: Node, observation: Observation) -> Candidate | None:
    if node.bounds is None:
        return None
    anchor = _nearest_unique_anchor(node, node.bounds, observation.nodes)
    if anchor is None or anchor.bounds is None:
        return None
    anchor_text = display_text(anchor)
    return VisualAnchorCandidate(
        anchor_text=anchor_text,
        dx=round(node.bounds.center_x - anchor.bounds.center_x, 1),
        dy=round(node.bounds.center_y - anchor.bounds.center_y, 1),
        confidence=VISUAL_ANCHOR_CONFIDENCE,
        reason=f"Last resort: a fixed offset from the unique text '{anchor_text}', for when the a11y tree fails.",
    )


def _nearest_unique_anchor(node: Node, node_bounds: Rect, nodes: list[Node]) -> Node | None:
    anchors = [
        other
        for other in nodes
        if _is_stable_anchor(node, other)
        and len(find_anchor_nodes(display_text(other), nodes)) == 1
    ]
    if not anchors:
        return None
    return min(anchors, key=lambda anchor: _center_distance(anchor, node_bounds))


def _center_distance(anchor: Node, target_bounds: Rect) -> float:
    if anchor.bounds is None:
        return math.inf
    return math.hypot(
        anchor.bounds.center_x - target_bounds.center_x,
        anchor.bounds.center_y - target_bounds.center_y,
    )


# ---------------------------------------------------------------- fallback


def _default_description(node: Node) -> str:
    name = display_text(node)
    return f"{node.role} '{name}'" if name else node.role


def _fallback_candidate(node: Node) -> Candidate:
    reason = "No unique candidate could be generated; this non-unique fallback needs human review."
    if node.structural_path:
        return StructuralCandidate(
            container_path=node.container_path,
            structural_path=node.structural_path,
            confidence=FALLBACK_CONFIDENCE,
            reason=reason,
        )
    return RoleNameCandidate(
        role=node.role,
        name=display_text(node) or node.role,
        exact=True,
        confidence=FALLBACK_CONFIDENCE,
        reason=reason,
    )
