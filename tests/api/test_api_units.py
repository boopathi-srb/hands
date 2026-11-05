"""Unit tests: validation, reference data, request translation, health probe, built-UI helpers, RunManager."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from hands.api.health import HealthProbe, health_report, package_version
from hands.api.models import DiscoveryStartBody, FaultRequest, ReplayStartBody
from hands.api.reference import (
    approve_capability,
    capability_detail,
    capability_list,
    fault_list,
    overlay_tenants,
    tenant_list,
)
from hands.api.run_requests import (
    discover_request,
    entry_point_for,
    fault_specs,
    replay_request,
    session_options,
)
from hands.api.runs import RunManager, RunRunners, RunStarted
from hands.api.spa import has_built_ui, is_non_ui_path, mount_spa, ui_file_for
from hands.api.validation import (
    ApiError,
    check_capability,
    check_faults,
    check_planner,
    check_sensitive_inputs,
    check_tenant,
    validate_discovery,
    validate_replay,
)
from hands.runtime.commands import CommandOutcome, ReplayRequest
from hands.runtime.shared_console import SharedConsole
from hands.session.doubles import make_intervention_request

from .helpers import CAPABILITY_ID, GOAL, answering_probe, failing_probe, fake_settings

# ---------------------------------------------------------------- validation


def test_check_tenant() -> None:
    assert check_tenant("lakeside") is None and check_tenant(None) is None
    error = check_tenant("nowhere")
    assert error is not None and error.status_code == 400 and error.code == "unknown_tenant"
    assert check_tenant("") is not None


def test_check_faults() -> None:
    assert check_faults([]) is None
    assert check_faults([FaultRequest(name="slow", count=2)]) is None
    error = check_faults([FaultRequest(name="meteor")])
    assert error is not None and error.code == "unknown_fault" and "meteor" in error.message


def test_check_capability(data_dir: Path) -> None:
    artifacts = data_dir / "artifacts"
    assert check_capability(artifacts, CAPABILITY_ID, None) is None
    assert check_capability(artifacts, CAPABILITY_ID, "1.0.0") is None
    for capability_id, version in (("nope.x", None), (CAPABILITY_ID, "2.0.0"), ("", None), ("../x", None)):
        error = check_capability(artifacts, capability_id, version)
        assert error is not None and error.status_code == 404


def test_check_planner() -> None:
    assert check_planner("scripted", False) is None and check_planner("ollama", False) is None
    assert check_planner("anthropic", True) is None
    assert check_planner("anthropic", False) == ApiError(
        400, "planner_unavailable", "planner 'anthropic' needs ANTHROPIC_API_KEY on the server")
    unknown = check_planner("", True)
    assert unknown is not None and unknown.code == "unknown_planner"


def test_check_sensitive_inputs() -> None:
    assert check_sensitive_inputs(DiscoveryStartBody(goal="g")) is None
    declared = DiscoveryStartBody(goal="g", inputs={"pin": "1"}, sensitive_inputs=["pin"])
    assert check_sensitive_inputs(declared) is None
    error = check_sensitive_inputs(DiscoveryStartBody(goal="g", sensitive_inputs=["pin"]))
    assert error is not None and error.code == "unknown_input"


def test_validate_replay_reports_the_first_problem(data_dir: Path) -> None:
    artifacts = data_dir / "artifacts"
    assert validate_replay(ReplayStartBody(capability_id=CAPABILITY_ID), artifacts) is None
    both_bad = ReplayStartBody(capability_id="nope.x", tenant="nowhere")
    assert validate_replay(both_bad, artifacts).code == "unknown_tenant"  # type: ignore[union-attr]


def test_validate_discovery() -> None:
    assert validate_discovery(DiscoveryStartBody(goal="g", planner="scripted"), False) is None
    assert validate_discovery(DiscoveryStartBody(goal="g"), False).code == "planner_unavailable"  # type: ignore[union-attr]


# ---------------------------------------------------------------- reference data


def test_tenant_and_fault_lists() -> None:
    assert [tenant["id"] for tenant in tenant_list()] == ["lakeside", "prairie"]
    assert {fault["name"] for fault in fault_list()} >= {"identity_check", "slow"}


def test_capability_list_on_empty_and_seeded_dirs(tmp_path: Path, data_dir: Path) -> None:
    assert capability_list(tmp_path / "none") == []
    entries = capability_list(data_dir / "artifacts")
    assert entries[0]["id"] == CAPABILITY_ID and entries[0]["stats"]["runs"] == 0


def test_overlay_tenants(tmp_path: Path, data_dir: Path) -> None:
    assert overlay_tenants(data_dir / "artifacts", CAPABILITY_ID) == ["prairie"]
    assert overlay_tenants(tmp_path, CAPABILITY_ID) == []


def test_capability_detail(data_dir: Path) -> None:
    detail = capability_detail(data_dir / "artifacts", CAPABILITY_ID, None)
    assert isinstance(detail, dict) and detail["capability"]["version"] == "1.0.0"
    missing = capability_detail(data_dir / "artifacts", "nope.x", None)
    assert isinstance(missing, ApiError) and missing.status_code == 404


def test_approve_capability(data_dir: Path) -> None:
    approved = approve_capability(data_dir / "artifacts", CAPABILITY_ID, "1.0.0")
    assert approved == {"id": CAPABILITY_ID, "version": "1.0.0", "status": "approved"}
    missing = approve_capability(data_dir / "artifacts", CAPABILITY_ID, "3.0.0")
    assert isinstance(missing, ApiError) and missing.code == "unknown_capability"


# ---------------------------------------------------------------- request translation


def test_session_options_use_settings_and_shared_console(tmp_path: Path) -> None:
    settings = fake_settings(tmp_path)
    shared = SharedConsole()
    options = session_options(settings, "replay", "replay-a", None, "console", shared, risky_confirmed=True)
    assert options.run_id == "replay-a" and options.evidence_root == tmp_path / "runs"
    assert options.surface == "fake" and options.fake_tenant == "lakeside" and options.risky_confirmed
    assert options.shared_console is shared and options.escalation_timeout_s == 30.0
    assert options.fake_base_url == settings.target_url


def test_fault_specs() -> None:
    assert fault_specs([]) == []
    assert fault_specs([FaultRequest(name="slow", count=3), FaultRequest(name="app_error")]) == ["slow:3", "app_error:1"]


def test_replay_request(tmp_path: Path) -> None:
    body = ReplayStartBody(capability_id=CAPABILITY_ID, inputs={"member_number": "1"}, tenant="prairie",
                           faults=[FaultRequest(name="slow")], escalation="none")
    request = replay_request(body, fake_settings(tmp_path), "replay-b", SharedConsole())
    assert request.tenant == "prairie" and request.faults == ["slow:1"] and request.inputs == {"member_number": "1"}
    assert request.session.escalation == "none" and request.session.fake_tenant == "prairie"
    assert request.artifacts_dir == tmp_path / "artifacts"


def test_entry_point_and_discover_request(tmp_path: Path) -> None:
    settings = fake_settings(tmp_path)
    assert entry_point_for(settings, "prairie") == "http://127.0.0.1:8700/t/prairie/login"
    body = DiscoveryStartBody(goal=GOAL, inputs={"member_number": "1"}, planner="scripted", max_steps=7)
    request = discover_request(body, settings, "disc-a", SharedConsole())
    assert request.planner == "scripted" and request.max_steps == 7 and request.cassette_mode == "off"
    assert request.session.mode == "discovery" and request.profile_path == settings.profile_path


# ---------------------------------------------------------------- health


async def test_health_probe_reachable() -> None:
    assert await answering_probe(200).reachable("http://x/ok") is True
    assert await answering_probe(404).reachable("http://x/missing") is True
    assert await answering_probe(503).reachable("http://x/down") is False
    assert await failing_probe().reachable("http://x/refused") is False


async def test_health_probe_hits_the_documented_paths() -> None:
    seen: list[str] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200)

    report = await health_report(HealthProbe(transport=httpx.MockTransport(record)), "http://core", "http://ollama",
                                 auth_required=True, anthropic_key_present=False, active_run_id="replay-a")
    assert seen == ["http://core/t/lakeside/_health", "http://ollama/api/version"]
    assert report["auth_required"] is True and report["active_run"] == "replay-a"


def test_package_version() -> None:
    assert package_version()


# ---------------------------------------------------------------- built UI


def test_spa_helpers(tmp_path: Path) -> None:
    assert has_built_ui(tmp_path) is False
    (tmp_path / "index.html").write_text("x")
    (tmp_path / "logo.svg").write_text("<svg/>")
    assert has_built_ui(tmp_path) is True
    assert ui_file_for(tmp_path, "") == tmp_path / "index.html"
    assert ui_file_for(tmp_path, "logo.svg") == (tmp_path / "logo.svg").resolve()
    assert ui_file_for(tmp_path, "runs/abc") == tmp_path / "index.html"
    assert ui_file_for(tmp_path, "../../etc/passwd") == tmp_path / "index.html"


@pytest.mark.parametrize(("path", "expected"), [("api", True), ("api/x", True), ("/console/", True), ("", False),
                                                ("apis", False), ("runs/api", False)])
def test_is_non_ui_path(path: str, expected: bool) -> None:
    assert is_non_ui_path(path) is expected


def test_mount_spa_without_build_registers_nothing(tmp_path: Path) -> None:
    app = FastAPI()
    assert mount_spa(app, tmp_path) is False
    assert len(app.routes) == len(FastAPI().routes)


# ---------------------------------------------------------------- RunManager


def test_run_manager_queries_with_nothing_running(tmp_path: Path) -> None:
    manager = RunManager(fake_settings(tmp_path), SharedConsole())
    assert manager.active_run_id is None
    assert manager.list_runs(50) == [] and manager.list_runs(0) == []
    assert manager.find("replay-none") is None and manager.detail("replay-none") is None
    assert manager.events("replay-none", 0) is None and manager.file("replay-none", "a.png") is None
    assert manager.open_intervention("replay-none") is None


async def test_run_manager_shutdown_cancels_the_active_run(tmp_path: Path) -> None:
    async def never_ending(request: ReplayRequest) -> CommandOutcome:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    shared = SharedConsole()
    manager = RunManager(fake_settings(tmp_path), shared, RunRunners(replay=never_ending))
    started = manager.start_replay(ReplayStartBody(capability_id=CAPABILITY_ID))
    assert isinstance(started, RunStarted)
    assert await manager.wait_for_active(timeout_s=0.05) is False
    await manager.shutdown()

    record = manager.find(started.run_id)
    assert manager.active_run_id is None
    assert record is not None and record.state == "error" and "cancelled" in record.headline
    assert await manager.wait_for_active(timeout_s=0.01) is True
    await manager.shutdown()  # idempotent with nothing running


async def test_run_manager_reports_waiting_for_operator_from_the_board(tmp_path: Path) -> None:
    release = asyncio.Event()

    async def waiting_replay(request: ReplayRequest) -> CommandOutcome:
        await release.wait()
        return CommandOutcome(0, {"status": "success", "outputs": {"x": "1"}})

    shared = SharedConsole()
    manager = RunManager(fake_settings(tmp_path), shared, RunRunners(replay=waiting_replay))
    started = manager.start_replay(ReplayStartBody(capability_id=CAPABILITY_ID))
    assert isinstance(started, RunStarted)
    shared.board.open(make_intervention_request(session_id=started.run_id, run_id=started.run_id))

    waiting = manager.detail(started.run_id)
    waiting_events = manager.events(started.run_id, 0)
    release.set()
    await manager.wait_for_active(timeout_s=5)

    assert waiting is not None and waiting["state"] == "waiting_for_operator"
    assert waiting["intervention"]["session_id"] == started.run_id and waiting["intervention"]["lease"] is None
    assert waiting_events == {"events": [], "last_seq": 0, "state": "waiting_for_operator"}
    assert manager.find(started.run_id).state == "finished"  # type: ignore[union-attr]
