"""`hands serve`: the API and (by default) the CoreOne mock app as two uvicorn servers on ONE event loop.

One loop because runs, the operator console and the live browser share asyncio objects. The mock app binds
127.0.0.1 only (internal), the API binds `--host` (0.0.0.0 on Railway). Sockets are bound up front so a busy
port is a typed, logged failure. SIGTERM / SIGINT ask both servers to exit; the API's lifespan then cancels
an active run so its browser closes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import socket
from collections.abc import Generator, Mapping
from dataclasses import dataclass, replace
from typing import Literal

import uvicorn
from fastapi import FastAPI

from hands.api.app import create_api_app
from hands.api.settings import ApiSettings
from hands.core.log import get_logger, log_failure

_logger: logging.Logger = get_logger(__name__)

DEFAULT_API_PORT = 8080
DEFAULT_TARGET_PORT = 8700
TARGET_HOST = "127.0.0.1"
SHUTDOWN_SIGNALS = (signal.SIGTERM, signal.SIGINT)
LifespanMode = Literal["auto", "on", "off"]


@dataclass(frozen=True)
class ServeConfig:
    host: str = "0.0.0.0"
    port: int = DEFAULT_API_PORT
    with_target: bool = True
    target_port: int = DEFAULT_TARGET_PORT


@dataclass(frozen=True)
class NamedServer:
    name: str
    server: uvicorn.Server
    listener: socket.socket
    url: str


class _HostedUvicorn(uvicorn.Server):
    """A uvicorn server that leaves signal handling to `serve` (two servers share one process)."""

    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None, None, None]:
        yield


def resolve_port(cli_port: int | None, environ: Mapping[str, str] | None = None) -> int:
    """--port wins, then $PORT (Railway), then 8080. A non-numeric $PORT is logged and ignored."""
    if cli_port is not None:
        return cli_port
    raw_port = (os.environ if environ is None else environ).get("PORT", "")
    if raw_port.isascii() and raw_port.isdigit():
        return int(raw_port)
    if raw_port:
        log_failure(_logger, "resolve_port", "PORT is not a number, using default", port=raw_port)
    return DEFAULT_API_PORT


def settings_for(config: ServeConfig, environ: Mapping[str, str] | None = None) -> ApiSettings:
    """Env settings; with an in-process mock app and no HANDS_TARGET_URL, point the API at it."""
    source = os.environ if environ is None else environ
    settings = ApiSettings.from_env(source)
    if config.with_target and not source.get("HANDS_TARGET_URL"):
        return replace(settings, target_url=f"http://{TARGET_HOST}:{config.target_port}")
    return settings


def bind_tcp_socket(host: str, port: int) -> socket.socket | str:
    """A bound TCP socket, or an error message (logged)."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:  # socket I/O boundary
        listener.bind((host, port))
    except OSError as bind_error:
        listener.close()
        log_failure(_logger, "bind_tcp_socket", repr(bind_error), host=host, port=port)
        return f"cannot bind {host}:{port}: {bind_error}"
    return listener


def hosted_server(name: str, app: FastAPI, host: str, port: int, lifespan: LifespanMode) -> NamedServer | str:
    listener = bind_tcp_socket(host, port)
    if isinstance(listener, str):
        return listener
    bound_port = listener.getsockname()[1]
    config = uvicorn.Config(app, log_level="info", lifespan=lifespan, proxy_headers=True, forwarded_allow_ips="*")
    return NamedServer(name, _HostedUvicorn(config), listener, f"http://{host}:{bound_port}")


def build_servers(config: ServeConfig, settings: ApiSettings) -> list[NamedServer] | str:
    """Mock app first (the API probes it), then the API. Closes what was bound if a later bind fails."""
    servers: list[NamedServer] = []
    if config.with_target:
        target = hosted_server("coreone mock app", _target_app(), TARGET_HOST, config.target_port, "auto")
        if isinstance(target, str):
            return target
        servers.append(target)
    api = hosted_server("hands API", create_api_app(settings), config.host, config.port, "on")
    if isinstance(api, str):
        close_listeners(servers)
        return api
    servers.append(api)
    return servers


def _target_app() -> FastAPI:
    from target_app.app import create_app
    from target_app.config import AppConfig

    return create_app(AppConfig.from_env())


def close_listeners(servers: list[NamedServer]) -> None:
    for named in servers:
        named.listener.close()


def request_shutdown(servers: list[NamedServer]) -> None:
    for named in servers:
        named.server.should_exit = True


def install_signal_handlers(loop: asyncio.AbstractEventLoop, servers: list[NamedServer]) -> None:
    for shutdown_signal in SHUTDOWN_SIGNALS:
        loop.add_signal_handler(shutdown_signal, _on_signal, shutdown_signal, servers)


def _on_signal(shutdown_signal: signal.Signals, servers: list[NamedServer]) -> None:
    _logger.info("received %s; shutting down", shutdown_signal.name)
    request_shutdown(servers)


async def run_servers(servers: list[NamedServer]) -> int:
    """Serve until a signal or until any server stops; then stop the rest. 0 on a clean exit."""
    tasks = [asyncio.create_task(named.server.serve(sockets=[named.listener]), name=named.name) for named in servers]
    for named in servers:
        _logger.info("%s listening on %s", named.name, named.url)
    _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    request_shutdown(servers)
    if pending:
        await asyncio.wait(pending)
    close_listeners(servers)
    return exit_code_for(tasks)


def exit_code_for(tasks: list[asyncio.Task[None]]) -> int:
    failures = [task for task in tasks if task.cancelled() or task.exception() is not None]
    for task in failures:
        log_failure(_logger, "run_servers", "server stopped with an error", server=task.get_name(),
                    error=None if task.cancelled() else repr(task.exception()))
    return 1 if failures else 0


async def serve(config: ServeConfig, environ: Mapping[str, str] | None = None) -> int:
    """Bind, log the URLs, serve until SIGTERM/SIGINT. Returns the process exit code."""
    settings = settings_for(config, environ)
    servers = build_servers(config, settings)
    if isinstance(servers, str):
        return 1
    install_signal_handlers(asyncio.get_running_loop(), servers)
    _logger.info("UI and API at http://%s:%s (console at /console, data dir %s, surface %s)",
                 config.host, config.port, settings.data_dir, settings.surface)
    return await run_servers(servers)
