"""Unit tests: token auth helpers, the ASGI middleware, and the error shape."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.exceptions import RequestValidationError

from hands.api.auth import (
    WEBSOCKET_UNAUTHORIZED_CLOSE,
    TokenAuthMiddleware,
    bearer_token,
    query_token,
    requires_auth,
    tokens_match,
)
from hands.api.errors import error_response, validation_message


@pytest.mark.parametrize(("path", "expected"), [
    ("/api/health", False), ("/api/runs", True), ("/api", True), ("/console", True), ("/console/", True),
    ("/console/api/interventions", True), ("/", False), ("/runs/abc", False), ("/apis", False), ("", False),
])
def test_requires_auth(path: str, expected: bool) -> None:
    assert requires_auth(path) is expected


@pytest.mark.parametrize(("presented", "expected"), [("secret", True), ("Secret", False), ("", False),
                                                     (None, False), ("secret ", False)])
def test_tokens_match(presented: str | None, expected: bool) -> None:
    assert tokens_match(presented, "secret") is expected


def test_bearer_token() -> None:
    assert bearer_token({"headers": [(b"authorization", b"Bearer abc ")]}) == "abc"
    assert bearer_token({"headers": [(b"Authorization", b"bearer abc")]}) == "abc"
    assert bearer_token({"headers": [(b"authorization", b"Basic abc")]}) is None
    assert bearer_token({"headers": []}) is None
    assert bearer_token({}) is None


def test_query_token() -> None:
    assert query_token({"query_string": b"operator_id=a&token=t%2B1"}) == "t+1"
    assert query_token({"query_string": b"operator_id=a"}) is None
    assert query_token({}) is None


class _Recorder:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.app_called = False

    async def app(self, scope: Any, receive: Any, send: Any) -> None:
        self.app_called = True

    async def receive(self) -> dict[str, Any]:
        return {"type": "websocket.connect"}

    async def send(self, message: dict[str, Any]) -> None:
        self.sent.append(message)


async def test_middleware_closes_unauthorized_websocket() -> None:
    recorder = _Recorder()
    middleware = TokenAuthMiddleware(recorder.app, token="t")
    await middleware({"type": "websocket", "path": "/console/api/sessions/s/live", "query_string": b""},
                     recorder.receive, recorder.send)

    assert not recorder.app_called
    assert recorder.sent == [{"type": "websocket.close", "code": WEBSOCKET_UNAUTHORIZED_CLOSE}]


async def test_middleware_passes_websocket_with_query_token_and_lifespan() -> None:
    recorder = _Recorder()
    middleware = TokenAuthMiddleware(recorder.app, token="t")
    await middleware({"type": "websocket", "path": "/console/x", "query_string": b"token=t"},
                     recorder.receive, recorder.send)
    assert recorder.app_called
    lifespan_recorder = _Recorder()
    await TokenAuthMiddleware(lifespan_recorder.app, token="t")({"type": "lifespan"}, lifespan_recorder.receive,
                                                                 lifespan_recorder.send)
    assert lifespan_recorder.app_called


async def test_middleware_rejects_http_with_401_json() -> None:
    recorder = _Recorder()
    await TokenAuthMiddleware(recorder.app, token="t")({"type": "http", "path": "/api/runs", "headers": []},
                                                       recorder.receive, recorder.send)
    assert recorder.sent[0]["status"] == 401
    assert b'"error": "unauthorized"' in recorder.sent[1]["body"]


def test_error_response_shape() -> None:
    response = error_response(409, "busy", "run x is active", run_id="x")
    assert response.status_code == 409
    assert response.body == b'{"error":"busy","message":"run x is active","run_id":"x"}'


def test_validation_message_joins_locations() -> None:
    error = RequestValidationError([{"loc": ("body", "inputs"), "msg": "Input should be a valid dictionary"},
                                    {"loc": ("query", "limit"), "msg": "too big"}])
    assert validation_message(error) == "body.inputs: Input should be a valid dictionary; query.limit: too big"
    assert validation_message(RequestValidationError([])) == "invalid request"
