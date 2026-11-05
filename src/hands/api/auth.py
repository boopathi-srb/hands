"""Optional bearer-token auth for /api and /console, as plain ASGI middleware so websockets are covered too.

- HTTP: `Authorization: Bearer <token>`; 401 `{"error": "unauthorized"}` otherwise.
- Websocket: `?token=<token>` (browsers cannot set headers on a websocket); closed with 4401 otherwise.
- `GET /api/health` and everything outside /api and /console (the built UI) stay public.
"""

from __future__ import annotations

import hmac
import json
import logging
from urllib.parse import parse_qs

from starlette.types import ASGIApp, Receive, Scope, Send

from hands.core.log import get_logger, log_failure

_logger: logging.Logger = get_logger(__name__)

PROTECTED_PREFIXES = ("/api", "/console")
PUBLIC_PATHS = frozenset({"/api/health"})
WEBSOCKET_UNAUTHORIZED_CLOSE = 4401
UNAUTHORIZED_BODY = json.dumps({"error": "unauthorized", "message": "missing or wrong token"}).encode()


def requires_auth(path: str) -> bool:
    """True for /api/* and /console/* except the public health check."""
    if path in PUBLIC_PATHS:
        return False
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in PROTECTED_PREFIXES)


def tokens_match(presented: str | None, expected: str) -> bool:
    """Constant-time comparison; a missing token never matches."""
    if not presented:
        return False
    return hmac.compare_digest(presented.encode(), expected.encode())


def bearer_token(scope: Scope) -> str | None:
    """The token from `Authorization: Bearer <token>`, or None."""
    for name, value in scope.get("headers", []):
        if name.lower() == b"authorization":
            scheme, _, token = value.decode("latin-1").partition(" ")
            return token.strip() if scheme.lower() == "bearer" else None
    return None


def query_token(scope: Scope) -> str | None:
    """The `token` query parameter, or None."""
    query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
    values = query.get("token")
    return values[0] if values else None


class TokenAuthMiddleware:
    def __init__(self, app: ASGIApp, token: str) -> None:
        self._app = app
        self._token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or not requires_auth(scope.get("path", "")):
            await self._app(scope, receive, send)
            return
        if self._authorized(scope):
            await self._app(scope, receive, send)
            return
        log_failure(_logger, "TokenAuthMiddleware", "unauthorized request", path=scope.get("path"),
                    kind=scope["type"])
        if scope["type"] == "websocket":
            await receive()  # the websocket.connect event; closing before accept rejects the handshake
            await send({"type": "websocket.close", "code": WEBSOCKET_UNAUTHORIZED_CLOSE})
            return
        await _send_unauthorized(send)

    def _authorized(self, scope: Scope) -> bool:
        presented = bearer_token(scope)
        if presented is None and scope["type"] == "websocket":
            presented = query_token(scope)
        return tokens_match(presented, self._token)


async def _send_unauthorized(send: Send) -> None:
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(UNAUTHORIZED_BODY)).encode())]
    await send({"type": "http.response.start", "status": 401, "headers": headers})
    await send({"type": "http.response.body", "body": UNAUTHORIZED_BODY})
