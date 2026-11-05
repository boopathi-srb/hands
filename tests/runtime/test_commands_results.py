"""The command layer returns typed results, honours a pre-generated run id and a SharedConsole, injects faults
into the fake surface, and never leaves a session registered after a crash."""

from __future__ import annotations

from pathlib import Path

import pytest

from hands.core.results import SuccessResult
from hands.discovery.trace import DiscoveryOutcome
from hands.runtime import commands
from hands.runtime.assembly import SessionOptions
from hands.runtime.commands import DiscoverRequest, ReplayRequest, run_discover, run_replay
from hands.runtime.shared_console import SharedConsole

REPO_ROOT = Path(__file__).resolve().parents[2]
GOAL = "Look up member {{member_number}} in CoreOne and return the balance of their savings share as savings_balance."


def session(tmp_path: Path, mode: str, run_id: str, shared: SharedConsole | None = None) -> SessionOptions:
    return SessionOptions(mode=mode, run_id=run_id, evidence_root=tmp_path / "runs",  # type: ignore[arg-type]
                          policy_path=REPO_ROOT / "policies" / "coreone.yaml", surface="fake",
                          escalation="console" if shared else "none", shared_console=shared)


async def discover(tmp_path: Path, shared: SharedConsole | None = None) -> commands.CommandOutcome:
    return await run_discover(DiscoverRequest(
        goal=GOAL, entry_point="http://127.0.0.1:8700/t/lakeside/login", inputs={"member_number": "10001"},
        sensitive_inputs=[], capability_id="coreone.member_balance", title="t", description="d", tenant="lakeside",
        planner="scripted", model=None, cassette_path=None, cassette_mode="off", max_steps=25,
        session=session(tmp_path, "discovery", "disc-pre", shared), profile_path=REPO_ROOT / "profiles" / "coreone.yaml",
        artifacts_dir=tmp_path / "artifacts",
    ))


def replay_request(tmp_path: Path, run_id: str, faults: list[str], shared: SharedConsole | None = None) -> ReplayRequest:
    return ReplayRequest(capability_id="coreone.member_balance", version=None, inputs={"member_number": "10002"},
                         tenant=None, risky_confirmed=False, faults=faults, target_url="http://127.0.0.1:1",
                         session=session(tmp_path, "replay", run_id, shared), artifacts_dir=tmp_path / "artifacts")


async def test_discover_returns_the_outcome_with_times_tenant_and_run_id(tmp_path: Path) -> None:
    shared = SharedConsole()
    outcome = await discover(tmp_path, shared)

    assert isinstance(outcome.result, DiscoveryOutcome) and outcome.result.status == "completed"
    assert outcome.summary["run_id"] == "disc-pre" and outcome.summary["tenant"] == "lakeside"
    assert outcome.summary["capability_id"] == "coreone.member_balance"
    assert outcome.summary["started_at"] <= outcome.summary["finished_at"]
    assert (tmp_path / "runs" / "disc-pre" / "discovery_result.json").is_file()
    assert shared.leases == {}  # unregistered on close


async def test_replay_returns_the_typed_result_and_injects_fake_faults(tmp_path: Path) -> None:
    await discover(tmp_path)
    outcome = await run_replay(replay_request(tmp_path, "replay-pre", ["maintenance_notice:1", "slow:1"]))

    assert isinstance(outcome.result, SuccessResult) and outcome.result.run_id == "replay-pre"
    assert any(step.recoveries_applied for step in outcome.result.steps)


async def test_replay_with_a_bad_fault_spec_is_an_error(tmp_path: Path) -> None:
    await discover(tmp_path)
    outcome = await run_replay(replay_request(tmp_path, "replay-bad", ["meteor:1"]))

    assert outcome.exit_code == 2 and outcome.result is None and "invalid fault" in outcome.summary["message"]
    assert not (tmp_path / "runs" / "replay-bad").exists()


async def test_a_crash_inside_the_engine_still_closes_the_session(tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    await discover(tmp_path)
    shared = SharedConsole()

    async def exploding_engine(*_args: object) -> None:
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(commands, "_run_engine", exploding_engine)
    with pytest.raises(RuntimeError, match="engine exploded"):
        await run_replay(replay_request(tmp_path, "replay-crash", [], shared))
    assert shared.leases == {}
    assert (tmp_path / "runs" / "replay-crash" / "summary.md").is_file()
