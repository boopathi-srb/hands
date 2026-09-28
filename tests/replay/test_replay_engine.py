"""ReplayEngine behaviour against a scripted member-lookup app: success, business outcomes, hard failures."""

from __future__ import annotations

from hands.core.results import BusinessOutcomeResult, FailedResult, SuccessResult

from .app import (
    KNOWN_MEMBER,
    MISSING_MEMBER,
    RESTRICTED_MEMBER,
    Harness,
    lookup_app,
    lookup_capability,
    lookup_capability_data,
    lookup_steps,
    role_name,
    target,
    text_visible,
)
from .fakes import FakeCredentials


async def test_happy_path_returns_typed_outputs_and_traces() -> None:
    harness = Harness()
    result = await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER}, run_id="run-happy")

    assert isinstance(result, SuccessResult)
    assert result.outputs == {"balance": "1250.00"}
    assert result.run_id == "run-happy"
    assert [trace.step_id for trace in result.steps] == [
        "login_open", "login_user", "login_password", "login_submit", "sign_in",
        "type_member", "search", "read_balance",
    ]
    assert all(trace.status == "ok" for trace in result.steps)
    assert result.drift.fallback_steps == []
    assert result.evidence_dir == "evidence/test-run"


async def test_happy_path_types_credentials_and_member_number() -> None:
    harness = Harness()
    await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    typed = [action.text for _target, action in harness.surface.actions if action.kind == "type"]
    assert typed == ["teller1", "pw-123", KNOWN_MEMBER]


async def test_happy_path_emits_evidence_for_every_phase_and_writes_result() -> None:
    harness = Harness()
    await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    kinds = harness.evidence.kinds()
    for expected_kind in ("run_started", "step_started", "target_resolved", "policy_decision", "action",
                          "action_result", "checkpoint", "step_finished", "run_finished"):
        assert expected_kind in kinds, expected_kind
    assert harness.evidence.documents["result"].status == "success"
    typed_events = [data["action"] for data in harness.evidence.of_kind("action") if data["action"]["kind"] == "type"]
    assert all("text" not in action and action["text_length"] > 0 for action in typed_events)


async def test_member_not_found_is_a_business_outcome_with_message() -> None:
    harness = Harness()
    result = await harness.engine.run(lookup_capability(), {"member_number": MISSING_MEMBER})

    assert isinstance(result, BusinessOutcomeResult)
    assert result.code == "MEMBER_NOT_FOUND"
    assert result.message == f"No member found for number {MISSING_MEMBER}."
    assert result.at_step == "search"
    assert "outcome_detected" in harness.evidence.kinds()


async def test_restricted_member_is_a_business_outcome() -> None:
    result = await Harness().engine.run(lookup_capability(), {"member_number": RESTRICTED_MEMBER})

    assert isinstance(result, BusinessOutcomeResult)
    assert result.code == "MEMBER_RESTRICTED"
    assert result.message is not None and result.message.startswith("ACCESS DENIED")


async def test_invalid_format_rejected_by_input_pattern_before_touching_the_app() -> None:
    harness = Harness()
    result = await harness.engine.run(lookup_capability(), {"member_number": "12AB"})

    assert isinstance(result, FailedResult)
    assert result.failure.code == "invalid_input"
    assert "member_number" in result.failure.message
    assert harness.surface.actions == []
    assert harness.surface.observation_count == 0


async def test_invalid_format_rejected_by_the_app_is_a_business_outcome() -> None:
    data = lookup_capability_data()
    data["inputs"] = {"member_number": {"type": "string", "description": "Member number"}}
    result = await Harness().engine.run(lookup_capability(inputs=data["inputs"]), {"member_number": "12AB"})

    assert isinstance(result, BusinessOutcomeResult)
    assert result.code == "INVALID_MEMBER_NUMBER"
    assert result.message is None


async def test_outcome_scoped_to_another_step_does_not_fire() -> None:
    data = lookup_capability_data()
    data["outcomes"][0]["scope"] = ["type_member"]
    harness = Harness()
    result = await harness.engine.run(lookup_capability(outcomes=data["outcomes"]), {"member_number": MISSING_MEMBER})

    assert isinstance(result, FailedResult)
    assert result.failure.code == "postcondition_timeout"


async def test_slow_load_within_timeout_succeeds() -> None:
    harness = Harness(surface=lookup_app(search_route=["loading"] * 5 + ["member"]))
    result = await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, SuccessResult)
    assert harness.clock.sleeps.count(0.25) >= 5


async def test_slow_load_beyond_timeout_fails_with_expected_and_observed() -> None:
    steps = lookup_steps()
    steps[2]["timeout_ms"] = 1_000
    harness = Harness(surface=lookup_app(search_route=["loading"] * 50 + ["member"]))
    result = await harness.engine.run(lookup_capability(steps=steps), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, FailedResult)
    failure = result.failure
    assert failure.code == "postcondition_timeout"
    assert failure.step_id == "search"
    assert failure.expected is not None and "Member Detail" in failure.expected
    assert failure.observed is not None and "Loading..." in failure.observed
    assert "http://app.test/main" in failure.observed
    assert failure.evidence == ["snapshots/failure-search.json", "screenshots/failure-search.png"]
    assert result.steps[-1].step_id == "search" and result.steps[-1].status == "failed"


async def test_target_never_resolving_is_target_not_found_with_candidates() -> None:
    steps = lookup_steps()
    steps[2]["target"] = target("Lookup button", role_name("button", "Lookup"), role_name("link", "Lookup"))
    steps[2]["timeout_ms"] = 500
    result = await Harness().engine.run(lookup_capability(steps=steps), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, FailedResult)
    assert result.failure.code == "target_not_found"
    assert result.failure.expected is not None
    assert "role_name(button 'Lookup')" in result.failure.expected
    assert "role_name(link 'Lookup')" in result.failure.expected


async def test_precondition_timeout() -> None:
    steps = lookup_steps()
    steps[1]["precondition"] = text_visible("Never shown")
    steps[1]["timeout_ms"] = 500
    result = await Harness().engine.run(lookup_capability(steps=steps), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, FailedResult)
    assert result.failure.code == "precondition_timeout"
    assert result.failure.step_id == "type_member"


async def test_checkpoint_failure_reports_expected_condition() -> None:
    result = await Harness().engine.run(
        lookup_capability(checkpoint=text_visible("Never shown")), {"member_number": KNOWN_MEMBER}
    )

    assert isinstance(result, FailedResult)
    assert result.failure.code == "checkpoint_failed"
    assert result.failure.step_id is None
    assert result.failure.expected is not None and "Never shown" in result.failure.expected


async def test_act_failure_is_retried_once_after_reobserving() -> None:
    harness = Harness()
    harness.surface.fail_next_acts = 1
    result = await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, SuccessResult)
    assert "action_retry" in harness.evidence.kinds()


async def test_act_failing_twice_is_action_failed() -> None:
    harness = Harness()
    harness.surface.fail_next_acts = 2
    result = await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, FailedResult)
    assert result.failure.code == "action_failed"
    assert result.failure.step_id == "login_open"
    assert result.failure.observed is not None and "simulated act failure" in result.failure.observed


async def test_surface_exception_is_surface_error() -> None:
    harness = Harness()
    harness.surface.observe_error = ConnectionError("browser crashed")
    result = await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, FailedResult)
    assert result.failure.code == "surface_error"
    assert result.failure.evidence == []


async def test_act_exception_is_surface_error() -> None:
    harness = Harness()
    harness.surface.act_error = RuntimeError("driver gone")
    result = await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, FailedResult)
    assert result.failure.code == "surface_error"


async def test_extraction_pattern_mismatch_is_extraction_failed() -> None:
    steps = lookup_steps()
    steps[3]["pattern"] = r"Available:\s*(.+)"
    result = await Harness().engine.run(lookup_capability(steps=steps), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, FailedResult)
    assert result.failure.code == "extraction_failed"
    assert result.failure.observed is not None and "Balance: $1,250.00" in result.failure.observed


async def test_extraction_of_wrong_type_is_extraction_failed() -> None:
    outputs = {"balance": {"type": "integer", "description": "Balance"}}
    steps = lookup_steps()
    steps[3]["pattern"] = r"Balance:\s*\$(.+)"
    result = await Harness().engine.run(lookup_capability(outputs=outputs, steps=steps), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, FailedResult)
    assert result.failure.code == "extraction_failed"


async def test_run_timeout() -> None:
    harness = Harness(surface=lookup_app(search_route=["loading"] * 100 + ["member"]))
    result = await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER}, run_timeout_ms=3_000)

    assert isinstance(result, FailedResult)
    assert result.failure.code == "run_timeout"


async def test_missing_credential_is_invalid_input() -> None:
    credentials = FakeCredentials({("teller", "username"): "teller1"})
    harness = Harness(credentials=credentials)
    result = await harness.engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, FailedResult)
    assert result.failure.code == "invalid_input"
    assert "credential 'teller.password' is missing" in result.failure.message
    assert harness.surface.actions == []


async def test_credentials_and_sensitive_inputs_are_registered_as_secrets() -> None:
    data = lookup_capability_data()
    data["inputs"]["verification_code"] = {"type": "string", "description": "Code", "sensitive": True,
                                           "required": False}
    harness = Harness()
    await harness.engine.run(
        lookup_capability(inputs=data["inputs"]), {"member_number": KNOWN_MEMBER, "verification_code": "7788"}
    )

    registered = {label_text: value for value, label_text in harness.secrets.registered}
    assert registered["input:verification_code"] == "7788"
    assert registered["credential:teller.username"] == "teller1"
    assert registered["credential:teller.password"] == "pw-123"
    assert "pw-123" not in str(harness.evidence.events)


async def test_sensitive_input_is_not_echoed_when_rejected() -> None:
    data = lookup_capability_data()
    data["inputs"]["verification_code"] = {"type": "string", "description": "Code", "sensitive": True,
                                           "pattern": r"^\d{4}$"}
    result = await Harness().engine.run(
        lookup_capability(inputs=data["inputs"]), {"member_number": KNOWN_MEMBER, "verification_code": "secret-xyz"}
    )

    assert isinstance(result, FailedResult)
    assert "secret-xyz" not in result.model_dump_json()
    assert result.failure.observed == "<sensitive value, 10 characters>"


async def test_empty_inputs_for_a_capability_without_inputs_succeeds() -> None:
    data = lookup_capability_data()
    steps = [step for step in lookup_steps() if step["id"] != "type_member"]
    steps[1]["target"] = target("Search", role_name("button", "Search"))
    capability = lookup_capability(inputs={}, steps=steps, outcomes=data["outcomes"][1:])
    harness = Harness(surface=lookup_app(search_route="member"))

    result = await harness.engine.run(capability, {})
    none_result = await Harness(surface=lookup_app(search_route="member")).engine.run(capability, None)

    assert isinstance(result, SuccessResult)
    assert isinstance(none_result, SuccessResult)


async def test_missing_and_none_required_inputs_are_invalid_input() -> None:
    empty = await Harness().engine.run(lookup_capability(), {})
    none_value = await Harness().engine.run(lookup_capability(), {"member_number": None})

    for result in (empty, none_value):
        assert isinstance(result, FailedResult)
        assert result.failure.code == "invalid_input"
        assert "missing required input 'member_number'" in result.failure.message


async def test_unknown_input_is_invalid_input() -> None:
    result = await Harness().engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER, "extra": "x"})

    assert isinstance(result, FailedResult)
    assert "unknown input 'extra'" in result.failure.message


async def test_fallback_candidate_is_reported_as_drift() -> None:
    surface = lookup_app()
    surface.transitions[("Sign On", "click")] = "find_inquiry"
    result = await Harness(surface=surface).engine.run(lookup_capability(), {"member_number": KNOWN_MEMBER})

    assert isinstance(result, SuccessResult)
    assert result.drift.fallback_steps == ["search"]
    assert result.drift.drifted
    search_trace = next(trace for trace in result.steps if trace.step_id == "search")
    assert search_trace.matched_candidate_rank == 1
    assert search_trace.matched_candidate_kind == "role_name"
    assert search_trace.fingerprint == "fp-find_inquiry"


async def test_tenant_aliases_are_applied_at_resolution_time_without_drift() -> None:
    surface = lookup_app()
    surface.transitions[("Sign On", "click")] = "aliased_inquiry"
    aliases = {"Member Number": "Account Number", "Search": "Find"}
    result = await Harness(surface=surface).engine.run(
        lookup_capability(), {"member_number": KNOWN_MEMBER}, tenant_id="prairie", aliases=aliases
    )

    assert isinstance(result, SuccessResult)
    assert result.tenant_id == "prairie"
    assert result.drift.fallback_steps == []
