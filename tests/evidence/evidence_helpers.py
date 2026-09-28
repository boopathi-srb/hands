"""Builders shared by the evidence tests (uniquely named module, not conftest, to avoid import clashes)."""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from PIL import Image

from hands.core.observation import Location, Node, Observation, Rect
from hands.evidence import EvidenceRecorder, RecorderReady
from hands.redact import Redactor

START = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def stepping_clock(step_ms: int = 250) -> Callable[[], datetime]:
    """A deterministic clock that advances by step_ms on every call."""
    ticks = iter(range(1_000_000))
    return lambda: START + timedelta(milliseconds=step_ms * next(ticks))


def make_recorder(
    root: Path, redactor: Redactor | None = None, run_id: str = "run-abc"
) -> EvidenceRecorder:
    result = EvidenceRecorder.create(root, run_id, redactor or Redactor(), clock=stepping_clock())
    assert isinstance(result, RecorderReady), result
    return result.recorder


def read_events(recorder: EvidenceRecorder) -> list[dict[str, Any]]:
    lines = (Path(recorder.run_dir) / "events.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def white_png(width: int = 60, height: int = 40) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (255, 255, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def black_pixel_count(png: bytes) -> int:
    with Image.open(io.BytesIO(png)) as image:
        raw = image.convert("L").tobytes()
    return sum(1 for value in raw if value == 0)


def login_observation(password_value: str, screenshot_png: bytes | None = None) -> Observation:
    return Observation(
        observed_at=START,
        location=Location(kind="url", value="http://127.0.0.1:8700/t/lakeside/login"),
        nodes=[
            Node(
                ref="n1",
                role="textbox",
                name="User ID",
                value="teller1",
                bounds=Rect(x=5, y=5, width=20, height=8),
            ),
            Node(
                ref="n2",
                role="textbox",
                name="Password",
                value=password_value,
                bounds=Rect(x=5, y=20, width=20, height=8),
            ),
            Node(
                ref="n3", role="button", name="Sign On", bounds=Rect(x=30, y=20, width=20, height=8)
            ),
        ],
        fingerprint="fp-login",
        screenshot_png=screenshot_png,
    )


def all_bytes_under(directory: Path) -> bytes:
    return b"".join(path.read_bytes() for path in sorted(directory.rglob("*")) if path.is_file())
