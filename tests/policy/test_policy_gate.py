from __future__ import annotations

import copy
from typing import Any

import pytest
from policy_helpers import (
    build_request,
    button,
    config_from,
    minimal_policy_mapping,
    url_location,
)

from hands.core.observation import Location, Node
from hands.core.ports import PolicyGate, PolicyRequest
from hands.policy import YamlPolicyGate
from hands.policy.gate import decide_risky
from hands.policy.risk import RiskAssessment

LAKESIDE_REVIEW = url_location("/t/lakeside/member/10001/review")
PRAIRIE_INQUIRY = url_location("/t/prairie/inquiry")


def _gate(**overrides: Any) -> YamlPolicyGate:
    return YamlPolicyGate(config_from(minimal_policy_mapping(**overrides)))


def _risk_section(**changes: Any) -> dict[str, Any]:
    risk = copy.deepcopy(minimal_policy_mapping()["risk"])
    risk.update(changes)
    return risk


def test_yaml_policy_gate_satisfies_the_core_port(coreone_gate: YamlPolicyGate) -> None:
    gate: PolicyGate = coreone_gate
    assert gate.check(build_request()).verdict == "allow"
    assert coreone_gate.config.name == "coreone"


# ---------------------------------------------------------------- web location allowlist


@pytest.mark.parametrize(
    "location",
    [
        url_location("/t/lakeside/inquiry"),
        url_location("/t/prairie/member/10002"),
        url_location("/t/lakeside/main?frame=content"),
    ],
)
def test_allowlisted_web_locations_are_allowed(
    coreone_gate: YamlPolicyGate, location: Location
) -> None:
    decision = coreone_gate.check(build_request(location=location, target_node=button("Search")))
    assert decision.verdict == "allow"
    assert decision.risk == "safe"


@pytest.mark.parametrize(
    ("location", "rule"),
    [
        (
            url_location("/t/lakeside/inquiry", origin="http://localhost:8700"),
            "surfaces.web.allowed_origins",
        ),
        (
            url_location("/t/lakeside/inquiry", origin="https://127.0.0.1:8700"),
            "surfaces.web.allowed_origins",
        ),
        (
            url_location("/t/lakeside/inquiry", origin="http://evil.example"),
            "surfaces.web.allowed_origins",
        ),
        (Location(kind="url", value="about:blank"), "surfaces.web.allowed_origins"),
        (url_location("/t/otherbank/login"), "surfaces.web.allowed_path_patterns"),
        (url_location("/"), "surfaces.web.allowed_path_patterns"),
        (url_location("/_admin/faults"), "surfaces.web.blocked_path_patterns"),
        (url_location("/t/lakeside/../../_admin/faults"), "surfaces.web.blocked_path_patterns"),
        (
            url_location("/t/lakeside/%2e%2e/%2e%2e/_admin/faults"),
            "surfaces.web.blocked_path_patterns",
        ),
        (url_location("/docs/index"), "surfaces.web.blocked_path_patterns"),
    ],
)
def test_locations_outside_the_allowlist_are_denied(
    coreone_gate: YamlPolicyGate, location: Location, rule: str
) -> None:
    decision = coreone_gate.check(build_request(location=location))
    assert decision.verdict == "deny"
    assert decision.rule == rule
    assert decision.reason


def test_blocked_patterns_win_over_allowed_patterns() -> None:
    web = {
        "allowed_origins": ["http://127.0.0.1:8700"],
        "allowed_path_patterns": ["/**"],
        "blocked_path_patterns": ["/t/*/reports/**"],
    }
    gate = _gate(surfaces={"web": web})
    decision = gate.check(build_request(location=url_location("/t/lakeside/reports/eod")))
    assert decision.verdict == "deny"
    assert decision.rule == "surfaces.web.blocked_path_patterns"
    assert "/t/*/reports/**" in decision.reason


# ---------------------------------------------------------------- open actions check the entry point too


def _open(entry_point: str) -> dict[str, str]:
    return {"kind": "open", "entry_point": entry_point}


def test_open_from_a_start_location_to_an_allowed_entry_point(coreone_gate: YamlPolicyGate) -> None:
    request = build_request(
        mode="discovery",
        action=_open("http://127.0.0.1:8700/t/lakeside/login"),
        location=Location(kind="url", value="about:blank"),
    )
    decision = coreone_gate.check(request)
    assert decision.verdict == "allow"
    assert "/t/lakeside/login allowed by '/t/lakeside/**'" in decision.reason


@pytest.mark.parametrize(
    ("entry_point", "rule"),
    [
        ("http://127.0.0.1:8700/_admin/faults", "surfaces.web.blocked_path_patterns"),
        ("http://127.0.0.1:8700/t/otherbank/login", "surfaces.web.allowed_path_patterns"),
        ("https://evil.example/t/lakeside/login", "surfaces.web.allowed_origins"),
        ("javascript:alert(1)", "surfaces.desktop.allowed_bundle_ids"),
        ("com.apple.Terminal", "surfaces.desktop.allowed_bundle_ids"),
    ],
)
def test_open_to_a_disallowed_entry_point_is_denied(
    coreone_gate: YamlPolicyGate, entry_point: str, rule: str
) -> None:
    request = build_request(
        action=_open(entry_point), location=Location(kind="url", value="about:blank")
    )
    decision = coreone_gate.check(request)
    assert decision.verdict == "deny"
    assert decision.rule == rule


def test_open_from_a_disallowed_current_location_is_denied(coreone_gate: YamlPolicyGate) -> None:
    request = build_request(
        action=_open("http://127.0.0.1:8700/t/lakeside/login"),
        location=url_location("/phish", origin="https://evil.example"),
    )
    decision = coreone_gate.check(request)
    assert decision.verdict == "deny"
    assert decision.rule == "surfaces.web.allowed_origins"


def test_open_from_an_allowlisted_location_is_allowed(coreone_gate: YamlPolicyGate) -> None:
    request = build_request(
        action=_open("http://127.0.0.1:8700/t/prairie/login"), location=PRAIRIE_INQUIRY
    )
    assert coreone_gate.check(request).verdict == "allow"


def test_start_locations_only_permit_open(coreone_gate: YamlPolicyGate) -> None:
    request = build_request(
        location=Location(kind="url", value="about:blank"), target_node=button("OK")
    )
    decision = coreone_gate.check(request)
    assert decision.verdict == "deny"
    assert decision.rule == "surfaces.web.allowed_origins"


# ---------------------------------------------------------------- desktop allowlist


def _window(bundle_id: str, title: str = "Calculator") -> Location:
    return Location(kind="window", value=bundle_id, title=title)


def test_desktop_allowlisted_window_is_allowed(coreone_gate: YamlPolicyGate) -> None:
    request = build_request(location=_window("com.apple.calculator"), target_node=button("7"))
    decision = coreone_gate.check(request)
    assert decision.verdict == "allow"


def test_desktop_other_application_is_denied(coreone_gate: YamlPolicyGate) -> None:
    decision = coreone_gate.check(build_request(location=_window("com.apple.Terminal", "zsh")))
    assert decision.verdict == "deny"
    assert decision.rule == "surfaces.desktop.allowed_bundle_ids"


def test_desktop_window_title_patterns_are_enforced() -> None:
    desktop = {
        "allowed_bundle_ids": ["com.apple.calculator"],
        "allowed_window_title_patterns": ["Calculator"],
    }
    gate = _gate(surfaces={"desktop": desktop})
    allowed = gate.check(build_request(location=_window("com.apple.calculator", "Calculator")))
    denied = gate.check(build_request(location=_window("com.apple.calculator", "Paper Tape")))
    assert allowed.verdict == "allow"
    assert denied.verdict == "deny"
    assert denied.rule == "surfaces.desktop.allowed_window_title_patterns"


def test_desktop_open_checks_the_bundle_id(coreone_gate: YamlPolicyGate) -> None:
    from_empty = Location(kind="window", value="")
    allowed = coreone_gate.check(
        build_request(action=_open("com.apple.calculator"), location=from_empty)
    )
    denied = coreone_gate.check(build_request(action=_open("com.apple.mail"), location=from_empty))
    assert allowed.verdict == "allow"
    assert denied.verdict == "deny"


# ---------------------------------------------------------------- action kinds per mode


def test_action_kind_not_allowed_for_mode_is_denied(coreone_gate: YamlPolicyGate) -> None:
    request = build_request(mode="human", action=_open("http://127.0.0.1:8700/t/lakeside/login"))
    decision = coreone_gate.check(request)
    assert decision.verdict == "deny"
    assert decision.rule == "actions.allowed.human"


@pytest.mark.parametrize("kind", ["click", "press", "scroll"])
def test_mode_with_no_listed_kinds_cannot_act(kind: str) -> None:
    gate = _gate(actions={"allowed": {"discovery": ["click"]}})
    action: dict[str, Any] = {"kind": kind}
    if kind == "press":
        action["key"] = "Enter"
    decision = gate.check(build_request(mode="replay", action=action))
    assert decision.verdict == "deny"
    assert decision.rule == "actions.allowed.replay"


def test_location_is_checked_before_action_kind(coreone_gate: YamlPolicyGate) -> None:
    request = build_request(
        mode="human",
        action=_open("http://127.0.0.1:8700/t/lakeside/login"),
        location=url_location("/x", origin="http://evil.example"),
    )
    assert coreone_gate.check(request).rule == "surfaces.web.allowed_origins"


# ---------------------------------------------------------------- risk classification


@pytest.mark.parametrize(
    "node",
    [
        button("Submit"),
        button("", text="Confirm"),
        button("Delete member"),
        button("Transfer Funds"),
        button("Send Wire"),
        button("Close Account"),
        button("APPROVE"),
        Node(ref="n9", role="link", name="", text="", label="Authorize"),
    ],
)
def test_irreversible_controls_are_risky_by_name_text_or_label(
    coreone_gate: YamlPolicyGate, node: Node
) -> None:
    decision = coreone_gate.check(build_request(mode="discovery", target_node=node))
    assert decision.risk == "risky"
    assert decision.verdict == "escalate"
    assert "irreversible-controls" in decision.reason


@pytest.mark.parametrize(
    "name", ["Search", "Find", "Sign On", "Continue", "Acknowledge", "Submission Log"]
)
def test_ordinary_controls_are_safe(coreone_gate: YamlPolicyGate, name: str) -> None:
    decision = coreone_gate.check(build_request(mode="discovery", target_node=button(name)))
    assert decision.risk == "safe"
    assert decision.verdict == "allow"
    assert decision.rule == "risk.default"


def test_review_page_classification_by_path(coreone_gate: YamlPolicyGate) -> None:
    continue_click = build_request(
        mode="discovery", location=LAKESIDE_REVIEW, target_node=button("Continue")
    )
    enter_press = build_request(
        mode="discovery", location=LAKESIDE_REVIEW, action={"kind": "press", "key": "Enter"}
    )
    cancel_click = build_request(
        mode="discovery", location=LAKESIDE_REVIEW, target_node=button("Cancel")
    )
    typing = build_request(
        mode="discovery",
        location=LAKESIDE_REVIEW,
        action={"kind": "type", "text": "x"},
        target_node=None,
    )
    assert coreone_gate.check(continue_click).rule == "risk.handling.discovery"
    assert "review-page-commit" in coreone_gate.check(continue_click).reason
    assert coreone_gate.check(enter_press).risk == "risky"
    assert coreone_gate.check(cancel_click).risk == "safe"
    assert coreone_gate.check(typing).risk == "safe"


def test_risky_classification_by_action_kind_alone() -> None:
    rules = [
        {
            "name": "no-selects",
            "description": "selects commit",
            "match": {"action_kinds": ["select"]},
        }
    ]
    gate = _gate(risk=_risk_section(rules=rules))
    select = gate.check(
        build_request(mode="discovery", action={"kind": "select", "option": "Wire"})
    )
    click = gate.check(build_request(mode="discovery", target_node=button("Search")))
    assert select.verdict == "escalate"
    assert click.risk == "safe"


def test_path_rules_use_the_entry_point_for_open() -> None:
    rules = [
        {
            "name": "open-review",
            "description": "deep links into review pages",
            "match": {"path_patterns": ["/t/*/member/*/review"], "action_kinds": ["open"]},
        }
    ]
    gate = _gate(risk=_risk_section(rules=rules))
    request = build_request(
        mode="discovery",
        action=_open("http://127.0.0.1:8700/t/lakeside/member/1/review"),
        location=Location(kind="url", value="about:blank"),
    )
    assert gate.check(request).risk == "risky"


def test_first_matching_rule_wins_and_may_mark_safe() -> None:
    rules = [
        {
            "name": "submit-search",
            "description": "the search form's submit is harmless",
            "risk": "safe",
            "match": {"control_pattern": "^submit search$"},
        },
        {"name": "submit", "description": "commits", "match": {"control_pattern": "submit"}},
    ]
    gate = _gate(risk=_risk_section(rules=rules))
    search = gate.check(build_request(mode="discovery", target_node=button("Submit Search")))
    commit = gate.check(build_request(mode="discovery", target_node=button("Submit")))
    assert search.risk == "safe" and search.rule == "risk.rules.submit-search"
    assert commit.risk == "risky"


def test_default_risky_policy_treats_unmatched_actions_as_risky() -> None:
    gate = _gate(risk=_risk_section(default="risky", rules=[]))
    decision = gate.check(build_request(mode="discovery", target_node=button("Search")))
    assert decision.verdict == "escalate"


# ---------------------------------------------------------------- risk cannot be downgraded


def test_declared_safe_cannot_downgrade_policy_risk(coreone_gate: YamlPolicyGate) -> None:
    request = build_request(
        location=LAKESIDE_REVIEW,
        target_node=button("Submit"),
        declared_risk="safe",
        capability_status="approved",
    )
    decision = coreone_gate.check(request)
    assert decision.risk == "risky"
    assert decision.verdict == "deny"


def test_declared_risky_raises_policy_safe(coreone_gate: YamlPolicyGate) -> None:
    request = build_request(mode="discovery", target_node=button("Search"), declared_risk="risky")
    decision = coreone_gate.check(request)
    assert decision.risk == "risky"
    assert decision.verdict == "escalate"
    assert "declares this action risky" in decision.reason


# ---------------------------------------------------------------- risky handling per mode


def _submit(mode: str, **extra: Any) -> PolicyRequest:
    return build_request(mode=mode, location=LAKESIDE_REVIEW, target_node=button("Submit"), **extra)


def test_discovery_escalates_risky_actions(coreone_gate: YamlPolicyGate) -> None:
    decision = coreone_gate.check(
        _submit("discovery", capability_status="approved", risky_confirmed=True)
    )
    assert decision.verdict == "escalate"
    assert decision.rule == "risk.handling.discovery"


def test_replay_allows_risky_when_approved_and_confirmed(coreone_gate: YamlPolicyGate) -> None:
    decision = coreone_gate.check(
        _submit("replay", capability_status="approved", risky_confirmed=True)
    )
    assert decision.verdict == "allow"
    assert decision.risk == "risky"
    assert decision.rule == "risk.handling.replay"


@pytest.mark.parametrize(
    ("status", "confirmed", "reason_fragment"),
    [
        ("approved", False, "risky_confirmed"),
        ("draft", True, "draft, not approved"),
        ("deprecated", True, "deprecated, not approved"),
        (None, False, "unknown, not approved"),
    ],
)
def test_replay_denies_risky_otherwise(
    coreone_gate: YamlPolicyGate, status: str | None, confirmed: bool, reason_fragment: str
) -> None:
    decision = coreone_gate.check(
        _submit("replay", capability_status=status, risky_confirmed=confirmed)
    )
    assert decision.verdict == "deny"
    assert reason_fragment in decision.reason


def test_human_risky_actions_are_allowed_and_audited(coreone_gate: YamlPolicyGate) -> None:
    decision = coreone_gate.check(_submit("human"))
    assert decision.verdict == "allow"
    assert decision.risk == "risky"
    assert "audit" in decision.reason


def test_deny_handling() -> None:
    handling = {"discovery": "deny", "replay": "deny", "human": "deny"}
    gate = _gate(risk=_risk_section(handling=handling))
    decision = gate.check(_submit("human"))
    assert decision.verdict == "deny"
    assert decision.rule == "risk.handling.human"


@pytest.mark.parametrize(
    ("handling", "verdict"),
    [("allow", "allow"), ("deny", "deny"), ("escalate", "escalate")],
)
def test_decide_risky_branches(handling: str, verdict: str) -> None:
    assessment = RiskAssessment(risk="risky", rule="risk.rules.x", reason="because")
    decision = decide_risky(handling, _submit("replay"), assessment)  # type: ignore[arg-type]
    assert decision.verdict == verdict
    assert decision.risk == "risky"
    assert "because" in decision.reason


def test_location_denial_still_reports_the_risk(coreone_gate: YamlPolicyGate) -> None:
    request = build_request(
        location=url_location("/_admin/faults"), target_node=button("Submit"), risky_confirmed=True
    )
    decision = coreone_gate.check(request)
    assert decision.verdict == "deny"
    assert decision.risk == "risky"
    assert decision.rule == "surfaces.web.blocked_path_patterns"


# ---------------------------------------------------------------- decision quality


def test_safe_allow_reason_explains_every_check(coreone_gate: YamlPolicyGate) -> None:
    decision = coreone_gate.check(build_request(target_node=button("Search")))
    assert "allowed by '/t/lakeside/**'" in decision.reason
    assert "'click' is allowed in replay mode" in decision.reason
    assert "no risk rule matched" in decision.reason


def test_decisions_are_deterministic(coreone_gate: YamlPolicyGate) -> None:
    request = _submit("replay", capability_status="approved", risky_confirmed=True)
    assert coreone_gate.check(request) == coreone_gate.check(request)


@pytest.mark.parametrize("mode", ["discovery", "replay", "human"])
def test_every_decision_names_a_rule_and_reason(coreone_gate: YamlPolicyGate, mode: str) -> None:
    for request in (
        _submit(mode),
        build_request(mode=mode, target_node=button("Search")),
        build_request(mode=mode, location=url_location("/_admin")),
    ):
        decision = coreone_gate.check(request)
        assert decision.rule
        assert decision.reason
