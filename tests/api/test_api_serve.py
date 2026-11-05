"""`hands serve` wiring: ports, settings, binding, two servers on one loop, and SIGTERM shutdown."""

from __future__ import annotations

import asyncio
import os
import signal
import socket
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from hands.api.serve import (
    SHUTDOWN_SIGNALS,
    ServeConfig,
    bind_tcp_socket,
    build_servers,
    close_listeners,
    exit_code_for,
    hosted_server,
    install_signal_handlers,
    request_shutdown,
    resolve_port,
    run_servers,
    serve,
    settings_for,
)
from hands.cli import app as cli_app

from .helpers import fake_settings


@pytest.fixture
def busy_port() -> Iterator[int]:
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen()
    yield holder.getsockname()[1]
    holder.close()


@pytest.mark.parametrize(("cli_port", "environ", "expected"), [
    (9001, {"PORT": "7000"}, 9001), (None, {"PORT": "7000"}, 7000), (None, {}, 8080), (None, {"PORT": "abc"}, 8080),
    (None, {"PORT": ""}, 8080), (0, {}, 0),
])
def test_resolve_port(cli_port: int | None, environ: dict[str, str], expected: int) -> None:
    assert resolve_port(cli_port, environ) == expected


def test_settings_for_points_the_api_at_the_in_process_mock_app() -> None:
    assert settings_for(ServeConfig(target_port=8799), {}).target_url == "http://127.0.0.1:8799"
    assert settings_for(ServeConfig(target_port=8799), {"HANDS_TARGET_URL": "http://core:1"}).target_url == "http://core:1"
    assert settings_for(ServeConfig(with_target=False, target_port=8799), {}).target_url == "http://127.0.0.1:8700"


def test_bind_tcp_socket(busy_port: int) -> None:
    bound = bind_tcp_socket("127.0.0.1", 0)
    assert isinstance(bound, socket.socket)
    bound.close()
    refused = bind_tcp_socket("127.0.0.1", busy_port)
    assert isinstance(refused, str) and str(busy_port) in refused


def test_hosted_server_on_a_busy_port_is_an_error(busy_port: int) -> None:
    from fastapi import FastAPI

    assert isinstance(hosted_server("x", FastAPI(), "127.0.0.1", busy_port, "off"), str)


def test_build_servers_closes_the_mock_app_socket_when_the_api_port_is_busy(tmp_path: Path, busy_port: int) -> None:
    servers = build_servers(ServeConfig(host="127.0.0.1", port=busy_port, target_port=0), fake_settings(tmp_path))
    assert isinstance(servers, str)


def test_build_servers_without_target(tmp_path: Path) -> None:
    servers = build_servers(ServeConfig(host="127.0.0.1", port=0, with_target=False), fake_settings(tmp_path))
    assert not isinstance(servers, str) and [named.name for named in servers] == ["hands API"]
    close_listeners(servers)


def test_request_shutdown_and_exit_codes(tmp_path: Path) -> None:
    servers = build_servers(ServeConfig(host="127.0.0.1", port=0, target_port=0), fake_settings(tmp_path))
    assert not isinstance(servers, str)
    request_shutdown(servers)
    assert all(named.server.should_exit for named in servers)
    close_listeners(servers)
    assert exit_code_for([]) == 0


async def test_exit_code_for_failed_and_cancelled_tasks() -> None:
    async def boom() -> None:
        raise RuntimeError("bind lost")

    async def fine() -> None:
        return None

    failed, ok = asyncio.create_task(boom()), asyncio.create_task(fine())
    await asyncio.wait({failed, ok})
    assert exit_code_for([ok]) == 0 and exit_code_for([ok, failed]) == 1


async def test_two_servers_on_one_loop_stop_on_sigterm(tmp_path: Path) -> None:
    servers = build_servers(ServeConfig(host="127.0.0.1", port=0, target_port=0), fake_settings(tmp_path))
    assert not isinstance(servers, str)
    loop = asyncio.get_running_loop()
    install_signal_handlers(loop, servers)
    serving = asyncio.create_task(run_servers(servers))
    try:
        while not all(named.server.started for named in servers):
            await asyncio.sleep(0.02)
        mock_app_url, api_url = (named.url for named in servers)
        async with httpx.AsyncClient() as client:
            mock_login = await client.get(f"{mock_app_url}/t/lakeside/login")
            tenants = await client.get(f"{api_url}/api/tenants")
        os.kill(os.getpid(), signal.SIGTERM)
        exit_code = await asyncio.wait_for(serving, timeout=10)
    finally:
        for shutdown_signal in SHUTDOWN_SIGNALS:
            loop.remove_signal_handler(shutdown_signal)

    assert mock_login.status_code == 200 and "Sign On" in mock_login.text
    assert tenants.json()[0]["id"] == "lakeside"
    assert exit_code == 0


async def test_serve_returns_1_when_the_port_is_busy(tmp_path: Path, busy_port: int) -> None:
    environ = {"HANDS_DATA_DIR": str(tmp_path), "HANDS_SURFACE": "fake"}
    assert await serve(ServeConfig(host="127.0.0.1", port=busy_port, with_target=False), environ) == 1


def test_cli_lists_serve() -> None:
    output = CliRunner().invoke(cli_app, ["serve", "--help"]).output
    assert "--no-target" in output and "--target-port" in output
