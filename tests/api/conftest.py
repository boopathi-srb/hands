"""API test fixtures. The repo's committed artifact was recorded on the live web app and its flow differs
from the FakeSurface after sign-on, so tests replay an artifact discovered here, once, on the fake surface
with the scripted planner (no network, no browser, no model)."""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from hands.runtime.assembly import SessionOptions
from hands.runtime.commands import DiscoverRequest, run_discover

from .helpers import GOAL, REPO_ROOT, ApiHarness, build_app, client_for, fake_settings


@pytest.fixture(scope="session")
def fake_artifacts(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("fake-artifacts")
    request = DiscoverRequest(
        goal=GOAL, entry_point="http://127.0.0.1:8700/t/lakeside/login", inputs={"member_number": "10001"},
        sensitive_inputs=[], capability_id="coreone.member_balance", title="Member savings balance",
        description="Balance lookup.", tenant="lakeside", planner="scripted", model=None, cassette_path=None,
        cassette_mode="off", max_steps=25,
        session=SessionOptions(mode="discovery", run_id="disc-seed", evidence_root=root / "runs",
                               policy_path=REPO_ROOT / "policies" / "coreone.yaml", surface="fake",
                               escalation="none"),
        profile_path=REPO_ROOT / "profiles" / "coreone.yaml", artifacts_dir=root / "artifacts",
    )
    outcome = asyncio.run(run_discover(request))
    assert outcome.exit_code == 0, outcome.summary
    shutil.copytree(REPO_ROOT / "artifacts" / "coreone.member_balance" / "overlays",
                    root / "artifacts" / "coreone.member_balance" / "overlays")
    return root / "artifacts"


@pytest.fixture
def data_dir(tmp_path: Path, fake_artifacts: Path) -> Path:
    shutil.copytree(fake_artifacts, tmp_path / "data" / "artifacts")
    return tmp_path / "data"


@pytest.fixture
async def harness(data_dir: Path) -> AsyncIterator[ApiHarness]:
    app = build_app(fake_settings(data_dir))
    async with client_for(app) as api_client:
        yield ApiHarness(app=app, client=api_client)
    await app.state.runs.shutdown()


@pytest.fixture
def client(harness: ApiHarness) -> httpx.AsyncClient:
    return harness.client
