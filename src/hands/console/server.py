"""Run the console with uvicorn as a task on the CURRENT event loop (the run's loop).

The socket is bound here, before uvicorn starts, so a busy port is a typed failure instead of uvicorn's
`sys.exit(1)` escaping from a task. Uvicorn's signal capture is disabled so Ctrl+C still belongs to the
host run, which is expected to call `stop()` during its own shutdown.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
from collections.abc import Generator
from typing import Literal

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from hands.core.log import get_logger, log_failure

_logger: logging.Logger = get_logger(__name__)

LOOPBACK_HOST = "127.0.0.1"
STARTUP_POLL_S = 0.02


class ServerStarted(BaseModel):
    ok: Literal[True] = True
    url: str


class ServerStartFailed(BaseModel):
    ok: Literal[False] = False
    message: str


ServerStartResult = ServerStarted | ServerStartFailed


class _EmbeddedUvicorn(uvicorn.Server):
    """uvicorn.Server that leaves process signal handlers to the host application."""

    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None, None, None]:
        yield


def bind_loopback_socket(port: int) -> socket.socket | str:
    """A listening-ready TCP socket on 127.0.0.1:port (0 = any free port), or an error message."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind((LOOPBACK_HOST, port))
    except OSError as error:  # socket I/O boundary
        listener.close()
        log_failure(_logger, "bind_loopback_socket", repr(error), port=port)
        return f"cannot bind {LOOPBACK_HOST}:{port}: {error}"
    return listener


class ConsoleServer:
    """Start/stop the operator console on 127.0.0.1 inside the running event loop."""

    def __init__(self, app: FastAPI, port: int = 8765, startup_timeout_s: float = 5.0) -> None:
        self._app = app
        self._requested_port = port
        self._startup_timeout_s = startup_timeout_s
        self._server: _EmbeddedUvicorn | None = None
        self._task: asyncio.Task[None] | None = None
        self._socket: socket.socket | None = None
        self._url: str | None = None

    @property
    def url(self) -> str | None:
        """Base URL once started, e.g. http://127.0.0.1:8765."""
        return self._url

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> ServerStartResult:
        if self.running and self._url is not None:
            return ServerStarted(url=self._url)
        bound = bind_loopback_socket(self._requested_port)
        if isinstance(bound, str):
            return ServerStartFailed(message=bound)
        self._socket = bound
        config = uvicorn.Config(self._app, log_level="warning", lifespan="off")
        self._server = _EmbeddedUvicorn(config)
        self._task = asyncio.create_task(self._server.serve(sockets=[bound]))
        return await self._await_startup(bound)

    async def stop(self) -> None:
        if self._server is None or self._task is None:
            return
        self._server.should_exit = True
        done, _pending = await asyncio.wait({self._task}, timeout=self._startup_timeout_s)
        if not done:
            log_failure(_logger, "ConsoleServer.stop", "graceful shutdown timed out", url=self._url)
            self._server.force_exit = True
            self._task.cancel()
        self._close_socket()
        self._server, self._task, self._url = None, None, None

    async def _await_startup(self, bound: socket.socket) -> ServerStartResult:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._startup_timeout_s
        while self._server is not None and not self._server.started:
            if self._task is None or self._task.done() or loop.time() > deadline:
                return await self._startup_failed()
            await asyncio.sleep(STARTUP_POLL_S)
        port = bound.getsockname()[1]
        self._url = f"http://{LOOPBACK_HOST}:{port}"
        _logger.info("operator console listening on %s", self._url)
        return ServerStarted(url=self._url)

    async def _startup_failed(self) -> ServerStartFailed:
        message = "uvicorn did not start"
        log_failure(_logger, "ConsoleServer.start", message, port=self._requested_port)
        await self.stop()
        return ServerStartFailed(message=message)

    def _close_socket(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None
