"""YamlPolicyGate: the PolicyGate adapter every action passes through before it reaches a surface.

Checks, in order, stopping at the first that fails:
1. location allowlist (for `open`, the current location and the target entry point)
2. action kind allowed for the mode
3. risk classification: max(declared risk, rule-derived risk)
4. risky handling for the mode

The gate is pure and deterministic: the same request always yields the same decision, and every decision
names the rule that produced it plus a readable reason. Nothing the model says is consulted.
"""

from __future__ import annotations

from hands.core.ports import PolicyDecision, PolicyRequest
from hands.policy.checks import CheckResult, check_action_kind, check_request_location
from hands.policy.config import PolicyConfig, RiskHandling
from hands.policy.risk import RiskAssessment, classify_risk


class YamlPolicyGate:
    """Implements hands.core.ports.PolicyGate from a validated PolicyConfig."""

    def __init__(self, config: PolicyConfig) -> None:
        self._config = config

    @property
    def config(self) -> PolicyConfig:
        return self._config

    def check(self, request: PolicyRequest) -> PolicyDecision:
        assessment = classify_risk(self._config.risk, request)
        location_check = check_request_location(self._config.surfaces, request)
        if not location_check.passed:
            return _deny_for_check(location_check, assessment)
        kind_check = check_action_kind(self._config.actions.allowed, request)
        if not kind_check.passed:
            return _deny_for_check(kind_check, assessment)
        if assessment.risk == "safe":
            return _allow_safe(assessment, [location_check, kind_check])
        handling = self._config.risk.handling.for_mode(request.mode)
        return decide_risky(handling, request, assessment)


def decide_risky(
    handling: RiskHandling, request: PolicyRequest, assessment: RiskAssessment
) -> PolicyDecision:
    """Apply the mode's handling to an action already classified risky."""
    rule = f"risk.handling.{request.mode}"
    if handling == "allow":
        reason = (
            f"risky action allowed in {request.mode} mode; recorded for audit. {assessment.reason}"
        )
        return PolicyDecision(verdict="allow", risk="risky", rule=rule, reason=reason)
    if handling == "deny":
        reason = f"risky actions are denied in {request.mode} mode. {assessment.reason}"
        return PolicyDecision(verdict="deny", risk="risky", rule=rule, reason=reason)
    if handling == "escalate":
        reason = f"risky action needs a human decision in {request.mode} mode. {assessment.reason}"
        return PolicyDecision(verdict="escalate", risk="risky", rule=rule, reason=reason)
    return _decide_approved_and_confirmed(request, assessment, rule)


def _decide_approved_and_confirmed(
    request: PolicyRequest, assessment: RiskAssessment, rule: str
) -> PolicyDecision:
    missing = _missing_risky_preconditions(request)
    if missing:
        reason = f"risky action denied: {' and '.join(missing)}. {assessment.reason}"
        return PolicyDecision(verdict="deny", risk="risky", rule=rule, reason=reason)
    reason = f"risky action allowed: capability is approved and the caller confirmed it. {assessment.reason}"
    return PolicyDecision(verdict="allow", risk="risky", rule=rule, reason=reason)


def _missing_risky_preconditions(request: PolicyRequest) -> list[str]:
    missing = []
    if request.capability_status != "approved":
        missing.append(
            f"capability status is {request.capability_status or 'unknown'}, not approved"
        )
    if not request.risky_confirmed:
        missing.append("the caller did not pass risky_confirmed")
    return missing


def _deny_for_check(check_result: CheckResult, assessment: RiskAssessment) -> PolicyDecision:
    return PolicyDecision(
        verdict="deny", risk=assessment.risk, rule=check_result.rule, reason=check_result.reason
    )


def _allow_safe(assessment: RiskAssessment, passed_checks: list[CheckResult]) -> PolicyDecision:
    check_reasons = "; ".join(check_result.reason for check_result in passed_checks)
    reason = f"safe action allowed: {check_reasons}; {assessment.reason}"
    return PolicyDecision(verdict="allow", risk="safe", rule=assessment.rule, reason=reason)
