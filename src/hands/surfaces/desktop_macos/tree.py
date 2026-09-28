"""Walk an application's AX tree and build the core Observation pieces.

Mapping to the core model:
- One container per window: `window:<title>`; a sheet attached to a window nests a second container
  `sheet:<title>` (so a sheet's controls read `("window:Save", "sheet:Replace?")`). This mirrors
  frames on the web (`frame:content`).
- `structural_path` is role-indexed inside its container (`table[1]/row[3]/cell[2]`), 1-based per role
  among siblings. Pure-layout groups (group-like role with no name/text/value) are flattened: they get
  no node and no path segment, and their children count as siblings of the group's parent.
- Coordinates: `Node.bounds` are WINDOW-RELATIVE points (AXPosition minus the owning window's
  AXPosition). That matches the core's "relative to the viewport or window" convention and the
  window-only screenshot, so a Point target or a live-view pointer event uses the same frame as bounds.
  Each ref also keeps its window's screen origin, so the surface converts back to screen coordinates
  for CGEvent input.
- Windows are walked focused-first; the first window is the Location title.
- Limits: depth, emitted-node count and a raw-visit budget bound the IPC cost of huge trees.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from hands.core.log import get_logger
from hands.core.observation import Dialog, Location, Node, Rect
from hands.surfaces.desktop_macos.ax import Attr, AxBackend, AxElement, AxPoint, AxSize
from hands.surfaces.desktop_macos.labeling import assign_geometric_labels
from hands.surfaces.desktop_macos.mapping import (
    collapse_whitespace,
    extract_name,
    extract_text,
    extract_value,
    is_dialog_element,
    is_structural,
    normalize_role,
)

logger = get_logger(__name__)

ELEMENT_ATTRIBUTES: tuple[str, ...] = (
    Attr.ROLE,
    Attr.SUBROLE,
    Attr.TITLE,
    Attr.DESCRIPTION,
    Attr.LABEL,
    Attr.HELP,
    Attr.VALUE,
    Attr.PLACEHOLDER,
    Attr.TITLE_UI_ELEMENT,
    Attr.POSITION,
    Attr.SIZE,
    Attr.ENABLED,
    Attr.FOCUSED,
    Attr.CHILDREN,
)

TITLE_ELEMENT_ATTRIBUTES: tuple[str, ...] = (Attr.VALUE, Attr.TITLE, Attr.DESCRIPTION)

NAME_FROM_CONTENT_ROLES = frozenset(
    {"button", "link", "cell", "row", "heading", "menuitem", "tab", "radio", "checkbox"}
)
"""ARIA name-from-content roles: an unnamed one is named by its descendant static text."""

SHEET_AX_ROLE = "AXSheet"
ORIGIN = AxPoint(0.0, 0.0)


@dataclass(frozen=True)
class TreeLimits:
    max_depth: int = 30
    max_nodes: int = 1500
    max_visited: int = 6000
    max_text_chars: int = 500


@dataclass(frozen=True)
class WindowFrame:
    """A walked window: its title, container, and screen-space frame."""

    title: str
    container_path: tuple[str, ...]
    origin: AxPoint
    size: AxSize
    focused: bool


@dataclass(frozen=True)
class RefEntry:
    """What `act()` needs for a ref: the live element and the screen origin of its window."""

    element: AxElement
    window_origin: AxPoint


@dataclass
class TreeSnapshot:
    location: Location
    nodes: list[Node]
    dialogs: list[Dialog]
    fingerprint: str
    windows: list[WindowFrame] = field(default_factory=list)
    entries_by_ref: dict[str, RefEntry] = field(default_factory=dict)
    truncated: bool = False

    @property
    def primary_window(self) -> WindowFrame | None:
        return self.windows[0] if self.windows else None

    def screen_center(self, ref: str) -> AxPoint | None:
        """Screen-space center of a node, for CGEvent input. None if unknown or unbounded."""
        node = next((candidate for candidate in self.nodes if candidate.ref == ref), None)
        entry = self.entries_by_ref.get(ref)
        if node is None or entry is None or node.bounds is None:
            return None
        return AxPoint(
            entry.window_origin.x + node.bounds.center_x,
            entry.window_origin.y + node.bounds.center_y,
        )


@dataclass
class _RawElement:
    element: AxElement
    depth: int
    attributes: dict[str, Any]
    ax_role: str
    role: str
    name: str
    text: str
    value: str | None

    @property
    def children(self) -> list[AxElement]:
        raw_children = self.attributes.get(Attr.CHILDREN)
        return list(raw_children) if isinstance(raw_children, list) else []

    @property
    def is_sheet(self) -> bool:
        return self.ax_role == SHEET_AX_ROLE


# ---------------------------------------------------------------- pure helpers


def compute_fingerprint(nodes: list[Node]) -> str:
    """Structural hash of sorted (container_path, structural_path, role). Same recipe as the web surface."""
    structure = sorted(
        (list(node.container_path), node.structural_path, node.role) for node in nodes
    )
    return hashlib.sha256(json.dumps(structure).encode("utf-8")).hexdigest()[:16]


def content_signature(nodes: list[Node]) -> str:
    """Hash of structure plus visible content, used to decide the UI has settled between polls."""
    content = [
        (
            list(node.container_path),
            node.structural_path,
            node.role,
            node.name,
            node.text,
            node.value,
            node.enabled,
        )
        for node in nodes
    ]
    return hashlib.sha256(json.dumps(content).encode("utf-8")).hexdigest()


def truncate_text(raw_text: str, max_chars: int) -> str:
    return raw_text if len(raw_text) <= max_chars else raw_text[:max_chars]


def relative_bounds(position: Any, size: Any, window_origin: AxPoint) -> Rect | None:
    """Window-relative Rect from AXPosition/AXSize, or None when either is missing."""
    if not isinstance(position, AxPoint) or not isinstance(size, AxSize):
        return None
    return Rect(
        x=position.x - window_origin.x,
        y=position.y - window_origin.y,
        width=size.width,
        height=size.height,
    )


def join_structural_path(parent_path: str, role: str, index: int) -> str:
    segment = f"{role}[{index}]"
    return f"{parent_path}/{segment}" if parent_path else segment


def dialog_text(nodes: list[Node], container_path: tuple[str, ...], max_chars: int) -> str:
    texts = [
        node.text
        for node in nodes
        if node.container_path == container_path and node.role == "text" and node.text
    ]
    return truncate_text(" ".join(texts), max_chars)


def empty_snapshot(bundle_id: str) -> TreeSnapshot:
    """Snapshot for an app with no windows (or no reachable tree)."""
    return TreeSnapshot(
        location=Location(kind="window", value=bundle_id, title=""),
        nodes=[],
        dialogs=[],
        fingerprint=compute_fingerprint([]),
    )


# ---------------------------------------------------------------- walker


class _TreeWalker:
    def __init__(self, backend: AxBackend, limits: TreeLimits) -> None:
        self._backend = backend
        self._limits = limits
        self._visited = 0
        self._truncated = False
        self._slots: list[Node | None] = []
        self._entries: dict[str, RefEntry] = {}
        self._windows: list[WindowFrame] = []
        self._dialog_containers: list[tuple[str, tuple[str, ...]]] = []

    # ---------------------------------------------------- entry point

    def build(self, app_element: AxElement, bundle_id: str) -> TreeSnapshot:
        windows, has_focused_window = self._ordered_windows(app_element)
        for window_index, window_element in enumerate(windows):
            self._walk_window(window_element, focused=has_focused_window and window_index == 0)
        nodes = assign_geometric_labels([node for node in self._slots if node is not None])
        if self._truncated:
            logger.warning(
                "AX tree for %s truncated: visited=%d nodes=%d limits=%s",
                bundle_id,
                self._visited,
                len(nodes),
                self._limits,
            )
        primary_title = self._windows[0].title if self._windows else ""
        return TreeSnapshot(
            location=Location(kind="window", value=bundle_id, title=primary_title),
            nodes=nodes,
            dialogs=self._build_dialogs(nodes),
            fingerprint=compute_fingerprint(nodes),
            windows=self._windows,
            entries_by_ref=self._entries,
            truncated=self._truncated,
        )

    def _ordered_windows(self, app_element: AxElement) -> tuple[list[AxElement], bool]:
        focused_window = self._backend.attribute(app_element, Attr.FOCUSED_WINDOW).value
        all_windows_result = self._backend.attribute(app_element, Attr.WINDOWS)
        all_windows = all_windows_result.value if isinstance(all_windows_result.value, list) else []
        if focused_window is None:
            return list(all_windows), False
        others = [window for window in all_windows if window != focused_window]
        return [focused_window, *others], True

    def _build_dialogs(self, nodes: list[Node]) -> list[Dialog]:
        return [
            Dialog(
                title=title,
                text=dialog_text(nodes, container_path, self._limits.max_text_chars),
                native=False,
            )
            for title, container_path in self._dialog_containers
        ]

    # ---------------------------------------------------- windows and sheets

    def _walk_window(self, window_element: AxElement, focused: bool) -> None:
        window = self._read(window_element, depth=0)
        if window is None:
            return
        title = collapse_whitespace(str(window.attributes.get(Attr.TITLE) or ""))
        container_path = (f"window:{title}",)
        position = window.attributes.get(Attr.POSITION)
        size = window.attributes.get(Attr.SIZE)
        origin = position if isinstance(position, AxPoint) else ORIGIN
        frame_size = size if isinstance(size, AxSize) else AxSize(0.0, 0.0)
        self._windows.append(WindowFrame(title, container_path, origin, frame_size, focused))
        if is_dialog_element(window.ax_role, window.attributes.get(Attr.SUBROLE)):
            self._dialog_containers.append((title, container_path))
        self._emit_children(window, container_path, "", origin)

    def _walk_sheet(
        self, sheet: _RawElement, parent_container: tuple[str, ...], origin: AxPoint
    ) -> None:
        title = sheet.name or sheet.text
        container_path = (*parent_container, f"sheet:{title}")
        self._dialog_containers.append((title, container_path))
        self._emit_children(sheet, container_path, "", origin)

    # ---------------------------------------------------- elements

    def _read(self, element: AxElement, depth: int) -> _RawElement | None:
        if self._visited >= self._limits.max_visited:
            self._truncated = True
            return None
        self._visited += 1
        attributes_result = self._backend.attributes(element, ELEMENT_ATTRIBUTES)
        if not attributes_result.ok or attributes_result.value is None:
            return None
        attributes = attributes_result.value
        ax_role = str(attributes.get(Attr.ROLE) or "")
        role = normalize_role(ax_role, attributes.get(Attr.SUBROLE))
        max_chars = self._limits.max_text_chars
        return _RawElement(
            element=element,
            depth=depth,
            attributes=attributes,
            ax_role=ax_role,
            role=role,
            name=truncate_text(extract_name(attributes, role), max_chars),
            text=truncate_text(extract_text(attributes, role), max_chars),
            value=_truncate_optional(extract_value(attributes, role), max_chars),
        )

    def _effective_children(self, parent: _RawElement) -> list[_RawElement]:
        """Children with pure-layout groups flattened away (recursively)."""
        if parent.depth >= self._limits.max_depth:
            self._truncated = self._truncated or bool(parent.children)
            return []
        effective: list[_RawElement] = []
        for child_element in parent.children:
            child = self._read(child_element, parent.depth + 1)
            if child is None:
                continue
            if not child.is_sheet and is_structural(
                child.role, child.name, child.text, child.value
            ):
                effective.extend(self._effective_children(child))
            else:
                effective.append(child)
        return effective

    def _emit_children(
        self,
        parent: _RawElement,
        container_path: tuple[str, ...],
        parent_path: str,
        origin: AxPoint,
    ) -> list[Node]:
        """Emit nodes for the parent's effective children in pre-order; return every node emitted below."""
        emitted: list[Node] = []
        role_counts: dict[str, int] = {}
        for child in self._effective_children(parent):
            if child.is_sheet:
                self._walk_sheet(child, container_path, origin)
                continue
            if len(self._slots) >= self._limits.max_nodes:
                self._truncated = True
                break
            role_counts[child.role] = role_counts.get(child.role, 0) + 1
            structural_path = join_structural_path(parent_path, child.role, role_counts[child.role])
            slot_index = len(self._slots)
            self._slots.append(None)
            ref = f"n{slot_index + 1}"
            descendants = self._emit_children(child, container_path, structural_path, origin)
            node = self._make_node(child, ref, container_path, structural_path, origin, descendants)
            self._slots[slot_index] = node
            self._entries[ref] = RefEntry(element=child.element, window_origin=origin)
            emitted.append(node)
            emitted.extend(descendants)
        return emitted

    def _make_node(
        self,
        raw: _RawElement,
        ref: str,
        container_path: tuple[str, ...],
        structural_path: str,
        origin: AxPoint,
        descendants: list[Node],
    ) -> Node:
        label = self._title_element_text(raw.attributes) or None
        content_text = self._descendant_text(raw.role, descendants)
        name = raw.name or label or (content_text if raw.role in NAME_FROM_CONTENT_ROLES else "")
        text = raw.text or content_text
        return Node(
            ref=ref,
            role=raw.role,
            name=name,
            text=text,
            value=raw.value,
            label=label,
            container_path=container_path,
            structural_path=structural_path,
            bounds=relative_bounds(
                raw.attributes.get(Attr.POSITION), raw.attributes.get(Attr.SIZE), origin
            ),
            enabled=raw.attributes.get(Attr.ENABLED) is not False,
            focused=raw.attributes.get(Attr.FOCUSED) is True,
        )

    def _descendant_text(self, role: str, descendants: list[Node]) -> str:
        if role not in NAME_FROM_CONTENT_ROLES:
            return ""
        texts = [node.text for node in descendants if node.role == "text" and node.text]
        return truncate_text(" ".join(texts), self._limits.max_text_chars)

    def _title_element_text(self, attributes: dict[str, Any]) -> str:
        """Text of the element named by AXTitleUIElement (the programmatic label), if any."""
        title_element = attributes.get(Attr.TITLE_UI_ELEMENT)
        if title_element is None:
            return ""
        title_attributes = (
            self._backend.attributes(title_element, TITLE_ELEMENT_ATTRIBUTES).value or {}
        )
        for attribute_name in TITLE_ELEMENT_ATTRIBUTES:
            candidate = title_attributes.get(attribute_name)
            if isinstance(candidate, str) and collapse_whitespace(candidate):
                return truncate_text(collapse_whitespace(candidate), self._limits.max_text_chars)
        return ""


def _truncate_optional(raw_text: str | None, max_chars: int) -> str | None:
    return None if raw_text is None else truncate_text(raw_text, max_chars)


def build_tree_snapshot(
    backend: AxBackend, app_element: AxElement, bundle_id: str, limits: TreeLimits | None = None
) -> TreeSnapshot:
    """Walk every window of the application (focused first) into Nodes, dialogs and a fingerprint."""
    return _TreeWalker(backend, limits or TreeLimits()).build(app_element, bundle_id)
