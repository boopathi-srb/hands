from __future__ import annotations

from typing import Any

import pytest

from hands.core.artifact import (
    AppRef,
    Capability,
    ExtractStep,
    InputSpec,
    OpenStep,
    SubflowStep,
    TypeStep,
)
from hands.core.conditions import AllOf, LocationMatches, NodePresent, TextVisible
from hands.discovery.loop import DiscoveryAgent
from hands.discovery.planners.scripted import (
    COREONE_BALANCE_GOAL,
    ScriptedPlanner,
    ScriptRule,
    click,
    coreone_member_balance_script,
    extract_near,
    screen_has,
    type_into,
)
from hands.discovery.recorder import RecordResult, record_capability
from hands.discovery.recorder_steps import StepIdAllocator, find_login_block
from hands.discovery.trace import DiscoveryOutcome, TraceStep
from hands.profiles import AppProfile, load_profile

from .helpers import (
    COREONE_PROFILE_PATH,
    FIXED_TIME,
    LOGIN_URL,
    TEST_PASSWORD,
    TEST_USERNAME,
    DictCredentials,
    RecordingEvidence,
    StubEscalator,
    coreone_policy,
    lakeside_fake,
    make_node,
    make_observation,
    respond,
)

APP = AppRef(vendor="Northwind Core Systems", product="CoreOne", product_version="7.4", surface="web")
INPUT_SPECS = {"member_number": InputSpec(type="string", description="Member number", pattern=r"^\d+$")}


def coreone_profile() -> AppProfile:
    loaded = load_profile(COREONE_PROFILE_PATH)
    assert loaded.profile is not None, loaded.error
    return loaded.profile


async def discover(planner: Any, escalator: StubEscalator | None = None) -> DiscoveryOutcome:
    agent = DiscoveryAgent(lakeside_fake(), planner, coreone_policy(), RecordingEvidence(), DictCredentials(),
                           escalator, run_id="run-rec")
    return await agent.run(COREONE_BALANCE_GOAL, LOGIN_URL, {"member_number": "10001"}, ["teller"])


def record(outcome: DiscoveryOutcome, profile: AppProfile | None = None, **overrides: Any) -> RecordResult:
    arguments: dict[str, Any] = {
        "capability_id": "coreone.member_savings_balance", "title": "Member savings balance",
        "description": "Returns the savings balance of a member.", "app": APP, "inputs": INPUT_SPECS,
        "profile": profile, "planner_name": "scripted", "model": None, "tenant_id": "lakeside",
        "recorded_at": FIXED_TIME,
    }
    arguments.update(overrides)
    return record_capability(outcome, **arguments)


@pytest.fixture
async def balance_outcome() -> DiscoveryOutcome:
    outcome = await discover(coreone_member_balance_script())
    assert outcome.status == "completed"
    return outcome


async def test_recorded_capability_validates_and_collapses_login(balance_outcome: DiscoveryOutcome) -> None:
    result = record(balance_outcome, coreone_profile())
    assert result.ok and result.error is None, result.error
    capability = result.capability
    assert capability is not None
    Capability.model_validate(capability.model_dump(mode="json"))
    first_step = capability.steps[0]
    assert isinstance(first_step, SubflowStep) and first_step.subflow == "login"
    assert first_step.postcondition == LocationMatches(pattern="/t/:tenant/main")
    assert "login" in capability.subflows
    assert [step.action for step in capability.steps] == ["subflow", "click", "type", "click", "extract"]
    assert capability.status == "draft" and capability.version == "1.0.0"


async def test_recorded_capability_parameterizes_and_types_outputs(balance_outcome: DiscoveryOutcome) -> None:
    capability = record(balance_outcome, coreone_profile()).capability
    assert capability is not None
    type_step = next(step for step in capability.steps if isinstance(step, TypeStep))
    assert type_step.value == "{{member_number}}"
    assert type_step.target.description == "Member Number textbox"
    assert capability.outputs["savings_balance"].type == "decimal"
    extract_step = next(step for step in capability.steps if isinstance(step, ExtractStep))
    assert extract_step.output == "savings_balance"
    serialized = capability.model_dump_json()
    for leaked in ("10001", "1,250.00", TEST_PASSWORD, TEST_USERNAME):
        assert leaked not in serialized


async def test_recorded_postconditions_and_checkpoint(balance_outcome: DiscoveryOutcome) -> None:
    capability = record(balance_outcome, coreone_profile()).capability
    assert capability is not None
    postconditions = {step.id: step.postcondition for step in capability.steps}
    assert postconditions["click_search_button"] == TextVisible(pattern="Member Detail")
    assert postconditions["type_member_number_textbox"] is None
    checkpoint = capability.checkpoint
    assert isinstance(checkpoint, AllOf)
    assert checkpoint.conditions[0] == LocationMatches(pattern="/t/:tenant/main")
    assert isinstance(checkpoint.conditions[1], NodePresent)


async def test_recorded_capability_merges_profile_and_provenance(balance_outcome: DiscoveryOutcome) -> None:
    capability = record(balance_outcome, coreone_profile()).capability
    assert capability is not None
    assert "MEMBER_NOT_FOUND" in [detector.code for detector in capability.outcomes]
    assert "session_expired" in [rule.name for rule in capability.recoveries]
    assert list(capability.credentials) == ["teller"]
    provenance = capability.provenance
    assert (provenance.discovery_run_id, provenance.planner, provenance.recorded_on_tenant) == (
        "run-rec", "scripted", "lakeside")
    assert provenance.goal == COREONE_BALANCE_GOAL


async def test_without_profile_login_steps_are_kept(balance_outcome: DiscoveryOutcome) -> None:
    result = record(balance_outcome, None, tenant_id=None)
    capability = result.capability
    assert capability is not None, result.error
    assert isinstance(capability.steps[0], OpenStep)
    assert capability.steps[0].entry_point == LOGIN_URL
    typed = [step.value for step in capability.steps if isinstance(step, TypeStep)]
    assert typed == ["{{teller.username}}", "{{teller.password}}", "{{member_number}}"]
    assert capability.credentials["teller"].fields == ["username", "password"]
    assert capability.subflows == {} and capability.outcomes == []
    location_checks = [step.postcondition for step in capability.steps
                       if isinstance(step.postcondition, LocationMatches)]
    assert LocationMatches(pattern="/t/lakeside/main") in location_checks


async def test_literal_input_value_is_parameterized() -> None:
    rules = [
        ScriptRule("user", screen_has('textbox "User ID"'), type_into("textbox", "User ID", "{{teller.username}}")),
        ScriptRule("password", screen_has('textbox "Password"'),
                   type_into("textbox", "Password", "{{teller.password}}")),
        ScriptRule("sign_on", screen_has('button "Sign On"'), click("button", "Sign On")),
        ScriptRule("inquiry", screen_has('link "Member Inquiry"'), click("link", "Member Inquiry")),
        ScriptRule("member", screen_has('textbox "Member Number"'), type_into("textbox", "Member Number", "10001")),
        ScriptRule("search", screen_has('button "Search"'), click("button", "Search")),
        ScriptRule("extract", screen_has('"Member Detail"'), extract_near("Regular Savings", 1, "savings_balance")),
        ScriptRule("done", screen_has('"Member Detail"'), lambda _context: respond("done").decision),
    ]
    outcome = await discover(ScriptedPlanner(rules))
    capability = record(outcome, coreone_profile()).capability
    assert capability is not None
    assert [step.value for step in capability.steps if isinstance(step, TypeStep)] == ["{{member_number}}"]


async def test_risky_steps_are_marked_risky() -> None:
    rules = [
        ScriptRule("user", screen_has('textbox "User ID"'), type_into("textbox", "User ID", "{{teller.username}}")),
        ScriptRule("password", screen_has('textbox "Password"'),
                   type_into("textbox", "Password", "{{teller.password}}")),
        ScriptRule("sign_on", screen_has('button "Sign On"'), click("button", "Sign On")),
        ScriptRule("inquiry", screen_has('link "Member Inquiry"'), click("link", "Member Inquiry")),
        ScriptRule("member", screen_has('textbox "Member Number"'),
                   type_into("textbox", "Member Number", "{{member_number}}")),
        ScriptRule("search", screen_has('button "Search"'), click("button", "Search")),
        ScriptRule("open_share", screen_has('button "Open Share"'), click("button", "Open Share")),
        ScriptRule("continue", screen_has('button "Continue"'), click("button", "Continue")),
        ScriptRule("submit", screen_has('button "Submit"'), click("button", "Submit")),
        ScriptRule("done", screen_has("opened for member"), lambda _context: respond("done").decision),
    ]
    outcome = await discover(ScriptedPlanner(rules), StubEscalator(["resume"]))
    result = record(outcome, coreone_profile(), inputs=INPUT_SPECS)
    capability = result.capability
    assert capability is not None, result.error
    risky = [step.id for step in capability.steps if step.risk == "risky"]
    assert risky == ["click_submit_button"]
    assert capability.outputs == {}
    assert isinstance(capability.checkpoint, AllOf)


async def test_unrecordable_outcomes_are_error_results(balance_outcome: DiscoveryOutcome) -> None:
    empty = balance_outcome.model_copy(update={"trace": []})
    assert record(empty).error == "the discovery trace is empty"
    stuck = balance_outcome.model_copy(update={"status": "stuck", "reason": "no idea"})
    stuck_result = record(stuck)
    assert not stuck_result.ok and "did not complete" in (stuck_result.error or "")
    failed_only = balance_outcome.model_copy(update={
        "trace": [step.model_copy(update={"result": "failed"}) for step in balance_outcome.trace]})
    assert record(failed_only).error == "no recordable steps in the trace"


async def test_undeclared_placeholder_is_an_error_result(balance_outcome: DiscoveryOutcome) -> None:
    result = record(balance_outcome, coreone_profile(), inputs={})
    assert not result.ok and "not a declared input" in (result.error or "")


async def test_warnings_for_unused_inputs_and_human_steps(balance_outcome: DiscoveryOutcome) -> None:
    human_step = TraceStep(index=99, action="human", observation_before=balance_outcome.trace[-1].observation_before,
                           result="human", human_summary="click on button 'OK'")
    outcome = balance_outcome.model_copy(update={"trace": [*balance_outcome.trace, human_step]})
    inputs = {**INPUT_SPECS, "branch": InputSpec(type="string", description="Unused")}
    result = record(outcome, coreone_profile(), inputs=inputs)
    assert result.ok
    assert any("a human acted" in warning for warning in result.warnings)
    assert "declared input 'branch' had no value in the discovery run" in result.warnings
    assert "declared input 'branch' is never used by a step" in result.warnings


def test_find_login_block_edge_cases() -> None:
    observation = make_observation([])
    field = make_node("n1", "textbox", label="User ID", text="")

    def step(action: str, value: str | None = None, node: Any = None) -> TraceStep:
        return TraceStep(index=0, action=action, value_template=value, node_before=node,
                         observation_before=observation, result="ok")

    names = ["teller.username", "teller.password"]
    assert find_login_block([step("click", node=field)], names) is None
    focus_block = [step("open", "http://x"), step("click", node=field), step("type", "{{teller.username}}"),
                   step("click", node=field), step("type", "{{teller.password}}"), step("press")]
    assert find_login_block(focus_block, names) == (0, 5)
    broken = [step("type", "{{teller.username}}"), step("type", "{{member_number}}", field),
              step("type", "{{teller.password}}")]
    assert find_login_block(broken, names) is None


def test_step_id_allocator_reserves_and_suffixes() -> None:
    allocator = StepIdAllocator(taken=["login_open"])
    assert allocator.allocate("Login Open") == "login_open_2"
    assert allocator.allocate("click Search button") == "click_search_button"
    assert allocator.allocate("click Search button") == "click_search_button_2"
    assert allocator.allocate("123 go") == "step_123_go"
    assert allocator.allocate("") == "step"

