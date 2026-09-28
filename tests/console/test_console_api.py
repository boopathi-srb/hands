"""Console HTTP API in-process (httpx ASGITransport on the test's own event loop)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from hands.console.app import create_console_app
from hands.session.board import InterventionBoard
from hands.session.doubles import (
    TINY_PNG_FRAME,
    InMemoryEvidence,
    StubLiveView,
    StubSurface,
    make_intervention_request,
    make_observation,
)
from hands.session.escalation import ConsoleEscalator
from hands.session.lease import LeaseManager

SESSION = "session-1"
RUN = "run-1"


class Console:
    def __init__(self, run_dir: Path) -> None:
        self.board = InterventionBoard()
        self.evidence = InMemoryEvidence(run_dir=str(run_dir))
        self.lease = LeaseManager(SESSION, interventions=self.board, evidence=self.evidence)
        self.surface = StubSurface(make_observation(), live_view=StubLiveView())
        self.app = create_console_app(
            self.board, {SESSION: self.lease}, {SESSION: self.surface}, {SESSION: self.evidence}
        )


@pytest.fixture
async def console(tmp_path: Path) -> AsyncIterator[tuple[Console, httpx.AsyncClient]]:
    setup = Console(tmp_path)
    transport = httpx.ASGITransport(app=setup.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://console.test") as client:
        yield setup, client


def open_intervention(setup: Console, screenshot_path: str | None = None) -> None:
    setup.lease.grant_automation(RUN)
    setup.board.open(make_intervention_request(screenshot_path=screenshot_path))
    setup.lease.release(reason="escalation")


async def test_operator_page_is_served(console: tuple[Console, httpx.AsyncClient]) -> None:
    _, client = console
    response = await client.get("/")
    assert response.status_code == 200
    assert "hands operator console" in response.text
    assert "<script" in response.text and "cdn" not in response.text.lower()


async def test_list_is_empty_then_shows_open_intervention(
    console: tuple[Console, httpx.AsyncClient],
) -> None:
    setup, client = console
    assert (await client.get("/api/interventions")).json() == {"interventions": []}
    open_intervention(setup)
    listed = (await client.get("/api/interventions")).json()["interventions"]
    assert [item["intervention_id"] for item in listed] == ["iv-1"]
    assert listed[0]["lease"]["holder"] == "nobody"


async def test_context_includes_screenshot_from_relative_evidence_path(
    console: tuple[Console, httpx.AsyncClient], tmp_path: Path
) -> None:
    setup, client = console
    (tmp_path / "shot.png").write_bytes(TINY_PNG_FRAME)
    open_intervention(setup, screenshot_path="shot.png")
    context = (await client.get("/api/interventions/iv-1")).json()
    assert context["request"]["reason"]
    assert context["request"]["step_id"] == "search"
    assert context["status"] == "open"
    assert context["screenshot_data_url"].startswith("data:image/png;base64,")


async def test_context_with_missing_screenshot_file_has_no_image(
    console: tuple[Console, httpx.AsyncClient],
) -> None:
    setup, client = console
    open_intervention(setup, screenshot_path="missing.png")
    context = (await client.get("/api/interventions/iv-1")).json()
    assert context["screenshot_data_url"] is None


async def test_unknown_intervention_is_404(console: tuple[Console, httpx.AsyncClient]) -> None:
    _, client = console
    assert (await client.get("/api/interventions/nope")).status_code == 404
    take = await client.post("/api/interventions/nope/take", json={"operator_id": "alice"})
    assert take.status_code == 404
    assert take.json()["error"] == "unknown_intervention"


async def test_take_requires_operator_id(console: tuple[Console, httpx.AsyncClient]) -> None:
    setup, client = console
    open_intervention(setup)
    response = await client.post("/api/interventions/iv-1/take", json={"operator_id": ""})
    assert response.status_code == 422


async def test_take_and_handback_resume(console: tuple[Console, httpx.AsyncClient]) -> None:
    setup, client = console
    open_intervention(setup)
    take = await client.post("/api/interventions/iv-1/take", json={"operator_id": "alice"})
    assert take.status_code == 200
    assert take.json()["lease"]["holder"] == "human"
    assert take.json()["live_path"] == "/api/sessions/session-1/live"

    second = await client.post("/api/interventions/iv-1/take", json={"operator_id": "bob"})
    assert second.status_code == 409 and second.json()["error"] == "held_by_human"

    wrong = await client.post(
        "/api/interventions/iv-1/handback", json={"operator_id": "bob", "outcome": "resume"}
    )
    assert wrong.status_code == 409 and wrong.json()["error"] == "not_holder"

    back = await client.post(
        "/api/interventions/iv-1/handback",
        json={"operator_id": "alice", "outcome": "resume", "note": "closed notice"},
    )
    assert back.status_code == 200
    assert back.json()["resolution"]["outcome"] == "resume"
    assert back.json()["lease"]["holder"] == "nobody"

    again = await client.post(
        "/api/interventions/iv-1/handback", json={"operator_id": "alice", "outcome": "resume"}
    )
    assert again.status_code == 409 and again.json()["error"] == "already_resolved"
    late_take = await client.post("/api/interventions/iv-1/take", json={"operator_id": "alice"})
    assert late_take.status_code == 409


async def test_handback_rejects_invalid_outcome(
    console: tuple[Console, httpx.AsyncClient],
) -> None:
    setup, client = console
    open_intervention(setup)
    response = await client.post(
        "/api/interventions/iv-1/handback", json={"operator_id": "alice", "outcome": "retry"}
    )
    assert response.status_code == 422


async def test_handback_refused_while_automation_holds(
    console: tuple[Console, httpx.AsyncClient],
) -> None:
    setup, client = console
    setup.board.open(make_intervention_request())
    setup.lease.grant_automation(RUN)
    response = await client.post(
        "/api/interventions/iv-1/handback", json={"operator_id": "alice", "outcome": "abort"}
    )
    assert response.status_code == 409 and response.json()["error"] == "held_by_automation"


async def test_session_lease_endpoint(console: tuple[Console, httpx.AsyncClient]) -> None:
    setup, client = console
    open_intervention(setup)
    payload = (await client.get("/api/sessions/session-1/lease")).json()
    assert payload["lease"]["holder"] == "nobody"
    assert [t["to_holder"] for t in payload["audit"]] == ["automation", "nobody"]
    assert (await client.get("/api/sessions/unknown/lease")).status_code == 404


async def test_abort_decision_without_taking_control_ends_escalation(
    console: tuple[Console, httpx.AsyncClient],
) -> None:
    setup, client = console
    setup.lease.grant_automation(RUN)
    escalator = ConsoleEscalator(
        setup.board, setup.lease, setup.evidence, "http://console.test", timeout_s=5
    )
    escalation = asyncio.create_task(escalator.escalate(make_intervention_request()))
    while not setup.board.list_open():
        await asyncio.sleep(0.005)

    response = await client.post(
        "/api/interventions/iv-1/handback",
        json={"operator_id": "alice", "outcome": "abort", "note": "member must visit branch"},
    )
    resolution = await escalation

    assert response.status_code == 200
    assert resolution.outcome == "abort" and resolution.operator_id == "alice"
    assert resolution.note == "member must visit branch"
    assert setup.lease.current().holder == "nobody"
    assert (await client.get("/api/interventions")).json() == {"interventions": []}
