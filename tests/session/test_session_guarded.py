"""GuardedSurface: lease gate, policy gate, escalate verdict, evidence."""

from __future__ import annotations

import json
from typing import Literal

from hands.core.actions import ActResult, ClickAction, NodeRef, OpenAction, Point, TypeAction
from hands.core.observation import Node, Rect
from hands.session.doubles import (
    FixedPolicyGate,
    InMemoryEvidence,
    StubLiveView,
    StubSurface,
    make_observation,
)
from hands.session.guarded import (
    GuardedSurface,
    describe_action,
    describe_target,
    location_kind_for,
)
from hands.session.lease import LeaseManager

RUN = "run-1"
Verdict = Literal["allow", "deny", "escalate"]
PASSWORD_FIELD = Node(
    ref="n7", role="textbox", name="Password", bounds=Rect(x=0, y=0, width=100, height=20)
)
SECRET_TEXT = "hunter2-synthetic"


def build(
    verdict: Verdict = "allow", grant: bool = True, surface: StubSurface | None = None
) -> tuple[GuardedSurface, StubSurface, FixedPolicyGate, InMemoryEvidence, LeaseManager]:
    raw_surface = surface or StubSurface(
        make_observation([PASSWORD_FIELD]), live_view=StubLiveView()
    )
    lease = LeaseManager("session-1")
    if grant:
        lease.grant_automation(RUN)
    policy = FixedPolicyGate(verdict=verdict, reason=f"policy said {verdict}")
    evidence = InMemoryEvidence()
    guarded = GuardedSurface(raw_surface, lease, policy, evidence, mode="replay", run_id=RUN)
    return guarded, raw_surface, policy, evidence, lease


async def test_blocks_when_automation_does_not_hold_lease() -> None:
    guarded, raw_surface, policy, evidence, _ = build(grant=False)
    result = await guarded.act(None, ClickAction())
    assert not result.ok
    assert result.error == "not in control"
    assert result.blocked_by == "not_in_control"
    assert raw_surface.acts == [] and policy.requests == []
    assert evidence.kinds() == ["action_attempted", "action_blocked"]


async def test_blocks_when_another_run_holds_lease() -> None:
    guarded, raw_surface, _, _, lease = build(grant=False)
    lease.grant_automation("run-other")
    result = await guarded.act(None, ClickAction())
    assert result.blocked_by == "not_in_control"
    assert raw_surface.acts == []


async def test_blocks_on_policy_deny() -> None:
    guarded, raw_surface, _, evidence, _ = build(verdict="deny")
    result = await guarded.act(NodeRef(ref="n7"), ClickAction())
    assert not result.ok
    assert result.blocked_by == "policy_denied"
    assert result.error == "policy said deny"
    assert result.decision is not None and result.decision.verdict == "deny"
    assert raw_surface.acts == []
    assert evidence.kinds() == ["action_attempted", "policy_decision", "action_blocked"]


async def test_escalate_verdict_is_distinct_and_not_performed() -> None:
    guarded, raw_surface, _, _, _ = build(verdict="escalate")
    result = await guarded.act(None, ClickAction())
    assert not result.ok
    assert result.needs_escalation
    assert result.blocked_by == "policy_escalate"
    assert raw_surface.acts == []


async def test_allows_and_records_result() -> None:
    guarded, raw_surface, _, evidence, _ = build()
    result = await guarded.act(Point(x=1, y=1), ClickAction())
    assert result.ok and result.blocked_by is None and not result.needs_escalation
    assert raw_surface.acts == [(Point(x=1, y=1), ClickAction())]
    assert evidence.kinds() == ["action_attempted", "policy_decision", "action_result"]


async def test_surface_failure_is_passed_through() -> None:
    failing = StubSurface(make_observation(), act_result=ActResult(ok=False, error="no such node"))
    guarded, _, _, evidence, _ = build(surface=failing)
    result = await guarded.act(NodeRef(ref="missing"), ClickAction())
    assert not result.ok and result.error == "no such node" and result.blocked_by is None
    assert evidence.of_kind("action_result")[0]["ok"] is False


async def test_policy_request_carries_node_location_risk_and_confirmation() -> None:
    guarded, _, policy, _, _ = build()
    await guarded.observe()
    await guarded.act(NodeRef(ref="n7"), ClickAction(), declared_risk="risky", confirm_risky=True)
    request = policy.requests[0]
    assert request.mode == "replay"
    assert request.target_node == PASSWORD_FIELD
    assert request.location.value == "http://app.test/page"
    assert request.declared_risk == "risky"
    assert request.risky_confirmed is True


async def test_point_target_is_hit_tested_for_policy() -> None:
    guarded, _, policy, _, _ = build()
    await guarded.observe()
    await guarded.act(Point(x=5, y=5), ClickAction())
    assert policy.requests[0].target_node == PASSWORD_FIELD


async def test_open_action_uses_entry_point_as_location_before_any_observation() -> None:
    guarded, _, policy, _, _ = build()
    await guarded.act(None, OpenAction(entry_point="http://app.test/login"))
    assert policy.requests[0].location.value == "http://app.test/login"
    assert policy.requests[0].target_node is None


async def test_location_is_empty_without_observation() -> None:
    guarded, _, policy, _, _ = build()
    await guarded.act(None, ClickAction())
    assert policy.requests[0].location.value == ""


async def test_typed_text_never_reaches_evidence() -> None:
    guarded, _, _, evidence, _ = build()
    await guarded.act(NodeRef(ref="n7"), TypeAction(text=SECRET_TEXT))
    serialized = json.dumps(evidence.events, default=str)
    assert SECRET_TEXT not in serialized
    assert evidence.of_kind("action_attempted")[0]["action"]["text_length"] == len(SECRET_TEXT)


async def test_observe_is_allowed_without_lease_and_recorded() -> None:
    guarded, raw_surface, _, evidence, _ = build(grant=False)
    observation = await guarded.observe(include_screenshot=False)
    assert observation is raw_surface.observation
    assert guarded.latest_observation is observation
    recorded = evidence.of_kind("observed")[0]
    assert recorded["node_count"] == 1 and recorded["fingerprint"] == "stub-fingerprint"


async def test_close_and_live_view_delegate() -> None:
    guarded, raw_surface, _, _, _ = build()
    assert guarded.kind == "fake"
    assert guarded.run_id == RUN
    assert guarded.live_view() is raw_surface.live_view()
    await guarded.close()
    assert raw_surface.closed


def test_describe_helpers() -> None:
    assert describe_action(ClickAction()) == {"kind": "click"}
    assert describe_action(TypeAction(text="")) == {
        "kind": "type",
        "text_length": 0,
        "clear_first": True,
    }
    assert describe_target(None, None) == {"type": "none"}
    assert describe_target(NodeRef(ref="n7"), PASSWORD_FIELD)["node_name"] == "Password"
    assert describe_target(Point(x=1, y=2), None) == {"type": "point", "x": 1, "y": 2}
    assert location_kind_for("desktop") == "window"
    assert location_kind_for("web") == "url"
