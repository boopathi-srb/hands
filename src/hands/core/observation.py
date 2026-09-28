"""What a Surface sees. Identical shape for web, desktop, and fake surfaces."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Rect(BaseModel):
    """Screen-space bounding box in CSS/device-independent pixels, relative to the viewport or window."""

    model_config = ConfigDict(frozen=True)

    x: float
    y: float
    width: float
    height: float

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2


class Node(BaseModel):
    """One accessibility node. `ref` is only valid for the observation that produced it."""

    model_config = ConfigDict(frozen=True)

    ref: str = Field(description="Per-observation handle, e.g. 'n42'. Never persisted into artifacts.")
    role: str = Field(description="Normalized a11y role: button, link, textbox, cell, row, heading, dialog, ...")
    name: str = Field(default="", description="Accessible name.")
    text: str = Field(default="", description="Visible text content, whitespace-collapsed.")
    value: str | None = Field(default=None, description="Current value for editable controls.")
    label: str | None = Field(default=None, description="Nearest associated or adjacent label text, if any.")
    container_path: tuple[str, ...] = Field(
        default=(),
        description="Frames on web ('frame:content'), windows/panes on desktop ('window:Member Detail').",
    )
    structural_path: str = Field(
        default="",
        description="Role-indexed path inside its container, e.g. 'table[1]/row[3]/cell[2]'. Never a DOM/CSS path.",
    )
    bounds: Rect | None = None
    enabled: bool = True
    focused: bool = False


class Dialog(BaseModel):
    """A modal, alert, native JS dialog, or OS sheet that is currently open."""

    model_config = ConfigDict(frozen=True)

    title: str = ""
    text: str = ""
    native: bool = Field(default=False, description="True for browser JS dialogs or OS alerts not in the a11y tree.")


class Location(BaseModel):
    """Where the surface currently is: a URL for web, an app + window title for desktop."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["url", "window"]
    value: str = Field(description="URL, or '<bundle_id>' for desktop.")
    title: str = ""


class Observation(BaseModel):
    """A point-in-time snapshot of the surface. The screenshot is never serialized."""

    observed_at: datetime
    location: Location
    nodes: list[Node]
    dialogs: list[Dialog] = Field(default_factory=list)
    fingerprint: str = Field(description="Structural hash (roles + structural paths), for drift detection.")
    screenshot_png: bytes | None = Field(default=None, exclude=True)

    def node_by_ref(self, ref: str) -> Node | None:
        return next((node for node in self.nodes if node.ref == ref), None)
