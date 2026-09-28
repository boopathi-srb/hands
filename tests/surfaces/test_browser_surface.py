"""BrowserSurface integration tests against a local static site (tests/surfaces/browser_site), headless.

The site has a frameset with nested frames and an iframe inside the content frame, a legacy table form
with adjacent-cell labels, a select, JS alert/confirm, a positioned-table modal, and a role=dialog.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from hands.core.actions import (
    ClickAction,
    NodeRef,
    OpenAction,
    Point,
    PressAction,
    ScrollAction,
    SelectAction,
    TypeAction,
)
from hands.core.observation import Node, Observation
from hands.core.ports import KeyEvent, PointerEvent
from hands.surfaces.browser import BrowserSurface

pytestmark = pytest.mark.browser

INNER = ("frame:content", "frame:inner")


# ---------------------------------------------------------------- helpers


def find_node(observation: Observation, role: str, *, name: str | None = None, label: str | None = None,
              text: str | None = None) -> Node:
    matches = [
        node for node in observation.nodes
        if node.role == role
        and (name is None or node.name == name)
        and (label is None or node.label == label)
        and (text is None or node.text == text)
    ]
    assert matches, f"no {role} name={name!r} label={label!r} text={text!r} in {[n.name for n in observation.nodes]}"
    return matches[0]


def visible_texts(observation: Observation) -> list[str]:
    return [node.text for node in observation.nodes if node.text]


async def open_and_observe(surface: BrowserSurface, url: str) -> Observation:
    opened = await surface.act(None, OpenAction(entry_point=url))
    assert opened.ok, opened.error
    return await surface.observe()


async def wait_until(predicate, timeout_s: float = 5.0) -> bool:  # type: ignore[no-untyped-def]
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


# ---------------------------------------------------------------- frames, bounds, labels


async def test_frames_become_container_paths(browser_surface: BrowserSurface, browser_site_url: str) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/index.html")

    containers = {node.container_path for node in observation.nodes}
    assert {("frame:top",), ("frame:nav",), ("frame:content",), INNER} <= containers
    assert find_node(observation, "link", name="Sign Off").container_path == ("frame:top",)
    assert find_node(observation, "link", name="Member Inquiry").container_path == ("frame:nav",)
    assert find_node(observation, "button", name="Search").container_path == INNER
    assert observation.location.kind == "url"
    assert observation.location.value.endswith("/index.html")
    assert observation.location.title == "CoreOne Test Frameset"


async def test_bounds_in_nested_frame_are_page_level(browser_surface: BrowserSurface, browser_site_url: str) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/index.html")
    textbox = find_node(observation, "textbox", label="Member Number")

    inner_frame = browser_surface.playwright_page.frame(name="inner")
    assert inner_frame is not None
    playwright_box = await inner_frame.locator("input[name=member_number]").bounding_box()
    assert playwright_box is not None and textbox.bounds is not None
    assert textbox.bounds.x == pytest.approx(playwright_box["x"], abs=1)
    assert textbox.bounds.y == pytest.approx(playwright_box["y"], abs=1)
    # nav frame (180px) + outer margins (20 + 30) put it well right of the frame origins
    assert textbox.bounds.x > 230


async def test_structural_paths_are_role_indexed(browser_surface: BrowserSurface, browser_site_url: str) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/index.html")

    assert find_node(observation, "cell", name="Member Number").structural_path == "table[1]/row[1]/cell[1]"
    textbox = find_node(observation, "textbox", label="Member Number")
    assert textbox.structural_path == "table[1]/row[1]/cell[2]/textbox[1]"
    assert find_node(observation, "button", name="Confirm").structural_path == "table[1]/row[4]/cell[1]/button[3]"


async def test_labels_from_label_element_and_adjacent_cells(
    browser_surface: BrowserSurface, browser_site_url: str
) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/index.html")

    assert find_node(observation, "textbox", label="Member Number").name == ""
    combobox = find_node(observation, "combobox", label="Share Type")
    assert combobox.value == "Regular Savings"
    nickname = find_node(observation, "textbox", name="Nickname")
    assert nickname.label == "Nickname"


async def test_inline_text_runs_are_merged(browser_surface: BrowserSurface, browser_site_url: str) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/index.html")

    assert "No member found for number 99999." in visible_texts(observation)
    assert "Lakeside Signed on as teller1" in visible_texts(observation)


# ---------------------------------------------------------------- acting


async def test_type_and_click_by_ref_inside_nested_frame(
    browser_surface: BrowserSurface, browser_site_url: str
) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/index.html")
    textbox = find_node(observation, "textbox", label="Member Number")
    search = find_node(observation, "button", name="Search")

    assert (await browser_surface.act(NodeRef(ref=textbox.ref), TypeAction(text="12345"))).ok
    assert (await browser_surface.act(NodeRef(ref=search.ref), ClickAction())).ok

    after = await browser_surface.observe()
    assert "Searched for 12345" in visible_texts(after)
    assert find_node(after, "textbox", label="Member Number").value == "12345"


async def test_type_respects_clear_first(browser_surface: BrowserSurface, browser_site_url: str) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/form.html")
    ref = NodeRef(ref=find_node(observation, "textbox", label="Member Number").ref)

    await browser_surface.act(ref, TypeAction(text="123"))
    await browser_surface.act(ref, TypeAction(text="45", clear_first=False))
    appended = await browser_surface.observe()
    assert find_node(appended, "textbox", label="Member Number").value == "12345"

    ref = NodeRef(ref=find_node(appended, "textbox", label="Member Number").ref)
    await browser_surface.act(ref, TypeAction(text="999"))
    replaced = await browser_surface.observe()
    assert find_node(replaced, "textbox", label="Member Number").value == "999"


async def test_press_enter_on_ref_focuses_it_first(browser_surface: BrowserSurface, browser_site_url: str) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/form.html")
    textbox = find_node(observation, "textbox", label="Member Number")

    assert (await browser_surface.act(NodeRef(ref=textbox.ref), PressAction(key="Enter"))).ok
    assert "Enter pressed" in visible_texts(await browser_surface.observe())


async def test_click_at_point(browser_surface: BrowserSurface, browser_site_url: str) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/form.html")
    search = find_node(observation, "button", name="Search")
    assert search.bounds is not None

    result = await browser_surface.act(Point(x=search.bounds.center_x, y=search.bounds.center_y), ClickAction())

    assert result.ok
    assert "Searched for" in visible_texts(await browser_surface.observe())


async def test_select_by_visible_text_fires_change(browser_surface: BrowserSurface, browser_site_url: str) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/index.html")
    combobox = find_node(observation, "combobox", label="Share Type")

    result = await browser_surface.act(NodeRef(ref=combobox.ref), SelectAction(option="Money Market"))

    assert result.ok, result.error
    after = await browser_surface.observe()
    assert find_node(after, "combobox", label="Share Type").value == "Money Market"
    assert "Selected Money Market" in visible_texts(after)


async def test_select_unknown_option_fails_with_choices(
    browser_surface: BrowserSurface, browser_site_url: str
) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/form.html")
    combobox = find_node(observation, "combobox", label="Share Type")

    result = await browser_surface.act(NodeRef(ref=combobox.ref), SelectAction(option="Gold Bars"))

    assert not result.ok
    assert result.error is not None and "Share Certificate" in result.error


async def test_scroll_moves_content(browser_surface: BrowserSurface, browser_site_url: str) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/tall.html")
    bottom_before = find_node(observation, "text", text="Bottom of page").bounds
    assert bottom_before is not None

    assert (await browser_surface.act(None, ScrollAction(direction="down", amount=10))).ok
    after = await browser_surface.observe()
    bottom_after = find_node(after, "text", text="Bottom of page").bounds

    assert bottom_after is not None and bottom_after.y < bottom_before.y - 500


async def test_unknown_ref_and_act_before_observe_fail_without_raising(
    browser_surface: BrowserSurface, browser_site_url: str
) -> None:
    before_observe = await browser_surface.act(NodeRef(ref="n1"), ClickAction())
    assert not before_observe.ok and "observe" in (before_observe.error or "")

    await open_and_observe(browser_surface, f"{browser_site_url}/form.html")
    unknown = await browser_surface.act(NodeRef(ref="n9999"), ClickAction())
    assert not unknown.ok and "unknown ref" in (unknown.error or "")


async def test_open_unreachable_url_fails(browser_surface: BrowserSurface) -> None:
    result = await browser_surface.act(None, OpenAction(entry_point="http://127.0.0.1:1/nothing"))
    assert not result.ok and result.error


# ---------------------------------------------------------------- dialogs


async def test_native_alert_is_held_reported_and_dismissed(
    browser_surface: BrowserSurface, browser_site_url: str
) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/index.html")
    alert_button = find_node(observation, "button", name="Show Alert")

    clicked = await browser_surface.act(NodeRef(ref=alert_button.ref), ClickAction())
    assert clicked.ok, clicked.error

    during = await browser_surface.observe()
    assert [(d.title, d.text, d.native) for d in during.dialogs] == [("alert", "Printer queue offline", True)]
    assert {node.container_path for node in during.nodes} == {("dialog:native",)}
    ok_button = find_node(during, "button", name="OK")
    blocked = await browser_surface.act(NodeRef(ref=find_node(during, "dialog").ref), TypeAction(text="x"))
    assert not blocked.ok and "native" in (blocked.error or "")

    assert (await browser_surface.act(NodeRef(ref=ok_button.ref), ClickAction())).ok
    after = await browser_surface.observe()
    assert after.dialogs == []
    assert find_node(after, "button", name="Search").container_path == INNER


async def test_native_confirm_escape_dismisses_and_ok_accepts(
    browser_surface: BrowserSurface, browser_site_url: str
) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/form.html")
    confirm_ref = NodeRef(ref=find_node(observation, "button", name="Confirm").ref)

    await browser_surface.act(confirm_ref, ClickAction())
    during = await browser_surface.observe()
    assert [node.name for node in during.nodes if node.role == "button"] == ["OK", "Cancel"]
    assert (await browser_surface.act(None, PressAction(key="Escape"))).ok
    dismissed = await browser_surface.observe()
    assert "Confirm: false" in visible_texts(dismissed)

    await browser_surface.act(NodeRef(ref=find_node(dismissed, "button", name="Confirm").ref), ClickAction())
    during_again = await browser_surface.observe()
    await browser_surface.act(NodeRef(ref=find_node(during_again, "button", name="OK").ref), ClickAction())
    assert "Confirm: true" in visible_texts(await browser_surface.observe())


async def test_alert_on_page_load_does_not_hang(browser_surface: BrowserSurface, browser_site_url: str) -> None:
    observation = await asyncio.wait_for(
        open_and_observe(browser_surface, f"{browser_site_url}/alert_on_load.html"), timeout=15
    )
    assert observation.dialogs and observation.dialogs[0].native

    assert (await browser_surface.act(None, PressAction(key="Enter"))).ok
    after = await browser_surface.observe()
    assert after.dialogs == []
    assert "Page after the alert" in visible_texts(after)


async def test_in_page_modals_are_reported(browser_surface: BrowserSurface, browser_site_url: str) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/modal.html")

    titles = [dialog.title for dialog in observation.dialogs]
    assert "System Notice" in titles
    assert "Verify Member Identity" in titles
    assert "Member Number" not in titles  # the table underneath is not an overlay
    notice = next(dialog for dialog in observation.dialogs if dialog.title == "System Notice")
    assert notice.text == "Scheduled maintenance tonight." and not notice.native

    acknowledge = find_node(observation, "button", name="Acknowledge")
    assert (await browser_surface.act(NodeRef(ref=acknowledge.ref), ClickAction())).ok
    after = await browser_surface.observe()
    assert "System Notice" not in [dialog.title for dialog in after.dialogs]


# ---------------------------------------------------------------- observation details


async def test_screenshot_and_fingerprint(browser_surface: BrowserSurface, browser_site_url: str) -> None:
    first = await open_and_observe(browser_surface, f"{browser_site_url}/form.html")
    assert first.screenshot_png is not None and first.screenshot_png.startswith(b"\x89PNG")

    textbox = find_node(first, "textbox", label="Member Number")
    await browser_surface.act(NodeRef(ref=textbox.ref), TypeAction(text="777"))
    without_screenshot = await browser_surface.observe(include_screenshot=False)

    assert without_screenshot.screenshot_png is None
    assert without_screenshot.fingerprint == first.fingerprint  # data changed, structure did not
    other_page = await open_and_observe(browser_surface, f"{browser_site_url}/modal.html")
    assert other_page.fingerprint != first.fingerprint


async def test_trace_can_be_saved(tmp_path: Path, browser_site_url: str) -> None:
    surface = await BrowserSurface.launch(headless=True, record_trace_dir=str(tmp_path / "traces"))
    await open_and_observe(surface, f"{browser_site_url}/form.html")

    saved = await surface.save_trace(str(tmp_path / "evidence" / "step.zip"))
    await surface.close()

    assert saved is not None and Path(saved).stat().st_size > 0
    assert (tmp_path / "traces" / "trace.zip").is_file()


async def test_save_trace_without_tracing_returns_none(browser_surface: BrowserSurface, tmp_path: Path) -> None:
    assert await browser_surface.save_trace(str(tmp_path / "t.zip")) is None


async def test_act_after_close_fails(browser_site_url: str) -> None:
    surface = await BrowserSurface.launch(headless=True)
    await surface.close()
    result = await surface.act(None, OpenAction(entry_point=f"{browser_site_url}/form.html"))
    assert not result.ok


# ---------------------------------------------------------------- live view


async def test_live_view_streams_jpeg_frames(browser_surface: BrowserSurface, browser_site_url: str) -> None:
    await open_and_observe(browser_surface, f"{browser_site_url}/form.html")
    frames: list[bytes] = []

    async def collect(frame: bytes) -> None:
        frames.append(frame)

    live_view = browser_surface.live_view()
    await live_view.start(collect)
    got_frame = await wait_until(lambda: bool(frames))
    await live_view.stop()

    assert got_frame
    assert frames[0].startswith(b"\xff\xd8")
    assert live_view.last_frame_metadata is not None
    assert not live_view.running


async def test_live_view_injected_click_lands_in_nested_frame(
    browser_surface: BrowserSurface, browser_site_url: str
) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/index.html")
    await browser_surface.act(NodeRef(ref=find_node(observation, "textbox", label="Member Number").ref),
                              TypeAction(text="555"))
    search = find_node(observation, "button", name="Search")
    assert search.bounds is not None
    live_view = browser_surface.live_view()

    async def ignore(frame: bytes) -> None:
        return

    await live_view.start(ignore)
    await live_view.inject_pointer(PointerEvent(type="click", x=search.bounds.center_x, y=search.bounds.center_y))
    await live_view.stop()

    assert "Searched for 555" in visible_texts(await browser_surface.observe())


async def test_live_view_key_injection_types_each_character_once(
    browser_surface: BrowserSurface, browser_site_url: str
) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/form.html")
    textbox = find_node(observation, "textbox", label="Member Number")
    assert textbox.bounds is not None
    live_view = browser_surface.live_view()

    async def ignore(frame: bytes) -> None:
        return

    await live_view.start(ignore)
    await live_view.inject_pointer(PointerEvent(type="click", x=textbox.bounds.center_x, y=textbox.bounds.center_y))
    for event in [
        KeyEvent(type="down", key="4"), KeyEvent(type="up", key="4"),  # down/up style
        KeyEvent(type="down", key="2"), KeyEvent(type="char", key="2", text="2"), KeyEvent(type="up", key="2"),
        KeyEvent(type="char", key="7", text="7"),  # char-only style
        KeyEvent(type="down", key="9"), KeyEvent(type="up", key="9"),
        KeyEvent(type="down", key="Backspace"), KeyEvent(type="up", key="Backspace"),
        KeyEvent(type="down", key="Enter"), KeyEvent(type="up", key="Enter"),
    ]:
        await live_view.inject_key(event)
    await live_view.stop()

    after = await browser_surface.observe()
    assert find_node(after, "textbox", label="Member Number").value == "427"
    assert "Enter pressed" in visible_texts(after)


async def test_live_view_enter_accepts_native_dialog(
    browser_surface: BrowserSurface, browser_site_url: str
) -> None:
    observation = await open_and_observe(browser_surface, f"{browser_site_url}/form.html")
    await browser_surface.act(NodeRef(ref=find_node(observation, "button", name="Confirm").ref), ClickAction())
    assert (await browser_surface.observe()).dialogs
    live_view = browser_surface.live_view()

    async def ignore(frame: bytes) -> None:
        return

    await live_view.start(ignore)
    await live_view.inject_key(KeyEvent(type="down", key="Enter"))
    await live_view.inject_key(KeyEvent(type="up", key="Enter"))
    await live_view.stop()

    assert "Confirm: true" in visible_texts(await browser_surface.observe())


# ---------------------------------------------------------------- fake parity


async def test_coreone_fake_login_matches_browser_extraction_of_same_markup(
    browser_surface: BrowserSurface, browser_site_url: str
) -> None:
    """The fake's screens must look like what BrowserSurface reports for legacy table markup."""
    from hands.surfaces.fake import coreone_fake

    browser_view = await open_and_observe(browser_surface, f"{browser_site_url}/coreone_login.html")
    fake = coreone_fake()
    await fake.act(None, OpenAction(entry_point="http://coreone.test/t/lakeside/login"))
    fake_view = await fake.observe()

    def shape(observation: Observation) -> list[tuple[str, str, str, str | None, tuple[str, ...]]]:
        return [(node.role, node.structural_path, node.name, node.label, node.container_path)
                for node in observation.nodes]

    assert shape(browser_view) == shape(fake_view)
    assert browser_view.fingerprint == fake_view.fingerprint


@pytest.mark.browser
async def test_live_view_is_one_transport_per_session() -> None:
    """The console starts the stream and the input channel injects; both must share one started transport."""
    surface = await BrowserSurface.launch(headless=True)
    try:
        assert surface.live_view() is surface.live_view()
    finally:
        await surface.close()
