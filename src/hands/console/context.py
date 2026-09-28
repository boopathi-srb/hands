"""Operator-facing views of interventions: summaries, full context, and screenshots as data URLs."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from hands.core.control import InterventionRequest
from hands.core.log import get_logger, log_failure
from hands.core.ports import EvidenceSink
from hands.session.board import InterventionRecord
from hands.session.lease import LeaseManager

_logger: logging.Logger = get_logger(__name__)

JPEG_SIGNATURE = b"\xff\xd8"
PNG_SIGNATURE = b"\x89PNG"


def image_mime(image: bytes) -> str:
    """MIME type from magic bytes; PNG is assumed when unrecognized."""
    if image.startswith(JPEG_SIGNATURE):
        return "image/jpeg"
    return "image/png"


def to_data_url(image: bytes) -> str:
    return f"data:{image_mime(image)};base64,{base64.b64encode(image).decode('ascii')}"


def resolve_screenshot_path(screenshot_path: str, evidence: EvidenceSink | None) -> Path:
    """Absolute paths are used as-is; relative ones are resolved against the run's evidence dir."""
    path = Path(screenshot_path)
    if path.is_absolute() or evidence is None:
        return path
    return Path(evidence.run_dir) / path


def load_screenshot_data_url(
    screenshot_path: str | None, evidence: EvidenceSink | None
) -> str | None:
    """The screenshot as a data URL, or None when absent or unreadable (logged)."""
    if not screenshot_path:
        return None
    path = resolve_screenshot_path(screenshot_path, evidence)
    try:
        image = path.read_bytes()
    except OSError as error:  # file I/O boundary
        log_failure(_logger, "load_screenshot_data_url", repr(error), screenshot_path=str(path))
        return None
    return to_data_url(image)


def lease_view(lease: LeaseManager | None) -> dict[str, Any] | None:
    return None if lease is None else lease.current().model_dump(mode="json")


def intervention_summary(
    request: InterventionRequest, lease: LeaseManager | None
) -> dict[str, Any]:
    """What the operator list shows for one open intervention."""
    return {
        "intervention_id": request.intervention_id,
        "session_id": request.session_id,
        "kind": request.kind,
        "reason": request.reason,
        "capability_id": request.capability_id,
        "created_at": request.created_at.isoformat(),
        "lease": lease_view(lease),
    }


def intervention_context(
    record: InterventionRecord, lease: LeaseManager | None, evidence: EvidenceSink | None
) -> dict[str, Any]:
    """Everything the operator needs to act: request, status, lease, screenshot, actions so far."""
    return {
        "request": record.request.model_dump(mode="json"),
        "status": record.status,
        "lease": lease_view(lease),
        "screenshot_data_url": load_screenshot_data_url(record.request.screenshot_path, evidence),
        "human_actions": [action.model_dump(mode="json") for action in record.human_actions],
        "resolution": None
        if record.resolution is None
        else record.resolution.model_dump(mode="json"),
    }
