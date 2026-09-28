"""Execute steps: wait -> resolve -> policy -> act (retry once) -> postcondition, or extract.

Per step:
1. Wait until the precondition (and, for wait steps, `until`) holds and the target resolves, with monitors.
2. Record the resolution (rank/kind/fingerprint; rank > 0 is drift).
3. Extract steps read their output; wait steps are done.
4. Ask the PolicyGate: deny -> policy_denied; escalate -> a human decides (risky_action).
5. Act. A failed act re-observes (the same wait) and retries once, then fails with action_failed.
6. Wait for the postcondition, with monitors.
A timeout that no declared rule explains is escalated once per step as 'unrecoverable' when an escalator is
configured, before it becomes a hard failure (precondition_timeout / target_not_found / postcondition_timeout).
"""

from __future__ import annotations

from collections.abc import Sequence

from hands.core.actions import Action, ActResult
from hands.core.artifact import ExtractStep, Step, SubflowStep, WaitStep
from hands.core.observation import Observation
from hands.core.ports import PolicyDecision
from hands.locate import resolve_target
from hands.replay.actions import (
    ACTING_STEP_TYPES,
    ActingStep,
    act_target_for,
    action_for_step,
    describe_action,
)
from hands.replay.context import RunContext, StepStatus, StepTracker
from hands.replay.escalation import escalated_end, flow_after_resolution, request_intervention
from hands.replay.extraction import ExtractionError, extract_value, raw_node_text
from hands.replay.failures import describe_target, run_timeout_failure, timeout_failure
from hands.replay.gate import ask_policy, policy_denial
from hands.replay.monitors import MonitorScope
from hands.replay.signals import (
    Continue,
    EscalatedEnd,
    FailureEnd,
    HumanCompleted,
    Readiness,
    Ready,
    RestartRun,
    RetryStep,
    RunEnd,
    SequenceCompleted,
    SequenceResult,
    StepCompleted,
    StepFlow,
    TimedOut,
)
from hands.replay.surface_io import act
from hands.replay.waits import ReadinessCheck, condition_check, wait_until_ready

AttemptResult = StepCompleted | StepFlow | RunEnd
StepResult = StepCompleted | RestartRun | RunEnd
FinishedAttempt = StepCompleted | HumanCompleted | RestartRun | RunEnd


async def run_sequence(ctx: RunContext, steps: Sequence[Step]) -> SequenceResult:
    for step in steps:
        step_result = await execute_step(ctx, step)
        if not isinstance(step_result, StepCompleted):
            return step_result
    return SequenceCompleted()


async def execute_step(ctx: RunContext, step: Step) -> StepResult:
    if ctx.run_timed_out():
        return run_timeout_failure(ctx, step.id)
    tracker = ctx.start_tracker(step.id)
    ctx.emit("step_started", step_id=step.id, action=step.action, description=step.description, risk=step.risk)
    while True:
        attempt = await _attempt_step(ctx, step, MonitorScope(step=step, tracker=tracker))
        if not isinstance(attempt, RetryStep):
            return _finish_step(ctx, tracker, attempt)
        ctx.emit("step_retry", step_id=step.id, reason=attempt.reason)


# ---------------------------------------------------------------- one attempt


async def _attempt_step(ctx: RunContext, step: Step, scope: MonitorScope) -> AttemptResult:
    if isinstance(step, SubflowStep):
        return await _run_inline_subflow(ctx, step, scope)
    ready = await _wait_for_step_ready(ctx, step, scope)
    if not isinstance(ready, Ready):
        return ready
    _record_resolution(ctx, step, scope.tracker, ready)
    if isinstance(step, WaitStep):
        return StepCompleted()
    if isinstance(step, ExtractStep):
        return _extract(ctx, step, ready)
    if not isinstance(step, ACTING_STEP_TYPES):
        return FailureEnd(code="unexpected_state", step_id=step.id, message=f"unsupported step action '{step.action}'")
    acted = await _act_with_retry(ctx, step, scope, ready)
    if not isinstance(acted, StepCompleted):
        return acted
    return await _await_postcondition(ctx, step, scope)


async def _run_inline_subflow(ctx: RunContext, step: SubflowStep, scope: MonitorScope) -> AttemptResult:
    subflow_result = await ctx.run_subflow(step.subflow)
    if not isinstance(subflow_result, SequenceCompleted):
        return subflow_result
    return await _await_postcondition(ctx, step, scope)


async def _wait_for_step_ready(ctx: RunContext, step: Step, scope: MonitorScope) -> Ready | StepFlow | RunEnd:
    waited = await wait_until_ready(ctx, scope, pre_action_check(ctx, step), step.timeout_ms)
    if isinstance(waited, TimedOut):
        return await _on_timeout(ctx, step, waited)
    return waited


def pre_action_check(ctx: RunContext, step: Step) -> ReadinessCheck:
    """Ready = precondition holds, `until` holds (wait steps), and the target resolves (steps with a target)."""
    precondition = condition_check(ctx, step.precondition, "precondition") if step.precondition else None
    until = condition_check(ctx, step.until, "until") if isinstance(step, WaitStep) else None
    raw_target = getattr(step, "target", None)
    target = ctx.target(raw_target) if raw_target is not None else None

    def check(observation: Observation) -> Readiness:
        for condition_readiness in (precondition, until):
            if condition_readiness is not None:
                readiness = condition_readiness(observation)
                if not readiness.ready:
                    return readiness
        if target is None:
            return Readiness(ready=True, phase="precondition", detail="ready")
        resolution = resolve_target(target, observation)
        if resolution is None:
            return Readiness(ready=False, phase="target", detail=f"target {describe_target(target)}; none matched")
        return Readiness(ready=True, phase="target", detail="target resolved", resolution=resolution)

    return check


def _record_resolution(ctx: RunContext, step: Step, tracker: StepTracker, ready: Ready) -> None:
    resolution = ready.resolution
    tracker.record_resolution(resolution, ready.observation)
    ctx.emit(
        "observation",
        step_id=step.id,
        location=ready.observation.location.value,
        fingerprint=ready.observation.fingerprint,
        node_count=len(ready.observation.nodes),
    )
    if resolution is None:
        return
    if resolution.rank > 0:
        ctx.state.note_fallback(step.id)
    ctx.emit(
        "target_resolved",
        step_id=step.id,
        rank=resolution.rank,
        candidate_kind=resolution.candidate_kind,
        ambiguous=resolution.ambiguous,
        match_count=resolution.match_count,
        node_ref=resolution.node.ref if resolution.node else None,
    )


# ---------------------------------------------------------------- acting


async def _act_with_retry(ctx: RunContext, step: ActingStep, scope: MonitorScope, ready: Ready) -> AttemptResult:
    action = action_for_step(ctx, step)
    first_attempt = await _guarded_act(ctx, step, action, ready)
    if not isinstance(first_attempt, ActResult) or first_attempt.ok:
        return _after_act(first_attempt)
    ctx.emit("action_retry", step_id=step.id, error=first_attempt.error)
    ready_again = await _wait_for_step_ready(ctx, step, scope)
    if not isinstance(ready_again, Ready):
        return ready_again
    _record_resolution(ctx, step, scope.tracker, ready_again)
    second_attempt = await _guarded_act(ctx, step, action, ready_again)
    if not isinstance(second_attempt, ActResult) or second_attempt.ok:
        return _after_act(second_attempt)
    return _action_failed(ctx, step, action, first_attempt, second_attempt)


def _after_act(result: ActResult | HumanCompleted | RunEnd) -> AttemptResult:
    return StepCompleted() if isinstance(result, ActResult) else result


async def _guarded_act(
    ctx: RunContext, step: ActingStep, action: Action, ready: Ready
) -> ActResult | HumanCompleted | RunEnd:
    target_node = ready.resolution.node if ready.resolution else None
    decision = ask_policy(ctx, step.id, action, ready.observation, target_node, step.risk)
    if decision.verdict == "deny":
        return policy_denial(step.id, action, decision)
    if decision.verdict == "escalate":
        human_decision = await _human_decides_risky(ctx, step, action, decision, ready.observation)
        if human_decision is not None:
            return human_decision
    ctx.emit("action", step_id=step.id, action=describe_action(action), target=_target_description(step))
    result = await act(ctx, step.id, act_target_for(ready.resolution), action)
    if isinstance(result, FailureEnd):
        return result
    ctx.emit("action_result", step_id=step.id, ok=result.ok, error=result.error)
    return result


async def _human_decides_risky(
    ctx: RunContext, step: ActingStep, action: Action, decision: PolicyDecision, observation: Observation
) -> HumanCompleted | RunEnd | None:
    """None means the operator approved and automation may perform the step."""
    resolution = await request_intervention(ctx, "risky_action", decision.reason, step, observation)
    if resolution is None:
        return policy_denial(step.id, action, decision)
    if resolution.outcome == "abort":
        return escalated_end(resolution, decision.reason)
    if resolution.outcome == "step_completed_by_human":
        return HumanCompleted(intervention_id=resolution.intervention_id)
    return None


def _action_failed(
    ctx: RunContext, step: ActingStep, action: Action, first_attempt: ActResult, second_attempt: ActResult
) -> FailureEnd:
    return FailureEnd(
        code="action_failed",
        step_id=step.id,
        message=f"{action.kind} on {_target_description(step)} failed twice: {second_attempt.error}",
        expected=f"{action.kind} on {_target_description(step)} succeeds",
        observed=f"first error: {first_attempt.error}; retry error: {second_attempt.error}",
    )


def _target_description(step: Step) -> str:
    raw_target = getattr(step, "target", None)
    if raw_target is not None:
        return repr(raw_target.description)
    return "the surface"


# ---------------------------------------------------------------- postcondition, extraction, timeouts


async def _await_postcondition(ctx: RunContext, step: Step, scope: MonitorScope) -> AttemptResult:
    if step.postcondition is None:
        return StepCompleted()
    check = condition_check(ctx, step.postcondition, "postcondition")
    waited = await wait_until_ready(ctx, scope, check, step.timeout_ms)
    if isinstance(waited, TimedOut):
        return await _on_timeout(ctx, step, waited)
    if isinstance(waited, Ready):
        ctx.emit("checkpoint", step_id=step.id, check="postcondition", ok=True)
        return StepCompleted()
    return waited


def _extract(ctx: RunContext, step: ExtractStep, ready: Ready) -> StepCompleted | FailureEnd:
    output_spec = ctx.capability.outputs[step.output]
    node = ready.resolution.node if ready.resolution else None
    if node is None:
        return _extraction_failure(step, "the target resolved to a point, not a node", "no node")
    extracted = extract_value(node, step.pattern, output_spec)
    if isinstance(extracted, ExtractionError):
        shown = "<sensitive>" if output_spec.sensitive else repr(raw_node_text(node))
        return _extraction_failure(step, extracted.reason, f"{node.role} node text {shown}")
    ctx.state.outputs[step.output] = extracted.value
    if output_spec.sensitive and ctx.ports.secret_registrar is not None:
        ctx.ports.secret_registrar(extracted.text, f"output:{step.output}")
    ctx.emit("output_extracted", step_id=step.id, output=step.output, type=output_spec.type)
    return StepCompleted()


def _extraction_failure(step: ExtractStep, reason: str, observed: str) -> FailureEnd:
    pattern_note = f" matching {step.pattern!r}" if step.pattern else ""
    return FailureEnd(
        code="extraction_failed",
        step_id=step.id,
        message=f"could not extract output '{step.output}': {reason}",
        expected=f"a value for '{step.output}' from {step.target.description!r}{pattern_note}",
        observed=observed,
    )


async def _on_timeout(ctx: RunContext, step: Step, timed_out: TimedOut) -> StepFlow | RunEnd:
    """Escalate an unexplained timeout once per step when possible; otherwise it is the hard failure."""
    failure = timeout_failure(step.id, timed_out, step.timeout_ms)
    if ctx.ports.escalator is None or step.id in ctx.state.escalated_step_ids:
        return failure
    ctx.state.escalated_step_ids.append(step.id)
    resolution = await request_intervention(ctx, "unrecoverable", failure.message, step, timed_out.observation)
    if resolution is None:
        return failure
    flow = await flow_after_resolution(ctx, resolution, failure.message, step)
    if isinstance(flow, Continue):
        return RetryStep(reason=flow.reason)
    return flow


# ---------------------------------------------------------------- finishing


def _finish_step(ctx: RunContext, tracker: StepTracker, attempt: FinishedAttempt) -> StepResult:
    if isinstance(attempt, HumanCompleted):
        tracker.completed_by_human = True
    status = _status_for(tracker, attempt)
    ctx.finish_tracker(tracker, status)
    ctx.emit("step_finished", step_id=tracker.step_id, status=status, recoveries=tracker.recoveries_applied)
    if isinstance(attempt, HumanCompleted):
        return StepCompleted()
    return attempt


def _status_for(tracker: StepTracker, attempt: FinishedAttempt) -> StepStatus:
    if isinstance(attempt, FailureEnd | EscalatedEnd):
        return "failed"
    return tracker.default_status()

