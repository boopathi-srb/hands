"""GET /api/health: is the mock app up, which planners can run, which run is active."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import httpx

from hands.core.log import get_logger, log_failure

_logger: logging.Logger = get_logger(__name__)

PROBE_TIMEOUT_S = 1.0
MOCK_APP_HEALTH_PATH = "/t/lakeside/_health"
OLLAMA_VERSION_PATH = "/api/version"
UNKNOWN_VERSION = "0.0.0+unknown"


@dataclass(frozen=True)
class HealthProbe:
    """HTTP reachability checks. `transport` lets tests answer without a network."""

    transport: httpx.AsyncBaseTransport | None = None
    timeout_s: float = PROBE_TIMEOUT_S

    async def reachable(self, url: str) -> bool:
        """True when GET url answers with a non-5xx status within the timeout."""
        try:  # network I/O boundary
            async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout_s) as client:
                response = await client.get(url)
        except httpx.HTTPError as http_error:
            log_failure(_logger, "HealthProbe.reachable", repr(http_error), url=url)
            return False
        return response.status_code < 500


def package_version() -> str:
    try:  # installed-metadata lookup boundary
        return version("hands")
    except PackageNotFoundError as missing:
        log_failure(_logger, "package_version", repr(missing))
        return UNKNOWN_VERSION


async def health_report(
    probe: HealthProbe, target_url: str, ollama_url: str, *, auth_required: bool,
    anthropic_key_present: bool, active_run_id: str | None,
) -> dict[str, Any]:
    mock_app_up = await probe.reachable(f"{target_url}{MOCK_APP_HEALTH_PATH}")
    ollama_up = await probe.reachable(f"{ollama_url}{OLLAMA_VERSION_PATH}")
    return {
        "status": "ok",
        "auth_required": auth_required,
        "mock_app": "up" if mock_app_up else "down",
        "planners": {"anthropic": anthropic_key_present, "ollama": ollama_up, "scripted": True},
        "active_run": active_run_id,
        "version": package_version(),
    }
