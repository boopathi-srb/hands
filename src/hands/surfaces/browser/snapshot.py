"""Build one Observation from the live page: frames -> AX trees -> geometry -> assembly -> dialogs.

Every renderer-bound call runs inside one guarded capture, so a native dialog that opens mid-capture
turns the observation into the native-dialog observation instead of hanging it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from hands.core.log import get_logger, log_failure
from hands.core.observation import Dialog, Location, Node, Observation, Rect
from hands.surfaces import structural_fingerprint
from hands.surfaces.browser.assemble import assemble_nodes
from hands.surfaces.browser.ax_extract import (
    ExtractedNode,
    FrameExtraction,
    TextPart,
    extract_frame,
)
from hands.surfaces.browser.cdp import CdpCaller
from hands.surfaces.browser.frames import FrameInfo, flatten_frame_tree
from hands.surfaces.browser.geometry import quad_to_rect
from hands.surfaces.browser.guard import run_guarded
from hands.surfaces.browser.modals import detect_modal_dialogs
from hands.surfaces.browser.native_dialogs import NativeControl, NativeDialogKeeper
from hands.surfaces.browser.settle import SettleConfig

_LOGGER = get_logger(__name__)


@dataclass(frozen=True)
class NodeHandle:
    """How act() reaches a node of the latest observation. Never leaves the browser package."""

    ref: str
    role: str
    backend_node_id: int | None
    frame_id: str | None
    bounds: Rect | None
    native_control: NativeControl | None = None


@dataclass(frozen=True)
class Snapshot:
    observation: Observation
    handles: dict[str, NodeHandle]


class SnapshotBuilder:
    def __init__(
        self,
        page: Page,
        cdp: CdpCaller,
        dialogs: NativeDialogKeeper,
        config: SettleConfig,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._page = page
        self._cdp = cdp
        self._dialogs = dialogs
        self._config = config
        self._clock = clock or (lambda: datetime.now(UTC))
        self._title = ""

    async def capture(self, include_screenshot: bool) -> Snapshot:
        if self._dialogs.has_pending_dialog:
            return self.native_dialog_snapshot()
        outcome = await run_guarded(
            self._capture_page(include_screenshot),
            self._dialogs,
            timeout_s=self._config.cdp_timeout_ms / 1000,
            operation="observe",
        )
        if outcome.status == "dialog":
            return self.native_dialog_snapshot()
        if outcome.value is None:
            log_failure(_LOGGER, "SnapshotBuilder.capture", outcome.error or "empty capture", url=self._page.url)
            return self._snapshot_of([], [], None)
        return outcome.value

    # ------------------------------------------------------------ page capture

    async def _capture_page(self, include_screenshot: bool) -> Snapshot:
        extractions = await self._extract_frames()
        extracted = [node for extraction in extractions for node in extraction.nodes]
        await attach_geometry(self._cdp, extracted)
        assembled = assemble_nodes(extracted)
        self._title = _top_document_title(extractions, self._title)
        screenshot = await self._screenshot() if include_screenshot else None
        return self._snapshot_of(assembled, detect_modal_dialogs(assembled), screenshot)

    async def _extract_frames(self) -> list[FrameExtraction]:
        frame_tree = await self._cdp.send("Page.getFrameTree")
        frames = flatten_frame_tree(frame_tree["frameTree"]) if frame_tree else []
        ax_trees = await asyncio.gather(
            *(self._cdp.send("Accessibility.getFullAXTree", {"frameId": frame.frame_id}) for frame in frames)
        )
        return [
            extract_frame(ax_tree.get("nodes", []), frame)
            for frame, ax_tree in zip(frames, ax_trees, strict=True)
            if ax_tree is not None
        ]

    async def _screenshot(self) -> bytes | None:
        try:
            return await self._page.screenshot(type="png")
        except PlaywrightError as error:
            log_failure(_LOGGER, "SnapshotBuilder._screenshot", str(error), url=self._page.url)
            return None

    def _snapshot_of(
        self, assembled: Sequence[ExtractedNode], dialogs: list[Dialog], screenshot: bytes | None
    ) -> Snapshot:
        nodes: list[Node] = []
        handles: dict[str, NodeHandle] = {}
        for position, extracted in enumerate(assembled, start=1):
            ref = f"n{position}"
            nodes.append(_to_node(extracted, ref))
            handles[ref] = NodeHandle(ref=ref, role=extracted.role, backend_node_id=extracted.backend_node_id,
                                      frame_id=extracted.frame_id, bounds=extracted.bounds)
        return Snapshot(observation=self._observation(nodes, dialogs, screenshot), handles=handles)

    # ------------------------------------------------------------ native dialog

    def native_dialog_snapshot(self) -> Snapshot:
        """While a JS dialog is open the page is frozen: report only the dialog's synthetic nodes."""
        nodes: list[Node] = []
        handles: dict[str, NodeHandle] = {}
        for position, synthetic in enumerate(self._dialogs.synthetic_nodes(), start=1):
            ref = f"n{position}"
            nodes.append(synthetic.node.model_copy(update={"ref": ref}))
            handles[ref] = NodeHandle(ref=ref, role=synthetic.node.role, backend_node_id=None, frame_id=None,
                                      bounds=None, native_control=synthetic.control)
        dialog = self._dialogs.dialog_model()
        return Snapshot(observation=self._observation(nodes, [dialog] if dialog else [], None), handles=handles)

    def _observation(self, nodes: list[Node], dialogs: list[Dialog], screenshot: bytes | None) -> Observation:
        return Observation(
            observed_at=self._clock(),
            location=Location(kind="url", value=self._page.url, title=self._title),
            nodes=nodes,
            dialogs=dialogs,
            fingerprint=structural_fingerprint(nodes),
            screenshot_png=screenshot,
        )


# ---------------------------------------------------------------- geometry


async def attach_geometry(cdp: CdpCaller, nodes: Sequence[ExtractedNode]) -> None:
    """Border boxes for element nodes, per-line content quads for every text fragment. Page-level."""
    elements = [node for node in nodes if not node.is_text_run and node.backend_node_id is not None]
    parts = [part for node in nodes for part in node.text_parts if part.backend_node_id is not None]
    element_boxes, part_lines = await asyncio.gather(
        asyncio.gather(*(fetch_border_box(cdp, node.backend_node_id) for node in elements)),
        asyncio.gather(*(fetch_line_boxes(cdp, part) for part in parts)),
    )
    for node, box in zip(elements, element_boxes, strict=True):
        node.bounds = box
    for part, line_boxes in zip(parts, part_lines, strict=True):
        part.line_boxes = line_boxes


async def fetch_border_box(cdp: CdpCaller, backend_node_id: int | None) -> Rect | None:
    if backend_node_id is None:
        return None
    result = await cdp.send("DOM.getBoxModel", {"backendNodeId": backend_node_id}, expected_failure=True)
    return quad_to_rect(result["model"]["border"]) if result else None


async def fetch_line_boxes(cdp: CdpCaller, part: TextPart) -> list[Rect]:
    result = await cdp.send("DOM.getContentQuads", {"backendNodeId": part.backend_node_id}, expected_failure=True)
    if not result:
        return []
    boxes = [quad_to_rect(quad) for quad in result.get("quads", [])]
    return [box for box in boxes if box is not None and box.width > 0]


# ---------------------------------------------------------------- conversions


def _to_node(extracted: ExtractedNode, ref: str) -> Node:
    return Node(
        ref=ref,
        role=extracted.role,
        name=extracted.name,
        text=extracted.text,
        value=extracted.value,
        label=extracted.label,
        container_path=extracted.container_path,
        structural_path=extracted.structural_path,
        bounds=extracted.bounds,
        enabled=extracted.enabled,
        focused=extracted.focused,
    )


def _top_document_title(extractions: Sequence[FrameExtraction], fallback: str) -> str:
    top: FrameInfo | None = extractions[0].frame if extractions else None
    if top is None or top.container_path != ():
        return fallback
    return extractions[0].document_title
