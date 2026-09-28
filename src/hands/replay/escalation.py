"""Bring a human in through the Escalator port, and interpret what they decided.

Kinds used by replay:
- stuck          a recovery rule says a human must handle a known interruption (e.g. identity check)
- unrecoverable  a wait timed out and no declared rule explains the state
- risky_action   the policy gate wants a human decision before an irreversible step
"""

from __future__ import annotations

from typing import Literal

from hands.core.artifact import Step
from hands.core.control import InterventionRequest, InterventionResolution
from hands.core.log import get_logger, log_failure
from hands.core.observation import Observation
from hands.locate import evaluate
from hands.replay.context import RunContext
from hands.replay.signals import (
    Continue,
    EscalatedEnd,
    FailureEnd,
    HumanCompleted,
    RetryStep,
    RunEnd,
    StepFlow,
)
from hands.replay.surface_io import observe

_logger = get_logger(__name__)

EscalationKind = Literal["stuck", "unrecoverable", "risky_action"]
SYSTEM_OPERATOR = "system"


async def request_intervention(
    ctx: RunContext, kind: EscalationKind, reason: str, step: Step | None, observation: Observation
) -> InterventionResolution | None:
    """Raise an intervention and wait for its resolution. None when no escalator is configured."""
    escalator = ctx.ports.escalator
    if escalator is None:
        return None
    request = _build_request(ctx, kind, reason, step, observation)
    ctx.state.interventions.append(request.intervention_id)
    ctx.emit(
        "escalation_requested",
        intervention_id=request.intervention_id,
        intervention_kind=kind,
        reason=reason,
        step_id=request.step_id,
        screenshot_path=request.screenshot_path,
    )
    try:
        resolution = await escalator.escalate(request)
    except Exception as escalator_error:  # noqa: BLE001 - adapter boundary, becomes an abort
        log_failure(
            _logger, "request_intervention", f"escalator raised: {escalator_error!r}",
            intervention_id=request.intervention_id, step_id=request.step_id,
        )
        resolution = _system_abort(ctx, request, f"escalator failed: {escalator_error!r}")
    ctx.emit(
        "escalation_handled",
        intervention_id=request.intervention_id,
        outcome=resolution.outcome,
        operator_id=resolution.operator_id,
        note=resolution.note,
        human_action_count=len(resolution.human_actions),
    )
    return resolution


def escalated_end(resolution: InterventionResolution, reason: str) -> EscalatedEnd:
    return EscalatedEnd(
        intervention_id=resolution.intervention_id,
        reason=reason,
        operator_note=resolution.note or None,
    )


async def flow_after_resolution(
    ctx: RunContext, resolution: InterventionResolution, reason: str, step: Step | None
) -> StepFlow | Continue | RunEnd:
    """abort ends the run; step_completed_by_human moves on; resume checks whether the human already did it."""
    if resolution.outcome == "abort":
        return escalated_end(resolution, reason)
    if resolution.outcome == "step_completed_by_human":
        return HumanCompleted(intervention_id=resolution.intervention_id)
    if step is None:
        return Continue(reason=f"resumed after {resolution.intervention_id}")
    return await _flow_after_resume(ctx, resolution, step)


async def _flow_after_resume(
    ctx: RunContext, resolution: InterventionResolution, step: Step
) -> HumanCompleted | RetryStep | FailureEnd:
    observation = await observe(ctx, step.id)
    if isinstance(observation, FailureEnd):
        return observation
    if step.postcondition is not None and evaluate(ctx.condition(step.postcondition), observation).met:
        return HumanCompleted(intervention_id=resolution.intervention_id)
    return RetryStep(reason=f"resumed after {resolution.intervention_id}")


def _build_request(
    ctx: RunContext, kind: EscalationKind, reason: str, step: Step | None, observation: Observation
) -> InterventionRequest:
    intervention_id = f"{ctx.invocation.run_id}-intervention-{len(ctx.state.interventions) + 1}"
    return InterventionRequest(
        intervention_id=intervention_id,
        session_id=ctx.invocation.session_id,
        run_id=ctx.invocation.run_id,
        mode="replay",
        kind=kind,
        reason=reason,
        capability_id=ctx.capability.id,
        step_id=step.id if step else None,
        step_description=step.description if step else None,
        location=observation.location.value,
        screenshot_path=_screenshot_for(ctx, intervention_id, observation),
        created_at=ctx.timing.now(),
    )


def _screenshot_for(ctx: RunContext, intervention_id: str, observation: Observation) -> str | None:
    if not observation.screenshot_png:
        return None
    ctx.ports.evidence.snapshot(intervention_id, observation)
    return ctx.ports.evidence.screenshot(intervention_id, observation.screenshot_png)


def _system_abort(ctx: RunContext, request: InterventionRequest, note: str) -> InterventionResolution:
    return InterventionResolution(
        intervention_id=request.intervention_id,
        outcome="abort",
        operator_id=SYSTEM_OPERATOR,
        note=note,
        resolved_at=ctx.timing.now(),
    )
