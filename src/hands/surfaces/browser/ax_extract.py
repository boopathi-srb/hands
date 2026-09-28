"""Accessibility tree -> extracted nodes for ONE frame. Pure: input is the raw CDP
`Accessibility.getFullAXTree` node list, output is a flat list in document order.

Walk rules
- Ignored nodes and transparent roles (generic, none, paragraph, LabelText, Iframe, ...) are not kept,
  but their children are, re-parented to the nearest kept ancestor.
- InlineTextBox subtrees are skipped. Children of leaf controls (textbox editor internals, closed
  <select> popups) are skipped, so typed values never leak into surrounding text.
- StaticText directly under a text sink (cell, link, button, heading, ...) becomes part of that sink's
  text. Anywhere else it becomes a standalone 'text' run. Adjacent runs under the same parent, with no
  kept node or line break between them, are marked as merge candidates; whether they really merge is
  decided later from geometry (same line), see `assemble.merge_text_runs`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hands.core.observation import Rect
from hands.surfaces.browser.frames import FrameInfo
from hands.surfaces.browser.roles import (
    LINE_BREAK_ROLE,
    SKIPPED_SUBTREE_ROLES,
    STATIC_TEXT_ROLE,
    TEXT_ROLE,
    is_leaf,
    is_text_sink,
    normalize_role,
)

_LABEL_NATIVE_SOURCES = ("label", "labelfor", "labelwrapped")


@dataclass(eq=False)
class TextPart:
    """One StaticText: raw text plus the line boxes it occupies (filled in by geometry)."""

    text: str
    backend_node_id: int | None
    line_boxes: list[Rect] = field(default_factory=list)


@dataclass(eq=False)
class ExtractedNode:
    """A kept accessibility node, mutable while the observation is being assembled.
    Compared by identity: two identical-looking cells are still two cells."""

    role: str
    chrome_name: str
    container_path: tuple[str, ...]
    frame_id: str
    parent: ExtractedNode | None
    backend_node_id: int | None
    value: str | None = None
    enabled: bool = True
    focused: bool = False
    name_from_label: bool = False
    text_parts: list[TextPart] = field(default_factory=list)
    merge_candidate: ExtractedNode | None = None
    merged_into: ExtractedNode | None = None
    bounds: Rect | None = None
    text: str = ""
    name: str = ""
    label: str | None = None
    structural_path: str = ""

    @property
    def is_text_run(self) -> bool:
        return self.role == TEXT_ROLE


@dataclass(frozen=True)
class FrameExtraction:
    frame: FrameInfo
    nodes: list[ExtractedNode]
    document_title: str


def extract_frame(ax_nodes: list[dict[str, Any]], frame: FrameInfo) -> FrameExtraction:
    """Walk one frame's AX tree from its root and return kept nodes in document order."""
    if not ax_nodes:
        return FrameExtraction(frame=frame, nodes=[], document_title="")
    nodes_by_id = {ax_node["nodeId"]: ax_node for ax_node in ax_nodes}
    root = next((ax_node for ax_node in ax_nodes if not ax_node.get("parentId")), ax_nodes[0])
    walker = _AxWalker(nodes_by_id, frame)
    walker.visit_children(root, parent=None)
    return FrameExtraction(frame=frame, nodes=walker.nodes, document_title=ax_string(root.get("name")))


class _AxWalker:
    def __init__(self, nodes_by_id: dict[str, dict[str, Any]], frame: FrameInfo) -> None:
        self._nodes_by_id = nodes_by_id
        self._frame = frame
        self._last_run_by_parent: dict[int, ExtractedNode | None] = {}
        self.nodes: list[ExtractedNode] = []

    def visit_children(self, ax_node: dict[str, Any], parent: ExtractedNode | None) -> None:
        for child_id in ax_node.get("childIds", []):
            child = self._nodes_by_id.get(child_id)
            if child is not None:
                self._visit(child, parent)

    def _visit(self, ax_node: dict[str, Any], parent: ExtractedNode | None) -> None:
        chrome_role = ax_string(ax_node.get("role"))
        if chrome_role in SKIPPED_SUBTREE_ROLES:
            return
        if ax_node.get("ignored"):
            self.visit_children(ax_node, parent)
            return
        if chrome_role == STATIC_TEXT_ROLE:
            self._visit_static_text(ax_node, parent)
            return
        if chrome_role == LINE_BREAK_ROLE:
            self._break_text_run(parent)
            return
        role = normalize_role(chrome_role, ax_string(ax_node.get("name")))
        if role is None:
            self.visit_children(ax_node, parent)
            return
        kept = self._keep(ax_node, role, parent)
        self._break_text_run(parent)
        if not is_leaf(role):
            self.visit_children(ax_node, kept)

    def _keep(self, ax_node: dict[str, Any], role: str, parent: ExtractedNode | None) -> ExtractedNode:
        properties = ax_properties(ax_node)
        kept = ExtractedNode(
            role=role,
            chrome_name=ax_string(ax_node.get("name")),
            container_path=self._frame.container_path,
            frame_id=self._frame.frame_id,
            parent=parent,
            backend_node_id=ax_node.get("backendDOMNodeId"),
            value=control_value(ax_node, properties),
            enabled=not properties.get("disabled", False),
            focused=bool(properties.get("focused", False)),
            name_from_label=name_comes_from_label(ax_node),
        )
        self.nodes.append(kept)
        return kept

    def _visit_static_text(self, ax_node: dict[str, Any], parent: ExtractedNode | None) -> None:
        part = TextPart(text=ax_string(ax_node.get("name")), backend_node_id=ax_node.get("backendDOMNodeId"))
        if parent is not None and is_text_sink(parent.role):
            parent.text_parts.append(part)
            return
        previous_run = self._last_run_by_parent.get(_parent_key(parent))
        if not part.text.strip():
            if previous_run is not None:
                previous_run.text_parts.append(part)
            return
        run = ExtractedNode(
            role=TEXT_ROLE,
            chrome_name="",
            container_path=self._frame.container_path,
            frame_id=self._frame.frame_id,
            parent=parent,
            backend_node_id=part.backend_node_id,
            text_parts=[part],
            merge_candidate=previous_run,
        )
        self.nodes.append(run)
        self._last_run_by_parent[_parent_key(parent)] = run

    def _break_text_run(self, parent: ExtractedNode | None) -> None:
        self._last_run_by_parent[_parent_key(parent)] = None


def _parent_key(parent: ExtractedNode | None) -> int:
    return id(parent) if parent is not None else 0


# ---------------------------------------------------------------- raw AX value helpers


def ax_string(ax_value: dict[str, Any] | None) -> str:
    """The string inside a CDP AXValue ({'type': ..., 'value': ...}); '' when absent."""
    if not ax_value:
        return ""
    raw = ax_value.get("value")
    return "" if raw is None else str(raw)


def ax_properties(ax_node: dict[str, Any]) -> dict[str, Any]:
    return {
        prop["name"]: prop.get("value", {}).get("value")
        for prop in ax_node.get("properties", [])
        if "name" in prop
    }


def control_value(ax_node: dict[str, Any], properties: dict[str, Any]) -> str | None:
    """Current value: text for editable controls, 'true'/'false'/'mixed' for checkable ones."""
    checked = properties.get("checked")
    if checked is not None:
        return str(checked).lower()
    raw_value = ax_node.get("value")
    return ax_string(raw_value) if raw_value is not None else None


def name_comes_from_label(ax_node: dict[str, Any]) -> bool:
    """True when the winning accessible-name source is a <label> or aria-labelledby."""
    winning = next(
        (
            source
            for source in ax_node.get("name", {}).get("sources", [])
            if ax_string(source.get("value")).strip() and not source.get("superseded")
        ),
        None,
    )
    if winning is None:
        return False
    return (
        winning.get("type") == "relatedElement"
        or winning.get("nativeSource") in _LABEL_NATIVE_SOURCES
        or winning.get("attribute") == "aria-labelledby"
    )
