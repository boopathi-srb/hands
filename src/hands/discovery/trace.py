"""What a discovery run produces: a trace of steps and an outcome. Input to the recorder.

Traces are secret-free: typed values are stored in placeholder form (`value_template`), and every
observation has been scrubbed of credential values before it is stored.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from hands.core.artifact import Risk
from hands.core.observation import Location, Node, Observation
from hands.discovery.planner import PlannerDecision

TraceAction = Literal["open", "click", "type", "press", "select", "scroll", "extract", "human"]
StepResult = Literal["ok", "failed", "denied", "human"]
DiscoveryStatus = Literal["completed", "stuck", "escalated_abort", "budget_exhausted", "error"]
SURFACE_ACTIONS: tuple[str, ...] = ("open", "click", "type", "press", "select", "scroll")


class TraceStep(BaseModel):
    index: int
    action: TraceAction
    decision: PlannerDecision | None = Field(
        default=None, description="None for the loop's own entry-point open and for human steps."
    )
    value_template: str | None = Field(
        default=None, description="Typed text / URL in placeholder form; never a resolved secret."
    )
    node_before: Node | None = None
    observation_before: Observation
    observation_after: Observation | None = None
    result: StepResult
    error: str | None = None
    risk: Risk = "safe"
    policy_rule: str | None = None
    output_name: str | None = None
    extracted_value: str | None = None
    human_summary: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fingerprint_before(self) -> str:
        return self.observation_before.fingerprint

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fingerprint_after(self) -> str | None:
        return self.observation_after.fingerprint if self.observation_after else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def location_before(self) -> Location:
        return self.observation_before.location

    @computed_field  # type: ignore[prop-decorator]
    @property
    def location_after(self) -> Location | None:
        return self.observation_after.location if self.observation_after else None

    @property
    def is_recordable(self) -> bool:
        """An action that worked and can become a capability step."""
        return self.result == "ok" and self.action != "human"


class DiscoveryOutcome(BaseModel):
    run_id: str
    goal: str
    entry_point: str
    status: DiscoveryStatus
    reason: str = ""
    trace: list[TraceStep] = Field(default_factory=list)
    extracted: dict[str, str] = Field(default_factory=dict)
    final_observation: Observation | None = None
    input_values: dict[str, str] = Field(
        default_factory=dict, description="Run values of declared inputs (not secrets); used to parameterize."
    )
    credential_names: list[str] = Field(default_factory=list, description="e.g. 'teller.password'")
    planner_calls: int = 0
    invalid_decisions: int = 0
    interventions: list[str] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime


def compact_trace(outcome: DiscoveryOutcome) -> dict[str, object]:
    """Outcome without observations: what evidence stores as the discovery summary."""
    return {
        "run_id": outcome.run_id,
        "goal": outcome.goal,
        "status": outcome.status,
        "reason": outcome.reason,
        "extracted": outcome.extracted,
        "planner_calls": outcome.planner_calls,
        "invalid_decisions": outcome.invalid_decisions,
        "interventions": outcome.interventions,
        "steps": [_compact_step(step) for step in outcome.trace],
    }


def _compact_step(step: TraceStep) -> dict[str, object]:
    return {
        "index": step.index,
        "action": step.action,
        "node_ref": step.node_before.ref if step.node_before else None,
        "node_role": step.node_before.role if step.node_before else None,
        "node_name": step.node_before.name if step.node_before else None,
        "value": step.value_template,
        "result": step.result,
        "error": step.error,
        "risk": step.risk,
        "rationale": step.decision.rationale if step.decision else None,
        "output_name": step.output_name,
        "human_summary": step.human_summary,
        "location_before": step.location_before.value,
        "location_after": step.location_after.value if step.location_after else None,
    }
