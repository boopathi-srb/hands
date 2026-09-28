"""Chrome accessibility roles -> normalized hands roles. Pure data and functions, no I/O.

Chrome reports ARIA roles ('button', 'cell', ...) and internal roles ('LayoutTableCell', 'StaticText',
'generic', ...). Legacy table layouts come through as LayoutTable/LayoutTableRow/LayoutTableCell; they
are normalized to table/row/cell so structural paths read the same for data and layout tables.
"""

from __future__ import annotations

STATIC_TEXT_ROLE = "StaticText"
LINE_BREAK_ROLE = "LineBreak"
TEXT_ROLE = "text"

# Subtrees that never contribute nodes or text (text rendering internals).
SKIPPED_SUBTREE_ROLES = ("InlineTextBox",)

_ROLE_MAP: dict[str, str] = {
    "button": "button",
    "PopUpButton": "button",
    "ToggleButton": "button",
    "link": "link",
    "textbox": "textbox",
    "searchbox": "textbox",
    "spinbutton": "spinbutton",
    "combobox": "combobox",
    "ComboBoxMenuButton": "combobox",
    "ComboBoxSelect": "combobox",
    "listbox": "listbox",
    "option": "option",
    "MenuListOption": "option",
    "checkbox": "checkbox",
    "switch": "switch",
    "radio": "radio",
    "slider": "slider",
    "table": "table",
    "grid": "table",
    "treegrid": "table",
    "LayoutTable": "table",
    "row": "row",
    "LayoutTableRow": "row",
    "cell": "cell",
    "gridcell": "cell",
    "LayoutTableCell": "cell",
    "columnheader": "columnheader",
    "rowheader": "rowheader",
    "heading": "heading",
    "dialog": "dialog",
    "alertdialog": "dialog",
    "alert": "alert",
    "status": "status",
    "image": "image",
    "img": "image",
    "list": "list",
    "listitem": "listitem",
    "menu": "menu",
    "menubar": "menu",
    "menuitem": "menuitem",
    "tab": "tab",
    "tablist": "tablist",
    "tabpanel": "tabpanel",
    "tree": "tree",
    "treeitem": "treeitem",
    "navigation": "navigation",
    "form": "form",
    "progressbar": "progressbar",
}

# Containers that only matter when an author gave them a name (fieldset legend, aria-label, ...).
_NAMED_GROUP_ROLES = ("group", "region", "generic", "Section", "radiogroup", "toolbar")

# Controls whose AX children are rendering internals (editor text, closed <select> popups).
LEAF_ROLES = ("textbox", "spinbutton", "combobox", "checkbox", "radio", "switch", "slider", "image",
              "progressbar")

# Nodes that absorb the StaticText directly under them into their own `text`.
TEXT_SINK_ROLES = ("cell", "columnheader", "rowheader", "heading", "link", "button", "option", "listitem",
                   "menuitem", "tab", "treeitem")

# Chrome's name for these comes from contents *including control values* (a cell holding a password
# field is named '••••••'), so their name is replaced by the visible text hands extracted itself.
NAME_FROM_OWN_TEXT_ROLES = ("cell", "columnheader", "rowheader")

LABELABLE_ROLES = ("textbox", "combobox", "listbox", "spinbutton")
LABEL_SOURCE_ROLES = (TEXT_ROLE, "cell", "columnheader", "rowheader", "heading")
DIALOG_ROLES = ("dialog",)


def normalize_role(chrome_role: str, name: str) -> str | None:
    """Normalized role, or None when the node is transparent (its children are kept, it is not)."""
    mapped = _ROLE_MAP.get(chrome_role)
    if mapped is not None:
        return mapped
    if chrome_role in _NAMED_GROUP_ROLES and name.strip():
        return "group"
    return None


def is_text_sink(role: str) -> bool:
    return role in TEXT_SINK_ROLES


def is_leaf(role: str) -> bool:
    return role in LEAF_ROLES
