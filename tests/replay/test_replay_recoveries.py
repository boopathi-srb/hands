"""Recoverable conditions are absorbed and recorded on the StepTrace; they never become a status."""

from __future__ import annotations

from collections.abc import Mapping

from hands.core.actions import PressAction
from hands.core.results import FailedResult, SuccessResult

from .app import (
    KNOWN_MEMBER,
    Harness,
    lookup_app,
    lookup_capability,
    lookup_capability_data,
    route_member_search,
)


def trace_for(result: SuccessResult | FailedResult, step_id: str) -> list:
    return [trace for trace in result.steps if trace.step_id == step_id]


async def test_maintenance_modal_is_dismissed_by_clicking_its_control() -> None:
    harness = Harness(surface=lookup_app(after_sign_on="notice"))
    result = await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, SuccessResult)
    submit_trace = trace_for(result, "login_submit")[0]
    assert submit_trace.status == "recovered"
    assert submit_trace.recoveries_applied == ["maintenance_notice"]
    recovery_events = harness.evidence.of_kind("recovery_applied")
    assert recovery_events[0]["recovery"] == "maintenance_notice"
    assert recovery_events[0]["response"] == "dismiss"


async def test_native_dialog_is_accepted_with_enter() -> None:
    harness = Harness(surface=lookup_app(search_route="alert"))
    result = await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, SuccessResult)
    presses = [action for _target, action in harness.surface.actions if isinstance(action, PressAction)]
    assert presses == [PressAction(key="Enter")]
    assert trace_for(result, "search")[0].recoveries_applied == ["native_alert"]


async def test_non_native_dialog_without_target_is_dismissed_with_escape() -> None:
    data = lookup_capability_data()
    data["recoveries"][2]["when"] = {"kind": "dialog_open", "title_pattern": "Printer"}
    surface = lookup_app(search_route="alert")
    surface.screens["alert"].dialogs[0] = surface.screens["alert"].dialogs[0].model_copy(
        update={"native": False, "title": "Printer"}
    )
    surface.transitions[("press:Escape", "press")] = "member"
    harness = Harness(surface=surface)
    result = await harness.engine.run(lookup_capability(recoveries=data["recoveries"]), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, SuccessResult)
    assert PressAction(key="Escape") in [action for _target, action in harness.surface.actions]


async def test_transient_error_is_retried_after_backoff() -> None:
    harness = Harness(surface=lookup_app(search_route=["error", "member"]))
    result = await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, SuccessResult)
    assert 1.5 in harness.clock.sleeps
    assert trace_for(result, "search")[0].recoveries_applied == ["transient_app_error"]


async def test_persistent_error_exhausts_the_bounded_retry() -> None:
    harness = Harness(surface=lookup_app(search_route="error"))
    result = await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, FailedResult)
    failure = result.failure
    assert failure.code == "recovery_exhausted"
    assert failure.step_id == "search"
    assert "transient_app_error" in failure.message
    assert failure.expected is not None and "at most 1" in failure.expected
    assert failure.observed is not None and "Internal Error" in failure.observed
    assert failure.evidence


def expire_once_then_route() -> object:
    searches: list[str] = []

    def route(values: Mapping[str, str]) -> str:
        searches.append(values.get("Member Number", ""))
        return "expired" if len(searches) == 1 else route_member_search(values)

    return route


async def test_session_expiry_runs_login_subflow_and_restarts() -> None:
    harness = Harness(surface=lookup_app(search_route=expire_once_then_route()))  # type: ignore[arg-type]
    result = await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, SuccessResult)
    assert result.outputs == {"balance": "1250.00"}
    step_ids = [trace.step_id for trace in result.steps]
    assert step_ids.count("login_submit") == 3  # initial sign-on, recovery subflow, restart
    assert trace_for(result, "search")[0].recoveries_applied == ["session_expired"]
    assert "run_restarted" in harness.evidence.kinds()


async def test_session_expiring_again_exhausts_the_recovery() -> None:
    harness = Harness(surface=lookup_app(search_route="expired"))
    result = await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, FailedResult)
    assert result.failure.code == "recovery_exhausted"
    assert "session_expired" in result.failure.message


async def test_dismiss_that_does_not_clear_exhausts_max_applications() -> None:
    surface = lookup_app(after_sign_on="notice")
    surface.transitions[("Acknowledge", "click")] = "notice"
    result = await Harness(surface=surface).engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, FailedResult)
    assert result.failure.code == "recovery_exhausted"
    assert result.failure.step_id == "login_submit"
    assert "maintenance_notice" in result.failure.message


async def test_step_scoped_rule_only_applies_to_listed_steps() -> None:
    data = lookup_capability_data()
    data["recoveries"][3]["scope"] = "step"
    steps = data["steps"]
    capability_without_listing = lookup_capability(recoveries=data["recoveries"], steps=steps)
    steps[2]["recoveries"] = ["transient_app_error"]
    capability_with_listing = lookup_capability(recoveries=data["recoveries"], steps=steps)

    unlisted = await Harness(surface=lookup_app(search_route=["error", "member"])).engine.run(
        capability_without_listing, {"member_number": KNOWN_MEMBER}
    )
    listed = await Harness(surface=lookup_app(search_route=["error", "member"])).engine.run(
        capability_with_listing, {"member_number": KNOWN_MEMBER}
    )

    assert isinstance(unlisted, SuccessResult)
    assert trace_for(unlisted, "search")[0].recoveries_applied == []
    assert isinstance(listed, SuccessResult)
    assert trace_for(listed, "search")[0].recoveries_applied == ["transient_app_error"]
