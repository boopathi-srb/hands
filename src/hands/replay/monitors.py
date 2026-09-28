"""Monitors run on EVERY observation of every wait phase, before the awaited state is checked.

Order:
1. Business outcome detectors in scope (unscoped, or scoped to the current step id). The first that holds
   ends the run with OutcomeEnd: a legitimate answer, not an error.
2. Recovery rules in scope: rules named in the current step's `recoveries` first (in that order), then every
   global rule in declared order. The first that holds is applied, bounded by its `max_applications` per run
   (one more match ends the run with recovery_exhausted):
   - dismiss   click the rule's target, or press Enter on a native dialog / Escape otherwise
   - retry     sleep the backoff, then keep polling
   - subflow   run the named subflow, then retry the current step or restart the run (`then`)
   - escalate  hand the live session to a human through the Escalator
Rules are data from the artifact/profile; the engine has no app-specific logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from hands.core.actions import Action, ClickAction, PressAction
from hands.core.artifact import (
    DismissResponse,
    EscalateResponse,
    OutcomeDetector,
    RecoveryRule,
    RetryResponse,
    Step,
    SubflowResponse,
)
from hands.core.observation import Observation
from hands.locate import evaluate, resolve_target
from hands.replay.actions import act_target_for, describe_action
from hands.replay.context import RunContext, StepTracker
from hands.replay.escalation import flow_after_resolution, request_intervention
from hands.replay.failures import describe_observation
from hands.replay.gate import ask_policy, policy_denial
from hands.replay.signals import (
    Continue,
    FailureEnd,
    OutcomeEnd,
    RestartRun,
    RetryStep,
    RunEnd,
    SequenceCompleted,
    StepFlow,
)
from hands.replay.surface_io import act

MonitorResult = Continue | StepFlow | RunEnd | None


@dataclass(frozen=True)
class MonitorScope:
    """Where the monitors are running: a step (with its trace tracker) or the final checkpoint (step None)."""

    step: Step | None
    tracker: StepTracker

    @property
    def step_id(self) -> str | None:
        return self.step.id if self.step else None


async def run_monitors(ctx: RunContext, scope: MonitorScope, observation: Observation) -> MonitorResult:
    """None when nothing fired; otherwise how the wait must proceed."""
    outcome = detect_outcome(ctx, scope, observation)
    if outcome is not None:
        return outcome
    rule = match_recovery(ctx, scope, observation)
    if rule is None:
        return None
    return await apply_recovery(ctx, scope, rule, observation)


# ---------------------------------------------------------------- business outcomes


def outcomes_in_scope(ctx: RunContext, step_id: str | None) -> list[OutcomeDetector]:
    return [
        detector
        for detector in ctx.capability.outcomes
        if detector.scope is None or (step_id is not None and step_id in detector.scope)
    ]


def detect_outcome(ctx: RunContext, scope: MonitorScope, observation: Observation) -> OutcomeEnd | None:
    for detector in outcomes_in_scope(ctx, scope.step_id):
        if evaluate(ctx.condition(detector.when), observation).met:
            message = outcome_message(ctx, detector, observation)
            ctx.emit("outcome_detected", step_id=scope.step_id, code=detector.code, message=message)
            return OutcomeEnd(code=detector.code, message=message, step_id=scope.step_id)
    return None


def outcome_message(ctx: RunContext, detector: OutcomeDetector, observation: Observation) -> str | None:
    if detector.message_target is None:
        return None
    resolution = resolve_target(ctx.target(detector.message_target), observation)
    if resolution is None or resolution.node is None:
        return None
    node = resolution.node
    return " ".join((node.text or node.name).split()) or None


# ---------------------------------------------------------------- recoveries


def recoveries_in_scope(ctx: RunContext, step: Step | None) -> list[RecoveryRule]:
    rules_by_name = {rule.name: rule for rule in ctx.capability.recoveries}
    step_rules = [rules_by_name[name] for name in (step.recoveries if step else []) if name in rules_by_name]
    global_rules = [rule for rule in ctx.capability.recoveries if rule.scope == "global" and rule not in step_rules]
    return [*step_rules, *global_rules]


def match_recovery(ctx: RunContext, scope: MonitorScope, observation: Observation) -> RecoveryRule | None:
    """The first rule in scope that holds. A rule whose subflow is running is suppressed: the interruption
    it handles is still on screen until that subflow has acted."""
    candidates = [
        rule for rule in recoveries_in_scope(ctx, scope.step) if rule.name not in ctx.state.active_recoveries
    ]
    return next((rule for rule in candidates if evaluate(ctx.condition(rule.when), observation).met), None)


async def apply_recovery(
    ctx: RunContext, scope: MonitorScope, rule: RecoveryRule, observation: Observation
) -> Continue | StepFlow | RunEnd:
    applications = ctx.state.count_recovery(rule.name)
    if applications > rule.max_applications:
        return _exhausted(scope, rule, applications, observation)
    scope.tracker.recoveries_applied.append(rule.name)
    ctx.emit(
        "recovery_applied",
        step_id=scope.step_id,
        recovery=rule.name,
        response=rule.response.kind,
        applications=applications,
        max_applications=rule.max_applications,
    )
    response = rule.response
    if isinstance(response, DismissResponse):
        return await _dismiss(ctx, scope, response, observation)
    if isinstance(response, RetryResponse):
        await ctx.timing.sleep(response.backoff_ms / 1000)
        return Continue(reason=f"retry after {rule.name}")
    if isinstance(response, SubflowResponse):
        return await _run_recovery_subflow(ctx, rule.name, response)
    return await _escalate_for_rule(ctx, scope, rule.name, response, observation)


def _exhausted(scope: MonitorScope, rule: RecoveryRule, applications: int, observation: Observation) -> FailureEnd:
    return FailureEnd(
        code="recovery_exhausted",
        step_id=scope.step_id,
        message=(
            f"recovery '{rule.name}' matched again after {rule.max_applications} application(s); "
            "the interruption did not clear"
        ),
        expected=f"'{rule.name}' needed at most {rule.max_applications} time(s): {rule.description}",
        observed=f"match #{applications}; {describe_observation(observation)}",
    )


async def _dismiss(
    ctx: RunContext, scope: MonitorScope, response: DismissResponse, observation: Observation
) -> Continue | FailureEnd:
    action: Action
    if response.target is None:
        has_native_dialog = any(dialog.native for dialog in observation.dialogs)
        action = PressAction(key="Enter" if has_native_dialog else "Escape")
        act_target, target_node = None, None
    else:
        resolution = resolve_target(ctx.target(response.target), observation)
        if resolution is None:
            return Continue(reason=f"dismiss control {response.target.description!r} not found yet")
        action, act_target, target_node = ClickAction(), act_target_for(resolution), resolution.node
    decision = ask_policy(ctx, scope.step_id, action, observation, target_node, "safe")
    if decision.verdict != "allow":
        return policy_denial(scope.step_id, action, decision)
    ctx.emit("action", step_id=scope.step_id, action=describe_action(action), purpose="recovery_dismiss")
    result = await act(ctx, scope.step_id, act_target, action)
    if isinstance(result, FailureEnd):
        return result
    ctx.emit("action_result", step_id=scope.step_id, ok=result.ok, error=result.error, purpose="recovery_dismiss")
    return Continue(reason="dismissed")


async def _run_recovery_subflow(
    ctx: RunContext, rule_name: str, response: SubflowResponse
) -> RetryStep | RestartRun | RunEnd:
    ctx.state.active_recoveries.append(rule_name)
    subflow_result = await ctx.run_subflow(response.subflow)
    ctx.state.active_recoveries.remove(rule_name)
    if not isinstance(subflow_result, SequenceCompleted):
        return subflow_result
    if response.then == "restart":
        return RestartRun(reason=f"recovery '{rule_name}' ran subflow '{response.subflow}' then restart")
    return RetryStep(reason=f"recovery '{rule_name}' ran subflow '{response.subflow}'")


async def _escalate_for_rule(
    ctx: RunContext, scope: MonitorScope, rule_name: str, response: EscalateResponse, observation: Observation
) -> Continue | StepFlow | RunEnd:
    resolution = await request_intervention(ctx, "stuck", response.reason, scope.step, observation)
    if resolution is None:
        return FailureEnd(
            code="unexpected_state",
            step_id=scope.step_id,
            message=f"recovery '{rule_name}' requires a human operator but no escalator is configured",
            expected="an escalator to hand the session to an operator",
            observed=describe_observation(observation),
        )
    return await flow_after_resolution(ctx, resolution, response.reason, scope.step)
