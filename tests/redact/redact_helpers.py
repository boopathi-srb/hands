"""Builders shared by the redaction tests (uniquely named module, not conftest, to avoid import clashes)."""

from __future__ import annotations

import io
from datetime import UTC, datetime

from PIL import Image

from hands.core.observation import Dialog, Location, Node, Observation, Rect

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)


def white_png(width: int = 100, height: int = 80) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), WHITE).save(buffer, format="PNG")
    return buffer.getvalue()


def pixels(png: bytes) -> list[list[tuple[int, int, int]]]:
    with Image.open(io.BytesIO(png)) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        raw = rgb.tobytes()
    flat = [(raw[index], raw[index + 1], raw[index + 2]) for index in range(0, len(raw), 3)]
    return [flat[row * width : (row + 1) * width] for row in range(height)]


def observation_with(
    nodes: list[Node],
    dialogs: list[Dialog] | None = None,
    location: Location | None = None,
    screenshot_png: bytes | None = None,
) -> Observation:
    return Observation(
        observed_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        location=location or Location(kind="url", value="http://127.0.0.1:8700/t/lakeside/inquiry"),
        nodes=nodes,
        dialogs=dialogs or [],
        fingerprint="fp-abc",
        screenshot_png=screenshot_png,
    )


def node(
    ref: str,
    role: str = "cell",
    name: str = "",
    text: str = "",
    value: str | None = None,
    label: str | None = None,
    bounds: Rect | None = None,
) -> Node:
    return Node(ref=ref, role=role, name=name, text=text, value=value, label=label, bounds=bounds)
