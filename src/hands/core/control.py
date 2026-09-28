"""Control-transfer model: exactly one holder of a live session at a time."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Holder = Literal["automation", "human", "nobody"]


class ControlLease(BaseModel):
    session_id: str
    holder: Holder
    holder_id: str | None = Field(default=None, description="Run id for automation, operator id for human.")
    since: datetime
    reason: str = ""


class InterventionRequest(BaseModel):
    """Everything an operator needs to act, with sensitive values already redacted."""

    intervention_id: str
    session_id: str
    run_id: str
    mode: Literal["discovery", "replay"]
    kind: Literal["stuck", "unrecoverable", "risky_action", "policy_block"]
    reason: str
    capability_id: str | None = None
    goal: str | None = None
    step_id: str | None = None
    step_description: str | None = None
    location: str | None = None
    screenshot_path: str | None = None
    created_at: datetime


class HumanAction(BaseModel):
    """One operator input, captured by the live-view transport and described in artifact vocabulary."""

    at: datetime
    kind: Literal["click", "type", "press", "scroll"]
    x: float | None = None
    y: float | None = None
    key: str | None = None
    text_length: int | None = Field(default=None, description="Typed text is never stored, only its length.")
    node_role: str | None = None
    node_name: str | None = None


class InterventionResolution(BaseModel):
    intervention_id: str
    outcome: Literal["resume", "abort", "step_completed_by_human"]
    operator_id: str
    note: str = ""
    human_actions: list[HumanAction] = Field(default_factory=list)
    resolved_at: datetime
