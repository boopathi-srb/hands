"""SharedConsole and how build_session joins it; fault specs and fake-surface fault injection."""

from __future__ import annotations

from pathlib import Path

import pytest

from hands.console.server import ConsoleServer
from hands.runtime.assembly import SessionOptions, build_session
from hands.runtime.commands import FaultSpec, arm_fake_faults, catalog_set_status, parse_fault_specs
from hands.runtime.shared_console import SharedConsole
from hands.session.board import InterventionBoard
from hands.session.doubles import (
    InMemoryEvidence,
    StubSurface,
    make_intervention_request,
    make_observation,
)
from hands.session.escalation import ConsoleEscalator
from hands.session.lease import LeaseManager
from hands.surfaces.fake import coreone_fake

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY = REPO_ROOT / "policies" / "coreone.yaml"


def options(tmp_path: Path, run_id: str, shared: SharedConsole | None, escalation: str = "console") -> SessionOptions:
    return SessionOptions(mode="replay", run_id=run_id, evidence_root=tmp_path, policy_path=POLICY,
                          surface="fake", escalation=escalation, console_port=0,  # type: ignore[arg-type]
                          shared_console=shared)


# ---------------------------------------------------------------- SharedConsole


def parts(session_id: str) -> tuple[LeaseManager, StubSurface, InMemoryEvidence]:
    evidence = InMemoryEvidence(run_dir="/tmp/none")
    return LeaseManager(session_id, interventions=InterventionBoard(), evidence=evidence), \
        StubSurface(make_observation([])), evidence


def test_register_and_unregister() -> None:
    shared = SharedConsole()
    lease, surface, evidence = parts("s-1")

    assert shared.register("s-1", lease, surface, evidence) is True
    assert shared.is_registered("s-1") and shared.leases["s-1"] is lease and shared.surfaces["s-1"] is surface
    assert shared.register("s-1", lease, surface, evidence) is False
    assert shared.unregister("s-1") is True
    assert not shared.is_registered("s-1") and shared.evidence == {}
    assert shared.unregister("s-1") is False


def test_open_intervention_comes_from_the_board() -> None:
    shared = SharedConsole()
    assert shared.open_intervention("s-1") is None
    shared.board.open(make_intervention_request(session_id="s-1"))
    opened = shared.open_intervention("s-1")
    assert opened is not None and opened.session_id == "s-1"
    assert shared.open_intervention("s-2") is None


@pytest.mark.parametrize(("base_path", "expected"), [("/console", "/console"), ("/console/", "/console"), ("/", "/"),
                                                     ("", "/")])
def test_operator_url(base_path: str, expected: str) -> None:
    assert SharedConsole(public_base_path=base_path).operator_url() == expected


# ---------------------------------------------------------------- build_session with and without it


async def test_shared_console_session_registers_without_a_server(tmp_path: Path) -> None:
    shared = SharedConsole()
    built = await build_session(options(tmp_path, "replay-aa", shared))
    assert built.session is not None, built.error
    session = built.session

    assert session.console is None
    assert session.board is shared.board and shared.leases["replay-aa"] is session.lease
    assert shared.surfaces["replay-aa"] is session.surface and shared.evidence["replay-aa"] is session.evidence
    assert isinstance(session.escalator, ConsoleEscalator)
    await session.close()
    assert not shared.is_registered("replay-aa")


async def test_shared_console_with_escalation_none_does_not_register(tmp_path: Path) -> None:
    shared = SharedConsole()
    built = await build_session(options(tmp_path, "replay-bb", shared, escalation="none"))
    assert built.session is not None and built.session.escalator is None
    assert shared.leases == {}
    await built.session.close()


async def test_duplicate_session_id_on_the_shared_console_is_refused(tmp_path: Path) -> None:
    shared = SharedConsole()
    lease, surface, evidence = parts("replay-cc")
    shared.register("replay-cc", lease, surface, evidence)
    built = await build_session(options(tmp_path, "replay-cc", shared))

    assert built.session is None and "already registered" in (built.error or "")
    assert shared.leases["replay-cc"] is lease  # the other session stays registered


async def test_without_shared_console_a_private_console_server_starts(tmp_path: Path) -> None:
    built = await build_session(options(tmp_path, "replay-dd", None))
    assert built.session is not None
    assert isinstance(built.session.console, ConsoleServer) and built.session.console.running
    assert built.session.shared_console is None
    await built.session.close()
    assert not built.session.console.running


def test_shared_console_is_not_part_of_options_equality(tmp_path: Path) -> None:
    assert options(tmp_path, "r", SharedConsole()) == options(tmp_path, "r", SharedConsole())


# ---------------------------------------------------------------- faults


def test_parse_fault_specs() -> None:
    assert parse_fault_specs([]) == []
    assert parse_fault_specs(["session_expired", "slow:3"]) == [FaultSpec("session_expired", 1), FaultSpec("slow", 3)]
    for bad_spec in ("meteor", "slow:0", "slow:x", "slow:-1", "slow:²", "slow:1001", ""):
        assert isinstance(parse_fault_specs([bad_spec]), str), bad_spec


def test_arm_fake_faults_queues_screens() -> None:
    surface = coreone_fake("lakeside")
    assert arm_fake_faults(surface, [FaultSpec("identity_check", 2), FaultSpec("slow", 1)]) is None
    assert arm_fake_faults(surface, []) is None


def test_arm_fake_faults_refuses_other_surfaces() -> None:
    assert arm_fake_faults(StubSurface(make_observation([])), []) is None
    error = arm_fake_faults(StubSurface(make_observation([])), [FaultSpec("slow", 1)])
    assert error == "faults can only be injected into the fake surface"


def test_arm_fake_faults_reports_a_missing_screen() -> None:
    error = arm_fake_faults(coreone_fake("lakeside"), [FaultSpec("no_such_screen", 1)])
    assert error is not None and "no_such_screen" in error


def test_catalog_set_status_returns_id_and_version(tmp_path: Path) -> None:
    import shutil

    shutil.copytree(REPO_ROOT / "artifacts", tmp_path / "artifacts")
    outcome = catalog_set_status(tmp_path / "artifacts", "coreone.member_balance", None, "approved")
    assert outcome.exit_code == 0
    assert outcome.summary == {"capability": "coreone.member_balance@1.0.0", "id": "coreone.member_balance",
                               "version": "1.0.0", "status": "approved"}
