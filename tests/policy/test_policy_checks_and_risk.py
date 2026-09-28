"""Unit tests for the individual check and risk functions the gate composes."""

from __future__ import annotations

from policy_helpers import build_request, button, config_from, minimal_policy_mapping, url_location

from hands.core.observation import Location, Node
from hands.policy.checks import (
    check_action_kind,
    check_desktop_bundle,
    check_desktop_window,
    check_entry_point,
    check_location,
    check_request_location,
    check_web_url,
)
from hands.policy.config import RiskMatch
from hands.policy.risk import (
    action_path,
    classify_risk,
    control_texts,
    derive_risk_from_rules,
    rule_matches,
)

CONFIG = config_from(minimal_policy_mapping())
SURFACES = CONFIG.surfaces


def test_check_web_url_pass_and_fail() -> None:
    assert check_web_url(SURFACES.web, "http://127.0.0.1:8700/t/lakeside/login").passed
    assert not check_web_url(SURFACES.web, "http://127.0.0.1:8700/t/prairie/login").passed
    assert not check_web_url(SURFACES.web, "").passed


def test_check_desktop_bundle_and_window() -> None:
    assert check_desktop_bundle(SURFACES.desktop, "com.apple.calculator").passed
    assert not check_desktop_bundle(SURFACES.desktop, "").passed
    assert check_desktop_window(SURFACES.desktop, "com.apple.calculator", "").passed
    assert not check_desktop_window(SURFACES.desktop, "com.apple.mail", "Inbox").passed


def test_check_location_dispatches_on_kind() -> None:
    assert check_location(SURFACES, url_location("/t/lakeside/main")).passed
    assert check_location(SURFACES, Location(kind="window", value="com.apple.calculator")).passed
    assert not check_location(
        SURFACES, Location(kind="window", value="http://127.0.0.1:8700/t/lakeside")
    ).passed


def test_check_entry_point_dispatches_on_shape() -> None:
    assert check_entry_point(SURFACES, "http://127.0.0.1:8700/t/lakeside/login").passed
    assert check_entry_point(SURFACES, "com.apple.calculator").passed
    assert not check_entry_point(SURFACES, "").passed


def test_check_request_location_for_open_uses_start_locations() -> None:
    request = build_request(
        action={"kind": "open", "entry_point": "http://127.0.0.1:8700/t/lakeside/login"},
        location=Location(kind="url", value="about:blank"),
    )
    result = check_request_location(SURFACES, request)
    assert result.passed
    assert result.rule == "surfaces.web.allowed_path_patterns"


def test_check_action_kind() -> None:
    allowed = CONFIG.actions.allowed
    assert check_action_kind(allowed, build_request(mode="replay")).passed
    denied = check_action_kind(
        allowed,
        build_request(
            mode="human", action={"kind": "open", "entry_point": "http://127.0.0.1:8700/t/lakeside"}
        ),
    )
    assert not denied.passed and denied.rule == "actions.allowed.human"


def test_action_path_for_open_and_other_actions() -> None:
    open_request = build_request(
        action={"kind": "open", "entry_point": "http://127.0.0.1:8700/a/b?x=1"}
    )
    click_request = build_request(location=url_location("/t/lakeside/inquiry"))
    desktop_request = build_request(location=Location(kind="window", value="com.apple.calculator"))
    bundle_open = build_request(action={"kind": "open", "entry_point": "com.apple.calculator"})
    assert action_path(open_request) == "/a/b"
    assert action_path(click_request) == "/t/lakeside/inquiry"
    assert action_path(desktop_request) is None
    assert action_path(bundle_open) is None


def test_control_texts() -> None:
    assert control_texts(None) == []
    assert control_texts(Node(ref="n1", role="button")) == []
    assert control_texts(Node(ref="n1", role="button", name="A", text="B", label="C")) == [
        "A",
        "B",
        "C",
    ]


def test_rule_matches_criteria_are_anded() -> None:
    match = RiskMatch(control_pattern="submit", action_kinds=["click"], path_patterns=["/t/**"])
    assert rule_matches(match, build_request(target_node=button("Submit")))
    assert not rule_matches(match, build_request(target_node=button("Search")))
    assert not rule_matches(
        match, build_request(action={"kind": "press", "key": "Enter"}, target_node=button("Submit"))
    )
    assert not rule_matches(
        match,
        build_request(target_node=button("Submit"), location=Location(kind="window", value="x")),
    )


def test_control_pattern_needs_a_node_but_exclusion_does_not() -> None:
    assert not rule_matches(RiskMatch(control_pattern="."), build_request(target_node=None))
    assert rule_matches(
        RiskMatch(control_exclude_pattern="cancel"), build_request(target_node=None)
    )
    assert not rule_matches(
        RiskMatch(control_exclude_pattern="cancel"), build_request(target_node=button("Cancel"))
    )


def test_derive_and_classify_risk() -> None:
    derived = derive_risk_from_rules(CONFIG.risk, build_request(target_node=button("Submit")))
    assert derived.risk == "risky" and derived.rule == "risk.rules.irreversible"
    default = derive_risk_from_rules(CONFIG.risk, build_request(target_node=None))
    assert default.risk == "safe" and default.rule == "risk.default"
    declared = classify_risk(CONFIG.risk, build_request(target_node=None, declared_risk="risky"))
    assert declared.risk == "risky" and declared.rule == "declared_risk"
    both = classify_risk(
        CONFIG.risk, build_request(target_node=button("Submit"), declared_risk="risky")
    )
    assert both.rule == "risk.rules.irreversible"
