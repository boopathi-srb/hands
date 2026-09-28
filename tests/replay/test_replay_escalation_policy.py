"""Policy gating of every action, risky steps, and the three ways a human can resolve an escalation."""

from __future__ import annotations

from typing import Any

from hands.core.control import InterventionRequest
from hands.core.results import EscalatedResult, FailedResult, SuccessResult

from .app import (
    KNOWN_MEMBER,
    Harness,
    lookup_app,
    lookup_capability,
    lookup_capability_data,
    lookup_steps,
    role_name,
    target,
    text_visible,
)
from .fakes import FakeEscalator, FakePolicy, Screen, button, text


def risky_capability_overrides(status: str = "approved") -> dict[str, Any]:
    steps = lookup_steps()[:3]
    steps[2]["postcondition"] = text_visible("Confirm New Share")
    steps.append({"id": "submit", "action": "click", "description": "Submit the change", "risk": "risky",
                  "target": target("Submit", role_name("button", "Submit")),
                  "postcondition": text_visible("Share opened")})
    return {"status": status, "steps": steps, "outputs": {}, "checkpoint": text_visible("Share opened")}


def review_app() -> Any:
    surface = lookup_app(search_route="review")
    surface.screens["review"] = Screen("review", [text("Confirm New Share", 0), button("Submit", 1)])
    surface.screens["opened"] = Screen("opened", [text("Share opened for member 10001.", 0)])
    surface.transitions[("Submit", "click")] = "opened"
    return surface


def human_moves_to(surface: Any, screen_name: str) -> Any:
    def act_as_human(_request: InterventionRequest) -> None:
        surface.show(screen_name)

    return act_as_human


# ---------------------------------------------------------------- policy


async def test_policy_deny_is_policy_denied_with_rule_and_reason() -> None:
    harness = Harness(policy=FakePolicy(deny_kinds=("type",)))
    result = await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, FailedResult)
    assert result.failure.code == "policy_denied"
    assert result.failure.step_id == "login_user"
    assert "actions.allowed" in result.failure.message
    assert "kind not allowed" in result.failure.message
    assert not any(action.kind == "type" for _target, action in harness.surface.actions)


async def test_every_action_is_checked_in_replay_mode_with_declared_risk() -> None:
    harness = Harness()
    await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    assert len(harness.policy.requests) == len(harness.surface.actions)
    assert {request.mode for request in harness.policy.requests} == {"replay"}
    assert {request.capability_status for request in harness.policy.requests} == {"approved"}


async def test_recovery_dismiss_also_passes_the_policy_gate() -> None:
    harness = Harness(surface=lookup_app(after_sign_on="notice"), policy=FakePolicy(deny_kinds=("click",)))
    result = await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, FailedResult)
    assert result.failure.code == "policy_denied"


async def test_risky_step_without_confirmation_is_denied() -> None:
    harness = Harness(surface=review_app())
    result = await harness.engine.run(lookup_capability(**risky_capability_overrides()), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, FailedResult)
    assert result.failure.code == "policy_denied"
    assert result.failure.step_id == "submit"
    assert harness.surface.current == "review"


async def test_risky_step_on_draft_capability_is_denied_even_when_confirmed() -> None:
    harness = Harness(surface=review_app())
    result = await harness.engine.run(
        lookup_capability(**risky_capability_overrides(status="draft")), {"member_number": KNOWN_MEMBER},
        risky_confirmed=True,
    )

    assert isinstance(result, FailedResult)
    assert result.failure.code == "policy_denied"


async def test_risky_step_approved_and_confirmed_is_allowed() -> None:
    harness = Harness(surface=review_app())
    result = await harness.engine.run(
        lookup_capability(**risky_capability_overrides()), {"member_number": KNOWN_MEMBER}, risky_confirmed=True
    )

    assert isinstance(result, SuccessResult)
    submit_request = harness.policy.requests[-1]
    assert submit_request.declared_risk == "risky"
    assert submit_request.risky_confirmed is True
    assert submit_request.target_node is not None and submit_request.target_node.name == "Submit"


async def test_policy_escalate_without_escalator_is_denied() -> None:
    harness = Harness(surface=review_app(), policy=FakePolicy(escalate_risky=True))
    result = await harness.engine.run(lookup_capability(**risky_capability_overrides()), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, FailedResult)
    assert result.failure.code == "policy_denied"


async def test_policy_escalate_with_human_approval_performs_the_step() -> None:
    escalator = FakeEscalator(outcome="resume")
    harness = Harness(surface=review_app(), policy=FakePolicy(escalate_risky=True), escalator=escalator)
    result = await harness.engine.run(lookup_capability(**risky_capability_overrides()), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, SuccessResult)
    assert escalator.requests[0].kind == "risky_action"
    assert result.interventions == [escalator.requests[0].intervention_id]


async def test_policy_escalate_with_human_abort_is_escalated() -> None:
    escalator = FakeEscalator(outcome="abort", note="member did not confirm")
    harness = Harness(surface=review_app(), policy=FakePolicy(escalate_risky=True), escalator=escalator)
    result = await harness.engine.run(lookup_capability(**risky_capability_overrides()), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, EscalatedResult)
    assert result.operator_note == "member did not confirm"
    assert harness.surface.current == "review"


# ---------------------------------------------------------------- escalation from a recovery rule


async def test_identity_check_resume_after_human_finishes_marks_step_human() -> None:
    surface = lookup_app(search_route="identity")
    escalator = FakeEscalator(outcome="resume", human=human_moves_to(surface, "member"))
    harness = Harness(surface=surface, escalator=escalator)
    result = await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER}, session_id="sess-1")

    assert isinstance(result, SuccessResult)
    request = escalator.requests[0]
    assert request.kind == "stuck"
    assert request.mode == "replay"
    assert request.session_id == "sess-1"
    assert request.step_id == "search"
    assert request.capability_id == "test.member_lookup"
    assert request.screenshot_path is not None
    search_trace = next(trace for trace in result.steps if trace.step_id == "search")
    assert search_trace.status == "human"
    assert result.interventions == [request.intervention_id]


async def test_identity_check_resume_without_human_progress_retries_the_step() -> None:
    surface = lookup_app(search_route="identity")

    def human_clears_modal_only(_request: InterventionRequest) -> None:
        surface.show("inquiry")
        surface.transitions[("Search", "click")] = "member"

    escalator = FakeEscalator(outcome="resume", human=human_clears_modal_only)
    result = await Harness(surface=surface, escalator=escalator).engine.run(
        lookup_capability(), {"member_number": KNOWN_MEMBER}
    )

    assert isinstance(result, SuccessResult)
    search_clicks = [action for _target, action in surface.actions if action.kind == "click"]
    assert len(search_clicks) >= 3  # sign on, first search, retried search


async def test_identity_check_step_completed_by_human() -> None:
    surface = lookup_app(search_route="identity")
    escalator = FakeEscalator(outcome="step_completed_by_human", human=human_moves_to(surface, "member"))
    result = await Harness(surface=surface, escalator=escalator).engine.run(
        lookup_capability(), {"member_number": KNOWN_MEMBER}
    )

    assert isinstance(result, SuccessResult)
    assert next(trace for trace in result.steps if trace.step_id == "search").status == "human"


async def test_identity_check_abort_is_escalated_with_operator_note() -> None:
    escalator = FakeEscalator(outcome="abort", note="could not verify the member")
    result = await Harness(surface=lookup_app(search_route="identity"), escalator=escalator).engine.run(
        lookup_capability(), {"member_number": KNOWN_MEMBER}
    )

    assert isinstance(result, EscalatedResult)
    assert result.reason == "Identity verification requires a human."
    assert result.operator_note == "could not verify the member"
    assert result.intervention_id == escalator.requests[0].intervention_id
    assert result.interventions == [result.intervention_id]


async def test_escalate_rule_without_escalator_is_unexpected_state() -> None:
    result = await Harness(surface=lookup_app(search_route="identity")).engine.run(
        lookup_capability(), {"member_number": KNOWN_MEMBER}
    )

    assert isinstance(result, FailedResult)
    assert result.failure.code == "unexpected_state"


# ---------------------------------------------------------------- unrecoverable timeouts


async def test_unexplained_timeout_escalates_as_unrecoverable_before_failing() -> None:
    surface = lookup_app(search_route="error")
    data = lookup_capability_data()
    recoveries = [rule for rule in data["recoveries"] if rule["name"] != "transient_app_error"]
    escalator = FakeEscalator(outcome="resume", human=human_moves_to(surface, "member"))
    result = await Harness(surface=surface, escalator=escalator).engine.run(
        lookup_capability(recoveries=recoveries), {"member_number": KNOWN_MEMBER}
    )

    assert isinstance(result, SuccessResult)
    assert escalator.requests[0].kind == "unrecoverable"
    assert "postcondition not met" in escalator.requests[0].reason


async def test_unrecoverable_escalation_happens_once_per_step_then_fails() -> None:
    data = lookup_capability_data()
    recoveries = [rule for rule in data["recoveries"] if rule["name"] != "transient_app_error"]
    escalator = FakeEscalator(outcome="resume")
    result = await Harness(surface=lookup_app(search_route="error"), escalator=escalator).engine.run(
        lookup_capability(recoveries=recoveries), {"member_number": KNOWN_MEMBER}
    )

    assert isinstance(result, FailedResult)
    assert result.failure.code == "target_not_found"  # the resumed retry cannot find Search on the error page
    assert len(escalator.requests) == 1
