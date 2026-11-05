"""Shared operator console over a real uvicorn server on the test's loop: an identity check stops a replay,
the operator takes control through /console, answers over the live websocket, hands back, and the run
finishes. Token auth applies to the console's HTTP routes and its websocket (`?token=`)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import InvalidStatus

from hands.console.server import ConsoleServer, ServerStarted

from .helpers import TOKEN, build_app, fake_settings, replay_body, wait_for_state

OPERATOR = "op-7"
IDENTITY_ANSWER_SCRIPT: list[dict[str, Any]] = [
    {"kind": "pointer", "event": {"type": "click", "x": 482, "y": 250, "button": "left"}},  # Answer textbox
    *[{"kind": "key", "event": {"type": "char", "key": letter, "text": letter}} for letter in "Quinn"],
    {"kind": "pointer", "event": {"type": "click", "x": 423, "y": 301, "button": "left"}},  # Verify
]


@dataclass
class LiveApi:
    url: str
    client: httpx.AsyncClient

    def ws_url(self, session_id: str, token: str | None) -> str:
        query = f"operator_id={OPERATOR}" + (f"&token={token}" if token else "")
        return f"{self.url.replace('http://', 'ws://')}/console/api/sessions/{session_id}/live?{query}"


@pytest.fixture
async def live_api(data_dir: Path) -> AsyncIterator[LiveApi]:
    app = build_app(replace(fake_settings(data_dir), api_token=TOKEN))
    server = ConsoleServer(app, port=0)
    started = await server.start()
    assert isinstance(started, ServerStarted)
    async with httpx.AsyncClient(base_url=started.url, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield LiveApi(url=started.url, client=client)
    await app.state.runs.shutdown()
    await server.stop()


async def send_script(socket: ClientConnection) -> list[dict[str, Any]]:
    replies = []
    for message in IDENTITY_ANSWER_SCRIPT:
        await socket.send(json.dumps(message))
        replies.append(json.loads(await socket.recv()))
    return replies


async def test_websocket_without_token_is_rejected(live_api: LiveApi) -> None:
    with pytest.raises(InvalidStatus):
        async with connect(live_api.ws_url("replay-anything", token=None)):
            pass
    with pytest.raises(InvalidStatus):
        async with connect(live_api.ws_url("replay-anything", token="wrong")):
            pass


async def test_identity_check_waits_for_operator_then_take_and_handback_finish_the_run(
    live_api: LiveApi,
) -> None:
    client = live_api.client
    started = await client.post("/api/runs/replay", json=replay_body(
        "10001", faults=[{"name": "identity_check", "count": 1}]))
    run_id = started.json()["run_id"]
    waiting = await wait_for_state(client, run_id, ("waiting_for_operator",))
    intervention_id = waiting["intervention"]["intervention_id"]
    listed = (await client.get("/console/api/interventions")).json()["interventions"]

    taken = await client.post(f"/console/api/interventions/{intervention_id}/take", json={"operator_id": OPERATOR})
    async with connect(live_api.ws_url(run_id, token=TOKEN)) as socket:
        connected = json.loads(await socket.recv())
        replies = await send_script(socket)
        handback = await client.post(f"/console/api/interventions/{intervention_id}/handback",
                                     json={"operator_id": OPERATOR, "outcome": "resume", "note": "verified"})
    finished = await wait_for_state(client, run_id)

    assert waiting["state"] == "waiting_for_operator" and waiting["headline"].startswith("waiting for operator")
    assert waiting["intervention"]["session_id"] == run_id and waiting["intervention"]["lease"]["holder"] == "nobody"
    assert [item["intervention_id"] for item in listed] == [intervention_id]
    assert taken.status_code == 200 and connected["type"] == "connected"
    assert all(reply["type"] == "input_accepted" for reply in replies)
    assert handback.status_code == 200
    assert finished["state"] == "finished" and finished["status"] == "success"
    assert finished["result"]["interventions"] == [intervention_id]
    assert finished["headline"] == "savings_balance 1250.00"
    assert (await client.get("/console/api/interventions")).json()["interventions"] == []
