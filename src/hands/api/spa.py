"""Serve the built web UI (`web/dist`) at `/` with single-page-app fallback to index.html.

Paths under /api and /console never fall back: an unknown API path is a JSON 404, not the UI.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response

from hands.api.errors import error_response
from hands.core.log import get_logger

_logger: logging.Logger = get_logger(__name__)

INDEX_FILE = "index.html"
NON_UI_PREFIXES = ("api", "console")


def has_built_ui(dist_dir: Path) -> bool:
    return (dist_dir / INDEX_FILE).is_file()


def is_non_ui_path(path: str) -> bool:
    first_segment = path.lstrip("/").split("/", 1)[0]
    return first_segment in NON_UI_PREFIXES


def ui_file_for(dist_dir: Path, path: str) -> Path:
    """The built file at `path` when it exists inside dist, else index.html (client-side routing)."""
    if path.strip("/"):
        candidate = (dist_dir / path.lstrip("/")).resolve()
        if candidate.is_relative_to(dist_dir.resolve()) and candidate.is_file():
            return candidate
    return dist_dir / INDEX_FILE


def mount_spa(app: FastAPI, dist_dir: Path) -> bool:
    """Register the catch-all UI route (call last). False when there is no built UI."""
    if not has_built_ui(dist_dir):
        _logger.info("no built UI at %s; serving the API only", dist_dir)
        return False

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_route(path: str) -> Response:
        if is_non_ui_path(path):
            return error_response(404, "not_found", f"/{path}")
        return FileResponse(ui_file_for(dist_dir, path))

    _logger.info("serving the built UI from %s", dist_dir)
    return True
