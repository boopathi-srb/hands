from __future__ import annotations

import io

from PIL import Image

from hands.core.observation import Dialog
from hands.discovery.render import (
    SECRET_MASK,
    downscale_screenshot,
    is_password_field,
    mask_screenshot,
    mask_secrets,
    render_node_line,
    render_observation,
    scrub_observation,
    sensitive_nodes,
)

from .helpers import make_node, make_observation, png_bytes

SECRET = "hunter2-secret"


def test_mask_secrets_longest_first_and_empty_inputs() -> None:
    assert mask_secrets("user abc and abcdef", ["abc", "abcdef"]) == f"user {SECRET_MASK} and {SECRET_MASK}"
    assert mask_secrets("", ["x"]) == ""
    assert mask_secrets("keep", []) == "keep"
    assert mask_secrets("keep", [""]) == "keep"


def test_password_fields_are_detected() -> None:
    assert is_password_field(make_node("n1", "textbox", label="Password", value="x"))
    assert is_password_field(make_node("n1", "textbox", label="PIN"))
    assert is_password_field(make_node("n1", "textbox", label="Other", value="•••"))
    assert not is_password_field(make_node("n1", "textbox", label="User ID", value="bob"))
    assert not is_password_field(make_node("n1", "button", "Password reset"))


def test_rendering_masks_secrets_everywhere() -> None:
    observation = make_observation(
        [
            make_node("n1", "text", f"Signed on as {SECRET}"),
            make_node("n2", "textbox", label="User ID", value=SECRET, text=""),
            make_node("n3", "textbox", label="Password", value="plain-typed", text=""),
            make_node("n4", "textbox", label="Password 2", value="", text=""),
        ],
        url=f"http://app.test/p?token={SECRET}",
        dialogs=[Dialog(title="Hello", text=f"welcome {SECRET}")],
    )
    rendered = render_observation(observation, secret_values=[SECRET])
    assert SECRET not in rendered.text
    assert "plain-typed" not in rendered.text
    assert f'[n3] textbox "Password" value="{SECRET_MASK}"' in rendered.text
    assert '[n4] textbox "Password 2" value=""' in rendered.text
    assert f"Signed on as {SECRET_MASK}" in rendered.text


def test_scrub_observation_keeps_structure_and_screenshot() -> None:
    observation = make_observation([make_node("n1", "text", SECRET)], screenshot=b"png")
    scrubbed = scrub_observation(observation, [SECRET])
    assert scrubbed.nodes[0].name == SECRET_MASK
    assert scrubbed.fingerprint == observation.fingerprint
    assert scrubbed.screenshot_png == b"png"


def test_dialogs_first_and_grouped_by_container() -> None:
    observation = make_observation(
        [
            make_node("n1", "link", "Home", container=("frame:nav",)),
            make_node("n2", "text", "Detail", container=("frame:content",)),
            make_node("d1", "dialog", "Verify Identity", container=("frame:content",), path="dialog[1]"),
            make_node("d2", "button", "Verify", container=("frame:content",), path="dialog[1]/button[1]"),
        ],
        dialogs=[Dialog(title="Verify Identity", text="question?")],
    )
    lines = render_observation(observation).text.splitlines()
    assert lines[1] == 'OPEN DIALOG "Verify Identity": question?'
    assert lines[2] == "-- dialog --"
    assert lines[3:5] == ['[d1] dialog "Verify Identity"', '[d2] button "Verify"']
    assert lines.index("-- frame:nav --") < lines.index("-- frame:content --")


def test_native_alert_line_and_page_group() -> None:
    observation = make_observation([make_node("n1", "button", "OK", container=())],
                                   dialogs=[Dialog(title="alert", text="Printer offline", native=True)])
    text = render_observation(observation).text
    assert 'OPEN NATIVE ALERT "alert": Printer offline' in text
    assert "-- page --" in text


def test_limit_keeps_interactive_before_text_and_reports_omitted() -> None:
    nodes = [make_node(f"t{index}", "cell", f"value {index}") for index in range(5)]
    nodes += [make_node("b1", "button", "Go"), make_node("h1", "button", "Hidden", box=(0, 0, 0, 0))]
    rendered = render_observation(make_observation(nodes), max_nodes=3)
    assert rendered.shown_refs == ["t0", "t1", "b1"]
    assert rendered.omitted_count == 4
    assert rendered.text.endswith("(4 more elements not shown)")


def test_containers_without_text_are_skipped_and_empty_observation_renders() -> None:
    observation = make_observation([make_node("n1", "table", ""), make_node("n2", "row", ""),
                                    make_node("n3", "cell", "")])
    rendered = render_observation(observation)
    assert rendered.shown_refs == []
    assert rendered.text.startswith("LOCATION: ")
    assert render_observation(make_observation([]), max_nodes=0).omitted_count == 0


def test_node_line_flags_and_truncation() -> None:
    node = make_node("n9", "button", "x" * 120, enabled=False)
    line = render_node_line(node.model_copy(update={"focused": True}))
    assert line.endswith("(disabled) (focused)")
    assert "…" in line
    labelled = make_node("n1", "textbox", "Search", label="Find member", value="abc", text="")
    assert render_node_line(labelled) == '[n1] textbox "Search" label="Find member" value="abc"'


def _image_size(png: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(png)) as image:
        return image.size


def test_downscale_wide_screenshot_to_max_width() -> None:
    resized = downscale_screenshot(png_bytes(2048, 1000))
    assert resized is not None and _image_size(resized) == (1024, 500)


def test_downscale_keeps_small_screenshot_size() -> None:
    resized = downscale_screenshot(png_bytes(800, 600))
    assert resized is not None and _image_size(resized) == (800, 600)


def test_downscale_edge_cases() -> None:
    assert downscale_screenshot(None) is None
    assert downscale_screenshot(b"") is None
    assert downscale_screenshot(b"not a png") is None
    assert downscale_screenshot(png_bytes(10, 10), max_width=0) is None


def test_mask_screenshot_blacks_out_sensitive_nodes() -> None:
    node = make_node("n1", "text", f"Signed on as {SECRET}", box=(10, 10, 40, 20))
    observation = make_observation([node, make_node("n2", "text", "safe", box=(60, 60, 10, 10))])
    masked = mask_screenshot(png_bytes(100, 100), observation, [SECRET])
    assert masked is not None
    with Image.open(io.BytesIO(masked)) as image:
        assert image.getpixel((20, 20)) == (0, 0, 0)
        assert image.getpixel((90, 90)) == (255, 255, 255)
    assert sensitive_nodes(observation, [SECRET]) == [node]


def test_mask_screenshot_edge_cases() -> None:
    observation = make_observation([make_node("n1", "text", "nothing secret")])
    original = png_bytes(20, 20)
    assert mask_screenshot(original, observation, [SECRET]) == original
    assert mask_screenshot(None, observation, [SECRET]) is None
    secret_observation = make_observation([make_node("n1", "text", SECRET)])
    assert mask_screenshot(b"garbage", secret_observation, [SECRET]) is None
