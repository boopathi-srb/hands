"""In-page modal detection over assembled nodes. Pure.

Two sources:
1. Semantic: any node with role dialog/alertdialog (normalized to 'dialog').
2. Heuristic, for legacy apps that draw a positioned <table> over the page without ARIA:
   a table is reported as a dialog when ALL of these hold
   - its first row has text (the title row, e.g. 'System Notice'),
   - it contains at least one button or link (something to dismiss it with),
   - the center of at least one EARLIER node (document order) of the same frame, which is neither its
     ancestor nor its descendant, lies inside the table's box. Normal flow never stacks unrelated
     boxes, so that overlap means the table is positioned over content that precedes it. Requiring
     the covered node to come earlier makes the test directional: the content underneath is not
     itself reported as an overlay.
   Limits: z-index is not in the AX tree, so an overlay placed BEFORE the content it covers in the
   DOM is missed; overlays built from divs without a dialog role are missed; a table positioned over
   empty space is missed.
"""

from __future__ import annotations

from collections.abc import Sequence

from hands.core.observation import Dialog
from hands.surfaces.browser.ax_extract import ExtractedNode
from hands.surfaces.browser.geometry import contains_point
from hands.surfaces.browser.roles import DIALOG_ROLES, TEXT_ROLE

_DIALOG_TEXT_ROLES = (TEXT_ROLE, "cell", "columnheader", "rowheader", "heading")
_DISMISS_CONTROL_ROLES = ("button", "link")


def detect_modal_dialogs(nodes: Sequence[ExtractedNode]) -> list[Dialog]:
    semantic = [semantic_dialog(node, nodes) for node in nodes if node.role in DIALOG_ROLES]
    return [*semantic, *overlay_table_dialogs(nodes)]


def semantic_dialog(dialog_node: ExtractedNode, nodes: Sequence[ExtractedNode]) -> Dialog:
    descendants = [node for node in nodes if is_descendant(node, dialog_node)]
    headings = [node.text for node in descendants if node.role == "heading" and node.text]
    title = dialog_node.name or (headings[0] if headings else "")
    return Dialog(title=title, text=_joined_text(descendants, exclude=title))


def overlay_table_dialogs(nodes: Sequence[ExtractedNode]) -> list[Dialog]:
    detected_tables: list[ExtractedNode] = []
    dialogs: list[Dialog] = []
    for position, table in enumerate(nodes):
        if table.role != "table" or any(is_descendant(table, found) for found in detected_tables):
            continue
        dialog = overlay_table_dialog(table, nodes, earlier_nodes=nodes[:position])
        if dialog is not None:
            detected_tables.append(table)
            dialogs.append(dialog)
    return dialogs


def overlay_table_dialog(
    table: ExtractedNode, nodes: Sequence[ExtractedNode], earlier_nodes: Sequence[ExtractedNode]
) -> Dialog | None:
    if table.bounds is None or _inside_semantic_dialog(table):
        return None
    descendants = [node for node in nodes if is_descendant(node, table)]
    rows = [node for node in descendants if node.role == "row" and node.parent is table]
    if not rows:
        return None
    title_row_nodes = [node for node in descendants if node is rows[0] or is_descendant(node, rows[0])]
    title = _joined_text(title_row_nodes, exclude="")
    has_dismiss_control = any(node.role in _DISMISS_CONTROL_ROLES for node in descendants)
    if not title or not has_dismiss_control or not _covers_earlier_content(table, earlier_nodes):
        return None
    body_nodes = [node for node in descendants if node not in title_row_nodes]
    return Dialog(title=title, text=_joined_text(body_nodes, exclude=title))


def is_descendant(node: ExtractedNode, ancestor: ExtractedNode) -> bool:
    current = node.parent
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent
    return False


def _covers_earlier_content(table: ExtractedNode, earlier_nodes: Sequence[ExtractedNode]) -> bool:
    table_box = table.bounds
    if table_box is None:
        return False
    for other in earlier_nodes:
        unrelated = not is_descendant(table, other)
        if (
            unrelated
            and other.frame_id == table.frame_id
            and other.bounds is not None
            and contains_point(table_box, other.bounds.center_x, other.bounds.center_y)
        ):
            return True
    return False


def _inside_semantic_dialog(node: ExtractedNode) -> bool:
    current = node.parent
    while current is not None:
        if current.role in DIALOG_ROLES:
            return True
        current = current.parent
    return False


def _joined_text(nodes: Sequence[ExtractedNode], exclude: str) -> str:
    texts = [node.text for node in nodes if node.role in _DIALOG_TEXT_ROLES and node.text and node.text != exclude]
    return " ".join(texts)
