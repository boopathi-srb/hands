"""Pure mapping from raw AX attributes to the core Node vocabulary.

The goal is that a TargetSpec written against the browser surface reads the same on a native app:
`role_name(button, "Sign On")` means the same thing whether the button is an <input type=submit>
or an NSButton. Nothing here talks to the AX API; inputs are plain attribute dicts.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from hands.surfaces.desktop_macos.ax import Attr

UNKNOWN_ROLE = "generic"
"""Roles with no mapping become 'generic', matching ARIA's catch-all used by the browser surface."""

ROLE_MAP: dict[str, str] = {
    "AXApplication": "application",
    "AXWindow": "window",
    "AXSheet": "dialog",
    "AXDrawer": "group",
    "AXButton": "button",
    "AXMenuButton": "button",
    "AXDisclosureTriangle": "button",
    "AXTextField": "textbox",
    "AXTextArea": "textbox",
    "AXSearchField": "textbox",
    "AXSecureTextField": "textbox",
    "AXStaticText": "text",
    "AXHeading": "heading",
    "AXLink": "link",
    "AXCell": "cell",
    "AXRow": "row",
    "AXColumn": "column",
    "AXTable": "table",
    "AXOutline": "table",
    "AXBrowser": "table",
    "AXList": "list",
    "AXMenuBar": "menubar",
    "AXMenuBarItem": "menuitem",
    "AXMenu": "menu",
    "AXMenuItem": "menuitem",
    "AXCheckBox": "checkbox",
    "AXRadioButton": "radio",
    "AXRadioGroup": "radiogroup",
    "AXPopUpButton": "combobox",
    "AXComboBox": "combobox",
    "AXTabGroup": "tablist",
    "AXSlider": "slider",
    "AXIncrementor": "spinbutton",
    "AXStepper": "spinbutton",
    "AXProgressIndicator": "progressbar",
    "AXBusyIndicator": "progressbar",
    "AXLevelIndicator": "meter",
    "AXImage": "image",
    "AXToolbar": "toolbar",
    "AXScrollBar": "scrollbar",
    "AXSplitter": "separator",
    "AXGroup": "group",
    "AXScrollArea": "group",
    "AXSplitGroup": "group",
    "AXLayoutArea": "group",
    "AXLayoutItem": "group",
    "AXWebArea": "document",
    "AXDateField": "textbox",
    "AXColorWell": "button",
    "AXHelpTag": "tooltip",
    "AXUnknown": UNKNOWN_ROLE,
}

SUBROLE_MAP: dict[str, str] = {
    "AXDialog": "dialog",
    "AXSystemDialog": "dialog",
    "AXTabButton": "tab",
    "AXSwitch": "switch",
    "AXToggle": "button",
    "AXSortButton": "button",
    "AXTextAttachment": "image",
    "AXContentList": "list",
    "AXDefinitionList": "list",
}

DIALOG_SUBROLES = frozenset({"AXDialog", "AXSystemDialog"})

EDITABLE_ROLES = frozenset(
    {"textbox", "combobox", "checkbox", "radio", "switch", "slider", "spinbutton"}
)
"""Roles whose AXValue is user state, reported in Node.value rather than Node.text."""

TOGGLE_ROLES = frozenset({"checkbox", "radio", "switch"})

TITLED_TEXT_ROLES = frozenset(
    {"button", "link", "menuitem", "tab", "heading", "cell", "window", "dialog"}
)
"""Roles whose visible title text is also their visible text content."""

STRUCTURAL_ROLES = frozenset({"group", UNKNOWN_ROLE})
"""Roles that are pure layout when they carry no name/text/value; the tree builder may flatten them."""

TOGGLE_STATES = {0: "false", 1: "true", 2: "mixed"}

NAME_ATTRIBUTES = (Attr.TITLE, Attr.DESCRIPTION, Attr.LABEL, Attr.HELP)

_WHITESPACE = re.compile(r"\s+")


def collapse_whitespace(raw_text: str | None) -> str:
    """Collapse runs of whitespace to single spaces and strip. None becomes ''."""
    if not raw_text:
        return ""
    return _WHITESPACE.sub(" ", raw_text).strip()


def normalize_role(ax_role: str | None, ax_subrole: str | None = None) -> str:
    """Map an AX role/subrole pair to the normalized a11y role used by every surface."""
    if ax_subrole and ax_subrole in SUBROLE_MAP:
        return SUBROLE_MAP[ax_subrole]
    if not ax_role:
        return UNKNOWN_ROLE
    return ROLE_MAP.get(ax_role, UNKNOWN_ROLE)


def is_dialog_element(ax_role: str | None, ax_subrole: str | None) -> bool:
    """True for sheets and for windows with a dialog subrole."""
    return ax_role == "AXSheet" or (ax_subrole is not None and ax_subrole in DIALOG_SUBROLES)


def format_ax_value(raw_value: Any, role: str = "") -> str:
    """Render an AXValue as text: toggles become 'true'/'false'/'mixed', numbers lose trailing '.0'."""
    if raw_value is None:
        return ""
    if isinstance(raw_value, bool):
        return "true" if raw_value else "false"
    if role in TOGGLE_ROLES and isinstance(raw_value, int | float):
        return TOGGLE_STATES.get(int(raw_value), str(raw_value))
    if isinstance(raw_value, float) and raw_value.is_integer():
        return str(int(raw_value))
    if isinstance(raw_value, int | float | str):
        return str(raw_value)
    return ""


def _first_text_attribute(attributes: Mapping[str, Any], names: tuple[str, ...]) -> str:
    for attribute_name in names:
        candidate = attributes.get(attribute_name)
        if isinstance(candidate, str):
            collapsed = collapse_whitespace(candidate)
            if collapsed:
                return collapsed
    return ""


def extract_name(attributes: Mapping[str, Any], role: str) -> str:
    """Accessible name: static text is named by its content; others by title, description, label, help.

    Text boxes fall back to their placeholder, as browsers do when there is no label.
    """
    if role == "text":
        content = collapse_whitespace(format_ax_value(attributes.get(Attr.VALUE)))
        return content or _first_text_attribute(attributes, NAME_ATTRIBUTES)
    name = _first_text_attribute(attributes, NAME_ATTRIBUTES)
    if name or role != "textbox":
        return name
    return _first_text_attribute(attributes, (Attr.PLACEHOLDER,))


def extract_text(attributes: Mapping[str, Any], role: str) -> str:
    """Visible text content: the content of static text, the title of titled controls, else ''."""
    if role == "text":
        return collapse_whitespace(format_ax_value(attributes.get(Attr.VALUE)))
    if role in TITLED_TEXT_ROLES:
        return _first_text_attribute(attributes, (Attr.TITLE,))
    return ""


def extract_value(attributes: Mapping[str, Any], role: str) -> str | None:
    """Current value for editable controls; None for everything else (matching the browser surface)."""
    if role not in EDITABLE_ROLES:
        return None
    if Attr.VALUE not in attributes:
        return ""
    return format_ax_value(attributes[Attr.VALUE], role)


def is_structural(role: str, name: str, text: str, value: str | None) -> bool:
    """A pure-layout container: group-like role with no name, text or value of its own."""
    return role in STRUCTURAL_ROLES and not name and not text and not value
