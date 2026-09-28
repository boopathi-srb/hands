"""ConsoleEscalator (without HTTP) and ScriptedEscalator."""

from __future__ import annotations

import asyncio

from hands.core.observation import Node, Rect
from hands.core.ports import KeyEvent, PointerEvent
from hands.session.board import InterventionBoard
from hands.session.doubles import (
    InMemoryEvidence,
    StubLiveView,
    StubSurface,
    make_intervention_request,
    make_observation,
)
from hands.session.escalation import (
    SYSTEM_OPERATOR,
    ConsoleEscalator,
    ScriptedEscalator,
    operator_url,
)
from hands.session.lease import LeaseManager

SESSION = "session-1"
RUN = "run-1"
ACK_BUTTON = Node(
    ref="n1", role="button", name="Acknowledge", bounds=Rect(x=0, y=0, width=100, height=30)
)


class Harness:
    def __init__(self) -> None:
        self.board = InterventionBoard()
        self.evidence = InMemoryEvidence()
        self.lease = LeaseManager(SESSION, interventions=self.board, evidence=self.evidence)
        self.lease.grant_automation(RUN)
        self.announcements: list[str] = []

    def console(self, timeout_s: float | None = 1.0) -> ConsoleEscalator:
        return ConsoleEscalator(
            self.board,
            self.lease,
            self.evidence,
            console_url="http://127.0.0.1:9999/",
            timeout_s=timeout_s,
            announce=self.announcements.append,
        )


async def wait_until_open(board: InterventionBoard) -> None:
    for _ in range(200):
        if board.list_open():
            return
        await asyncio.sleep(0.005)


def test_operator_url_strips_trailing_slash() -> None:
    assert operator_url("http://h:1/", "iv-9") == "http://h:1/?intervention=iv-9"


async def test_console_escalator_releases_lease_and_resumes_on_resolution() -> None:
    harness = Harness()
    task = asyncio.create_task(harness.console().escalate(make_intervention_request()))
    await wait_until_open(harness.board)

    assert harness.lease.current().holder == "nobody"
    assert "http://127.0.0.1:9999/?intervention=iv-1" in harness.announcements[0]
    harness.board.resolve_from_operator("iv-1", "resume", "alice", "dismissed modal")
    resolution = await task

    assert resolution.outcome == "resume" and resolution.operator_id == "alice"
    assert harness.lease.is_held_by("automation", RUN)
    kinds = harness.evidence.kinds()
    assert kinds.index("escalation_raised") < kinds.index("escalation_resolved")
    raised = harness.evidence.of_kind("escalation_raised")[0]
    assert raised["reason"] and "screenshot_path" in raised
    assert raised["intervention_kind"] == "stuck"


async def test_console_escalator_abort_leaves_lease_with_nobody() -> None:
    harness = Harness()
    task = asyncio.create_task(harness.console().escalate(make_intervention_request()))
    await wait_until_open(harness.board)
    harness.board.resolve_from_operator("iv-1", "abort", "alice", "member must call in")
    resolution = await task
    assert resolution.outcome == "abort"
    assert harness.lease.current().holder == "nobody"
    assert harness.evidence.of_kind("escalation_resolved")[0]["holder_after"] == "nobody"


async def test_console_escalator_times_out_to_abort() -> None:
    harness = Harness()
    resolution = await harness.console(timeout_s=0.02).escalate(make_intervention_request())
    assert resolution.outcome == "abort"
    assert resolution.operator_id == SYSTEM_OPERATOR
    assert "no operator resolution" in resolution.note
    assert harness.lease.current().holder == "nobody"
    assert "escalation_timeout" in harness.evidence.kinds()
    assert harness.board.list_open() == []


async def test_console_escalator_timeout_force_releases_a_human_holder() -> None:
    harness = Harness()
    task = asyncio.create_task(
        harness.console(timeout_s=0.05).escalate(make_intervention_request())
    )
    await wait_until_open(harness.board)
    assert harness.lease.take_human("alice").ok
    resolution = await task
    assert resolution.outcome == "abort"
    assert harness.lease.current().holder == "nobody"
    assert harness.lease.audit_trail()[-1].from_holder == "human"


async def test_escalation_for_a_different_session_is_refused() -> None:
    harness = Harness()
    request = make_intervention_request(session_id="session-other")
    resolution = await harness.console().escalate(request)
    assert resolution.outcome == "abort" and resolution.operator_id == SYSTEM_OPERATOR
    assert "escalation refused" in resolution.note
    assert harness.lease.is_held_by("automation", RUN)
    assert harness.board.list_open() == []


async def test_duplicate_intervention_is_refused_without_touching_lease() -> None:
    harness = Harness()
    harness.board.open(make_intervention_request())
    harness.board.resolve_from_operator("iv-1", "resume", "alice")
    resolution = await harness.console().escalate(make_intervention_request())
    assert resolution.outcome == "abort" and "duplicate_intervention" in resolution.note
    assert harness.lease.is_held_by("automation", RUN)


async def test_scripted_escalator_performs_actions_through_live_view() -> None:
    harness = Harness()
    transport = StubLiveView()
    surface = StubSurface(make_observation([ACK_BUTTON]), live_view=transport)
    escalator = ScriptedEscalator(
        harness.board,
        harness.lease,
        harness.evidence,
        outcome="step_completed_by_human",
        note="acknowledged notice",
        script=[
            PointerEvent(type="click", x=50, y=15),
            KeyEvent(type="char", key="o", text="ok"),
        ],
        surface=surface,
    )
    resolution = await escalator.escalate(make_intervention_request())

    assert resolution.outcome == "step_completed_by_human"
    assert resolution.operator_id == "scripted-operator"
    assert [a.kind for a in resolution.human_actions] == ["click", "type"]
    assert resolution.human_actions[0].node_name == "Acknowledge"
    assert len(transport.pointer_events) == 1 and len(transport.key_events) == 1
    holders = [t.to_holder for t in harness.lease.audit_trail()]
    assert holders == ["automation", "nobody", "human", "nobody", "automation"]
    assert len(harness.evidence.of_kind("human_action")) == 2


async def test_scripted_escalator_without_script_just_resolves() -> None:
    harness = Harness()
    escalator = ScriptedEscalator(harness.board, harness.lease, harness.evidence, outcome="abort")
    resolution = await escalator.escalate(make_intervention_request())
    assert resolution.outcome == "abort" and resolution.human_actions == []
    assert harness.lease.current().holder == "nobody"


async def test_scripted_escalator_aborts_when_take_is_refused() -> None:
    harness = Harness()
    escalator = ScriptedEscalator(harness.board, harness.lease, harness.evidence, operator_id="")
    resolution = await escalator.escalate(make_intervention_request())
    assert resolution.outcome == "abort"
    assert resolution.operator_id == SYSTEM_OPERATOR
    assert "invalid_identity" in resolution.note
