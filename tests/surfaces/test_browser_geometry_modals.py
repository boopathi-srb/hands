"""Pure geometry helpers and in-page modal detection (no browser)."""

from __future__ import annotations

from hands.core.observation import Dialog, Rect
from hands.surfaces.browser.ax_extract import ExtractedNode
from hands.surfaces.browser.geometry import (
    can_merge_runs,
    contains_point,
    horizontal_gap,
    in_same_row,
    join_fragments,
    on_same_line,
    quad_to_rect,
    text_separator,
    union_rects,
)
from hands.surfaces.browser.modals import detect_modal_dialogs, is_descendant


def _box(x: float, y: float, width: float = 50, height: float = 18) -> Rect:
    return Rect(x=x, y=y, width=width, height=height)


# ---------------------------------------------------------------- geometry


def test_quad_to_rect() -> None:
    assert quad_to_rect([10, 20, 60, 20, 60, 40, 10, 40]) == Rect(x=10, y=20, width=50, height=20)
    assert quad_to_rect([]) is None
    assert quad_to_rect([1, 2, 3]) is None


def test_union_rects() -> None:
    assert union_rects([]) is None
    assert union_rects([_box(0, 0, 10, 10), _box(20, 5, 10, 10)]) == Rect(x=0, y=0, width=30, height=15)


def test_line_and_row_relations() -> None:
    assert on_same_line(_box(0, 0), _box(60, 5))
    assert not on_same_line(_box(0, 0), _box(0, 30))
    assert not on_same_line(_box(0, 0, height=0), _box(0, 0, height=0))  # zero-height boxes never align
    assert in_same_row(_box(0, 100, height=26), _box(200, 104, height=20))
    assert not in_same_row(_box(0, 100), _box(0, 140))
    assert horizontal_gap(_box(0, 0, 50), _box(60, 0)) == 10
    assert contains_point(_box(0, 0), 50, 18) and not contains_point(_box(0, 0), 51, 0)


def test_text_separator_and_merge_rules() -> None:
    assert text_separator(_box(0, 0, 40), _box(40, 0)) == ""
    assert text_separator(_box(0, 0, 40), _box(48, 0)) == " "
    assert text_separator(None, _box(0, 0)) == " "
    assert can_merge_runs(_box(0, 0, 40), _box(48, 0))
    assert not can_merge_runs(_box(0, 0, 40), _box(100, 0))
    assert not can_merge_runs(None, _box(0, 0))


def test_join_fragments() -> None:
    assert join_fragments([]) == ""
    assert join_fragments([("Name: ", _box(0, 0, 40), _box(0, 0, 40)), ("Avery", _box(40, 0), _box(40, 0))]) == (
        "Name: Avery"
    )
    touching = [("99999", _box(0, 0, 40), _box(0, 0, 40)), (".", _box(40, 0, 4), _box(40, 0, 4))]
    assert join_fragments(touching) == "99999."
    assert join_fragments([("Line1", None, None), ("Line2", None, None)]) == "Line1 Line2"
    assert join_fragments([("  a \n", None, None), ("", None, None)]) == "a"


# ---------------------------------------------------------------- modals


class _Page:
    """Tiny builder for assembled nodes in one frame."""

    def __init__(self) -> None:
        self.nodes: list[ExtractedNode] = []

    def add(self, role: str, parent: ExtractedNode | None = None, *, text: str = "", name: str = "",
            box: Rect | None = None, frame_id: str = "F1") -> ExtractedNode:
        node = ExtractedNode(role=role, chrome_name=name, container_path=(), frame_id=frame_id, parent=parent,
                             backend_node_id=None, text=text, name=name or text, bounds=box)
        self.nodes.append(node)
        return node

    def table(self, rows: list[list[tuple[str, str]]], box: Rect) -> ExtractedNode:
        table = self.add("table", box=box)
        for row_index, cells in enumerate(rows):
            row = self.add("row", table, box=_box(box.x, box.y + row_index * 20, box.width, 20))
            for role, text in cells:
                cell = self.add("cell", row, text="" if role == "button" else text,
                                box=_box(box.x, box.y + row_index * 20, box.width, 20))
                if role == "button":
                    self.add("button", cell, name=text, box=_box(box.x + 2, box.y + row_index * 20 + 2, 60, 16))
        return table


def _form_underneath(page: _Page) -> ExtractedNode:
    return page.table([[("cell", "Member Number"), ("cell", "")], [("button", "Search")]], _box(0, 0, 400, 40))


def test_semantic_dialog_title_and_text() -> None:
    page = _Page()
    dialog = page.add("dialog", name="Verify Member Identity", box=_box(0, 0, 300, 100))
    page.add("heading", dialog, text="Security check")
    page.add("text", dialog, text="What is the pet's name?")
    page.add("button", dialog, name="Verify")
    untitled = page.add("dialog", box=_box(0, 200, 300, 100))
    page.add("heading", untitled, text="Heads up")
    page.add("text", untitled, text="Body")

    assert detect_modal_dialogs(page.nodes) == [
        Dialog(title="Verify Member Identity", text="Security check What is the pet's name?"),
        Dialog(title="Heads up", text="Body"),
    ]


def test_positioned_table_over_earlier_content_is_a_dialog() -> None:
    page = _Page()
    _form_underneath(page)
    page.table([[("cell", "System Notice")], [("cell", "Maintenance tonight.")], [("button", "Acknowledge")]],
               _box(10, 5, 200, 60))

    assert detect_modal_dialogs(page.nodes) == [Dialog(title="System Notice", text="Maintenance tonight.")]


def test_table_is_not_a_dialog_without_overlap_title_or_button() -> None:
    page = _Page()
    _form_underneath(page)
    page.table([[("cell", "Below the form")], [("button", "OK")]], _box(0, 100, 300, 40))  # no overlap
    page.table([[("cell", "")], [("button", "OK")]], _box(10, 5, 100, 40))  # no title
    page.table([[("cell", "Title")], [("cell", "no controls")]], _box(10, 5, 100, 40))  # no button

    assert detect_modal_dialogs(page.nodes) == []


def test_content_underneath_an_overlay_is_not_reported() -> None:
    page = _Page()
    _form_underneath(page)
    page.table([[("cell", "System Notice")], [("button", "Acknowledge")]], _box(10, 5, 200, 60))

    assert [dialog.title for dialog in detect_modal_dialogs(page.nodes)] == ["System Notice"]


def test_overlap_in_another_frame_does_not_count() -> None:
    page = _Page()
    page.add("text", text="In another frame", box=_box(20, 20), frame_id="F0")
    page.table([[("cell", "Notice")], [("button", "OK")]], _box(10, 5, 200, 60))
    assert detect_modal_dialogs(page.nodes) == []


def test_tables_inside_a_semantic_dialog_are_not_reported_twice() -> None:
    page = _Page()
    _form_underneath(page)
    dialog = page.add("dialog", name="Notice", box=_box(10, 5, 200, 60))
    inner = page.add("table", dialog, box=_box(10, 5, 200, 60))
    row = page.add("row", inner, box=_box(10, 5, 200, 20))
    page.add("cell", row, text="Title", box=_box(10, 5, 200, 20))
    page.add("button", row, name="OK", box=_box(12, 7, 60, 16))

    assert [dialog.title for dialog in detect_modal_dialogs(page.nodes)] == ["Notice"]


def test_is_descendant() -> None:
    page = _Page()
    table = page.add("table")
    row = page.add("row", table)
    cell = page.add("cell", row)
    assert is_descendant(cell, table) and not is_descendant(table, cell) and not is_descendant(table, table)
