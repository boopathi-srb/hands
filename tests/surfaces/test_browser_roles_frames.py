"""Pure browser helpers: role normalization and frame-tree flattening."""

from __future__ import annotations

import pytest

from hands.surfaces.browser.frames import container_segment, flatten_frame_tree
from hands.surfaces.browser.roles import is_leaf, is_text_sink, normalize_role


@pytest.mark.parametrize(
    ("chrome_role", "name", "expected"),
    [
        ("LayoutTable", "", "table"),
        ("LayoutTableRow", "", "row"),
        ("LayoutTableCell", "", "cell"),
        ("gridcell", "", "cell"),
        ("searchbox", "", "textbox"),
        ("alertdialog", "Warning", "dialog"),
        ("img", "logo", "image"),
        ("MenuListOption", "Money Market", "option"),
        ("generic", "", None),
        ("generic", "Account summary", "group"),
        ("group", "  ", None),
        ("paragraph", "", None),
        ("LabelText", "", None),
        ("Iframe", "", None),
        ("none", "", None),
        ("", "", None),
        ("SomethingNew", "x", None),
    ],
)
def test_normalize_role(chrome_role: str, name: str, expected: str | None) -> None:
    assert normalize_role(chrome_role, name) == expected


def test_leaf_and_sink_roles() -> None:
    assert is_leaf("textbox") and is_leaf("combobox") and not is_leaf("cell")
    assert is_text_sink("cell") and is_text_sink("link") and not is_text_sink("table")


def test_container_segment_named_and_unnamed() -> None:
    assert container_segment("content", 3) == "frame:content"
    assert container_segment("  ", 2) == "frame[2]"
    assert container_segment("", 1) == "frame[1]"


def test_flatten_empty_frame_tree() -> None:
    assert flatten_frame_tree({}) == []


def test_flatten_nested_frameset_in_document_order() -> None:
    tree = {
        "frame": {"id": "TOP", "url": "http://x/index.html"},
        "childFrames": [
            {"frame": {"id": "A", "name": "top", "url": "http://x/top.html"}},
            {"frame": {"id": "B", "name": "nav", "url": "http://x/nav.html"}},
            {
                "frame": {"id": "C", "name": "content", "url": "http://x/outer.html"},
                "childFrames": [
                    {"frame": {"id": "D", "name": "inner", "url": "http://x/form.html"}},
                    {"frame": {"id": "E", "url": "http://x/ad.html"}},
                ],
            },
        ],
    }
    frames = flatten_frame_tree(tree)

    assert [frame.frame_id for frame in frames] == ["TOP", "A", "B", "C", "D", "E"]
    assert [frame.container_path for frame in frames] == [
        (),
        ("frame:top",),
        ("frame:nav",),
        ("frame:content",),
        ("frame:content", "frame:inner"),
        ("frame:content", "frame[2]"),
    ]
    assert frames[0].name == "" and frames[3].url == "http://x/outer.html"
