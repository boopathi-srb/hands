"""How a recorded step identifies its control, independent of surface technology.

A TargetSpec is a ranked list of candidates. Replay tries them in order and records which rank matched;
a match below rank 0 is a drift signal. Every candidate kind is computable from an accessibility tree plus
bounds, so the same spec resolves on web, legacy web, and desktop surfaces.

String fields may contain `{{param}}` placeholders, filled from invocation inputs at replay time.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class _CandidateBase(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0, description="Recorder's estimate of robustness.")
    reason: str = Field(description="Why this candidate should survive; shown to human reviewers.")


class RoleNameCandidate(_CandidateBase):
    """Most robust: semantic role plus accessible name."""

    kind: Literal["role_name"] = "role_name"
    role: str
    name: str
    exact: bool = True


class LabelCandidate(_CandidateBase):
    """A form control identified by its visible label (for/aria-labelledby or adjacency)."""

    kind: Literal["label"] = "label"
    label: str
    role: str | None = None


class TextAnchorCandidate(_CandidateBase):
    """A control located relative to stable anchor text, e.g. the cell right of 'Savings'."""

    kind: Literal["text_anchor"] = "text_anchor"
    anchor_text: str
    relation: Literal["right_of", "below", "same_row", "inside"]
    role: str | None = None
    ordinal: int = Field(default=0, ge=0, description="Which match, in reading order, when several qualify.")


class StructuralCandidate(_CandidateBase):
    """Container path plus role-indexed a11y path. Brittle to layout change; stable in slow-moving apps."""

    kind: Literal["structural"] = "structural"
    container_path: tuple[str, ...]
    structural_path: str


class VisualAnchorCandidate(_CandidateBase):
    """Last resort: a point offset from the center of an anchor text node. For canvas/no-a11y regions."""

    kind: Literal["visual_anchor"] = "visual_anchor"
    anchor_text: str
    dx: float
    dy: float


Candidate = Annotated[
    RoleNameCandidate | LabelCandidate | TextAnchorCandidate | StructuralCandidate | VisualAnchorCandidate,
    Field(discriminator="kind"),
]

CandidateKind = Literal["role_name", "label", "text_anchor", "structural", "visual_anchor"]


class TargetSpec(BaseModel):
    description: str = Field(description="Human-readable name of the control, e.g. 'Member ID search box'.")
    candidates: list[Candidate] = Field(min_length=1)
