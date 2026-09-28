"""InterventionBoard lifecycle."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from hands.core.control import HumanAction, InterventionResolution
from hands.session.board import BoardAccepted, BoardRefused, InterventionBoard, merge_typing
from hands.session.doubles import make_intervention_request


def typed(length: int, node_name: str | None = "Member Number") -> HumanAction:
    return HumanAction(
        at=datetime.now(UTC),
        kind="type",
        text_length=length,
        node_role="textbox",
        node_name=node_name,
    )


def click() -> HumanAction:
    return HumanAction(at=datetime.now(UTC), kind="click", x=1, y=2)


def test_empty_board() -> None:
    board = InterventionBoard()
    assert board.list_open() == []
    assert board.get("missing") is None
    assert not board.has_open("session-1")
    assert board.open_for_session("session-1") is None


def test_open_list_get_and_resolve() -> None:
    board = InterventionBoard()
    request = make_intervention_request()
    assert isinstance(board.open(request), BoardAccepted)
    assert board.list_open() == [request]
    assert board.has_open("session-1")
    assert board.open_for_session("session-1") == request

    resolved = board.resolve_from_operator("iv-1", "resume", "alice", "closed the modal")
    assert isinstance(resolved, BoardAccepted)
    record = board.get("iv-1")
    assert record is not None and record.status == "resolved"
    assert record.resolution is not None and record.resolution.note == "closed the modal"
    assert board.list_open() == []
    assert not board.has_open("session-1")


def test_duplicate_id_and_second_open_per_session_are_refused() -> None:
    board = InterventionBoard()
    board.open(make_intervention_request())
    duplicate = board.open(make_intervention_request())
    busy = board.open(make_intervention_request(intervention_id="iv-2"))
    assert isinstance(duplicate, BoardRefused) and duplicate.code == "duplicate_intervention"
    assert isinstance(busy, BoardRefused) and busy.code == "session_busy"


def test_other_sessions_can_have_their_own_open_intervention() -> None:
    board = InterventionBoard()
    board.open(make_intervention_request())
    other = board.open(make_intervention_request(session_id="session-2", intervention_id="iv-2"))
    assert isinstance(other, BoardAccepted)
    assert len(board.list_open()) == 2


def test_resolve_unknown_and_twice_are_refused() -> None:
    board = InterventionBoard()
    unknown = board.resolve_from_operator("nope", "abort", "alice")
    board.open(make_intervention_request())
    board.resolve_from_operator("iv-1", "abort", "alice")
    twice = board.resolve_from_operator("iv-1", "resume", "alice")
    assert isinstance(unknown, BoardRefused) and unknown.code == "unknown_intervention"
    assert isinstance(twice, BoardRefused) and twice.code == "already_resolved"


def test_resolve_with_explicit_resolution_is_stored_as_given() -> None:
    board = InterventionBoard()
    board.open(make_intervention_request())
    resolution = InterventionResolution(
        intervention_id="iv-1",
        outcome="step_completed_by_human",
        operator_id="bob",
        resolved_at=datetime.now(UTC),
    )
    board.resolve(resolution)
    record = board.get("iv-1")
    assert record is not None and record.resolution == resolution


def test_human_actions_accumulate_and_typing_merges() -> None:
    board = InterventionBoard()
    board.open(make_intervention_request())
    board.record_human_action("iv-1", click())
    board.record_human_action("iv-1", typed(3))
    board.record_human_action("iv-1", typed(4))
    board.resolve_from_operator("iv-1", "resume", "alice")
    record = board.get("iv-1")
    assert record is not None and record.resolution is not None
    kinds = [(action.kind, action.text_length) for action in record.resolution.human_actions]
    assert kinds == [("click", None), ("type", 7)]


def test_recording_on_resolved_or_unknown_intervention_is_refused() -> None:
    board = InterventionBoard()
    unknown = board.record_human_action("nope", click())
    board.open(make_intervention_request())
    board.resolve_from_operator("iv-1", "abort", "alice")
    late = board.record_human_action("iv-1", click())
    assert isinstance(unknown, BoardRefused) and unknown.code == "unknown_intervention"
    assert isinstance(late, BoardRefused) and late.code == "already_resolved"


def test_merge_typing_rules() -> None:
    merged = merge_typing(typed(2), typed(5))
    assert merged is not None and merged.text_length == 7
    assert merge_typing(typed(2), typed(5, node_name="Password")) is None
    assert merge_typing(click(), typed(1)) is None
    assert merge_typing(typed(1), click()) is None


async def test_wait_for_resolution_wakes_on_resolve() -> None:
    board = InterventionBoard()
    board.open(make_intervention_request())
    waiter = asyncio.create_task(board.wait_for_resolution("iv-1", timeout=1.0))
    await asyncio.sleep(0)
    board.resolve_from_operator("iv-1", "resume", "alice")
    resolution = await waiter
    assert resolution is not None and resolution.operator_id == "alice"


async def test_wait_for_resolution_times_out_and_handles_unknown_id() -> None:
    board = InterventionBoard()
    board.open(make_intervention_request())
    assert await board.wait_for_resolution("iv-1", timeout=0.01) is None
    assert await board.wait_for_resolution("unknown", timeout=0.01) is None
