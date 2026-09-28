"""The replay result contract returned to the calling agent.

Exactly four terminal statuses:
- success          checkpoint met, declared outputs returned
- business_outcome a declared OutcomeDetector fired; a legitimate answer, not an error
- escalated        a human was brought in and the run ended in human hands without completing
- failed           hard failure with step, expected, observed, and evidence paths

Recoverable conditions never appear as a status; they are recorded on the StepTrace that absorbed them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from hands.core.targets import CandidateKind

FailureCode = Literal[
    "invalid_input",
    "policy_denied",
    "precondition_timeout",
    "target_not_found",
    "action_failed",
    "postcondition_timeout",
    "extraction_failed",
    "checkpoint_failed",
    "recovery_exhausted",
    "unexpected_state",
    "surface_error",
    "run_timeout",
]


class StepTrace(BaseModel):
    step_id: str
    status: Literal["ok", "recovered", "failed", "skipped", "human"]
    matched_candidate_rank: int | None = None
    matched_candidate_kind: CandidateKind | None = None
    recoveries_applied: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    fingerprint: str | None = None


class DriftReport(BaseModel):
    """Signals that the UI differs from what was recorded. Non-fatal; feeds review and overlays."""

    fallback_steps: list[str] = Field(default_factory=list, description="Resolved by a non-primary candidate.")
    fingerprint_changes: list[str] = Field(default_factory=list, description="Steps whose fingerprint changed.")

    @property
    def drifted(self) -> bool:
        return bool(self.fallback_steps or self.fingerprint_changes)


class FailureDetail(BaseModel):
    code: FailureCode
    step_id: str | None
    message: str
    expected: str | None = None
    observed: str | None = None
    evidence: list[str] = Field(default_factory=list, description="Relative paths: screenshot, a11y snapshot, trace.")


class _ResultBase(BaseModel):
    run_id: str
    capability_id: str
    capability_version: str
    tenant_id: str | None = None
    started_at: datetime
    finished_at: datetime
    steps: list[StepTrace] = Field(default_factory=list)
    interventions: list[str] = Field(default_factory=list, description="Intervention ids raised during the run.")
    drift: DriftReport = Field(default_factory=DriftReport)
    evidence_dir: str


class SuccessResult(_ResultBase):
    status: Literal["success"] = "success"
    outputs: dict[str, Any]


class BusinessOutcomeResult(_ResultBase):
    status: Literal["business_outcome"] = "business_outcome"
    code: str
    message: str | None = None
    at_step: str | None = None


class EscalatedResult(_ResultBase):
    status: Literal["escalated"] = "escalated"
    intervention_id: str
    reason: str
    operator_note: str | None = None


class FailedResult(_ResultBase):
    status: Literal["failed"] = "failed"
    failure: FailureDetail


RunResult = Annotated[
    SuccessResult | BusinessOutcomeResult | EscalatedResult | FailedResult,
    Field(discriminator="status"),
]
