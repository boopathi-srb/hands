"""Frame walking: CDP `Page.getFrameTree` -> ordered frames with their container paths. Pure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FrameInfo:
    """One document in the page. The top document has container_path ()."""

    frame_id: str
    container_path: tuple[str, ...]
    url: str
    name: str


def container_segment(frame_name: str, sibling_position: int) -> str:
    """'frame:<name>' from the frame element's name attribute; 'frame[<n>]' (1-based) when unnamed."""
    cleaned_name = frame_name.strip()
    return f"frame:{cleaned_name}" if cleaned_name else f"frame[{sibling_position}]"


def flatten_frame_tree(frame_tree: dict[str, Any]) -> list[FrameInfo]:
    """Pre-order (document order) list of frames: top document first, then each child subtree."""
    if not frame_tree or "frame" not in frame_tree:
        return []
    frames: list[FrameInfo] = []
    _collect_frames(frame_tree, (), frames)
    return frames


def _collect_frames(tree_node: dict[str, Any], container_path: tuple[str, ...], frames: list[FrameInfo]) -> None:
    frame = tree_node["frame"]
    frames.append(
        FrameInfo(
            frame_id=frame["id"],
            container_path=container_path,
            url=frame.get("url", ""),
            name=frame.get("name", "") or "",
        )
    )
    for position, child in enumerate(tree_node.get("childFrames", []), start=1):
        child_name = child["frame"].get("name", "") or ""
        _collect_frames(child, (*container_path, container_segment(child_name, position)), frames)
