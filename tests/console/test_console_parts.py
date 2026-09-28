"""Console building blocks: message parsing/formatting, context helpers, page loading, server."""

from __future__ import annotations

import base64
import socket
from datetime import UTC, datetime
from pathlib import Path

import httpx

from hands.console.app import create_console_app, error_response, load_operator_page
from hands.console.context import (
    image_mime,
    intervention_summary,
    lease_view,
    load_screenshot_data_url,
    resolve_screenshot_path,
    to_data_url,
)
from hands.console.live import (
    frame_message,
    input_reply,
    parse_operator_input,
)
from hands.console.server import (
    ConsoleServer,
    ServerStarted,
    ServerStartFailed,
    bind_loopback_socket,
)
from hands.core.control import HumanAction
from hands.core.ports import KeyEvent, PointerEvent
from hands.session.board import InterventionBoard
from hands.session.doubles import TINY_PNG_FRAME, InMemoryEvidence, make_intervention_request
from hands.session.human_input import InputAccepted, InputRejected
from hands.session.lease import LeaseManager

JPEG_BYTES = b"\xff\xd8\xff\xe0jpeg-body"


# ---------------------------------------------------------------- live message helpers


def test_parse_pointer_and_key_messages() -> None:
    pointer = parse_operator_input(
        '{"kind": "pointer", "event": {"type": "click", "x": 1, "y": 2}}'
    )
    key = parse_operator_input('{"kind": "key", "event": {"type": "down", "key": "Tab"}}')
    assert pointer == PointerEvent(type="click", x=1, y=2)
    assert key == KeyEvent(type="down", key="Tab")


def test_parse_rejects_bad_input() -> None:
    assert isinstance(parse_operator_input(None), str)
    assert isinstance(parse_operator_input(""), str)
    assert isinstance(parse_operator_input("not json"), str)
    assert isinstance(parse_operator_input("[1, 2]"), str)
    assert isinstance(parse_operator_input('{"kind": "gamepad", "event": {}}'), str)
    assert isinstance(parse_operator_input('{"kind": "pointer", "event": {"type": "tap"}}'), str)
    assert isinstance(parse_operator_input('{"kind": "key"}'), str)


def test_frame_message_encodes_and_detects_mime() -> None:
    png = frame_message(TINY_PNG_FRAME)
    jpeg = frame_message(JPEG_BYTES)
    assert png["type"] == "frame" and png["mime"] == "image/png"
    assert base64.b64decode(png["data"]) == TINY_PNG_FRAME
    assert jpeg["mime"] == "image/jpeg"


def test_input_reply_shapes() -> None:
    action = HumanAction(at=datetime.now(UTC), kind="press", key="Enter")
    accepted = input_reply(InputAccepted(action=action, intervention_id="iv-1"))
    silent = input_reply(InputAccepted(action=None, intervention_id="iv-1"))
    rejected = input_reply(InputRejected(code="not_in_control", message="not in control"))
    assert accepted["type"] == "input_accepted" and accepted["action"]["key"] == "Enter"
    assert silent == {"type": "input_accepted", "action": None}
    assert rejected == {
        "type": "input_rejected",
        "code": "not_in_control",
        "message": "not in control",
    }


# ---------------------------------------------------------------- context helpers


def test_image_mime_and_data_url() -> None:
    assert image_mime(JPEG_BYTES) == "image/jpeg"
    assert image_mime(TINY_PNG_FRAME) == "image/png"
    assert image_mime(b"") == "image/png"
    assert to_data_url(b"").startswith("data:image/png;base64,")


def test_resolve_screenshot_path(tmp_path: Path) -> None:
    evidence = InMemoryEvidence(run_dir=str(tmp_path))
    absolute = str(tmp_path / "a.png")
    assert resolve_screenshot_path(absolute, evidence) == Path(absolute)
    assert resolve_screenshot_path("b.png", evidence) == tmp_path / "b.png"
    assert resolve_screenshot_path("b.png", None) == Path("b.png")


def test_load_screenshot_data_url(tmp_path: Path) -> None:
    (tmp_path / "shot.jpg").write_bytes(JPEG_BYTES)
    evidence = InMemoryEvidence(run_dir=str(tmp_path))
    assert load_screenshot_data_url(None, evidence) is None
    assert load_screenshot_data_url("", evidence) is None
    assert load_screenshot_data_url("absent.png", evidence) is None
    loaded = load_screenshot_data_url("shot.jpg", evidence)
    assert loaded is not None and loaded.startswith("data:image/jpeg;base64,")


def test_intervention_summary_and_lease_view() -> None:
    lease = LeaseManager("session-1")
    summary = intervention_summary(make_intervention_request(), lease)
    assert summary["intervention_id"] == "iv-1" and summary["lease"]["holder"] == "nobody"
    assert intervention_summary(make_intervention_request(), None)["lease"] is None
    assert lease_view(None) is None


# ---------------------------------------------------------------- app helpers


def test_load_operator_page_missing_file_returns_fallback(tmp_path: Path) -> None:
    page = load_operator_page(tmp_path / "missing.html")
    assert "operator page missing" in page


def test_load_operator_page_default_is_the_static_file() -> None:
    page = load_operator_page()
    assert "Take control" in page and "Hand back" in page


def test_error_response_body() -> None:
    response = error_response(409, "held_by_human", "a human holds control")
    assert response.status_code == 409
    assert b'"error":"held_by_human"' in response.body


# ---------------------------------------------------------------- server


async def test_console_server_starts_serves_and_stops() -> None:
    server = ConsoleServer(create_console_app(InterventionBoard(), {}, {}, {}), port=0)
    assert server.url is None and not server.running
    started = await server.start()
    assert isinstance(started, ServerStarted)
    assert started.url.startswith("http://127.0.0.1:")
    assert (await server.start()) == started
    async with httpx.AsyncClient(base_url=started.url) as client:
        assert (await client.get("/api/interventions")).json() == {"interventions": []}
    await server.stop()
    assert server.url is None and not server.running
    await server.stop()


async def test_console_server_reports_busy_port() -> None:
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen()
    busy_port = blocker.getsockname()[1]
    try:
        server = ConsoleServer(create_console_app(InterventionBoard(), {}, {}, {}), port=busy_port)
        result = await server.start()
    finally:
        blocker.close()
    assert isinstance(result, ServerStartFailed)
    assert str(busy_port) in result.message
    assert not server.running


def test_bind_loopback_socket_any_port() -> None:
    bound = bind_loopback_socket(0)
    assert isinstance(bound, socket.socket)
    assert bound.getsockname()[0] == "127.0.0.1"
    bound.close()
