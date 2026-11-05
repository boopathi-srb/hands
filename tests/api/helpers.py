"""Shared builders for API tests: settings over a temp data dir, a no-network health probe, polling."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI

from hands.api import ApiDependencies, ApiSettings, create_api_app
from hands.api.health import HealthProbe
from hands.api.runs import RunRunners

REPO_ROOT = Path(__file__).resolve().parents[2]
CAPABILITY_ID = "coreone.member_balance"
GOAL = "Look up member {{member_number}} in CoreOne and return the balance of their savings share as savings_balance."
TOKEN = "test-token-123"
FINAL_STATES = ("finished", "error")


@dataclass(frozen=True)
class ApiHarness:
    app: FastAPI
    client: httpx.AsyncClient


def fake_settings(data_dir: Path, **overrides: Any) -> ApiSettings:
    settings = ApiSettings(data_dir=data_dir, evidence_root=data_dir / "runs", surface="fake",
                           web_dist_dir=data_dir / "no-dist", escalation_timeout_s=30.0)
    return replace(settings, **overrides)


def answering_probe(status_code: int = 200) -> HealthProbe:
    return HealthProbe(transport=httpx.MockTransport(lambda _request: httpx.Response(status_code)))


def failing_probe() -> HealthProbe:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    return HealthProbe(transport=httpx.MockTransport(refuse))


def build_app(settings: ApiSettings, runners: RunRunners | None = None, probe: HealthProbe | None = None) -> FastAPI:
    return create_api_app(settings, ApiDependencies(runners=runners, probe=probe or answering_probe()))


def client_for(app: FastAPI, token: str | None = None) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://api.test", headers=headers)


def replay_body(member_number: str, **overrides: Any) -> dict[str, Any]:
    return {"capability_id": CAPABILITY_ID, "inputs": {"member_number": member_number}, "tenant": "lakeside",
            **overrides}


async def wait_for_state(client: httpx.AsyncClient, run_id: str, states: tuple[str, ...] = FINAL_STATES,
                         timeout_s: float = 30.0) -> dict[str, Any]:
    """Poll GET /api/runs/{id} until its state is one of `states`."""
    deadline = asyncio.get_running_loop().time() + timeout_s
    while True:
        detail = (await client.get(f"/api/runs/{run_id}")).json()
        if detail.get("state") in states:
            return detail
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"run {run_id} stuck in {detail.get('state')}: {detail}")
        await asyncio.sleep(0.02)
