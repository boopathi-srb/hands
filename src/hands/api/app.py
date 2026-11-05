"""create_api_app: the HTTP API, the shared operator console at /console, and the built UI at /."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hands.api.auth import TokenAuthMiddleware
from hands.api.errors import install_error_handlers
from hands.api.health import HealthProbe
from hands.api.routes import register_api_routes
from hands.api.runs import RunManager, RunRunners
from hands.api.settings import ApiSettings, seed_artifacts
from hands.api.spa import mount_spa
from hands.console.app import create_console_app
from hands.core.log import get_logger, log_failure
from hands.runtime.shared_console import DEFAULT_CONSOLE_BASE_PATH, SharedConsole

_logger: logging.Logger = get_logger(__name__)


@dataclass(frozen=True)
class ApiDependencies:
    """Seams for tests: command runners, the health probe's HTTP transport, a pre-built shared console."""

    runners: RunRunners | None = None
    probe: HealthProbe | None = None
    shared_console: SharedConsole | None = None


def create_api_app(settings: ApiSettings | None = None, dependencies: ApiDependencies | None = None) -> FastAPI:
    resolved_settings = settings or ApiSettings.from_env()
    resolved_dependencies = dependencies or ApiDependencies()
    _seed_data_dir(resolved_settings)
    shared_console = resolved_dependencies.shared_console or SharedConsole(public_base_path=DEFAULT_CONSOLE_BASE_PATH)
    runs = RunManager(resolved_settings, shared_console, resolved_dependencies.runners)
    app = FastAPI(title="hands API", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None,
                  lifespan=_lifespan(runs))
    app.state.settings = resolved_settings
    app.state.runs = runs
    app.state.shared_console = shared_console
    install_error_handlers(app)
    register_api_routes(app, resolved_settings, runs, resolved_dependencies.probe or HealthProbe())
    app.mount(DEFAULT_CONSOLE_BASE_PATH, _console_app(shared_console))
    mount_spa(app, resolved_settings.web_dist_dir)
    _add_middleware(app, resolved_settings)
    return app


def _seed_data_dir(settings: ApiSettings) -> None:
    seeded = seed_artifacts(settings.seed_artifacts_dir, settings.artifacts_dir)
    if seeded.status == "failed":
        log_failure(_logger, "create_api_app", f"artifact seeding failed: {seeded.message}",
                    artifacts_dir=str(settings.artifacts_dir))


def _console_app(shared_console: SharedConsole) -> FastAPI:
    return create_console_app(shared_console.board, shared_console.leases, shared_console.surfaces,
                              shared_console.evidence)


def _add_middleware(app: FastAPI, settings: ApiSettings) -> None:
    """Auth inside, CORS outermost, so preflights and 401s both carry CORS headers."""
    if settings.api_token:
        app.add_middleware(TokenAuthMiddleware, token=settings.api_token)
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
                           allow_methods=["*"], allow_headers=["*"])


def _lifespan(runs: RunManager) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Cancel an active run on shutdown so its browser closes and its record ends as `error`."""
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await runs.shutdown()

    return lifespan
