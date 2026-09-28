"""End-to-end handoff over a real uvicorn server on the test's event loop, with a websocket client.

Exercises: escalate -> list -> context -> take -> live frame -> click + typing + Enter -> hand back
-> escalate() returns the resolution with the human actions, typed text not stored, lease back to
automation. Plus the websocket refusal paths.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from websockets.asyncio.client import ClientConnection, connect

from hands.console.app import create_console_app
from hands.console.server import ConsoleServer, ServerStarted
from hands.core.observation import Node, Rect
from hands.session.board import InterventionBoard
from hands.session.doubles import (
    TINY_PNG_FRAME,
    InMemoryEvidence,
    StubLiveView,
    StubSurface,
    make_intervention_request,
    make_observation,
)
from hands.session.escalation import ConsoleEscalator
from hands.session.lease import LeaseManager

SESSION = "session-1"
RUN = "run-1"
TYPED_SECRET = "Blue-Heron-77"
ANSWER_FIELD = Node(
    ref="n4", role="textbox", name="Security answer", bounds=Rect(x=20, y=40, width=200, height=24)
)


class LiveConsole:
    def __init__(self, run_dir: Path) -> None:
        self.board = InterventionBoard()
        self.evidence = InMemoryEvidence(run_dir=str(run_dir))
        self.lease = LeaseManager(SESSION, interventions=self.board, evidence=self.evidence)
        self.transport = StubLiveView()
        self.surface = StubSurface(make_observation([ANSWER_FIELD]), live_view=self.transport)
        app = create_console_app(
            self.board, {SESSION: self.lease}, {SESSION: self.surface}, {SESSION: self.evidence}
        )
        self.server = ConsoleServer(app, port=0)
        self.url = ""

    def ws_url(self, operator_id: str, session_id: str = SESSION) -> str:
        base = self.url.replace("http://", "ws://")
        return f"{base}/api/sessions/{session_id}/live?operator_id={operator_id}"


@pytest.fixture
async def live_console(tmp_path: Path) -> AsyncIterator[LiveConsole]:
    console = LiveConsole(tmp_path)
    started = await console.server.start()
    assert isinstance(started, ServerStarted)
    console.url = started.url
    yield console
    await console.server.stop()


async def next_message(socket: ClientConnection, message_type: str) -> dict[str, Any]:
    while True:
        message = json.loads(await asyncio.wait_for(socket.recv(), timeout=5))
        if message["type"] == message_type:
            return dict(message)


async def wait_for_open(board: InterventionBoard) -> None:
    for _ in range(400):
        if board.list_open():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("intervention never opened")


async def operate(console: LiveConsole, http: httpx.AsyncClient) -> None:
    """What a human does in the browser: take, click the field, type, press Enter, hand back."""
    listed = (await http.get("/api/interventions")).json()["interventions"]
    assert [item["intervention_id"] for item in listed] == ["iv-1"]
    context = (await http.get("/api/interventions/iv-1")).json()
    assert context["screenshot_data_url"].startswith("data:image/png;base64,")

    take = await http.post("/api/interventions/iv-1/take", json={"operator_id": "alice"})
    assert take.status_code == 200

    async with connect(console.ws_url("alice")) as socket:
        connected = await next_message(socket, "connected")
        assert connected["lease"]["holder"] == "human"
        frame = await next_message(socket, "frame")
        assert frame["mime"] == "image/png" and frame["data"]

        click = {"kind": "pointer", "event": {"type": "click", "x": 60, "y": 50}}
        await socket.send(json.dumps(click))
        clicked = await next_message(socket, "input_accepted")
        assert clicked["action"]["node_name"] == "Security answer"

        for character in TYPED_SECRET:
            char = {"type": "char", "key": character, "text": character}
            await socket.send(json.dumps({"kind": "key", "event": char}))
            await next_message(socket, "input_accepted")
        enter = {"kind": "key", "event": {"type": "down", "key": "Enter"}}
        await socket.send(json.dumps(enter))
        await next_message(socket, "input_accepted")

        await socket.send("not json")
        rejected = await next_message(socket, "input_rejected")
        assert rejected["code"] == "invalid_input"

        back = await http.post(
            "/api/interventions/iv-1/handback",
            json={"operator_id": "alice", "outcome": "resume", "note": "answered identity check"},
        )
        assert back.status_code == 200
        lost = await next_message(socket, "control_lost")
        assert lost["lease"]["holder"] in ("nobody", "automation")


async def test_full_handoff_cycle_over_http_and_websocket(
    live_console: LiveConsole, tmp_path: Path
) -> None:
    (tmp_path / "escalation.png").write_bytes(TINY_PNG_FRAME)
    live_console.lease.grant_automation(RUN)
    escalator = ConsoleEscalator(
        live_console.board,
        live_console.lease,
        live_console.evidence,
        live_console.url,
        timeout_s=10,
    )
    request = make_intervention_request(kind="unrecoverable", screenshot_path="escalation.png")
    escalation = asyncio.create_task(escalator.escalate(request))
    await wait_for_open(live_console.board)

    async with httpx.AsyncClient(base_url=live_console.url) as http:
        await operate(live_console, http)
    resolution = await asyncio.wait_for(escalation, timeout=5)

    assert resolution.outcome == "resume" and resolution.operator_id == "alice"
    summary = [(a.kind, a.node_name, a.text_length, a.key) for a in resolution.human_actions]
    assert summary == [
        ("click", "Security answer", None, None),
        ("type", "Security answer", len(TYPED_SECRET), None),
        ("press", "Security answer", None, "Enter"),
    ]
    assert live_console.lease.is_held_by("automation", RUN)
    holders = [t.to_holder for t in live_console.lease.audit_trail()]
    assert holders == ["automation", "nobody", "human", "nobody", "automation"]
    assert len(live_console.transport.key_events) == len(TYPED_SECRET) + 1
    assert live_console.transport.started and live_console.transport.stopped

    recorded = json.dumps(live_console.evidence.events, default=str)
    assert TYPED_SECRET not in recorded
    assert resolution.model_dump_json().find(TYPED_SECRET) == -1
    human_actions = live_console.evidence.of_kind("human_action")
    assert len(human_actions) == 1 + len(TYPED_SECRET) + 1
    assert "escalation_resolved" in live_console.evidence.kinds()


async def test_live_view_refused_when_operator_does_not_hold_lease(
    live_console: LiveConsole,
) -> None:
    live_console.board.open(make_intervention_request())
    async with connect(live_console.ws_url("alice")) as socket:
        error = await next_message(socket, "error")
        assert error["code"] == "not_in_control"
        await socket.wait_closed()
    assert socket.close_code == 4403
    assert not live_console.transport.started


async def test_live_view_refused_for_unknown_session(live_console: LiveConsole) -> None:
    async with connect(live_console.ws_url("alice", session_id="nope")) as socket:
        error = await next_message(socket, "error")
        assert error["code"] == "unknown_session"
        await socket.wait_closed()
    assert socket.close_code == 4404


async def test_second_live_view_for_same_session_is_refused(live_console: LiveConsole) -> None:
    live_console.board.open(make_intervention_request())
    live_console.lease.take_human("alice")
    async with connect(live_console.ws_url("alice")) as first:
        await next_message(first, "connected")
        async with connect(live_console.ws_url("alice")) as second:
            error = await next_message(second, "error")
            assert error["code"] == "already_streaming"
    live_console.lease.hand_back("alice")


async def test_live_view_closes_when_control_is_force_released(
    live_console: LiveConsole,
) -> None:
    live_console.board.open(make_intervention_request())
    live_console.lease.take_human("alice")
    async with connect(live_console.ws_url("alice")) as socket:
        await next_message(socket, "connected")
        live_console.lease.release(reason="operator timeout")
        lost = await next_message(socket, "control_lost")
        assert lost["lease"]["holder"] == "nobody"
        await socket.wait_closed()
    assert live_console.transport.stopped
