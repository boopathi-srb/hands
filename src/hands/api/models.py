"""Request bodies of the HTTP API (docs/API.md). Shape errors become 422 `invalid_request`; semantic checks
(known tenant, capability, planner) happen in `hands.api.validation` with their own 4xx codes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from target_app.faults import MAX_FAULT_COUNT

ApiEscalation = Literal["console", "none"]
MAX_INPUTS = 32
MAX_TEXT = 4000


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FaultRequest(_Body):
    name: str = Field(min_length=1, max_length=64)
    count: int = Field(default=1, ge=1, le=MAX_FAULT_COUNT)


class ReplayStartBody(_Body):
    capability_id: str = Field(min_length=1, max_length=128)
    version: str | None = Field(default=None, max_length=32)
    inputs: dict[str, str] = Field(default_factory=dict, max_length=MAX_INPUTS)
    tenant: str | None = Field(default="lakeside", max_length=64)
    faults: list[FaultRequest] = Field(default_factory=list, max_length=10)
    risky_confirmed: bool = False
    escalation: ApiEscalation = "console"


class DiscoveryStartBody(_Body):
    goal: str = Field(min_length=1, max_length=MAX_TEXT)
    inputs: dict[str, str] = Field(default_factory=dict, max_length=MAX_INPUTS)
    sensitive_inputs: list[str] = Field(default_factory=list, max_length=MAX_INPUTS)
    capability_id: str = Field(default="coreone.member_balance", min_length=1, max_length=128)
    title: str = Field(default="Member savings balance", min_length=1, max_length=200)
    description: str = Field(
        default="Look up a member by member number and return the balance of their savings share.",
        min_length=1, max_length=MAX_TEXT,
    )
    tenant: str = Field(default="lakeside", max_length=64)
    planner: str = Field(default="anthropic", min_length=1, max_length=32)
    model: str | None = Field(default=None, max_length=128)
    max_steps: int = Field(default=25, ge=1, le=100)
    escalation: ApiEscalation = "console"


class ApproveBody(_Body):
    version: str | None = Field(default=None, max_length=32)
