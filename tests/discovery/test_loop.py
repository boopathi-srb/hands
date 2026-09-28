from __future__ import annotations

from collections.abc import Callable
from typing import Any

from hands.core.control import HumanAction
from hands.core.observation import Location
from hands.core.ports import PolicyGate
from hands.discovery.loop import DiscoveryAgent, DiscoveryLimits, summarize_human_actions
from hands.discovery.planner import PlannerContext, PlannerResponse
from hands.discovery.planners.scripted import (
    ScriptedPlanner,
    ScriptRule,
    click,
    coreone_member_balance_script,
    find_ref,
    screen_has,
    type_into,
)
from hands.discovery.trace import DiscoveryOutcome
from hands.surfaces.fake import SAME_SCREEN, FakeScreen, FakeSurface, fake_node

from .helpers import (
    FIXED_TIME,
    LOGIN_URL,
    TEST_PASSWORD,
    TEST_USERNAME,
    DictCredentials,
    FixedPolicy,
    RecordingEvidence,
    SequencePlanner,
    StubEscalator,
    coreone_policy,
    failed_response,
    lakeside_fake,
    node_named,
    respond,
)

HOME_URL = "http://app.test/home"
MEMBER_INPUTS = {"member_number": "10001"}


def home_surface() -> FakeSurface:
    buttons = ("Refresh", "Other", "Third")
    nodes = [fake_node("text", "Welcome home", path="text[1]")]
    nodes += [fake_node("button", name, path=f"button[{index}]") for index, name in enumerate(buttons, start=1)]
    home = FakeScreen(
        name="home", location=Location(kind="url", value=HOME_URL), nodes=nodes,
        transitions={(name, "click"): SAME_SCREEN for name in buttons}, entry_points=[HOME_URL],
    )
    blank = FakeScreen(name="blank", location=Location(kind="url", value="about:blank"))
    return FakeSurface([blank, home], initial="blank")


def click_button(name: str) -> Callable[[PlannerContext], PlannerResponse]:
    return lambda context: respond("click", node_ref=find_ref(context.observation_text, "button", name))


def done_after_human(name: str) -> Callable[[PlannerContext], PlannerResponse]:
    def decide(context: PlannerContext) -> PlannerResponse:
        if context.feedback and "human operator" in context.feedback:
            return respond("done")
        return click_button(name)(context)

    return decide


async def run_agent(
    planner: Any,
    *,
    surface: FakeSurface | None = None,
    policy: PolicyGate | None = None,
    escalator: StubEscalator | None = None,
    entry_point: str = HOME_URL,
    max_steps: int = 25,
    evidence: RecordingEvidence | None = None,
    registrar: Callable[[str, str], object] | None = None,
) -> tuple[DiscoveryOutcome, RecordingEvidence, FakeSurface]:
    target_surface = surface or home_surface()
    sink = evidence or RecordingEvidence()
    agent = DiscoveryAgent(
        target_surface, planner, policy or FixedPolicy(), sink, DictCredentials(), escalator,
        secret_registrar=registrar, max_steps=max_steps, run_id="run-test",
    )
    outcome = await agent.run("test goal", entry_point, MEMBER_INPUTS, ["teller"])
    return outcome, sink, target_surface


# ---------------------------------------------------------------- happy path


async def test_coreone_happy_path_completes_with_extracted_value() -> None:
    planner = coreone_member_balance_script()
    registered: list[str] = []
    outcome, _evidence, surface = await run_agent(
        planner, surface=lakeside_fake(), policy=coreone_policy(), entry_point=LOGIN_URL,
        registrar=lambda value, label: registered.append(label),
    )
    assert outcome.status == "completed", outcome.reason
    assert outcome.extracted == {"savings_balance": "1,250.00"}
    assert [step.action for step in outcome.trace] == [
        "open", "type", "type", "click", "click", "type", "click", "extract",
    ]
    assert [step.value_template for step in outcome.trace if step.action == "type"] == [
        "{{teller.username}}", "{{teller.password}}", "{{member_number}}",
    ]
    assert all(step.observation_after is not None for step in outcome.trace)
    assert outcome.credential_names == ["teller.username", "teller.password"]
    assert registered == ["teller.username", "teller.password"]
    assert surface.current_screen == "member_10001"


async def test_coreone_happy_path_records_evidence_for_everything() -> None:
    outcome, evidence, _surface = await run_agent(
        coreone_member_balance_script(), surface=lakeside_fake(), policy=coreone_policy(), entry_point=LOGIN_URL,
    )
    kinds = evidence.kinds()
    for kind in ("run_started", "observation", "decision", "policy_decision", "action", "action_result",
                 "run_finished"):
        assert kind in kinds
    decision_events = [data for data in evidence.of_kind("decision") if "latency_ms" in data]
    assert len(decision_events) == outcome.planner_calls
    assert {"rationale", "input_tokens", "output_tokens"} <= set(decision_events[0])
    assert len(evidence.screenshots) == len(evidence.snapshots) >= outcome.planner_calls
    assert evidence.json_documents["discovery_trace"]["status"] == "completed"


async def test_secrets_never_reach_model_trace_or_evidence() -> None:
    planner = coreone_member_balance_script()
    outcome, evidence, _surface = await run_agent(
        planner, surface=lakeside_fake(), policy=coreone_policy(), entry_point=LOGIN_URL,
    )
    for secret in (TEST_PASSWORD, TEST_USERNAME):
        assert secret not in evidence.all_text()
        assert secret not in outcome.model_dump_json()
        for context in planner.contexts:
            assert secret not in context.model_dump_json()
    assert any("Signed on as ••••" in context.observation_text for context in planner.contexts)


# ---------------------------------------------------------------- invalid decisions


class FailOnceThen:
    def __init__(self, inner: ScriptedPlanner) -> None:
        self._inner = inner
        self.contexts: list[PlannerContext] = []

    async def decide(self, context: PlannerContext) -> PlannerResponse:
        self.contexts.append(context)
        if len(self.contexts) == 1:
            return failed_response("invalid JSON: Expecting value at char 0")
        return await self._inner.decide(context)


async def test_invalid_decision_is_reprompted_then_succeeds() -> None:
    planner = FailOnceThen(coreone_member_balance_script())
    outcome, _evidence, _surface = await run_agent(
        planner, surface=lakeside_fake(), policy=coreone_policy(), entry_point=LOGIN_URL,
    )
    assert outcome.status == "completed"
    assert outcome.invalid_decisions == 1
    assert planner.contexts[1].feedback is not None and "invalid JSON" in planner.contexts[1].feedback
    assert planner.contexts[2].feedback is None


async def test_unknown_ref_is_rejected_until_the_limit() -> None:
    planner = SequencePlanner([respond("click", node_ref="n999")])
    outcome, evidence, surface = await run_agent(planner)
    assert outcome.status == "error"
    assert "3 invalid decisions" in outcome.reason
    assert "not on the current SCREEN" in (planner.contexts[1].feedback or "")
    assert [recorded.action.kind for recorded in surface.actions] == ["open"]
    assert any(data.get("rejected") for data in evidence.of_kind("decision"))


async def test_literal_credential_is_rejected_and_never_typed() -> None:
    planner = SequencePlanner([
        lambda context: respond("type", node_ref=find_ref(context.observation_text, "textbox", "User ID"),
                                value=TEST_USERNAME),
        respond("stuck", rationale="giving up"),
    ])
    outcome, evidence, surface = await run_agent(planner, surface=lakeside_fake(), policy=coreone_policy(),
                                                 entry_point=LOGIN_URL)
    assert outcome.status == "stuck"
    assert "never type credential values" in (planner.contexts[1].feedback or "")
    assert [recorded.action.kind for recorded in surface.actions] == ["open"]
    assert TEST_USERNAME not in evidence.all_text()


# ---------------------------------------------------------------- stuck detection and escalation


async def test_repetition_is_stuck_without_escalator() -> None:
    outcome, _evidence, surface = await run_agent(SequencePlanner([click_button("Refresh")]))
    assert outcome.status == "stuck"
    assert "repeated" in outcome.reason
    assert [recorded.action.kind for recorded in surface.actions] == ["open", "click", "click"]


async def test_repetition_escalates_and_resume_continues_with_human_note() -> None:
    human = HumanAction(at=FIXED_TIME, kind="click", node_role="button", node_name="Other")
    escalator = StubEscalator(["resume"], human_actions=[human], note="fixed it")
    planner = SequencePlanner([done_after_human("Refresh")])
    outcome, _evidence, _surface = await run_agent(planner, escalator=escalator)
    assert outcome.status == "completed"
    request = escalator.requests[0]
    assert request.kind == "stuck" and request.mode == "discovery" and request.location == HOME_URL
    assert request.screenshot_path is not None
    assert outcome.interventions == [request.intervention_id]
    feedback = planner.contexts[-1].feedback or ""
    assert feedback.startswith("A human operator acted: click on button 'Other'")
    assert "note: fixed it" in feedback
    assert [step.action for step in outcome.trace][-1] == "human"


async def test_repetition_escalation_abort_ends_the_run() -> None:
    outcome, _evidence, _surface = await run_agent(
        SequencePlanner([click_button("Refresh")]), escalator=StubEscalator(["abort"])
    )
    assert outcome.status == "escalated_abort"


async def test_planner_stuck_ends_without_escalator() -> None:
    outcome, _evidence, _surface = await run_agent(SequencePlanner([respond("stuck", rationale="no idea")]))
    assert outcome.status == "stuck" and "no idea" in outcome.reason


async def test_three_failed_actions_after_open_are_stuck() -> None:
    surface = home_surface()
    planner = SequencePlanner([
        _fail_then(surface, click_button("Refresh")),
        _fail_then(surface, click_button("Other")),
        _fail_then(surface, click_button("Third")),
    ])
    outcome, _evidence, _surface = await run_agent(planner, surface=surface)
    assert outcome.status == "stuck"
    assert "3 actions failed in a row" in outcome.reason
    assert "element detached" in (planner.contexts[1].feedback or "")
    assert [step.result for step in outcome.trace[1:]] == ["failed", "failed", "failed"]


def _fail_then(
    surface: FakeSurface, decide: Callable[[PlannerContext], PlannerResponse]
) -> Callable[[PlannerContext], PlannerResponse]:
    def arm_and_decide(context: PlannerContext) -> PlannerResponse:
        surface.fail_next_act("element detached")
        return decide(context)

    return arm_and_decide


async def test_budget_exhausted_without_escalator() -> None:
    planner = SequencePlanner([click_button("Refresh"), click_button("Other")])
    outcome, _evidence, _surface = await run_agent(planner, max_steps=2)
    assert outcome.status == "budget_exhausted"
    assert outcome.planner_calls == 2


async def test_budget_exhausted_escalation_grants_more_steps() -> None:
    planner = SequencePlanner([click_button("Refresh"), done_after_human("Other")])
    outcome, _evidence, _surface = await run_agent(planner, max_steps=1, escalator=StubEscalator(["resume"]))
    assert outcome.status == "completed"
    assert outcome.planner_calls == 2


# ---------------------------------------------------------------- policy


async def test_policy_deny_is_fed_back_to_the_model() -> None:
    planner = SequencePlanner([click_button("Refresh"), respond("done")])
    outcome, evidence, surface = await run_agent(planner, policy=FixedPolicy(deny_when=node_named("Refresh")))
    assert outcome.status == "completed"
    assert outcome.trace[1].result == "denied" and outcome.trace[1].policy_rule == "test.deny"
    assert "Policy refused that action" in (planner.contexts[1].feedback or "")
    assert [recorded.action.kind for recorded in surface.actions] == ["open"]
    assert "deny" in [data["verdict"] for data in evidence.of_kind("policy_decision")]


async def test_risky_action_escalates_and_resume_performs_it() -> None:
    escalator = StubEscalator(["resume"])
    planner = SequencePlanner([click_button("Refresh"), respond("done")])
    outcome, _evidence, surface = await run_agent(
        planner, policy=FixedPolicy(escalate_when=node_named("Refresh")), escalator=escalator,
    )
    assert outcome.status == "completed"
    assert escalator.requests[0].kind == "risky_action"
    assert outcome.trace[1].risk == "risky" and outcome.trace[1].result == "ok"
    assert [recorded.action.kind for recorded in surface.actions] == ["open", "click"]


async def test_risky_action_abort_and_human_completion_and_no_escalator() -> None:
    risky = FixedPolicy(escalate_when=node_named("Refresh"))
    aborted, _evidence, _surface = await run_agent(
        SequencePlanner([click_button("Refresh")]), policy=risky, escalator=StubEscalator(["abort"]),
    )
    assert aborted.status == "escalated_abort"
    planner = SequencePlanner([click_button("Refresh"), respond("done")])
    by_human, _evidence, surface = await run_agent(
        planner, policy=risky, escalator=StubEscalator(["step_completed_by_human"]),
    )
    assert by_human.status == "completed" and by_human.trace[-1].action == "human"
    assert [recorded.action.kind for recorded in surface.actions] == ["open"]
    no_escalator, _evidence, _surface = await run_agent(
        SequencePlanner([click_button("Refresh"), respond("done")]), policy=risky,
    )
    assert no_escalator.trace[1].result == "denied"
    assert "needs human approval" in (no_escalator.trace[1].error or "")


def _open_share_script() -> ScriptedPlanner:
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
        ScriptRule("done", screen_has("opened for member"),
                   lambda _context: respond("done").decision),
    ]
    return ScriptedPlanner(rules)


async def test_real_policy_escalates_submit_on_review_page() -> None:
    escalator = StubEscalator(["resume"])
    outcome, _evidence, surface = await run_agent(
        _open_share_script(), surface=lakeside_fake(), policy=coreone_policy(), escalator=escalator,
        entry_point=LOGIN_URL,
    )
    assert outcome.status == "completed", outcome.reason
    assert [request.kind for request in escalator.requests] == ["risky_action"]
    submit_step = next(step for step in outcome.trace if step.node_before and step.node_before.name == "Submit")
    assert submit_step.risk == "risky" and submit_step.policy_rule == "risk.handling.discovery"
    assert surface.current_screen == "share_opened_10001"


# ---------------------------------------------------------------- entry point


async def test_entry_point_denied_by_policy_is_an_error() -> None:
    policy = FixedPolicy(deny_when=lambda request: request.action.kind == "open")
    outcome, _evidence, surface = await run_agent(SequencePlanner([respond("done")]), policy=policy)
    assert outcome.status == "error" and "entry point" in outcome.reason
    assert surface.actions == []


async def test_unknown_entry_point_is_an_error() -> None:
    outcome, _evidence, _surface = await run_agent(SequencePlanner([respond("done")]),
                                                   entry_point="http://app.test/nowhere")
    assert outcome.status == "error"
    assert outcome.trace[0].result == "failed"


async def test_limits_object_overrides_positional_limits() -> None:
    agent = DiscoveryAgent(home_surface(), SequencePlanner([click_button("Refresh"), click_button("Other")]),
                           FixedPolicy(), RecordingEvidence(), DictCredentials(),
                           limits=DiscoveryLimits(max_steps=1))
    outcome = await agent.run("goal", HOME_URL, {}, [])
    assert outcome.status == "budget_exhausted" and outcome.planner_calls == 1


def test_summarize_human_actions() -> None:
    from hands.core.control import InterventionResolution

    actions = [
        HumanAction(at=FIXED_TIME, kind="type", text_length=6),
        HumanAction(at=FIXED_TIME, kind="press", key="Enter"),
        HumanAction(at=FIXED_TIME, kind="scroll"),
    ]
    resolution = InterventionResolution(intervention_id="i", outcome="resume", operator_id="o",
                                        human_actions=actions, resolved_at=FIXED_TIME)
    assert summarize_human_actions(resolution) == "typed 6 characters; pressed Enter; scroll"
    empty = resolution.model_copy(update={"human_actions": []})
    assert summarize_human_actions(empty) == "no recorded inputs"
