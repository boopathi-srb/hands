"""Screenshot masking: black out the on-screen bounds of sensitive accessibility nodes.

Known limit: masking can only cover what the accessibility tree describes. Pixels that carry sensitive data
but have no node (canvas drawings, images of text, content in frames the surface could not read, content that
changed between the snapshot and the screenshot) cannot be detected and are NOT masked.

Failure mode is closed: if the PNG cannot be decoded or re-encoded, a solid black placeholder is returned
instead of the original bytes.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw

from hands.core.log import get_logger, log_failure
from hands.core.observation import Rect

_logger = get_logger(__name__)
PLACEHOLDER_SIZE = (16, 16)
DEFAULT_PADDING_PX = 2


@dataclass(frozen=True)
class PixelBox:
    """Inclusive pixel box: left, top, right, bottom."""

    left: int
    top: int
    right: int
    bottom: int


def rect_contains(outer: Rect, inner: Rect) -> bool:
    return (
        outer.x <= inner.x
        and outer.y <= inner.y
        and outer.x + outer.width >= inner.x + inner.width
        and outer.y + outer.height >= inner.y + inner.height
    )


def innermost_rects(rects: list[Rect]) -> list[Rect]:
    """Drop any rect that strictly contains another one, so a sensitive cell masks the cell, not its page."""
    unique_rects = list(dict.fromkeys(rects))
    return [
        rect
        for rect in unique_rects
        if not any(other != rect and rect_contains(rect, other) for other in unique_rects)
    ]


def pixel_box(
    rect: Rect, scale: float, padding: int, image_size: tuple[int, int]
) -> PixelBox | None:
    """Convert a CSS-pixel rect to a clamped, padded pixel box; None if empty or fully off-image."""
    image_width, image_height = image_size
    left = max(0, math.floor(rect.x * scale) - padding)
    top = max(0, math.floor(rect.y * scale) - padding)
    right = min(image_width - 1, math.ceil((rect.x + rect.width) * scale) - 1 + padding)
    bottom = min(image_height - 1, math.ceil((rect.y + rect.height) * scale) - 1 + padding)
    if rect.width <= 0 or rect.height <= 0 or left > right or top > bottom:
        return None
    return PixelBox(left=left, top=top, right=right, bottom=bottom)


def black_out(
    png: bytes, rects: list[Rect], scale: float = 1.0, padding: int = DEFAULT_PADDING_PX
) -> bytes:
    """Return a PNG with every rect filled black. Unchanged bytes when there is nothing to mask."""
    if not rects:
        return png
    image = _decode_png(png)
    if image is None:
        return failsafe_placeholder_png()
    boxes = [pixel_box(rect, scale, padding, image.size) for rect in innermost_rects(rects)]
    drawer = ImageDraw.Draw(image)
    for box in boxes:
        if box is not None:
            drawer.rectangle((box.left, box.top, box.right, box.bottom), fill="black")
    return _encode_png(image)


@lru_cache(maxsize=1)
def failsafe_placeholder_png() -> bytes:
    """A solid black PNG written in place of a screenshot that could not be masked."""
    return _encode_png(Image.new("RGB", PLACEHOLDER_SIZE, "black"))


def _decode_png(png: bytes) -> Image.Image | None:
    try:
        with Image.open(io.BytesIO(png)) as opened:
            opened.load()
            decoded = opened.copy()
    except (OSError, ValueError, Image.DecompressionBombError) as decode_error:
        log_failure(
            _logger, "black_out", f"cannot decode screenshot: {decode_error}", png_bytes=len(png)
        )
        return None
    return decoded if decoded.mode in ("RGB", "RGBA", "L") else decoded.convert("RGBA")


def _encode_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
