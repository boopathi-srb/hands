"""HumanInputChannel and the pure event -> HumanAction converters."""

from __future__ import annotations

import json
from datetime import UTC, datetime

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
from hands.session.human_input import (
    HumanInputChannel,
    InputAccepted,
    InputRejected,
    human_action_evidence,
    is_printable_key,
    key_to_action,
    pointer_to_action,
)
from hands.session.lease import LeaseManager

SESSION = "session-1"
FIELD = Node(ref="n1", role="textbox", name="Answer", bounds=Rect(x=0, y=0, width=200, height=20))
NOW = datetime.now(UTC)


class Setup:
    def __init__(
        self, live_view: StubLiveView | None = None, take: bool = True, has_live_view: bool = True
    ) -> None:
        self.board = InterventionBoard()
        self.board.open(make_intervention_request())
        self.lease = LeaseManager(SESSION, interventions=self.board)
        self.transport = live_view if live_view is not None else StubLiveView()
        exposed_view = self.transport if has_live_view else None
        self.surface = StubSurface(make_observation([FIELD]), live_view=exposed_view)
        self.evidence = InMemoryEvidence()
        self.channel = HumanInputChannel(
            SESSION, self.lease, self.board, self.surface, self.evidence
        )
        if take:
            self.lease.take_human("alice")


def test_pointer_to_action_click_wheel_and_ignored_types() -> None:
    click = pointer_to_action(PointerEvent(type="click", x=5, y=6), FIELD, NOW)
    wheel = pointer_to_action(PointerEvent(type="wheel", x=1, y=1, delta_y=40), None, NOW)
    assert click is not None and click.kind == "click" and click.node_name == "Answer"
    assert wheel is not None and wheel.kind == "scroll" and wheel.node_role is None
    for ignored in ("down", "up", "move"):
        assert pointer_to_action(PointerEvent(type=ignored, x=0, y=0), FIELD, NOW) is None


def test_key_to_action_never_keeps_printable_text() -> None:
    typed = key_to_action(KeyEvent(type="char", key="x", text="xyz"), FIELD, NOW)
    typed_without_text = key_to_action(KeyEvent(type="char", key="q"), None, NOW)
    printable_down = key_to_action(KeyEvent(type="down", key="z"), None, NOW)
    enter = key_to_action(KeyEvent(type="down", key="Enter"), FIELD, NOW)
    assert typed is not None and typed.kind == "type" and typed.text_length == 3
    assert typed.key is None and typed.node_name == "Answer"
    assert typed_without_text is not None and typed_without_text.text_length == 1
    assert (
        printable_down is not None and printable_down.kind == "type" and printable_down.key is None
    )
    assert enter is not None and enter.kind == "press" and enter.key == "Enter"
    assert key_to_action(KeyEvent(type="up", key="Enter"), None, NOW) is None


def test_human_action_evidence_renames_kind() -> None:
    action = key_to_action(KeyEvent(type="down", key="Escape"), None, NOW)
    assert action is not None
    fields = human_action_evidence(action)
    assert fields["action_kind"] == "press" and "kind" not in fields
    assert fields["key"] == "Escape" and "node_name" not in fields


def test_is_printable_key() -> None:
    assert is_printable_key("a")
    assert not is_printable_key("Enter")
    assert not is_printable_key("")


async def test_rejects_input_when_operator_does_not_hold_lease() -> None:
    setup = Setup(take=False)
    result = await setup.channel.send_pointer("alice", PointerEvent(type="click", x=1, y=1))
    assert isinstance(result, InputRejected) and result.code == "not_in_control"
    assert setup.transport.pointer_events == []
    assert setup.evidence.events == []


async def test_rejects_input_from_a_different_operator() -> None:
    setup = Setup()
    result = await setup.channel.send_key("mallory", KeyEvent(type="char", key="a", text="a"))
    assert isinstance(result, InputRejected) and result.code == "not_in_control"
    assert setup.transport.key_events == []


async def test_rejects_input_when_no_intervention_is_open() -> None:
    setup = Setup()
    setup.board.resolve_from_operator("iv-1", "abort", "alice")
    result = await setup.channel.send_key("alice", KeyEvent(type="down", key="Enter"))
    assert isinstance(result, InputRejected) and result.code == "no_open_intervention"


async def test_rejects_input_when_surface_has_no_live_view() -> None:
    setup = Setup(has_live_view=False)
    result = await setup.channel.send_key("alice", KeyEvent(type="down", key="Enter"))
    assert isinstance(result, InputRejected) and result.code == "no_live_view"


async def test_reports_transport_failure() -> None:
    setup = Setup(live_view=StubLiveView(fail_injection=True))
    result = await setup.channel.send_pointer("alice", PointerEvent(type="click", x=1, y=1))
    assert isinstance(result, InputRejected) and result.code == "inject_failed"
    assert setup.evidence.events == []


async def test_click_then_typing_is_captured_without_text() -> None:
    setup = Setup()
    click = await setup.channel.send_pointer("alice", PointerEvent(type="click", x=10, y=10))
    for character in "s3cret":
        await setup.channel.send_key("alice", KeyEvent(type="char", key=character, text=character))
    enter = await setup.channel.send_key("alice", KeyEvent(type="down", key="Enter"))

    assert isinstance(click, InputAccepted) and click.action is not None
    assert click.action.node_role == "textbox" and click.action.node_name == "Answer"
    assert isinstance(enter, InputAccepted)
    assert len(setup.transport.key_events) == 7
    record = setup.board.get("iv-1")
    assert record is not None
    summary = [(a.kind, a.text_length, a.key, a.node_name) for a in record.human_actions]
    assert summary == [
        ("click", None, None, "Answer"),
        ("type", 6, None, "Answer"),
        ("press", None, "Enter", "Answer"),
    ]
    assert len(setup.evidence.of_kind("human_action")) == 8
    assert "s3cret" not in json.dumps(setup.evidence.events, default=str)


async def test_unrecorded_events_are_injected_but_not_recorded() -> None:
    setup = Setup()
    moved = await setup.channel.send_pointer("alice", PointerEvent(type="move", x=1, y=1))
    key_up = await setup.channel.send_key("alice", KeyEvent(type="up", key="Shift"))
    assert isinstance(moved, InputAccepted) and moved.action is None
    assert isinstance(key_up, InputAccepted) and key_up.action is None
    assert len(setup.transport.pointer_events) == 1
    assert setup.evidence.events == []


async def test_tab_clears_focus_attribution() -> None:
    setup = Setup()
    await setup.channel.send_pointer("alice", PointerEvent(type="click", x=10, y=10))
    await setup.channel.send_key("alice", KeyEvent(type="down", key="Tab"))
    typed = await setup.channel.send_key("alice", KeyEvent(type="char", key="a", text="a"))
    assert isinstance(typed, InputAccepted) and typed.action is not None
    assert typed.action.node_name is None


async def test_observation_refreshes_only_when_stale() -> None:
    setup = Setup()
    await setup.channel.refresh_observation()
    assert setup.surface.observe_calls == 1
    await setup.channel.send_pointer("alice", PointerEvent(type="wheel", x=1, y=1))
    assert setup.surface.observe_calls == 1
    await setup.channel.send_pointer("alice", PointerEvent(type="click", x=1, y=1))
    await setup.channel.send_pointer("alice", PointerEvent(type="click", x=1, y=1))
    assert setup.surface.observe_calls == 2
    assert setup.channel.latest_observation is setup.surface.observation


async def test_failed_observe_keeps_previous_observation() -> None:
    setup = Setup()
    await setup.channel.refresh_observation()

    async def broken_observe(include_screenshot: bool = True) -> None:
        raise TimeoutError("page did not settle")

    setup.surface.observe = broken_observe  # type: ignore[method-assign,assignment]
    kept = await setup.channel.refresh_observation()
    assert kept is setup.surface.observation
