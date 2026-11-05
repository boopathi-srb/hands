"""The /api routes of docs/API.md. Handlers stay thin: validate, call one function, shape the response."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, Response

from hands.api.errors import error_response
from hands.api.health import HealthProbe, health_report
from hands.api.models import ApproveBody, DiscoveryStartBody, ReplayStartBody
from hands.api.reference import (
    approve_capability,
    capability_detail,
    capability_list,
    fault_list,
    tenant_list,
)
from hands.api.run_files import media_type_for
from hands.api.runs import RunManager, RunStarted
from hands.api.settings import ApiSettings
from hands.api.validation import ApiError, validate_discovery, validate_replay

MAX_RUN_LIST = 500


def api_error_response(api_error: ApiError) -> JSONResponse:
    return error_response(api_error.status_code, api_error.code, api_error.message, **api_error.extra)


def respond(payload: dict[str, Any] | list[Any] | ApiError, status_code: int = 200) -> JSONResponse:
    if isinstance(payload, ApiError):
        return api_error_response(payload)
    return JSONResponse(payload, status_code=status_code)


def started_response(started: RunStarted | ApiError) -> JSONResponse:
    if isinstance(started, ApiError):
        return api_error_response(started)
    return JSONResponse({"run_id": started.run_id}, status_code=202)


def run_not_found(run_id: str) -> JSONResponse:
    return error_response(404, "unknown_run", f"no run '{run_id}'")


def register_api_routes(app: FastAPI, settings: ApiSettings, runs: RunManager, probe: HealthProbe) -> None:
    router = APIRouter(prefix="/api")
    _reference_routes(router, settings, runs, probe)
    _catalog_routes(router, settings)
    _run_start_routes(router, settings, runs)
    _run_query_routes(router, runs)
    app.include_router(router)


def _reference_routes(router: APIRouter, settings: ApiSettings, runs: RunManager, probe: HealthProbe) -> None:
    @router.get("/health")
    async def health() -> JSONResponse:
        report = await health_report(
            probe, settings.target_url, settings.ollama_url, auth_required=settings.auth_required,
            anthropic_key_present=settings.anthropic_key_present, active_run_id=runs.active_run_id,
        )
        return JSONResponse(report)

    @router.get("/tenants")
    async def tenants() -> JSONResponse:
        return JSONResponse(tenant_list())

    @router.get("/faults")
    async def faults() -> JSONResponse:
        return JSONResponse(fault_list())


def _catalog_routes(router: APIRouter, settings: ApiSettings) -> None:
    @router.get("/capabilities")
    async def capabilities() -> JSONResponse:
        return JSONResponse(capability_list(settings.artifacts_dir))

    @router.get("/capabilities/{capability_id}")
    async def capability(capability_id: str, version: str | None = None) -> JSONResponse:
        return respond(capability_detail(settings.artifacts_dir, capability_id, version))

    @router.post("/capabilities/{capability_id}/approve")
    async def approve(capability_id: str, body: ApproveBody | None = None) -> JSONResponse:
        version = None if body is None else body.version
        return respond(approve_capability(settings.artifacts_dir, capability_id, version))


def _run_start_routes(router: APIRouter, settings: ApiSettings, runs: RunManager) -> None:
    @router.post("/runs/replay")
    async def start_replay(body: ReplayStartBody) -> JSONResponse:
        invalid = validate_replay(body, settings.artifacts_dir)
        if invalid is not None:
            return api_error_response(invalid)
        return started_response(runs.start_replay(body))

    @router.post("/runs/discovery")
    async def start_discovery(body: DiscoveryStartBody) -> JSONResponse:
        invalid = validate_discovery(body, settings.anthropic_key_present)
        if invalid is not None:
            return api_error_response(invalid)
        return started_response(runs.start_discovery(body))


def _run_query_routes(router: APIRouter, runs: RunManager) -> None:
    @router.get("/runs")
    async def list_runs(limit: int = Query(default=50, ge=1, le=MAX_RUN_LIST)) -> JSONResponse:
        return JSONResponse(runs.list_runs(limit))

    @router.get("/runs/{run_id}")
    async def run_detail(run_id: str) -> JSONResponse:
        detail = runs.detail(run_id)
        return run_not_found(run_id) if detail is None else JSONResponse(detail)

    @router.get("/runs/{run_id}/events")
    async def run_events(run_id: str, after: int = Query(default=0, ge=0)) -> JSONResponse:
        page = runs.events(run_id, after)
        return run_not_found(run_id) if page is None else JSONResponse(page)

    @router.get("/runs/{run_id}/files/{file_path:path}")
    async def run_file(run_id: str, file_path: str) -> Response:
        path = runs.file(run_id, file_path)
        if path is None:
            return error_response(404, "file_not_found", f"no servable file '{file_path}' in run '{run_id}'")
        return FileResponse(path, media_type=media_type_for(path))
