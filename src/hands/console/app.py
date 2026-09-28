"""Operator console: FastAPI app served in the SAME process and event loop as the run.

Why in-process: taking control means driving the live Surface object automation was using (its
Playwright page / AX session / LiveViewTransport). Those objects are not serializable and belong to the
run's event loop, so the console must share both; a separate console process would have to open a
fresh session, which is exactly what the handoff must not do. The InterventionBoard and LeaseManager are
plain asyncio objects for the same reason.

Endpoints
- GET  /                                         operator page (static/operator.html)
- GET  /api/interventions                        open interventions with current lease
- GET  /api/interventions/{id}                   context: request, lease, screenshot data URL, actions
- POST /api/interventions/{id}/take              {operator_id} -> lease to human
- POST /api/interventions/{id}/handback          {operator_id, outcome, note} -> resolve
- GET  /api/sessions/{session_id}/lease          current lease and audit trail
- WS   /api/sessions/{session_id}/live?operator_id=...   frames out, pointer/key in (see live.py)

No authentication: the server binds 127.0.0.1 only and operator ids are self-declared. That is a
stated limit of this minimal console, not a design goal.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from hands.console.context import intervention_context, intervention_summary, lease_view
from hands.console.live import register_live_route
from hands.console.state import ConsoleState
from hands.core.log import get_logger, log_failure
from hands.core.ports import EvidenceSink, Surface
from hands.session.board import (
    BoardRefused,
    InterventionBoard,
    InterventionRecord,
    ResolutionOutcome,
)
from hands.session.lease import LeaseManager, LeaseRefused

_logger: logging.Logger = get_logger(__name__)

OPERATOR_PAGE_PATH = Path(__file__).parent / "static" / "operator.html"


@dataclass(frozen=True)
class _InterventionHandle:
    record: InterventionRecord
    lease: LeaseManager


class TakeControlBody(BaseModel):
    operator_id: str = Field(min_length=1, max_length=128)


class HandBackBody(BaseModel):
    operator_id: str = Field(min_length=1, max_length=128)
    outcome: ResolutionOutcome
    note: str = Field(default="", max_length=2000)


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": code, "message": message})


def load_operator_page(path: Path = OPERATOR_PAGE_PATH) -> str:
    """The operator page HTML; a minimal error page if the file cannot be read (logged)."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:  # file I/O boundary
        log_failure(_logger, "load_operator_page", repr(error), path=str(path))
        return "<!doctype html><title>hands console</title><p>operator page missing</p>"


def find_intervention(
    state: ConsoleState, intervention_id: str
) -> _InterventionHandle | JSONResponse:
    """The intervention and its session's lease, or a 404 response."""
    record = state.board.get(intervention_id)
    if record is None:
        return error_response(404, "unknown_intervention", intervention_id)
    lease = state.leases.get(record.request.session_id)
    if lease is None:
        return error_response(404, "unknown_session", record.request.session_id)
    return _InterventionHandle(record=record, lease=lease)


def take_control(state: ConsoleState, intervention_id: str, body: TakeControlBody) -> JSONResponse:
    found = find_intervention(state, intervention_id)
    if isinstance(found, JSONResponse):
        return found
    if found.record.status != "open":
        return error_response(409, "already_resolved", intervention_id)
    taken = found.lease.take_human(body.operator_id, reason=f"took control for {intervention_id}")
    if isinstance(taken, LeaseRefused):
        return error_response(409, taken.code, taken.message)
    session_id = found.record.request.session_id
    return JSONResponse(
        {"lease": lease_view(found.lease), "live_path": f"/api/sessions/{session_id}/live"}
    )


def hand_back(state: ConsoleState, intervention_id: str, body: HandBackBody) -> JSONResponse:
    """Hand the session back and resolve. With nobody holding control this is a decision only
    (e.g. approve a risky step or abort without touching the app)."""
    found = find_intervention(state, intervention_id)
    if isinstance(found, JSONResponse):
        return found
    if found.record.status != "open":
        return error_response(409, "already_resolved", intervention_id)
    lease_refusal = _return_lease(found.lease, body.operator_id, intervention_id)
    if lease_refusal is not None:
        return lease_refusal
    resolved = state.board.resolve_from_operator(
        intervention_id, body.outcome, body.operator_id, body.note
    )
    if isinstance(resolved, BoardRefused):
        return error_response(409, resolved.code, resolved.message)
    resolution = resolved.record.resolution
    return JSONResponse(
        {
            "resolution": None if resolution is None else resolution.model_dump(mode="json"),
            "lease": lease_view(found.lease),
        }
    )


def _return_lease(
    lease: LeaseManager, operator_id: str, intervention_id: str
) -> JSONResponse | None:
    holder = lease.current().holder
    if holder == "automation":
        return error_response(409, "held_by_automation", "automation holds control")
    if holder == "nobody":
        return None
    returned = lease.hand_back(operator_id, reason=f"handed back {intervention_id}")
    if isinstance(returned, LeaseRefused):
        return error_response(409, returned.code, returned.message)
    return None


def list_interventions(state: ConsoleState) -> dict[str, Any]:
    summaries = [
        intervention_summary(request, state.leases.get(request.session_id))
        for request in state.board.list_open()
    ]
    return {"interventions": summaries}


def get_intervention(state: ConsoleState, intervention_id: str) -> JSONResponse:
    found = find_intervention(state, intervention_id)
    if isinstance(found, JSONResponse):
        return found
    evidence = state.evidence.get(found.record.request.session_id)
    return JSONResponse(intervention_context(found.record, found.lease, evidence))


def get_session_lease(state: ConsoleState, session_id: str) -> JSONResponse:
    lease = state.leases.get(session_id)
    if lease is None:
        return error_response(404, "unknown_session", session_id)
    audit = [transition.model_dump(mode="json") for transition in lease.audit_trail()]
    return JSONResponse({"lease": lease_view(lease), "audit": audit})


def create_console_app(
    board: InterventionBoard,
    leases: Mapping[str, LeaseManager],
    surfaces_by_session: Mapping[str, Surface],
    evidence_by_session: Mapping[str, EvidenceSink],
) -> FastAPI:
    """Build the console. Mappings are read live, so sessions added later are visible."""
    state = ConsoleState(
        board=board, leases=leases, surfaces=surfaces_by_session, evidence=evidence_by_session
    )
    app = FastAPI(title="hands operator console", docs_url=None, redoc_url=None)
    app.state.console = state
    _register_http_routes(app, state, load_operator_page())
    register_live_route(app, state)
    return app


def _register_http_routes(app: FastAPI, state: ConsoleState, operator_page: str) -> None:
    @app.get("/", response_class=HTMLResponse)
    async def operator_page_route() -> HTMLResponse:
        return HTMLResponse(operator_page)

    @app.get("/api/interventions")
    async def list_route() -> dict[str, Any]:
        return list_interventions(state)

    @app.get("/api/interventions/{intervention_id}")
    async def context_route(intervention_id: str) -> JSONResponse:
        return get_intervention(state, intervention_id)

    @app.post("/api/interventions/{intervention_id}/take")
    async def take_route(intervention_id: str, body: TakeControlBody) -> JSONResponse:
        return take_control(state, intervention_id, body)

    @app.post("/api/interventions/{intervention_id}/handback")
    async def handback_route(intervention_id: str, body: HandBackBody) -> JSONResponse:
        return hand_back(state, intervention_id, body)

    @app.get("/api/sessions/{session_id}/lease")
    async def lease_route(session_id: str) -> JSONResponse:
        return get_session_lease(state, session_id)
