from __future__ import annotations

import io

from PIL import Image
from redact_helpers import BLACK, WHITE, node, observation_with, pixels, white_png

from hands.core.observation import Rect
from hands.redact import Redactor
from hands.redact.screenshot import (
    PixelBox,
    black_out,
    failsafe_placeholder_png,
    innermost_rects,
    pixel_box,
    rect_contains,
)


def _black_coordinates(png: bytes) -> set[tuple[int, int]]:
    return {
        (x, y) for y, row in enumerate(pixels(png)) for x, color in enumerate(row) if color == BLACK
    }


def _box_coordinates(left: int, top: int, right: int, bottom: int) -> set[tuple[int, int]]:
    return {(x, y) for x in range(left, right + 1) for y in range(top, bottom + 1)}


# ---------------------------------------------------------------- geometry


def test_pixel_box_scale_padding_and_clamping() -> None:
    rect = Rect(x=10, y=20, width=5, height=4)
    assert pixel_box(rect, 1.0, 0, (100, 100)) == PixelBox(10, 20, 14, 23)
    assert pixel_box(rect, 2.0, 0, (100, 100)) == PixelBox(20, 40, 29, 47)
    assert pixel_box(rect, 1.0, 2, (100, 100)) == PixelBox(8, 18, 16, 25)
    assert pixel_box(Rect(x=-5, y=-5, width=10, height=10), 1.0, 0, (100, 100)) == PixelBox(
        0, 0, 4, 4
    )
    assert pixel_box(Rect(x=95, y=95, width=10, height=10), 1.0, 0, (100, 100)) == PixelBox(
        95, 95, 99, 99
    )


def test_pixel_box_empty_or_offscreen_is_none() -> None:
    assert pixel_box(Rect(x=1, y=1, width=0, height=5), 1.0, 0, (10, 10)) is None
    assert pixel_box(Rect(x=50, y=50, width=5, height=5), 1.0, 0, (10, 10)) is None


def test_rect_contains() -> None:
    outer = Rect(x=0, y=0, width=10, height=10)
    assert rect_contains(outer, Rect(x=2, y=2, width=3, height=3))
    assert rect_contains(outer, outer)
    assert not rect_contains(Rect(x=2, y=2, width=3, height=3), outer)


def test_innermost_rects_drops_containers_and_duplicates() -> None:
    row = Rect(x=0, y=0, width=100, height=20)
    cell = Rect(x=10, y=2, width=30, height=16)
    other = Rect(x=0, y=40, width=10, height=10)
    assert innermost_rects([row, cell, cell, other]) == [cell, other]
    assert innermost_rects([]) == []


# ---------------------------------------------------------------- black_out


def test_black_out_without_rects_returns_the_same_bytes() -> None:
    png = white_png()
    assert black_out(png, []) is png


def test_black_out_changes_exactly_the_masked_region() -> None:
    masked = black_out(white_png(), [Rect(x=10, y=10, width=20, height=10)], padding=0)
    assert _black_coordinates(masked) == _box_coordinates(10, 10, 29, 19)
    assert pixels(masked)[0][0] == WHITE


def test_black_out_default_padding_and_scale() -> None:
    masked = black_out(white_png(200, 160), [Rect(x=10, y=10, width=5, height=5)], scale=2.0)
    assert _black_coordinates(masked) == _box_coordinates(18, 18, 31, 31)


def test_black_out_undecodable_png_fails_closed(caplog) -> None:  # type: ignore[no-untyped-def]
    result = black_out(b"not a png", [Rect(x=0, y=0, width=1, height=1)])
    assert result == failsafe_placeholder_png()
    assert "cannot decode screenshot" in caplog.text


def test_failsafe_placeholder_is_a_black_png() -> None:
    placeholder = failsafe_placeholder_png()
    with Image.open(io.BytesIO(placeholder)) as image:
        assert image.format == "PNG"
    assert all(color == BLACK for row in pixels(placeholder) for color in row)


def test_black_out_handles_palette_images() -> None:
    buffer = io.BytesIO()
    Image.new("P", (20, 20), 0).save(buffer, format="PNG")
    masked = black_out(buffer.getvalue(), [Rect(x=0, y=0, width=5, height=5)], padding=0)
    assert (0, 0) in _black_coordinates(masked)


def test_black_out_is_deterministic() -> None:
    rects = [Rect(x=3, y=3, width=7, height=7)]
    assert black_out(white_png(), rects) == black_out(white_png(), rects)


# ---------------------------------------------------------------- Redactor.mask_screenshot


def test_mask_screenshot_masks_password_and_redacted_nodes_only() -> None:
    redactor = Redactor()
    redactor.register_secret("s3cret-value", "input.answer")
    observation = observation_with(
        [
            node("n1", role="textbox", name="Password", bounds=Rect(x=5, y=5, width=10, height=5)),
            node("n2", text="answer s3cret-value", bounds=Rect(x=50, y=5, width=10, height=5)),
            node("n3", text="SSN 123-45-6789", bounds=Rect(x=5, y=40, width=10, height=5)),
            node("n4", text="Regular Savings", bounds=Rect(x=50, y=40, width=10, height=5)),
        ]
    )
    masked = redactor.mask_screenshot(white_png(), observation, padding=0)
    expected = (
        _box_coordinates(5, 5, 14, 9)
        | _box_coordinates(50, 5, 59, 9)
        | _box_coordinates(5, 40, 14, 44)
    )
    assert _black_coordinates(masked) == expected


def test_mask_screenshot_masks_the_cell_not_the_whole_row() -> None:
    observation = observation_with(
        [
            node(
                "row",
                role="row",
                text="Avery 123-45-6789",
                bounds=Rect(x=0, y=0, width=100, height=20),
            ),
            node(
                "cell", role="cell", text="123-45-6789", bounds=Rect(x=40, y=2, width=20, height=16)
            ),
        ]
    )
    masked = Redactor().mask_screenshot(white_png(), observation, padding=0)
    assert _black_coordinates(masked) == _box_coordinates(40, 2, 59, 17)


def test_mask_screenshot_with_nothing_sensitive_is_unchanged() -> None:
    png = white_png()
    observation = observation_with(
        [node("n1", text="Search", bounds=Rect(x=0, y=0, width=5, height=5))]
    )
    assert Redactor().mask_screenshot(png, observation) == png
