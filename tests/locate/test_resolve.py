from __future__ import annotations

from hands.core.actions import Point
from hands.core.observation import Observation
from hands.core.targets import (
    Candidate,
    LabelCandidate,
    RoleNameCandidate,
    StructuralCandidate,
    TargetSpec,
    TextAnchorCandidate,
    VisualAnchorCandidate,
)
from hands.locate import Resolution, fill_target, resolve_target
from hands.locate.resolve import (
    node_at_point,
    related_nodes,
    resolve_candidate,
    text_anchor_matches,
)

from .fixtures import (
    CONTENT_FRAME,
    NAV_FRAME,
    empty_observation,
    inquiry_observation,
    login_observation,
    make_node,
    make_observation,
    member_detail_observation,
    prairie_inquiry_observation,
    prairie_member_detail_observation,
)


def spec(*candidates: Candidate) -> TargetSpec:
    return TargetSpec(description="test target", candidates=list(candidates))


def role_name(role: str, name: str, exact: bool = True) -> RoleNameCandidate:
    return RoleNameCandidate(role=role, name=name, exact=exact, confidence=0.9, reason="test")


def label(text: str, role: str | None = None) -> LabelCandidate:
    return LabelCandidate(label=text, role=role, confidence=0.85, reason="test")


def anchor(
    text: str, relation: str, role: str | None = None, ordinal: int = 0
) -> TextAnchorCandidate:
    return TextAnchorCandidate.model_validate(
        {
            "anchor_text": text,
            "relation": relation,
            "role": role,
            "ordinal": ordinal,
            "confidence": 0.7,
            "reason": "t",
        }
    )


def structural(container: tuple[str, ...], path: str) -> StructuralCandidate:
    return StructuralCandidate(
        container_path=container, structural_path=path, confidence=0.5, reason="test"
    )


def visual(text: str, dx: float, dy: float) -> VisualAnchorCandidate:
    return VisualAnchorCandidate(anchor_text=text, dx=dx, dy=dy, confidence=0.3, reason="test")


def resolved_ref(resolution: Resolution | None) -> str | None:
    if resolution is None or resolution.node is None:
        return None
    return resolution.node.ref


# ---------------------------------------------------------------- role_name


def test_role_name_exact_is_case_and_whitespace_insensitive() -> None:
    resolution = resolve_target(spec(role_name("BUTTON", "  sign   on ")), login_observation())
    assert resolution is not None
    assert resolution.node is not None and resolution.node.ref == "n12"
    assert resolution.rank == 0
    assert resolution.candidate_kind == "role_name"
    assert not resolution.ambiguous
    assert resolution.match_count == 1
    assert resolution.point == Point(x=190, y=149)


def test_role_name_contains() -> None:
    observation = inquiry_observation()
    assert resolve_target(spec(role_name("link", "Share", exact=False)), observation) is not None
    assert resolve_target(spec(role_name("link", "Share", exact=True)), observation) is None


def test_role_name_falls_back_to_text_when_name_empty() -> None:
    resolution = resolve_target(
        spec(role_name("cell", "Holiday Club")), member_detail_observation()
    )
    assert resolved_ref(resolution) == "r3c2"


def test_role_name_empty_name_never_matches() -> None:
    assert resolve_target(spec(role_name("textbox", "")), login_observation()) is None


def test_ambiguous_role_name_picks_first_in_reading_order() -> None:
    resolution = resolve_target(spec(role_name("link", "View")), member_detail_observation())
    assert resolution is not None
    assert resolution.ambiguous
    assert resolution.match_count == 3
    assert resolved_ref(resolution) == "r1view"


def test_reading_order_beats_list_order() -> None:
    lower = make_node("lower", "button", name="Continue", box=(10, 300, 80, 20))
    upper = make_node("upper", "button", name="Continue", box=(10, 100, 80, 20))
    resolution = resolve_target(
        spec(role_name("button", "Continue")), make_observation([lower, upper])
    )
    assert resolved_ref(resolution) == "upper"


def test_list_order_when_no_bounds() -> None:
    first = make_node("first", "button", name="Continue")
    second = make_node("second", "button", name="Continue")
    resolution = resolve_target(
        spec(role_name("button", "Continue")), make_observation([first, second])
    )
    assert resolved_ref(resolution) == "first"
    assert resolution is not None and resolution.point is None and resolution.ambiguous


def test_disabled_nodes_still_match() -> None:
    resolution = resolve_target(
        spec(role_name("button", "Close Member")), member_detail_observation()
    )
    assert resolution is not None and resolution.node is not None
    assert resolution.node.enabled is False


# ---------------------------------------------------------------- label


def test_label_matches_adjacent_cell_ignoring_colon() -> None:
    observation = login_observation()
    assert resolved_ref(resolve_target(spec(label("User ID")), observation)) == "n6"
    assert resolved_ref(resolve_target(spec(label("password")), observation)) == "n10"


def test_label_matches_explicit_label() -> None:
    field = make_node("f", "combobox", label="Share Type:", box=(10, 10, 100, 20))
    resolution = resolve_target(
        spec(label("Share Type", role="combobox")), make_observation([field])
    )
    assert resolved_ref(resolution) == "f"


def test_label_without_role_only_considers_form_fields() -> None:
    caption = make_node("c", "cell", text="Member Number", box=(0, 0, 100, 20))
    button = make_node("b", "button", name="Go", box=(110, 0, 50, 20))
    assert resolve_target(spec(label("Member Number")), make_observation([caption, button])) is None
    assert (
        resolved_ref(
            resolve_target(
                spec(label("Member Number", role="button")), make_observation([caption, button])
            )
        )
        == "b"
    )


def test_label_empty_or_unknown_does_not_match() -> None:
    observation = login_observation()
    assert resolve_target(spec(label("")), observation) is None
    assert resolve_target(spec(label("Surname")), observation) is None


# ---------------------------------------------------------------- text_anchor


def test_text_anchor_right_of_finds_balance_cell_in_regular_savings_row() -> None:
    resolution = resolve_target(
        spec(anchor("Regular Savings", "right_of", "cell")), member_detail_observation()
    )
    assert resolved_ref(resolution) == "r1c3"
    assert resolution is not None
    assert resolution.candidate_kind == "text_anchor"
    assert resolution.match_count == 3  # Balance, Available, action cell
    assert not resolution.ambiguous


def test_text_anchor_ordinal_selects_later_match() -> None:
    observation = member_detail_observation()
    assert (
        resolved_ref(
            resolve_target(spec(anchor("Regular Savings", "right_of", "cell", 1)), observation)
        )
        == "r1c4"
    )
    assert (
        resolved_ref(resolve_target(spec(anchor("Balance", "below", "cell", 1)), observation))
        == "r2c3"
    )


def test_text_anchor_ordinal_out_of_range_falls_through_to_next_candidate() -> None:
    resolution = resolve_target(
        spec(anchor("Regular Savings", "right_of", "cell", 9), role_name("button", "Print")),
        member_detail_observation(),
    )
    assert (
        resolution is not None and resolution.rank == 1 and resolution.candidate_kind == "role_name"
    )


def test_text_anchor_below_column_header() -> None:
    resolution = resolve_target(
        spec(anchor("Balance", "below", "cell")), member_detail_observation()
    )
    assert resolved_ref(resolution) == "r1c3"


def test_text_anchor_same_row() -> None:
    resolution = resolve_target(
        spec(anchor("Checking", "same_row", "link")), member_detail_observation()
    )
    assert resolved_ref(resolution) == "r2view"


def test_text_anchor_inside_uses_innermost_enclosing_row() -> None:
    resolution = resolve_target(
        spec(anchor("Holiday Club", "inside", "link")), member_detail_observation()
    )
    assert resolved_ref(resolution) == "r3view"
    assert resolution is not None and not resolution.ambiguous and resolution.match_count == 1


def test_text_anchor_ambiguous_when_anchor_text_repeats() -> None:
    first = make_node("a1", "cell", text="Checking", box=(0, 0, 100, 20))
    first_value = make_node("v1", "cell", text="1.00", box=(100, 0, 100, 20))
    second = make_node("a2", "cell", text="Checking", box=(0, 40, 100, 20))
    second_value = make_node("v2", "cell", text="2.00", box=(100, 40, 100, 20))
    observation = make_observation([first, first_value, second, second_value])
    resolution = resolve_target(spec(anchor("Checking", "right_of", "cell")), observation)
    assert resolution is not None
    assert resolution.ambiguous
    assert resolved_ref(resolution) == "v1"
    assert resolution.match_count == 2


def test_text_anchor_respects_container() -> None:
    nav_text = make_node("t", "text", text="Menu", container=NAV_FRAME, box=(0, 0, 50, 20))
    content_link = make_node("l", "link", name="Go", container=CONTENT_FRAME, box=(60, 0, 50, 20))
    observation = make_observation([nav_text, content_link])
    assert resolve_target(spec(anchor("Menu", "right_of", "link")), observation) is None


def test_related_nodes_empty_when_anchor_has_no_bounds() -> None:
    anchor_node = make_node("a", "cell", text="Balance")
    assert related_nodes(anchor_node, "below", None, [anchor_node]) == []


def test_text_anchor_matches_counts_contributing_anchors() -> None:
    matches, anchor_count = text_anchor_matches(
        anchor("Balance", "below", "cell"), member_detail_observation().nodes
    )
    assert [node.ref for node in matches] == ["r1c3", "r2c3", "r3c3"]
    assert anchor_count == 1


# ---------------------------------------------------------------- structural


def test_structural_exact_paths() -> None:
    observation = member_detail_observation()
    resolution = resolve_target(
        spec(structural(CONTENT_FRAME, "table[2]/row[3]/cell[3]")), observation
    )
    assert resolved_ref(resolution) == "r2c3"
    assert (
        resolve_target(spec(structural(NAV_FRAME, "table[2]/row[3]/cell[3]")), observation) is None
    )
    assert resolve_target(spec(structural(CONTENT_FRAME, "")), observation) is None


# ---------------------------------------------------------------- visual_anchor


def test_visual_anchor_offsets_from_anchor_center_and_hit_tests() -> None:
    observation = member_detail_observation()
    # 'Regular Savings' cell center is (360, 207.5); Balance cell center is (490, 207.5).
    resolution = resolve_target(spec(visual("Regular Savings", 130, 0)), observation)
    assert resolution is not None
    assert resolution.point == Point(x=490, y=207.5)
    assert resolved_ref(resolution) == "r1c3"
    assert resolution.candidate_kind == "visual_anchor"


def test_visual_anchor_point_outside_any_node() -> None:
    resolution = resolve_target(
        spec(visual("Regular Savings", 5000, 0)), member_detail_observation()
    )
    assert resolution is not None and resolution.node is None
    assert resolution.point == Point(x=5360, y=207.5)


def test_visual_anchor_missing_anchor() -> None:
    assert resolve_target(spec(visual("Nowhere", 0, 0)), member_detail_observation()) is None


def test_node_at_point_prefers_smallest() -> None:
    observation = member_detail_observation()
    hit = node_at_point(Point(x=670, y=207), CONTENT_FRAME, observation.nodes)
    assert hit is not None and hit.ref == "r1view"
    assert node_at_point(Point(x=-5, y=-5), CONTENT_FRAME, observation.nodes) is None


# ---------------------------------------------------------------- rank, fallbacks, empties


def test_rank_reports_first_matching_candidate() -> None:
    resolution = resolve_target(
        spec(role_name("button", "Missing"), label("Nope"), role_name("button", "Search")),
        inquiry_observation(),
    )
    assert resolution is not None and resolution.rank == 2 and resolved_ref(resolution) == "c5"


def test_nothing_matches_returns_none() -> None:
    assert resolve_target(spec(role_name("button", "Missing")), member_detail_observation()) is None


def test_empty_observation_every_kind_returns_none() -> None:
    observation: Observation = empty_observation()
    every_kind = spec(
        role_name("button", "Search"),
        label("Member Number"),
        anchor("Balance", "below"),
        structural(CONTENT_FRAME, "button[1]"),
        visual("Balance", 0, 0),
    )
    assert resolve_target(every_kind, observation) is None


def test_resolve_candidate_directly() -> None:
    candidate_match = resolve_candidate(role_name("link", "Reports"), member_detail_observation())
    assert candidate_match is not None and candidate_match.node is not None
    assert candidate_match.node.ref == "v3"


# ---------------------------------------------------------------- tenant aliases end to end


def test_lakeside_spec_resolves_on_prairie_through_aliases() -> None:
    aliases = {
        "Member Number": "Account Number",
        "Search": "Find",
        "Regular Savings": "Share Savings",
    }
    member_field = spec(label("Member Number", "textbox"))
    search_button = spec(role_name("button", "Search"))
    savings_view = spec(anchor("Regular Savings", "right_of", "link"))
    assert resolve_target(member_field, prairie_inquiry_observation()) is None
    assert (
        resolved_ref(
            resolve_target(fill_target(member_field, {}, aliases), prairie_inquiry_observation())
        )
        == "c4"
    )
    assert (
        resolved_ref(
            resolve_target(fill_target(search_button, {}, aliases), prairie_inquiry_observation())
        )
        == "c5"
    )
    prairie_detail = prairie_member_detail_observation()
    assert (
        resolved_ref(resolve_target(fill_target(savings_view, {}, aliases), prairie_detail))
        == "r1view"
    )


def test_column_reorder_is_drift_that_aliases_alone_cannot_fix() -> None:
    """Prairie puts Balance before Description, so 'first cell right of the savings row' is Available.
    This is why tenant overlays carry target_overrides and why structural candidates can drift."""
    aliases = {"Regular Savings": "Share Savings"}
    balance = spec(anchor("Regular Savings", "right_of", "cell"))
    resolution = resolve_target(
        fill_target(balance, {}, aliases), prairie_member_detail_observation()
    )
    assert resolution is not None and resolution.node is not None
    assert resolution.node.text == "1,250.00"  # the Available column in the prairie layout
    assert resolved_ref(resolution) == "r1c4"
