import pytest

from hands.surfaces.desktop_macos.ax import Attr
from hands.surfaces.desktop_macos.mapping import (
    ROLE_MAP,
    UNKNOWN_ROLE,
    collapse_whitespace,
    extract_name,
    extract_text,
    extract_value,
    format_ax_value,
    is_dialog_element,
    is_structural,
    normalize_role,
)

SPECIFIED_ROLES = {
    "AXButton": "button",
    "AXTextField": "textbox",
    "AXTextArea": "textbox",
    "AXStaticText": "text",
    "AXCell": "cell",
    "AXRow": "row",
    "AXTable": "table",
    "AXOutline": "table",
    "AXMenuItem": "menuitem",
    "AXCheckBox": "checkbox",
    "AXPopUpButton": "combobox",
    "AXComboBox": "combobox",
    "AXSheet": "dialog",
    "AXLink": "link",
    "AXGroup": "group",
    "AXWindow": "window",
    "AXImage": "image",
    "AXRadioButton": "radio",
    "AXTabGroup": "tablist",
}


@pytest.mark.parametrize(("ax_role", "expected"), sorted(SPECIFIED_ROLES.items()))
def test_normalize_role_specified_roles(ax_role: str, expected: str) -> None:
    assert normalize_role(ax_role) == expected


@pytest.mark.parametrize(("ax_role", "expected"), sorted(ROLE_MAP.items()))
def test_normalize_role_every_mapped_role(ax_role: str, expected: str) -> None:
    assert normalize_role(ax_role, None) == expected


@pytest.mark.parametrize("ax_role", ["AXSomethingNew", "", None, "button"])
def test_normalize_role_unknown_or_empty_is_generic(ax_role: str | None) -> None:
    assert normalize_role(ax_role) == UNKNOWN_ROLE


@pytest.mark.parametrize(
    ("ax_role", "ax_subrole", "expected"),
    [
        ("AXWindow", "AXDialog", "dialog"),
        ("AXWindow", "AXSystemDialog", "dialog"),
        ("AXWindow", "AXStandardWindow", "window"),
        ("AXRadioButton", "AXTabButton", "tab"),
        ("AXCheckBox", "AXSwitch", "switch"),
        ("AXTextField", "AXSecureTextField", "textbox"),
        ("AXButton", "AXUnknownSubrole", "button"),
    ],
)
def test_normalize_role_subrole_overrides(ax_role: str, ax_subrole: str, expected: str) -> None:
    assert normalize_role(ax_role, ax_subrole) == expected


@pytest.mark.parametrize(
    ("ax_role", "ax_subrole", "expected"),
    [
        ("AXSheet", None, True),
        ("AXWindow", "AXDialog", True),
        ("AXWindow", "AXSystemDialog", True),
        ("AXWindow", "AXStandardWindow", False),
        ("AXWindow", None, False),
        (None, None, False),
    ],
)
def test_is_dialog_element(ax_role: str | None, ax_subrole: str | None, expected: bool) -> None:
    assert is_dialog_element(ax_role, ax_subrole) is expected


@pytest.mark.parametrize(
    ("raw", "expected"), [(None, ""), ("", ""), ("  a \n\t b  ", "a b"), ("x", "x")]
)
def test_collapse_whitespace(raw: str | None, expected: str) -> None:
    assert collapse_whitespace(raw) == expected


@pytest.mark.parametrize(
    ("raw", "role", "expected"),
    [
        (None, "", ""),
        (True, "", "true"),
        (False, "", "false"),
        (0, "checkbox", "false"),
        (1, "checkbox", "true"),
        (2, "checkbox", "mixed"),
        (7, "checkbox", "7"),
        (1, "radio", "true"),
        (3.0, "slider", "3"),
        (2.5, "slider", "2.5"),
        (42, "", "42"),
        ("hello", "textbox", "hello"),
        (object(), "", ""),
    ],
)
def test_format_ax_value(raw: object, role: str, expected: str) -> None:
    assert format_ax_value(raw, role) == expected


def test_extract_name_prefers_title_then_description_then_label_then_help() -> None:
    assert extract_name({Attr.TITLE: "Sign On", Attr.DESCRIPTION: "d"}, "button") == "Sign On"
    assert extract_name({Attr.TITLE: "  ", Attr.DESCRIPTION: "Add"}, "button") == "Add"
    assert extract_name({Attr.LABEL: "Lbl"}, "button") == "Lbl"
    assert extract_name({Attr.HELP: "Tooltip"}, "button") == "Tooltip"


def test_extract_name_static_text_is_its_content() -> None:
    assert extract_name({Attr.VALUE: " Member\nNumber "}, "text") == "Member Number"


def test_extract_name_static_text_without_value_falls_back_to_description() -> None:
    assert extract_name({Attr.DESCRIPTION: "Result"}, "text") == "Result"


def test_extract_name_textbox_falls_back_to_placeholder_only_for_textboxes() -> None:
    assert extract_name({Attr.PLACEHOLDER: "Search"}, "textbox") == "Search"
    assert extract_name({Attr.PLACEHOLDER: "Search"}, "button") == ""


def test_extract_name_empty_and_non_string_attributes() -> None:
    assert extract_name({}, "button") == ""
    assert extract_name({Attr.TITLE: 12}, "button") == ""


def test_extract_text_by_role() -> None:
    assert extract_text({Attr.VALUE: "0"}, "text") == "0"
    assert extract_text({Attr.TITLE: "Continue"}, "button") == "Continue"
    assert extract_text({Attr.DESCRIPTION: "Add"}, "button") == ""
    assert extract_text({Attr.VALUE: "typed"}, "textbox") == ""
    assert extract_text({Attr.TITLE: "Layout"}, "group") == ""
    assert extract_text({}, "text") == ""


def test_extract_value_editable_and_non_editable() -> None:
    assert extract_value({Attr.VALUE: "10001"}, "textbox") == "10001"
    assert extract_value({}, "textbox") == ""
    assert extract_value({Attr.VALUE: 1}, "checkbox") == "true"
    assert extract_value({Attr.VALUE: "Money Market"}, "combobox") == "Money Market"
    assert extract_value({Attr.VALUE: "0"}, "text") is None
    assert extract_value({Attr.VALUE: 1}, "button") is None


@pytest.mark.parametrize(
    ("role", "name", "text", "value", "expected"),
    [
        ("group", "", "", None, True),
        ("generic", "", "", None, True),
        ("group", "Keypad", "", None, False),
        ("group", "", "", "x", False),
        ("button", "", "", None, False),
    ],
)
def test_is_structural(role: str, name: str, text: str, value: str | None, expected: bool) -> None:
    assert is_structural(role, name, text, value) is expected
