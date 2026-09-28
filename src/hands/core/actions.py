"""Surface-neutral actions. No 'navigate', no 'fill selector'."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Point(BaseModel):
    model_config = ConfigDict(frozen=True)
    x: float
    y: float


class NodeRef(BaseModel):
    """Act on a node from the most recent observation."""

    model_config = ConfigDict(frozen=True)
    ref: str


ActTarget = NodeRef | Point | None


class OpenAction(BaseModel):
    kind: Literal["open"] = "open"
    entry_point: str = Field(description="URL for web; bundle id or app path for desktop.")


class ClickAction(BaseModel):
    kind: Literal["click"] = "click"


class TypeAction(BaseModel):
    kind: Literal["type"] = "type"
    text: str
    clear_first: bool = True


class PressAction(BaseModel):
    kind: Literal["press"] = "press"
    key: str = Field(description="Key name: Enter, Tab, Escape, ArrowDown, ...")


class SelectAction(BaseModel):
    kind: Literal["select"] = "select"
    option: str = Field(description="Visible option text.")


class ScrollAction(BaseModel):
    kind: Literal["scroll"] = "scroll"
    direction: Literal["up", "down"] = "down"
    amount: int = Field(default=3, ge=1, le=20)


Action = Annotated[
    OpenAction | ClickAction | TypeAction | PressAction | SelectAction | ScrollAction,
    Field(discriminator="kind"),
]

ActionKind = Literal["open", "click", "type", "press", "select", "scroll"]


class ActResult(BaseModel):
    ok: bool
    error: str | None = None
