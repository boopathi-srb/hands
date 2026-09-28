"""AX tree extraction and assembly over synthetic CDP payloads (no browser)."""

from __future__ import annotations

from typing import Any

from hands.core.observation import Rect
from hands.surfaces.browser.assemble import (
    assemble_nodes,
    assign_structural_paths,
    label_for,
    merge_text_runs,
    resolved_name,
)
from hands.surfaces.browser.ax_extract import (
    ExtractedNode,
    TextPart,
    ax_properties,
    ax_string,
    control_value,
    extract_frame,
    name_comes_from_label,
)
from hands.surfaces.browser.frames import FrameInfo

FRAME = FrameInfo(frame_id="F1", container_path=("frame:content",), url="http://x/", name="content")


class AxTreeBuilder:
    """Builds getFullAXTree-shaped node lists; backend ids equal node ids."""

    def __init__(self, title: str = "Page") -> None:
        self.nodes: list[dict[str, Any]] = []
        self.root = self.add("RootWebArea", title)

    def add(self, role: str, name: str = "", parent: str | None = None, *, ignored: bool = False,
            value: str | None = None, properties: dict[str, Any] | None = None,
            name_sources: list[dict[str, Any]] | None = None) -> str:
        node_id = str(len(self.nodes) + 1)
        node: dict[str, Any] = {
            "nodeId": node_id,
            "ignored": ignored,
            "role": {"type": "role", "value": role},
            "name": {"type": "computedString", "value": name, "sources": name_sources or []},
            "childIds": [],
            "backendDOMNodeId": int(node_id),
            "properties": [{"name": key, "value": {"value": val}} for key, val in (properties or {}).items()],
        }
        if value is not None:
            node["value"] = {"type": "string", "value": value}
        if parent is not None:
            node["parentId"] = parent
            self._node(parent)["childIds"].append(node_id)
        self.nodes.append(node)
        return node_id

    def _node(self, node_id: str) -> dict[str, Any]:
        return self.nodes[int(node_id) - 1]


def _extract(builder: AxTreeBuilder) -> list[ExtractedNode]:
    return extract_frame(builder.nodes, FRAME).nodes


def _box(x: float, y: float, width: float = 50, height: float = 18) -> Rect:
    return Rect(x=x, y=y, width=width, height=height)


# ---------------------------------------------------------------- extraction


def test_empty_tree_extracts_nothing() -> None:
    extraction = extract_frame([], FRAME)
    assert extraction.nodes == [] and extraction.document_title == ""


def test_ignored_and_generic_nodes_are_transparent() -> None:
    tree = AxTreeBuilder("Inquiry")
    wrapper = tree.add("none", parent=tree.root, ignored=True)
    generic = tree.add("generic", parent=wrapper)
    tree.add("button", "Search", parent=generic)

    extraction = extract_frame(tree.nodes, FRAME)
    assert extraction.document_title == "Inquiry"
    assert [(node.role, node.parent) for node in extraction.nodes] == [("button", None)]
    assert extraction.nodes[0].container_path == ("frame:content",)


def test_static_text_is_absorbed_by_cells_and_standalone_elsewhere() -> None:
    tree = AxTreeBuilder()
    table = tree.add("LayoutTable", parent=tree.root)
    row = tree.add("LayoutTableRow", parent=table)
    cell = tree.add("LayoutTableCell", "Member Number", parent=row)
    bold = tree.add("generic", parent=cell)
    tree.add("StaticText", "Member Number", parent=bold)
    tree.add("StaticText", "No member found", parent=tree.root)

    nodes = _extract(tree)
    assert [node.role for node in nodes] == ["table", "row", "cell", "text"]
    assert [part.text for part in nodes[2].text_parts] == ["Member Number"]
    assert nodes[3].parent is None and nodes[3].text_parts[0].text == "No member found"


def test_leaf_controls_hide_their_internal_text() -> None:
    tree = AxTreeBuilder()
    cell = tree.add("LayoutTableCell", "•••", parent=tree.root)
    textbox = tree.add("textbox", parent=cell, value="•••")
    editor = tree.add("generic", parent=textbox)
    tree.add("StaticText", "•••", parent=editor)
    select = tree.add("combobox", parent=tree.root, value="Regular Savings")
    popup = tree.add("MenuListPopup", parent=select)
    tree.add("option", "Money Market", parent=popup)

    nodes = _extract(tree)
    assert [node.role for node in nodes] == ["cell", "textbox", "combobox"]
    assert nodes[0].text_parts == []
    assert nodes[2].value == "Regular Savings"


def test_inline_text_boxes_are_skipped_and_whitespace_joins_runs() -> None:
    tree = AxTreeBuilder()
    first = tree.add("StaticText", "Hello", parent=tree.root)
    tree.add("InlineTextBox", "Hello", parent=first)
    tree.add("StaticText", " ", parent=tree.root)
    second = tree.add("StaticText", "world", parent=tree.root)

    nodes = _extract(tree)
    assert [node.role for node in nodes] == ["text", "text"]
    assert [part.text for part in nodes[0].text_parts] == ["Hello", " "]
    assert nodes[1].merge_candidate is nodes[0]
    assert nodes[1].backend_node_id == int(second)


def test_kept_nodes_and_line_breaks_split_text_runs() -> None:
    tree = AxTreeBuilder()
    tree.add("StaticText", "Name:", parent=tree.root)
    tree.add("LineBreak", "\n", parent=tree.root)
    tree.add("StaticText", "Avery", parent=tree.root)
    tree.add("link", "Edit", parent=tree.root)
    tree.add("StaticText", "after link", parent=tree.root)
    tree.add("StaticText", " ", parent=tree.root)  # trailing whitespace joins the previous run

    runs = [node for node in _extract(tree) if node.role == "text"]
    assert [run.merge_candidate for run in runs] == [None, None, None]
    assert [part.text for part in runs[2].text_parts] == ["after link", " "]


def test_leading_whitespace_without_a_run_is_dropped() -> None:
    tree = AxTreeBuilder()
    tree.add("StaticText", "  ", parent=tree.root)
    assert _extract(tree) == []


def test_properties_values_and_label_sources() -> None:
    tree = AxTreeBuilder()
    tree.add("checkbox", "Joint", parent=tree.root, properties={"checked": "true", "disabled": True})
    tree.add("textbox", "Nickname", parent=tree.root, properties={"focused": True},
             name_sources=[{"type": "relatedElement", "nativeSource": "labelfor", "value": {"value": "Nickname"}}])
    tree.add("button", "Search", parent=tree.root, name_sources=[
        {"type": "attribute", "attribute": "value", "value": {"value": "Search"}},
        {"type": "contents", "superseded": True, "value": {"value": "Search"}},
    ])

    checkbox, textbox, button = _extract(tree)
    assert (checkbox.value, checkbox.enabled) == ("true", False)
    assert textbox.focused and textbox.name_from_label
    assert not button.name_from_label


def test_raw_value_helpers() -> None:
    assert ax_string(None) == "" and ax_string({"value": None}) == "" and ax_string({"value": 3}) == "3"
    assert ax_properties({}) == {}
    assert control_value({}, {}) is None
    assert control_value({"value": {"value": "abc"}}, {}) == "abc"
    assert control_value({}, {"checked": "mixed"}) == "mixed"
    assert not name_comes_from_label({})
    assert name_comes_from_label({"name": {"sources": [{"type": "attribute", "attribute": "aria-labelledby",
                                                        "value": {"value": "Amount"}}]}})
    assert not name_comes_from_label({"name": {"sources": [{"type": "relatedElement", "value": {"value": " "}}]}})


# ---------------------------------------------------------------- assembly


def _run(text: str, box: Rect | None, candidate: ExtractedNode | None = None) -> ExtractedNode:
    return ExtractedNode(role="text", chrome_name="", container_path=(), frame_id="F1", parent=None,
                         backend_node_id=1, text_parts=[TextPart(text, 1, [box] if box else [])],
                         merge_candidate=candidate)


def test_merge_touching_runs_on_one_line() -> None:
    first = _run("No member found for number ", _box(0, 0, 190))
    second = _run("99999", _box(190, 0, 40), first)
    third = _run(".", _box(230, 0, 4), second)
    survivors = merge_text_runs([first, second, third])
    assemble = assemble_nodes(survivors)

    assert survivors == [first]
    assert assemble[0].text == "No member found for number 99999."
    assert assemble[0].bounds == Rect(x=0, y=0, width=234, height=18)


def test_runs_on_different_lines_or_far_apart_stay_separate() -> None:
    first = _run("Line one", _box(0, 0))
    below = _run("Line two", _box(0, 40), first)
    far = _run("Far away", _box(400, 40), below)
    no_geometry = _run("Unknown", None, far)

    assert merge_text_runs([first, below, far, no_geometry]) == [first, below, far, no_geometry]


def test_sink_text_joins_parts_with_geometry() -> None:
    cell = ExtractedNode(role="cell", chrome_name="Line1Line2 ••", container_path=(), frame_id="F1",
                         parent=None, backend_node_id=1, text_parts=[
                             TextPart("Line1", 2, [_box(0, 0)]), TextPart("Line2", 3, [_box(0, 20)]),
                         ])
    link = ExtractedNode(role="link", chrome_name="", container_path=(), frame_id="F1", parent=None,
                         backend_node_id=4, text_parts=[TextPart("Ave", 5, [_box(0, 0, 20)]),
                                                        TextPart("ry", 6, [_box(20, 0, 12)])])
    assemble_nodes([cell, link])

    assert cell.text == "Line1 Line2" and cell.name == "Line1 Line2"  # own text, not Chrome's contents name
    assert link.text == "Avery" and link.name == "Avery"


def test_resolved_name_prefers_chrome_name_for_controls() -> None:
    button = ExtractedNode(role="button", chrome_name=" Sign  On ", container_path=(), frame_id="F1",
                           parent=None, backend_node_id=1)
    table = ExtractedNode(role="table", chrome_name="", container_path=(), frame_id="F1", parent=None,
                          backend_node_id=2, text="ignored")
    assert resolved_name(button) == "Sign On"
    assert resolved_name(table) == ""


def test_structural_paths_count_same_role_siblings_per_frame() -> None:
    def node(role: str, parent: ExtractedNode | None, frame_id: str = "F1") -> ExtractedNode:
        return ExtractedNode(role=role, chrome_name="", container_path=(), frame_id=frame_id, parent=parent,
                             backend_node_id=None)

    table = node("table", None)
    row_one, row_two = node("row", table), node("row", table)
    cells = [node("cell", row_two), node("cell", row_two)]
    other_frame_table = node("table", None, frame_id="F2")
    assign_structural_paths([table, row_one, row_two, *cells, other_frame_table])

    assert [n.structural_path for n in (table, row_one, row_two, *cells)] == [
        "table[1]", "table[1]/row[1]", "table[1]/row[2]", "table[1]/row[2]/cell[1]", "table[1]/row[2]/cell[2]",
    ]
    assert other_frame_table.structural_path == "table[1]"


def _label_source(text: str, box: Rect, frame_id: str = "F1") -> ExtractedNode:
    return ExtractedNode(role="cell", chrome_name="", container_path=(), frame_id=frame_id, parent=None,
                         backend_node_id=None, text=text, bounds=box, text_parts=[TextPart(text, None, [box])])


def _control(box: Rect | None, name: str = "", from_label: bool = False) -> ExtractedNode:
    return ExtractedNode(role="textbox", chrome_name=name, container_path=(), frame_id="F1", parent=None,
                         backend_node_id=None, bounds=box, name=name, name_from_label=from_label)


def test_label_prefers_label_element_name() -> None:
    assert label_for(_control(_box(200, 0), "Nickname", from_label=True), []) == "Nickname"


def test_label_is_nearest_text_to_the_left_in_the_same_row() -> None:
    control = _control(_box(300, 100, 150, 20))
    sources = [
        _label_source("Far left", _box(0, 100, 80)),
        _label_source("Member Number", _box(150, 101, 120)),
        _label_source("Row above", _box(200, 60, 80)),
        _label_source("To the right", _box(500, 100, 80)),
        _label_source("Other frame", _box(280, 100, 10), frame_id="F2"),
    ]
    assert label_for(control, sources) == "Member Number"


def test_label_uses_text_inside_the_same_cell() -> None:
    cell_text = _label_source("Amount", _box(10, 0, 50))
    cell_text.bounds = _box(0, 0, 300)  # the cell box contains the control too
    assert label_for(_control(_box(70, 0, 120)), [cell_text]) == "Amount"


def test_no_label_without_bounds_or_candidates() -> None:
    assert label_for(_control(None), [_label_source("X", _box(0, 0))]) is None
    assert label_for(_control(_box(100, 0)), []) is None
