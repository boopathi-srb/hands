"""Routes: health, auth, reference data, catalog, request validation, and the built UI."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from hands.api import ApiSettings

from .helpers import (
    CAPABILITY_ID,
    GOAL,
    TOKEN,
    build_app,
    client_for,
    failing_probe,
    fake_settings,
    replay_body,
)

# ---------------------------------------------------------------- health


async def test_health_reports_mock_app_planners_and_version(client: httpx.AsyncClient) -> None:
    health = (await client.get("/api/health")).json()

    assert health == {"status": "ok", "auth_required": False, "mock_app": "up",
                      "planners": {"anthropic": False, "ollama": True, "scripted": True},
                      "active_run": None, "version": health["version"]}
    assert health["version"]


async def test_health_when_nothing_answers(data_dir: Path) -> None:
    settings = replace(fake_settings(data_dir), anthropic_key_present=True)
    async with client_for(build_app(settings, probe=failing_probe())) as client:
        health = (await client.get("/api/health")).json()

    assert health["mock_app"] == "down"
    assert health["planners"] == {"anthropic": True, "ollama": False, "scripted": True}


# ---------------------------------------------------------------- auth


@pytest.fixture
def secured_settings(data_dir: Path) -> ApiSettings:
    return replace(fake_settings(data_dir), api_token=TOKEN)


async def test_auth_required_everywhere_but_health(secured_settings: ApiSettings) -> None:
    app = build_app(secured_settings)
    async with client_for(app) as anonymous, client_for(app, token=TOKEN) as authorized, \
            client_for(app, token="wrong") as wrong:
        health = await anonymous.get("/api/health")
        for path in ("/api/tenants", "/api/capabilities", "/api/runs", "/console/api/interventions", "/console/"):
            refused = await anonymous.get(path)
            assert refused.status_code == 401, path
            assert refused.json()["error"] == "unauthorized"
            assert (await wrong.get(path)).status_code == 401, path
            assert (await authorized.get(path)).status_code == 200, path
        refused_post = await anonymous.post("/api/runs/replay", json=replay_body("10001"))

    assert health.status_code == 200 and health.json()["auth_required"] is True
    assert refused_post.status_code == 401


async def test_cors_preflight_is_answered_without_a_token(secured_settings: ApiSettings) -> None:
    settings = replace(secured_settings, cors_origins=("https://ui.example",))
    async with client_for(build_app(settings)) as client:
        preflight = await client.options("/api/runs", headers={
            "Origin": "https://ui.example", "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization"})
        refused = await client.get("/api/runs", headers={"Origin": "https://ui.example"})

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "https://ui.example"
    assert refused.status_code == 401 and refused.headers["access-control-allow-origin"] == "https://ui.example"


# ---------------------------------------------------------------- reference data


async def test_tenants(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/tenants")).json() == [
        {"id": "lakeside", "name": "Lakeside Community CU"}, {"id": "prairie", "name": "Prairie Federal CU"}]


async def test_faults_have_descriptions(client: httpx.AsyncClient) -> None:
    faults = (await client.get("/api/faults")).json()

    assert [fault["name"] for fault in faults] == ["session_expired", "slow", "maintenance_notice", "native_alert",
                                                    "identity_check", "app_error"]
    assert all(fault["description"] for fault in faults)


# ---------------------------------------------------------------- catalog


async def test_capability_list_includes_stats(client: httpx.AsyncClient) -> None:
    entries = (await client.get("/api/capabilities")).json()

    assert [entry["id"] for entry in entries] == [CAPABILITY_ID]
    assert entries[0]["latest_version"] == "1.0.0" and "member_number" in entries[0]["inputs"]
    assert entries[0]["stats"]["runs"] == 0


async def test_capability_detail_has_overlays_and_tool(client: httpx.AsyncClient) -> None:
    detail = (await client.get(f"/api/capabilities/{CAPABILITY_ID}", params={"version": "1.0.0"})).json()

    assert detail["capability"]["id"] == CAPABILITY_ID
    assert detail["overlays"] == ["prairie"]
    assert detail["tool"]["name"]


@pytest.mark.parametrize("path", ["/api/capabilities/nope.missing", f"/api/capabilities/{CAPABILITY_ID}?version=9.9.9",
                                  f"/api/capabilities/{CAPABILITY_ID}?version=bad"])
async def test_unknown_capability_is_404(client: httpx.AsyncClient, path: str) -> None:
    response = await client.get(path)
    assert response.status_code == 404 and response.json()["error"] == "unknown_capability"


async def test_approve_persists_status(client: httpx.AsyncClient, data_dir: Path) -> None:
    approved = await client.post(f"/api/capabilities/{CAPABILITY_ID}/approve", json={})
    without_body = await client.post(f"/api/capabilities/{CAPABILITY_ID}/approve")
    unknown = await client.post("/api/capabilities/nope.missing/approve", json={"version": "1.0.0"})

    assert approved.json() == {"id": CAPABILITY_ID, "version": "1.0.0", "status": "approved"}
    assert without_body.status_code == 200
    stored = json.loads((data_dir / "artifacts" / CAPABILITY_ID / "1.0.0.json").read_text())
    assert stored["status"] == "approved"
    assert unknown.status_code == 404 and unknown.json()["error"] == "unknown_capability"


# ---------------------------------------------------------------- validation


@pytest.mark.parametrize(("body", "status_code", "code"), [
    (replay_body("10001", tenant="nowhere"), 400, "unknown_tenant"),
    (replay_body("10001", capability_id="nope.missing"), 404, "unknown_capability"),
    (replay_body("10001", faults=[{"name": "meteor", "count": 1}]), 400, "unknown_fault"),
    (replay_body("10001", faults=[{"name": "slow", "count": 0}]), 422, "invalid_request"),
    (replay_body("10001", escalation="pager"), 422, "invalid_request"),
    (replay_body("10001", unexpected=True), 422, "invalid_request"),
    ({"inputs": {}}, 422, "invalid_request"),
])
async def test_replay_requests_are_validated(client: httpx.AsyncClient, body: dict[str, object],
                                             status_code: int, code: str) -> None:
    response = await client.post("/api/runs/replay", json=body)

    assert response.status_code == status_code, response.text
    assert response.json()["error"] == code and response.json()["message"]


@pytest.mark.parametrize(("overrides", "status_code", "code"), [
    ({"planner": "gpt"}, 400, "unknown_planner"),
    ({"planner": "anthropic"}, 400, "planner_unavailable"),
    ({"planner": "scripted", "tenant": "nowhere"}, 400, "unknown_tenant"),
    ({"planner": "scripted", "sensitive_inputs": ["ssn"]}, 400, "unknown_input"),
    ({"planner": "scripted", "max_steps": 0}, 422, "invalid_request"),
    ({"planner": "scripted", "goal": ""}, 422, "invalid_request"),
])
async def test_discovery_requests_are_validated(client: httpx.AsyncClient, overrides: dict[str, object],
                                                status_code: int, code: str) -> None:
    body = {"goal": GOAL, "inputs": {"member_number": "10001"}, **overrides}
    response = await client.post("/api/runs/discovery", json=body)

    assert response.status_code == status_code, response.text
    assert response.json()["error"] == code


async def test_unknown_api_path_uses_the_error_shape(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/nothing-here")
    assert response.status_code == 404 and response.json()["error"] == "not_found"


# ---------------------------------------------------------------- built UI


async def test_built_ui_is_served_with_spa_fallback(data_dir: Path, tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>hands</title>")
    (dist / "assets" / "app.js").write_text("console.log('ui')")
    async with client_for(build_app(replace(fake_settings(data_dir), web_dist_dir=dist))) as client:
        root = await client.get("/")
        deep_link = await client.get("/runs/replay-abc")
        asset = await client.get("/assets/app.js")
        escape = await client.get("/..%2F..%2Fpyproject.toml")
        api_miss = await client.get("/api/nothing-here")
        tenants = await client.get("/api/tenants")

    assert root.status_code == 200 and "<title>hands</title>" in root.text
    assert deep_link.text == root.text
    assert asset.text == "console.log('ui')"
    assert "[project]" not in escape.text
    assert api_miss.status_code == 404 and api_miss.json()["error"] == "not_found"
    assert tenants.status_code == 200


async def test_no_built_ui_means_api_only(client: httpx.AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 404
