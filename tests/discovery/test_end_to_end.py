"""Discovery on the CoreOne fake -> record_capability -> validated Capability -> replay on a fresh fake."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from hands.core.artifact import AppRef, Capability, InputSpec
from hands.discovery.cassette import CassettePlanner
from hands.discovery.loop import DiscoveryAgent
from hands.discovery.planners.scripted import COREONE_BALANCE_GOAL, coreone_member_balance_script
from hands.discovery.recorder import record_capability
from hands.discovery.trace import DiscoveryOutcome
from hands.profiles import load_profile

from .helpers import (
    COREONE_PROFILE_PATH,
    FIXED_TIME,
    LOGIN_URL,
    DictCredentials,
    RecordingEvidence,
    coreone_policy,
    lakeside_fake,
)

APP = AppRef(vendor="Northwind Core Systems", product="CoreOne", product_version="7.4", surface="web")
REPLAY_AVAILABLE = importlib.util.find_spec("hands.replay") is not None


async def discover(planner: Any) -> DiscoveryOutcome:
    agent = DiscoveryAgent(lakeside_fake(), planner, coreone_policy(), RecordingEvidence(), DictCredentials(),
                           run_id="run-e2e")
    return await agent.run(COREONE_BALANCE_GOAL, LOGIN_URL, {"member_number": "10001"}, ["teller"])


def to_capability(outcome: DiscoveryOutcome) -> Capability:
    profile = load_profile(COREONE_PROFILE_PATH).profile
    result = record_capability(
        outcome, capability_id="coreone.member_savings_balance", title="Member savings balance",
        description="Look up a member and return the savings share balance.", app=APP,
        inputs={"member_number": InputSpec(type="string", description="Member number", pattern=r"^\d+$")},
        profile=profile, planner_name="scripted", model=None, tenant_id="lakeside", recorded_at=FIXED_TIME,
    )
    assert result.capability is not None, result.error
    return result.capability


async def test_discovery_records_a_valid_capability() -> None:
    capability = to_capability(await discover(coreone_member_balance_script()))
    round_tripped = Capability.model_validate_json(capability.model_dump_json())
    assert round_tripped == capability


async def test_cassette_rerun_is_offline_and_identical(tmp_path: Path) -> None:
    cassette_path = tmp_path / "coreone_balance.jsonl"
    recorded = await discover(CassettePlanner(coreone_member_balance_script(), cassette_path, "record"))
    replayer = CassettePlanner(None, cassette_path, "replay")
    rerun = await discover(replayer)
    assert rerun.status == recorded.status == "completed"
    assert replayer.misses == 0
    assert to_capability(rerun) == to_capability(recorded)


@pytest.mark.skipif(not REPLAY_AVAILABLE, reason="hands.replay is not available yet")
@pytest.mark.parametrize(
    ("member_number", "status", "detail"),
    [("10001", "success", "1250.00"), ("10002", "success", "9870.12"), ("99999", "business_outcome",
                                                                          "MEMBER_NOT_FOUND")],
)
async def test_recorded_capability_replays_without_a_model(member_number: str, status: str, detail: str) -> None:
    from hands.replay import ReplayEngine

    capability = to_capability(await discover(coreone_member_balance_script()))
    engine = ReplayEngine(lakeside_fake(), coreone_policy(), RecordingEvidence(), DictCredentials(),
                          poll_interval_ms=1, checkpoint_timeout_ms=200)
    result = await engine.run(capability, {"member_number": member_number}, tenant_id="lakeside",
                              run_timeout_ms=20_000)
    assert result.status == status
    if status == "success":
        assert result.outputs == {"savings_balance": detail}  # type: ignore[union-attr]
    else:
        assert result.code == detail  # type: ignore[union-attr]
