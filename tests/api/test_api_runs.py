"""Integration: run lifecycle through the HTTP API on the fake surface (no browser, no model, no network)."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import httpx

from hands.api.runs import RunRunners
from hands.runtime.commands import CommandOutcome, DiscoverRequest, ReplayRequest

from .helpers import (
    CAPABILITY_ID,
    GOAL,
    REPO_ROOT,
    ApiHarness,
    build_app,
    client_for,
    fake_settings,
    replay_body,
    wait_for_state,
)


async def start_replay(client: httpx.AsyncClient, member_number: str, **overrides: object) -> str:
    response = await client.post("/api/runs/replay", json=replay_body(member_number, **overrides))
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    assert run_id.startswith("replay-")
    return run_id


# ---------------------------------------------------------------- replay lifecycle


async def test_replay_success_returns_outputs_and_headline(client: httpx.AsyncClient) -> None:
    run_id = await start_replay(client, "10002")
    detail = await wait_for_state(client, run_id)

    assert detail["state"] == "finished" and detail["status"] == "success"
    assert detail["result"]["outputs"] == {"savings_balance": "9870.12"}
    assert detail["headline"] == "savings_balance 9870.12"
    assert detail["intervention"] is None
    assert detail["files"] == {"screenshots": [], "snapshots": []}  # replay captures screens on failure only
    assert detail["capability_id"] == CAPABILITY_ID and detail["tenant"] == "lakeside"


async def test_replay_member_not_found_is_a_business_outcome(client: httpx.AsyncClient) -> None:
    detail = await wait_for_state(client, await start_replay(client, "99999"))

    assert detail["status"] == "business_outcome"
    assert detail["headline"] == "MEMBER_NOT_FOUND"


async def test_replay_non_numeric_input_fails_with_invalid_input(client: httpx.AsyncClient) -> None:
    detail = await wait_for_state(client, await start_replay(client, "abc"))

    assert detail["state"] == "finished" and detail["status"] == "failed"
    assert detail["result"]["failure"]["code"] == "invalid_input"
    assert detail["headline"].startswith("failed: invalid_input")


async def test_replay_absorbs_an_injected_fault(client: httpx.AsyncClient) -> None:
    run_id = await start_replay(client, "10002", faults=[{"name": "maintenance_notice", "count": 1}])
    detail = await wait_for_state(client, run_id)

    assert detail["status"] == "success"
    assert any(step["recoveries_applied"] for step in detail["result"]["steps"])


async def test_second_run_while_one_is_active_is_busy(data_dir: Path) -> None:
    release = asyncio.Event()

    async def blocking_replay(request: ReplayRequest) -> CommandOutcome:
        await release.wait()
        return CommandOutcome(0, {"status": "success", "outputs": {}})

    app = build_app(fake_settings(data_dir), runners=RunRunners(replay=blocking_replay))
    async with client_for(app) as client:
        first_run = await start_replay(client, "10001")
        busy = await client.post("/api/runs/replay", json=replay_body("10002"))
        health = (await client.get("/api/health")).json()
        release.set()
        await wait_for_state(client, first_run)

    assert busy.status_code == 409
    assert busy.json() == {"error": "busy", "message": f"run {first_run} is still active", "run_id": first_run}
    assert health["active_run"] == first_run


async def test_crashed_run_releases_the_lock(data_dir: Path) -> None:
    async def crashing_replay(request: ReplayRequest) -> CommandOutcome:
        raise RuntimeError("surface exploded")

    app = build_app(fake_settings(data_dir), runners=RunRunners(replay=crashing_replay))
    async with client_for(app) as client:
        crashed = await wait_for_state(client, await start_replay(client, "10001"))
        again = await client.post("/api/runs/replay", json=replay_body("10001"))
        await wait_for_state(client, again.json()["run_id"])

    assert crashed["state"] == "error" and crashed["status"] == "error"
    assert "surface exploded" in crashed["headline"]
    assert again.status_code == 202
    assert app.state.runs.active_run_id is None


async def test_command_error_before_the_run_is_state_error(data_dir: Path) -> None:
    async def refusing_replay(request: ReplayRequest) -> CommandOutcome:
        return CommandOutcome(2, {"status": "error", "command": "replay", "message": "cannot launch browser"})

    app = build_app(fake_settings(data_dir), runners=RunRunners(replay=refusing_replay))
    async with client_for(app) as client:
        detail = await wait_for_state(client, await start_replay(client, "10001"))

    assert detail["state"] == "error"
    assert detail["headline"] == "error: cannot launch browser"


# ---------------------------------------------------------------- discovery


async def test_discovery_with_scripted_planner_records_a_capability(client: httpx.AsyncClient,
                                                                     data_dir: Path) -> None:
    body = {"goal": GOAL, "inputs": {"member_number": "10001"}, "capability_id": "coreone.balance_copy",
            "title": "Balance copy", "description": "Copy for the test.", "tenant": "lakeside",
            "planner": "scripted", "max_steps": 25, "escalation": "none"}
    response = await client.post("/api/runs/discovery", json=body)
    assert response.status_code == 202, response.text
    detail = await wait_for_state(client, response.json()["run_id"])

    assert detail["mode"] == "discovery" and detail["status"] == "completed"
    assert detail["headline"] == "recorded coreone.balance_copy@1.0.0"
    assert (data_dir / "artifacts" / "coreone.balance_copy" / "1.0.0.json").is_file()
    listed = {entry["id"] for entry in (await client.get("/api/capabilities")).json()}
    assert "coreone.balance_copy" in listed


async def test_discovery_runner_receives_entry_point_and_shared_console(data_dir: Path) -> None:
    received: list[DiscoverRequest] = []

    async def recording_discover(request: DiscoverRequest) -> CommandOutcome:
        received.append(request)
        return CommandOutcome(1, {"mode": "discovery", "status": "stuck", "reason": "no progress"})

    app = build_app(fake_settings(data_dir), runners=RunRunners(discover=recording_discover))
    async with client_for(app) as client:
        response = await client.post("/api/runs/discovery", json={"goal": GOAL, "planner": "scripted",
                                                                   "tenant": "prairie"})
        detail = await wait_for_state(client, response.json()["run_id"])

    assert received[0].entry_point == "http://127.0.0.1:8700/t/prairie/login"
    assert received[0].session.shared_console is app.state.shared_console
    assert detail["status"] == "stuck" and detail["headline"] == "stuck: no progress"


# ---------------------------------------------------------------- events, files, disk


async def test_events_page_after_a_seq(client: httpx.AsyncClient) -> None:
    run_id = await start_replay(client, "10002")
    await wait_for_state(client, run_id)
    everything = (await client.get(f"/api/runs/{run_id}/events")).json()
    middle_seq = everything["events"][len(everything["events"]) // 2]["seq"]
    later = (await client.get(f"/api/runs/{run_id}/events", params={"after": middle_seq})).json()
    none_left = (await client.get(f"/api/runs/{run_id}/events", params={"after": everything["last_seq"]})).json()

    assert everything["state"] == "finished" and everything["events"]
    assert all(event["seq"] > middle_seq for event in later["events"])
    assert later["last_seq"] == everything["last_seq"]
    assert none_left == {"events": [], "last_seq": everything["last_seq"], "state": "finished"}
    assert set(everything["events"][0]) == {"seq", "ts", "kind", "data"}


async def escalated_run(client: httpx.AsyncClient) -> dict[str, object]:
    """A replay stopped by the identity check and aborted by the operator: it has an escalation screenshot."""
    run_id = await start_replay(client, "10001", faults=[{"name": "identity_check", "count": 1}])
    waiting = await wait_for_state(client, run_id, ("waiting_for_operator",))
    intervention_id = waiting["intervention"]["intervention_id"]
    handback = await client.post(f"/console/api/interventions/{intervention_id}/handback",
                                 json={"operator_id": "op-1", "outcome": "abort", "note": "cannot verify"})
    assert handback.status_code == 200, handback.text
    return await wait_for_state(client, run_id)


async def test_operator_abort_ends_the_run_escalated(client: httpx.AsyncClient) -> None:
    detail = await escalated_run(client)

    assert detail["state"] == "finished" and detail["status"] == "escalated"
    assert detail["headline"] == "escalated: cannot verify"
    assert detail["intervention"] is None


async def test_files_serve_png_and_refuse_traversal(client: httpx.AsyncClient) -> None:
    detail = await escalated_run(client)
    run_id = detail["run_id"]
    screenshot = await client.get(f"/api/runs/{run_id}/files/{detail['files']['screenshots'][0]}")
    result_json = await client.get(f"/api/runs/{run_id}/files/result.json")

    assert screenshot.status_code == 200 and screenshot.headers["content-type"] == "image/png"
    assert result_json.json()["status"] == "escalated"
    for bad_path in ("../../../pyproject.toml", "..%2F..%2Fartifacts%2Fx.json", "summary.md", "events.jsonl",
                     "screenshots/missing.png"):
        refused = await client.get(f"/api/runs/{run_id}/files/{bad_path}")
        assert refused.status_code == 404, bad_path
        assert refused.json()["error"] in ("file_not_found", "not_found")


async def test_unknown_run_is_404(client: httpx.AsyncClient) -> None:
    for path in ("/api/runs/replay-nope", "/api/runs/replay-nope/events", "/api/runs/replay-nope/files/a.png",
                 "/api/runs/..%2Fetc"):
        response = await client.get(path)
        assert response.status_code == 404, path


async def test_runs_found_on_disk_are_listed(data_dir: Path) -> None:
    runs_root = data_dir / "runs"
    shutil.copytree(REPO_ROOT / "evidence" / "runs" / "replay-0b683ecc08a5", runs_root / "replay-0b683ecc08a5")
    shutil.copytree(REPO_ROOT / "evidence" / "runs" / "disc-1458ec924f36", runs_root / "disc-1458ec924f36")
    (runs_root / "replay-broken").mkdir()
    (runs_root / "replay-broken" / "result.json").write_text("{not json")
    app = build_app(fake_settings(data_dir))
    async with client_for(app) as client:
        listed = (await client.get("/api/runs")).json()
        limited = (await client.get("/api/runs", params={"limit": 1})).json()
        disc_detail = (await client.get("/api/runs/disc-1458ec924f36")).json()

    by_id = {item["run_id"]: item for item in listed}
    assert set(by_id) == {"replay-0b683ecc08a5", "disc-1458ec924f36"}
    assert by_id["replay-0b683ecc08a5"]["headline"] == "savings_balance 9870.12"
    assert by_id["disc-1458ec924f36"]["capability_id"] == CAPABILITY_ID
    assert by_id["disc-1458ec924f36"]["started_at"].startswith("2026-")
    assert len(limited) == 1 and limited[0]["run_id"] == listed[0]["run_id"]
    assert disc_detail["result"]["planner"] == "ollama"


async def test_new_runs_are_listed_newest_first(harness: ApiHarness) -> None:
    first = await start_replay(harness.client, "10002")
    await wait_for_state(harness.client, first)
    second = await start_replay(harness.client, "99999")
    await wait_for_state(harness.client, second)
    listed = (await harness.client.get("/api/runs")).json()

    assert [item["run_id"] for item in listed[:2]] == [second, first]
    stats = json.loads((harness.app.state.settings.artifacts_dir / CAPABILITY_ID / "1.0.0.json").read_text())
    assert stats["stats"]["runs"] == 2
