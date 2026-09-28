"""Evidence helper: launch/attach to a native app, observe once, write the Observation as JSON.

Used to show that a native app yields the SAME Observation model as the browser surface. The
screenshot (never part of the JSON) is written next to it with a .png suffix.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from hands.core.log import get_logger, log_failure
from hands.core.observation import Observation
from hands.surfaces.desktop_macos.surface import PERMISSION_HELP, MacDesktopSurface

logger = get_logger(__name__)

ObserveStatus = Literal["ok", "permission_missing", "launch_failed", "write_failed"]

SCREENSHOT_MISSING_NOTE = "No screenshot: grant Screen Recording to the terminal app (System Settings > Privacy & Security)."


class ObserveOutcome(BaseModel):
    status: ObserveStatus
    bundle_id: str
    message: str
    observation_path: str | None = None
    screenshot_path: str | None = None
    node_count: int = 0
    dialog_count: int = 0
    window_title: str = ""
    fingerprint: str | None = None
    launched_by_us: bool = False


def screenshot_path_for(observation_path: Path) -> Path:
    return observation_path.with_suffix(".png")


def write_observation(observation: Observation, observation_path: Path) -> str | None:
    """Write Observation JSON (+ PNG if present). Returns the screenshot path, or None when absent."""
    observation_path.parent.mkdir(parents=True, exist_ok=True)
    observation_path.write_text(observation.model_dump_json(indent=2), encoding="utf-8")
    if observation.screenshot_png is None:
        return None
    screenshot_path = screenshot_path_for(observation_path)
    screenshot_path.write_bytes(observation.screenshot_png)
    return str(screenshot_path)


def _success_outcome(
    bundle_id: str,
    observation: Observation,
    observation_path: Path,
    screenshot_path: str | None,
    launched: bool,
) -> ObserveOutcome:
    message = f"observed {len(observation.nodes)} nodes"
    if screenshot_path is None:
        message = f"{message}. {SCREENSHOT_MISSING_NOTE}"
    return ObserveOutcome(
        status="ok",
        bundle_id=bundle_id,
        message=message,
        observation_path=str(observation_path),
        screenshot_path=screenshot_path,
        node_count=len(observation.nodes),
        dialog_count=len(observation.dialogs),
        window_title=observation.location.title,
        fingerprint=observation.fingerprint,
        launched_by_us=launched,
    )


async def observe_app(
    bundle_id: str,
    out_path: str,
    surface: MacDesktopSurface | None = None,
    quit_if_launched: bool = False,
) -> ObserveOutcome:
    """Launch or attach to `bundle_id`, observe once, write JSON. Missing AX permission is an outcome."""
    active_surface = surface or MacDesktopSurface()
    if not active_surface.permission_granted():
        return ObserveOutcome(
            status="permission_missing", bundle_id=bundle_id, message=PERMISSION_HELP
        )
    launch_result = await active_surface.launch(bundle_id)
    if not launch_result.ok:
        return ObserveOutcome(
            status="launch_failed",
            bundle_id=bundle_id,
            message=launch_result.error or "launch failed",
        )
    observation = await active_surface.observe(include_screenshot=True)
    launched = active_surface.launched_by_surface
    if quit_if_launched and launched:
        quit_result = await active_surface.quit_app()
        if not quit_result.ok:
            log_failure(
                logger, "observe_app", f"quit failed: {quit_result.error}", bundle_id=bundle_id
            )
    await active_surface.close()
    observation_path = Path(out_path)
    try:
        screenshot_path = write_observation(observation, observation_path)
    except OSError as write_error:
        log_failure(
            logger, "observe_app", f"cannot write observation: {write_error}", out_path=out_path
        )
        return ObserveOutcome(status="write_failed", bundle_id=bundle_id, message=str(write_error))
    return _success_outcome(bundle_id, observation, observation_path, screenshot_path, launched)


def observe_app_to_json(
    bundle_id: str, out_path: str, quit_if_launched: bool = False
) -> ObserveOutcome:
    """Synchronous entry point around `observe_app` with the real macOS backends."""
    return asyncio.run(observe_app(bundle_id, out_path, quit_if_launched=quit_if_launched))
