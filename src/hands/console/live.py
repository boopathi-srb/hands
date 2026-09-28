"""Live websocket: stream the SAME session's frames to the operator and inject their input.

Protocol on `WS /api/sessions/{session_id}/live?operator_id=...`

Server -> browser (JSON):
- {"type": "connected", "session_id", "operator_id", "lease"}
- {"type": "frame", "mime": "image/png"|"image/jpeg", "data": <base64>}
- {"type": "input_accepted", "action": HumanAction|null}
- {"type": "input_rejected", "code", "message"}
- {"type": "control_lost", "lease"}   then the socket closes (hand-back, timeout, forced release)
- {"type": "error", "code", "message"} then close, when the connection is refused

Browser -> server (JSON):
- {"kind": "pointer", "event": PointerEvent}   coordinates in frame pixels
- {"kind": "key", "event": KeyEvent}

A connection is refused unless the lease is held by `human` with this operator id. Every input is
re-checked against the lease by HumanInputChannel, so input after control is lost is rejected even if
the socket has not closed yet. One live stream per session, because a transport has one frame consumer.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from hands.console.context import image_mime, lease_view
from hands.console.state import ConsoleState
from hands.core.log import get_logger, log_failure
from hands.core.ports import KeyEvent, LiveViewTransport, PointerEvent
from hands.session.human_input import HumanInputChannel, InputAccepted, InputResult
from hands.session.lease import LeaseManager

_logger: logging.Logger = get_logger(__name__)

CLOSE_NORMAL = 1000
CLOSE_NOT_IN_CONTROL = 4403
CLOSE_UNKNOWN_SESSION = 4404
CLOSE_ALREADY_STREAMING = 4409
CLOSE_NO_LIVE_VIEW = 4412
SOCKET_ERRORS = (WebSocketDisconnect, RuntimeError, OSError)

OperatorInput = PointerEvent | KeyEvent


def frame_message(frame: bytes) -> dict[str, Any]:
    return {
        "type": "frame",
        "mime": image_mime(frame),
        "data": base64.b64encode(frame).decode("ascii"),
    }


def input_reply(result: InputResult) -> dict[str, Any]:
    if isinstance(result, InputAccepted):
        action = None if result.action is None else result.action.model_dump(mode="json")
        return {"type": "input_accepted", "action": action}
    return {"type": "input_rejected", "code": result.code, "message": result.message}


def parse_operator_input(text: str | None) -> OperatorInput | str:
    """A PointerEvent or KeyEvent from a browser message, or an error string (logged)."""
    try:
        payload = json.loads(text or "")
        kind = payload.get("kind") if isinstance(payload, dict) else None
        if kind == "pointer":
            return PointerEvent.model_validate(payload.get("event"))
        if kind == "key":
            return KeyEvent.model_validate(payload.get("event"))
    except (ValueError, ValidationError) as error:  # untrusted browser input boundary
        log_failure(_logger, "parse_operator_input", type(error).__name__, length=len(text or ""))
        return f"invalid input: {type(error).__name__}"
    log_failure(_logger, "parse_operator_input", "unknown kind", length=len(text or ""))
    return "invalid input: kind must be 'pointer' or 'key'"


class SerializedSender:
    """Sends JSON on one websocket from several tasks; never raises after the peer goes away."""

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._lock = asyncio.Lock()
        self._closed = False

    async def send(self, payload: dict[str, Any]) -> bool:
        async with self._lock:
            if self._closed:
                return False
            try:
                await self._websocket.send_json(payload)
            except SOCKET_ERRORS as error:  # network I/O boundary: the operator may leave anytime
                log_failure(
                    _logger, "SerializedSender.send", repr(error), message_type=payload.get("type")
                )
                self._closed = True
                return False
            return True

    async def send_frame(self, frame: bytes) -> None:
        await self.send(frame_message(frame))

    async def close(self, code: int = CLOSE_NORMAL, reason: str = "") -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                await self._websocket.close(code=code, reason=reason)
            except SOCKET_ERRORS as error:  # network I/O boundary
                log_failure(_logger, "SerializedSender.close", repr(error), code=code)


def register_live_route(app: FastAPI, state: ConsoleState) -> None:
    @app.websocket("/api/sessions/{session_id}/live")
    async def live_route(websocket: WebSocket, session_id: str, operator_id: str = "") -> None:
        await serve_live_session(websocket, state, session_id, operator_id)


async def serve_live_session(
    websocket: WebSocket, state: ConsoleState, session_id: str, operator_id: str
) -> None:
    await websocket.accept()
    sender = SerializedSender(websocket)
    refusal = connection_refusal(state, session_id, operator_id)
    if refusal is not None:
        close_code, code, message = refusal
        log_failure(
            _logger, "serve_live_session", code, session_id=session_id, operator_id=operator_id
        )
        await sender.send({"type": "error", "code": code, "message": message})
        await sender.close(close_code, code)
        return
    state.streaming_sessions.add(session_id)
    try:
        await LiveLink(state, session_id, operator_id, websocket, sender).run()
    finally:
        state.streaming_sessions.discard(session_id)


def connection_refusal(
    state: ConsoleState, session_id: str, operator_id: str
) -> tuple[int, str, str] | None:
    """(close code, error code, message) when the operator may not open a live link; else None."""
    lease = state.leases.get(session_id)
    surface = state.surfaces.get(session_id)
    if lease is None or surface is None:
        return CLOSE_UNKNOWN_SESSION, "unknown_session", f"no live session {session_id}"
    if not operator_id or not lease.is_held_by("human", operator_id):
        return CLOSE_NOT_IN_CONTROL, "not_in_control", "take control before opening the live view"
    if session_id in state.streaming_sessions:
        return CLOSE_ALREADY_STREAMING, "already_streaming", "a live view is already open"
    if surface.live_view() is None:
        return CLOSE_NO_LIVE_VIEW, "no_live_view", "this surface has no live view"
    return None


class LiveLink:
    """One operator's live connection: frames out, lease-checked input in, closed on control loss."""

    def __init__(
        self,
        state: ConsoleState,
        session_id: str,
        operator_id: str,
        websocket: WebSocket,
        sender: SerializedSender,
    ) -> None:
        self._session_id = session_id
        self._operator_id = operator_id
        self._websocket = websocket
        self._sender = sender
        self._lease: LeaseManager = state.leases[session_id]
        surface = state.surfaces[session_id]
        self._transport: LiveViewTransport | None = surface.live_view()
        self._channel = HumanInputChannel(
            session_id, self._lease, state.board, surface, state.evidence.get(session_id)
        )

    async def run(self) -> None:
        await self._sender.send(
            {
                "type": "connected",
                "session_id": self._session_id,
                "operator_id": self._operator_id,
                "lease": lease_view(self._lease),
            }
        )
        await self._channel.refresh_observation()
        stream_task = asyncio.create_task(self._stream_frames())
        watcher_task = asyncio.create_task(self._close_when_control_lost())
        try:
            await self._receive_inputs()
        finally:
            watcher_task.cancel()
            await self._stop_stream(stream_task)

    async def _receive_inputs(self) -> None:
        while True:
            message = await self._websocket.receive()
            if message.get("type") == "websocket.disconnect":
                return
            reply = await self._handle(message.get("text"))
            await self._sender.send(reply)

    async def _handle(self, text: str | None) -> dict[str, Any]:
        parsed = parse_operator_input(text)
        if isinstance(parsed, str):
            return {"type": "input_rejected", "code": "invalid_input", "message": parsed}
        if isinstance(parsed, PointerEvent):
            return input_reply(await self._channel.send_pointer(self._operator_id, parsed))
        return input_reply(await self._channel.send_key(self._operator_id, parsed))

    async def _stream_frames(self) -> None:
        if self._transport is None:
            return
        try:
            await self._transport.start(self._sender.send_frame)
        except Exception as error:  # noqa: BLE001 - transport adapter errors are adapter-specific
            log_failure(
                _logger, "LiveLink._stream_frames", repr(error), session_id=self._session_id
            )

    async def _close_when_control_lost(self) -> None:
        while self._lease.is_held_by("human", self._operator_id):
            await self._lease.wait_for_change()
        await self._sender.send({"type": "control_lost", "lease": lease_view(self._lease)})
        await self._sender.close(CLOSE_NORMAL, "control_lost")

    async def _stop_stream(self, stream_task: asyncio.Task[None]) -> None:
        if self._transport is not None:
            try:
                await self._transport.stop()
            except Exception as error:  # noqa: BLE001 - transport adapter errors are adapter-specific
                log_failure(
                    _logger, "LiveLink._stop_stream", repr(error), session_id=self._session_id
                )
        if not stream_task.done():
            stream_task.cancel()
