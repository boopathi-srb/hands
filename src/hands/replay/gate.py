"""Every replay action, including recovery dismissals, passes the PolicyGate before it reaches the surface."""

from __future__ import annotations

from hands.core.actions import Action
from hands.core.artifact import Risk
from hands.core.observation import Node, Observation
from hands.core.ports import PolicyDecision, PolicyRequest
from hands.replay.actions import describe_action
from hands.replay.context import RunContext
from hands.replay.signals import FailureEnd


def ask_policy(
    ctx: RunContext,
    step_id: str | None,
    action: Action,
    observation: Observation,
    target_node: Node | None,
    declared_risk: Risk,
) -> PolicyDecision:
    request = PolicyRequest(
        mode="replay",
        action=action,
        location=observation.location,
        target_node=target_node,
        declared_risk=declared_risk,
        capability_status=ctx.capability.status,
        risky_confirmed=ctx.invocation.risky_confirmed,
    )
    decision = ctx.ports.policy.check(request)
    ctx.emit(
        "policy_decision",
        step_id=step_id,
        action=describe_action(action),
        verdict=decision.verdict,
        risk=decision.risk,
        rule=decision.rule,
        reason=decision.reason,
    )
    return decision


def policy_denial(step_id: str | None, action: Action, decision: PolicyDecision) -> FailureEnd:
    return FailureEnd(
        code="policy_denied",
        step_id=step_id,
        message=f"policy refused {action.kind} (rule {decision.rule}): {decision.reason}",
        expected="the policy gate allows the action",
        observed=f"verdict '{decision.verdict}', risk '{decision.risk}', rule '{decision.rule}'",
    )
