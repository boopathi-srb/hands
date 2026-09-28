"""Risk classification: ordered policy rules, combined with the risk a capability declares.

The effective risk is the maximum of the declared risk and the rule-derived risk. A capability may make an
action riskier than the policy thinks, never safer: that is how a model- or recorder-authored artifact is
prevented from downgrading a Submit button to "safe".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from hands.core.actions import OpenAction
from hands.core.artifact import Risk
from hands.core.observation import Node
from hands.core.ports import PolicyRequest
from hands.policy.addresses import looks_like_url, parse_web_address
from hands.policy.config import RiskMatch, RiskPolicy, RiskRule
from hands.policy.paths import first_matching_pattern


@dataclass(frozen=True)
class RiskAssessment:
    risk: Risk
    rule: str
    reason: str


def classify_risk(risk_policy: RiskPolicy, request: PolicyRequest) -> RiskAssessment:
    """Effective risk of the request: max(declared, first matching rule or the policy default)."""
    derived = derive_risk_from_rules(risk_policy, request)
    if request.declared_risk == "risky" and derived.risk == "safe":
        return RiskAssessment(
            risk="risky",
            rule="declared_risk",
            reason=f"the capability declares this action risky (policy alone says safe via {derived.rule})",
        )
    return derived


def derive_risk_from_rules(risk_policy: RiskPolicy, request: PolicyRequest) -> RiskAssessment:
    matching_rule = next(
        (rule for rule in risk_policy.rules if rule_matches(rule.match, request)), None
    )
    if matching_rule is None:
        return RiskAssessment(
            risk=risk_policy.default,
            rule="risk.default",
            reason=f"no risk rule matched; default is {risk_policy.default}",
        )
    return RiskAssessment(
        risk=matching_rule.risk,
        rule=f"risk.rules.{matching_rule.name}",
        reason=_rule_reason(matching_rule, request),
    )


def rule_matches(match: RiskMatch, request: PolicyRequest) -> bool:
    return (
        _kind_matches(match, request)
        and _path_matches(match, request)
        and _control_matches(match, request.target_node)
        and _control_not_excluded(match, request.target_node)
    )


def action_path(request: PolicyRequest) -> str | None:
    """The URL path a request acts on: the entry point for `open`, else the current location."""
    if isinstance(request.action, OpenAction):
        url = request.action.entry_point if looks_like_url(request.action.entry_point) else ""
    else:
        url = request.location.value if request.location.kind == "url" else ""
    address = parse_web_address(url) if url else None
    return address.path if address is not None else None


def control_texts(node: Node | None) -> list[str]:
    """The strings a control pattern is searched in."""
    if node is None:
        return []
    return [text for text in (node.name, node.text, node.label or "") if text]


def _kind_matches(match: RiskMatch, request: PolicyRequest) -> bool:
    return not match.action_kinds or request.action.kind in match.action_kinds


def _path_matches(match: RiskMatch, request: PolicyRequest) -> bool:
    if not match.path_patterns:
        return True
    path = action_path(request)
    return path is not None and first_matching_pattern(match.path_patterns, path) is not None


def _control_matches(match: RiskMatch, node: Node | None) -> bool:
    if match.control_pattern is None:
        return True
    pattern = _compiled_control_pattern(match.control_pattern)
    return any(pattern.search(text) for text in control_texts(node))


def _control_not_excluded(match: RiskMatch, node: Node | None) -> bool:
    if match.control_exclude_pattern is None:
        return True
    pattern = _compiled_control_pattern(match.control_exclude_pattern)
    return not any(pattern.search(text) for text in control_texts(node))


@lru_cache(maxsize=256)
def _compiled_control_pattern(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


def _rule_reason(rule: RiskRule, request: PolicyRequest) -> str:
    node = request.target_node
    control = f" on {node.role} '{node.name or node.text}'" if node is not None else ""
    return f"{request.action.kind}{control} classified {rule.risk} by rule '{rule.name}': {rule.description}"
