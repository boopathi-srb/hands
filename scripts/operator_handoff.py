"""Act as a human operator over the console's real protocol: take control, operate the live session, hand back.

This is what the operator page does in a browser; it exists so the handoff demo can run without a person.
Usage: uv run python scripts/operator_handoff.py <intervention_id> <session_id>
"""

from __future__ import annotations

import asyncio
import json
import sys

import httpx
import websockets

CONSOLE = "http://127.0.0.1:8765"
OPERATOR_ID = "ops-demo"
ANSWER_FIELD = (479, 220)  # Security Answer textbox centre, from the escalation snapshot
VERIFY_BUTTON = (451, 282)
ANSWER = "supervisor-override"  # the mock app's test-only supervisor override


async def operate(intervention_id: str, session_id: str) -> None:
    async with httpx.AsyncClient(base_url=CONSOLE, timeout=10) as client:
        taken = await client.post(f"/api/interventions/{intervention_id}/take", json={"operator_id": OPERATOR_ID})
        print("take:", taken.status_code, taken.json().get("lease", {}).get("holder"))
        await drive_live_session(session_id)
        handed_back = await client.post(
            f"/api/interventions/{intervention_id}/handback",
            json={"operator_id": OPERATOR_ID, "outcome": "resume",
                  "note": "Verified member identity with a supervisor override; resuming automation."},
        )
        resolution = handed_back.json().get("resolution", {})
        print("handback:", handed_back.status_code, resolution.get("outcome"),
              [(a["kind"], a.get("node_role"), a.get("node_name"), a.get("text_length")) for a in resolution.get("human_actions", [])])


async def drive_live_session(session_id: str) -> None:
    url = f"ws://127.0.0.1:8765/api/sessions/{session_id}/live?operator_id={OPERATOR_ID}"
    async with websockets.connect(url, max_size=None) as socket:
        await wait_for_first_frame(socket)
        await send_pointer_click(socket, *ANSWER_FIELD)
        for character in ANSWER:
            await socket.send(json.dumps({"kind": "key", "event": {"type": "char", "key": character, "text": character}}))
        await asyncio.sleep(0.5)
        await send_pointer_click(socket, *VERIFY_BUTTON)
        await asyncio.sleep(2.0)


async def wait_for_first_frame(socket: websockets.ClientConnection) -> None:
    while True:
        message = json.loads(await socket.recv())
        if message.get("type") == "frame" or message.get("kind") == "frame":
            print("live frame received")
            return


async def send_pointer_click(socket: websockets.ClientConnection, x: float, y: float) -> None:
    await socket.send(json.dumps({"kind": "pointer", "event": {"type": "click", "x": x, "y": y, "button": "left"}}))
    await asyncio.sleep(0.4)


if __name__ == "__main__":
    asyncio.run(operate(sys.argv[1], sys.argv[2]))
