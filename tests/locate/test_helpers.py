"""Unit tests for the private text, geometry and node helpers shared by hands.locate modules."""

from __future__ import annotations

from hands.core.actions import Point
from hands.core.observation import Rect
from hands.locate._geometry import (
    area,
    center_point,
    contains_point,
    gap_above,
    gap_to_the_left,
    horizontal_overlap,
    is_below,
    is_inside,
    is_right_of,
    is_same_row,
    reading_order,
    same_container,
)
from hands.locate._nodes import (
    adjacent_label_node,
    adjacent_label_text,
    explicit_or_adjacent_label,
    find_anchor_nodes,
    find_enclosing_anchor_nodes,
    is_container,
    is_form_field,
    is_interactive,
    is_text_node,
    role_is,
)
from hands.locate._text import (
    collapse_whitespace,
    display_text,
    node_contains_text,
    node_matches_text_exactly,
    normalize_label,
    normalize_text,
)

from .fixtures import NAV_FRAME, login_observation, make_node, member_detail_observation


def rect(x: float, y: float, width: float, height: float) -> Rect:
    return Rect(x=x, y=y, width=width, height=height)


# ---------------------------------------------------------------- text


def test_collapse_whitespace_handles_none_empty_and_runs() -> None:
    assert collapse_whitespace(None) == ""
    assert collapse_whitespace("") == ""
    assert collapse_whitespace("  Regular \n\t Savings ") == "Regular Savings"


def test_normalize_text_casefolds_and_collapses() -> None:
    assert normalize_text("  MEMBER   Number ") == "member number"
    assert normalize_text(None) == ""


def test_normalize_label_drops_trailing_colon_and_asterisk() -> None:
    assert normalize_label("User ID:") == "user id"
    assert normalize_label("Password *") == "password"
    assert normalize_label(None) == ""


def test_display_text_prefers_name_then_text() -> None:
    assert display_text(make_node("a", "button", name="Search", text="ignored")) == "Search"
    assert display_text(make_node("b", "cell", text=" Balance ")) == "Balance"
    assert display_text(make_node("c", "cell")) == ""


def test_node_text_matching_exact_and_contains() -> None:
    cell = make_node("a", "cell", text="Regular Savings")
    assert node_matches_text_exactly(cell, "regular  savings")
    assert not node_matches_text_exactly(cell, "Savings")
    assert node_contains_text(cell, "savings")
    assert not node_matches_text_exactly(cell, "")
    assert not node_contains_text(cell, "")


# ---------------------------------------------------------------- geometry


def test_same_container_compares_paths() -> None:
    assert same_container(make_node("a", "cell"), make_node("b", "cell"))
    assert not same_container(make_node("a", "cell"), make_node("b", "cell", container=NAV_FRAME))


def test_center_area_and_contains_point_boundaries() -> None:
    box = rect(10, 20, 100, 40)
    assert center_point(box) == Point(x=60, y=40)
    assert area(box) == 4000
    assert contains_point(box, Point(x=10, y=20))
    assert contains_point(box, Point(x=110, y=60))
    assert not contains_point(box, Point(x=110.5, y=60))


def test_same_row_boundary_is_half_anchor_height() -> None:
    anchor = rect(0, 0, 100, 20)
    assert is_same_row(anchor, rect(200, 10, 50, 20))
    assert not is_same_row(anchor, rect(200, 10.5, 50, 20))


def test_right_of_below_and_inside() -> None:
    anchor = rect(100, 100, 100, 20)
    assert is_right_of(anchor, rect(200, 100, 50, 20))
    assert not is_right_of(anchor, rect(50, 100, 40, 20))
    assert is_below(anchor, rect(120, 120, 50, 20))
    assert not is_below(anchor, rect(300, 120, 50, 20))
    assert is_inside(anchor, rect(110, 102, 20, 10))
    assert not is_inside(anchor, rect(90, 102, 20, 10))


def test_gaps_and_overlap() -> None:
    assert gap_to_the_left(rect(0, 0, 100, 10), rect(105, 0, 10, 10)) == 5
    assert gap_above(rect(0, 0, 10, 20), rect(0, 30, 10, 10)) == 10
    assert horizontal_overlap(rect(0, 0, 100, 10), rect(50, 0, 100, 10)) == 50
    assert horizontal_overlap(rect(0, 0, 10, 10), rect(20, 0, 10, 10)) == 0


def test_reading_order_groups_lines_and_appends_unpositioned() -> None:
    right = make_node("right", "cell", box=(300, 101, 50, 20))
    left = make_node("left", "cell", box=(100, 100, 50, 20))
    below = make_node("below", "cell", box=(0, 200, 50, 20))
    floating = make_node("floating", "cell")
    ordered = reading_order([floating, below, right, left])
    assert [node.ref for node in ordered] == ["left", "right", "below", "floating"]


def test_reading_order_empty() -> None:
    assert reading_order([]) == []


# ---------------------------------------------------------------- node classification and lookups


def test_role_classification() -> None:
    assert role_is(make_node("a", "Button"), "button")
    assert role_is(make_node("a", "cell"), None)
    assert not role_is(make_node("a", "cell"), "button")
    assert is_interactive(make_node("a", "link"))
    assert is_form_field(make_node("a", "textbox"))
    assert not is_form_field(make_node("a", "button"))
    assert is_container(make_node("a", "row"))
    assert is_text_node(make_node("a", "cell", text="Balance"))
    assert not is_text_node(make_node("a", "cell"))
    assert not is_text_node(make_node("a", "button", name="Go"))


def test_find_anchor_nodes_prefers_exact_and_skips_containers() -> None:
    nodes = member_detail_observation().nodes
    exact = find_anchor_nodes("Regular Savings", nodes)
    assert [node.ref for node in exact] == ["r1c2"]
    contains = find_anchor_nodes("Regular", nodes)
    assert [node.ref for node in contains] == ["r1c2"]
    assert find_anchor_nodes("", nodes) == []


def test_find_enclosing_anchor_nodes_includes_containers() -> None:
    refs = {
        node.ref
        for node in find_enclosing_anchor_nodes("Holiday Club", member_detail_observation().nodes)
    }
    assert refs == {"s0", "r3", "r3c2"}


def test_adjacent_label_prefers_left_cell() -> None:
    observation = login_observation()
    user_id_box = observation.node_by_ref("n6")
    assert user_id_box is not None
    label_node = adjacent_label_node(user_id_box, observation.nodes)
    assert label_node is not None and label_node.ref == "n4"
    assert adjacent_label_text(user_id_box, observation.nodes) == "User ID"


def test_adjacent_label_uses_text_above_when_nothing_left() -> None:
    caption = make_node("a", "text", text="Nickname", box=(100, 100, 80, 16))
    field = make_node("b", "textbox", box=(100, 120, 150, 20))
    assert adjacent_label_text(field, [caption, field]) == "Nickname"


def test_adjacent_label_none_without_bounds_or_neighbours() -> None:
    field_without_bounds = make_node("a", "textbox")
    assert adjacent_label_node(field_without_bounds, [field_without_bounds]) is None
    lonely_field = make_node("b", "textbox", box=(0, 0, 10, 10))
    assert adjacent_label_text(lonely_field, [lonely_field]) == ""


def test_explicit_label_wins_over_adjacent() -> None:
    observation = login_observation()
    labelled = make_node("x", "textbox", label="Operator", box=(145, 63, 200, 24), container=())
    assert explicit_or_adjacent_label(labelled, [*observation.nodes, labelled]) == "Operator"
