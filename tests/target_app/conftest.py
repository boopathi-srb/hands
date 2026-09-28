"""Shared fixtures for the CoreOne mock target tests."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from target_app.app import create_app
from target_app.config import DEFAULT_DEMO_PASSWORD, AppConfig

SignOn = Callable[..., TestClient]
ArmFault = Callable[..., Any]


@pytest.fixture
def app_config() -> AppConfig:
    return AppConfig()


@pytest.fixture
def client(app_config: AppConfig) -> Iterator[TestClient]:
    with TestClient(create_app(app_config)) as test_client:
        yield test_client


@pytest.fixture
def sign_on(client: TestClient) -> SignOn:
    """Sign the shared client on to a tenant and return it."""

    def _sign_on(tenant: str = "lakeside", password: str = DEFAULT_DEMO_PASSWORD) -> TestClient:
        response = client.post(f"/t/{tenant}/login", data={"USERID": "teller1", "PASSWD": password})
        assert response.status_code == 200, response.text
        return client

    return _sign_on


@pytest.fixture
def arm_fault(client: TestClient) -> ArmFault:
    def _arm(fault: str, count: int = 1, tenant: str = "lakeside", **extra: Any) -> Any:
        response = client.post(
            "/_admin/faults", json={"fault": fault, "count": count, "tenant": tenant, **extra}
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _arm


@pytest.fixture
def recorded_delays(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Replace the slow-fault pause with a recorder so tests stay fast and deterministic."""
    delays_ms: list[int] = []

    async def fake_pause(delay_ms: int) -> None:
        delays_ms.append(delay_ms)

    monkeypatch.setattr("target_app.rendering.pause_for_fault", fake_pause)
    return delays_ms
