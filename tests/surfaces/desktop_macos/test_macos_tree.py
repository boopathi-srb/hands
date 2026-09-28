from macos_ax_fakes import (
    CALC_ORIGIN,
    FakeAxBackend,
    calc_button,
    calculator_app,
    element,
    form_scenario,
)

from hands.core.observation import Dialog, Node, Rect
from hands.surfaces.desktop_macos.ax import AxPoint, AxSize
from hands.surfaces.desktop_macos.tree import (
    TreeLimits,
    TreeSnapshot,
    build_tree_snapshot,
    compute_fingerprint,
    content_signature,
    dialog_text,
    empty_snapshot,
    join_structural_path,
    relative_bounds,
    truncate_text,
)

BUNDLE = "com.apple.calculator"


def build(app, limits: TreeLimits | None = None) -> TreeSnapshot:
    return build_tree_snapshot(FakeAxBackend(), app, BUNDLE, limits)


def by_name(snapshot: TreeSnapshot, role: str, name: str) -> Node:
    return next(node for node in snapshot.nodes if node.role == role and node.name == name)


# ---------------------------------------------------------------- Calculator


def test_calculator_buttons_named_by_description_and_display_is_text() -> None:
    snapshot = build(calculator_app("42"))
    assert [node.name for node in snapshot.nodes if node.role == "button"] == [
        "7",
        "8",
        "Add",
        "Clear",
    ]
    display = next(node for node in snapshot.nodes if node.role == "text")
    assert (display.name, display.text, display.value) == ("42", "42", None)


def test_calculator_structure_groups_are_pruned_and_paths_role_indexed() -> None:
    snapshot = build(calculator_app())
    assert all(node.role != "group" for node in snapshot.nodes)
    paths = {node.name: node.structural_path for node in snapshot.nodes}
    assert paths == {
        "0": "text[1]",
        "7": "button[1]",
        "8": "button[2]",
        "Add": "button[3]",
        "Clear": "button[4]",
    }
    assert {node.container_path for node in snapshot.nodes} == {("window:Calculator",)}


def test_calculator_bounds_are_window_relative_and_screen_center_restores_screen_space() -> None:
    snapshot = build(calculator_app())
    seven = by_name(snapshot, "button", "7")
    assert seven.bounds == Rect(x=10, y=100, width=40, height=40)
    assert snapshot.screen_center(seven.ref) == AxPoint(CALC_ORIGIN[0] + 30, CALC_ORIGIN[1] + 120)
    assert snapshot.primary_window is not None
    assert snapshot.primary_window.origin == AxPoint(*CALC_ORIGIN)
    assert snapshot.primary_window.size == AxSize(230, 400)


def test_location_is_bundle_id_and_focused_window_title() -> None:
    snapshot = build(calculator_app())
    assert snapshot.location.kind == "window"
    assert snapshot.location.value == BUNDLE
    assert snapshot.location.title == "Calculator"


def test_refs_are_unique_sequential_and_mapped_to_elements() -> None:
    snapshot = build(calculator_app())
    refs = [node.ref for node in snapshot.nodes]
    assert refs == [f"n{index}" for index in range(1, len(refs) + 1)]
    assert set(snapshot.entries_by_ref) == set(refs)
    assert snapshot.screen_center("n999") is None


# ---------------------------------------------------------------- fingerprints


def test_fingerprint_is_stable_across_identical_trees_and_ignores_values() -> None:
    first, second = build(calculator_app("0")), build(calculator_app("123"))
    assert first.fingerprint == second.fingerprint
    assert content_signature(first.nodes) != content_signature(second.nodes)


def test_fingerprint_changes_when_structure_changes() -> None:
    app = calculator_app()
    before = build(app).fingerprint
    window = app.attrs["AXFocusedWindow"]
    window.children.append(calc_button("Equals", 300, 300))
    assert build(app).fingerprint != before


def test_compute_fingerprint_is_order_independent_and_defined_for_empty() -> None:
    node_a = Node(
        ref="n1", role="button", structural_path="button[1]", container_path=("window:A",)
    )
    node_b = Node(ref="n2", role="text", structural_path="text[1]", container_path=("window:A",))
    assert compute_fingerprint([node_a, node_b]) == compute_fingerprint([node_b, node_a])
    assert len(compute_fingerprint([])) == 16


# ---------------------------------------------------------------- form window with a sheet


def test_form_focused_window_first_and_labels() -> None:
    snapshot = build(form_scenario().app)
    assert snapshot.location.title == "New Member"
    assert snapshot.nodes[0].container_path == ("window:New Member",)
    textboxes = [node for node in snapshot.nodes if node.role == "textbox"]
    assert [node.label for node in textboxes] == ["Member Number", "First Name", "Nickname"]
    nickname = textboxes[2]
    assert nickname.name == "Nickname"
    assert textboxes[0].name == ""


def test_form_editable_values_and_roles() -> None:
    snapshot = build(form_scenario().app)
    share_type = by_name(snapshot, "combobox", "Share Type")
    assert share_type.value == "Regular Savings"
    joint = by_name(snapshot, "checkbox", "Joint")
    assert joint.value == "false"
    assert by_name(snapshot, "button", "Continue").text == "Continue"


def test_form_table_paths_and_row_text_aggregation() -> None:
    snapshot = build(form_scenario().app)
    rows = [node for node in snapshot.nodes if node.role == "row"]
    assert [row.structural_path for row in rows] == ["table[1]/row[1]", "table[1]/row[2]"]
    assert rows[0].name == "S01 Savings"
    cell = next(
        node for node in snapshot.nodes if node.structural_path == "table[1]/row[2]/cell[2]"
    )
    assert (cell.role, cell.name, cell.text) == ("cell", "Checking", "Checking")
    text = next(
        node for node in snapshot.nodes if node.structural_path == "table[1]/row[2]/cell[2]/text[1]"
    )
    assert text.text == "Checking"


def test_sheet_is_a_nested_container_and_a_dialog() -> None:
    snapshot = build(form_scenario().app)
    sheet_nodes = [node for node in snapshot.nodes if len(node.container_path) == 2]
    assert {node.container_path for node in sheet_nodes} == {("window:New Member", "sheet:Confirm")}
    assert [node.structural_path for node in sheet_nodes] == ["text[1]", "button[1]", "button[2]"]
    assert Dialog(title="Confirm", text="Replace existing member?") in snapshot.dialogs
    assert all(node.role != "dialog" for node in snapshot.nodes)


def test_dialog_subrole_window_becomes_a_dialog_and_is_walked_after_focused() -> None:
    snapshot = build(form_scenario().app)
    assert snapshot.dialogs[-1] == Dialog(title="Printer", text="Printer queue offline")
    assert snapshot.nodes[-1].container_path == ("window:Printer",)
    assert [window.title for window in snapshot.windows] == ["New Member", "Printer"]
    assert [window.focused for window in snapshot.windows] == [True, False]


def test_no_sheet_means_no_sheet_dialog() -> None:
    snapshot = build(form_scenario(with_sheet=False).app)
    assert [dialog.title for dialog in snapshot.dialogs] == ["Printer"]


# ---------------------------------------------------------------- edge cases


def test_empty_app_without_windows() -> None:
    snapshot = build(element("AXApplication", title="Empty"))
    assert snapshot.nodes == []
    assert snapshot.dialogs == []
    assert snapshot.location.title == ""
    assert snapshot.fingerprint == compute_fingerprint([])
    assert snapshot.primary_window is None


def test_windows_without_focused_window_are_still_walked() -> None:
    window = element("AXWindow", element("AXButton", title="Go"), title="Only")
    app = element("AXApplication", AXWindows=[window])
    snapshot = build(app)
    assert snapshot.location.title == "Only"
    assert snapshot.windows[0].focused is False
    assert snapshot.nodes[0].bounds is None


def test_invalid_elements_are_skipped() -> None:
    broken = element("AXButton", title="Broken")
    broken.invalid = True
    window = element("AXWindow", broken, element("AXButton", title="Fine"), title="W")
    app = element("AXApplication", AXWindows=[window], AXFocusedWindow=window)
    assert [node.name for node in build(app).nodes] == ["Fine"]


def test_named_group_is_kept() -> None:
    window = element(
        "AXWindow",
        element("AXGroup", element("AXButton", title="7"), description="Keypad"),
        title="W",
    )
    app = element("AXApplication", AXWindows=[window], AXFocusedWindow=window)
    snapshot = build(app)
    assert [(node.role, node.structural_path) for node in snapshot.nodes] == [
        ("group", "group[1]"),
        ("button", "group[1]/button[1]"),
    ]


def test_max_nodes_truncates() -> None:
    snapshot = build(calculator_app(), TreeLimits(max_nodes=2))
    assert len(snapshot.nodes) == 2
    assert snapshot.truncated is True


def test_max_depth_stops_descent() -> None:
    deep = element("AXButton", title="deep")
    for level in range(5):
        deep = element("AXGroup", deep, description=f"level{level}")
    window = element("AXWindow", deep, title="W")
    app = element("AXApplication", AXWindows=[window], AXFocusedWindow=window)
    snapshot = build(app, TreeLimits(max_depth=3))
    assert len(snapshot.nodes) == 3
    assert snapshot.truncated is True
    assert all(node.name != "deep" for node in snapshot.nodes)


def test_max_visited_bounds_ax_calls() -> None:
    backend = FakeAxBackend()
    snapshot = build_tree_snapshot(backend, calculator_app(), BUNDLE, TreeLimits(max_visited=3))
    assert backend.attribute_fetches <= 3
    assert snapshot.truncated is True


def test_untruncated_tree_reports_not_truncated() -> None:
    assert build(calculator_app()).truncated is False


def test_text_is_truncated_to_limit() -> None:
    window = element("AXWindow", element("AXStaticText", value="x" * 50), title="W")
    app = element("AXApplication", AXWindows=[window], AXFocusedWindow=window)
    assert build(app, TreeLimits(max_text_chars=10)).nodes[0].text == "x" * 10


# ---------------------------------------------------------------- pure helpers


def test_truncate_text() -> None:
    assert truncate_text("", 3) == ""
    assert truncate_text("abc", 3) == "abc"
    assert truncate_text("abcd", 3) == "abc"


def test_relative_bounds() -> None:
    assert relative_bounds(AxPoint(15, 25), AxSize(5, 6), AxPoint(10, 20)) == Rect(
        x=5, y=5, width=5, height=6
    )
    assert relative_bounds(None, AxSize(5, 6), AxPoint(0, 0)) is None
    assert relative_bounds(AxPoint(1, 1), None, AxPoint(0, 0)) is None


def test_join_structural_path() -> None:
    assert join_structural_path("", "table", 1) == "table[1]"
    assert join_structural_path("table[1]", "row", 3) == "table[1]/row[3]"


def test_dialog_text_only_uses_text_in_container() -> None:
    nodes = [
        Node(ref="n1", role="text", text="In", container_path=("window:A", "sheet:S")),
        Node(ref="n2", role="text", text="Out", container_path=("window:A",)),
        Node(ref="n3", role="button", text="Btn", container_path=("window:A", "sheet:S")),
    ]
    assert dialog_text(nodes, ("window:A", "sheet:S"), 100) == "In"
    assert dialog_text([], ("window:A",), 100) == ""


def test_empty_snapshot() -> None:
    snapshot = empty_snapshot("com.x")
    assert snapshot.location.value == "com.x"
    assert snapshot.nodes == [] and snapshot.windows == [] and snapshot.entries_by_ref == {}
