"""Declarative conditions: the single primitive behind checkpoints, pre/postconditions,
business-outcome detectors, and recovery triggers. Evaluated purely over an Observation."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from hands.core.targets import TargetSpec


class TextVisible(BaseModel):
    kind: Literal["text_visible"] = "text_visible"
    pattern: str
    regex: bool = False
    case_sensitive: bool = False


class NodePresent(BaseModel):
    kind: Literal["node_present"] = "node_present"
    target: TargetSpec


class LocationMatches(BaseModel):
    """Pattern over Location.value (URL path for web) and optionally title.
    Supports ':name' segments and '*' wildcards, e.g. '/member/:id/*'."""

    kind: Literal["location_matches"] = "location_matches"
    pattern: str | None = None
    title_pattern: str | None = None


class DialogOpen(BaseModel):
    kind: Literal["dialog_open"] = "dialog_open"
    title_pattern: str | None = None
    text_pattern: str | None = None
    native: bool | None = Field(
        default=None, description="True: only browser/OS-native dialogs. False: only in-page modals. None: any."
    )


class ValueMatches(BaseModel):
    kind: Literal["value_matches"] = "value_matches"
    target: TargetSpec
    pattern: str = Field(description="Regex matched against the node's value, else text.")


class AllOf(BaseModel):
    kind: Literal["all_of"] = "all_of"
    conditions: list[Condition] = Field(min_length=1)


class AnyOf(BaseModel):
    kind: Literal["any_of"] = "any_of"
    conditions: list[Condition] = Field(min_length=1)


class Not(BaseModel):
    kind: Literal["not"] = "not"
    condition: Condition


Condition = Annotated[
    TextVisible | NodePresent | LocationMatches | DialogOpen | ValueMatches | AllOf | AnyOf | Not,
    Field(discriminator="kind"),
]

AllOf.model_rebuild()
AnyOf.model_rebuild()
Not.model_rebuild()
