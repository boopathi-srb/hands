"""FakeSurface unit tests: screens, transitions, typed values, interrupts, failures, fingerprints."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from surface_test_helpers import act_on, find_node, texts_of

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
from hands.core.observation import Dialog, Location, Rect
from hands.core.ports import Surface
from hands.surfaces.fake import (
    PREVIOUS_SCREEN,
    SAME_SCREEN,
    WILDCARD,
    FakeContext,
    FakeScreen,
    FakeSurface,
    blank_png,
    fake_node,
    native_alert_screen,
    node_keys,
)

LOGIN_URL = "http://app.test/login"
HOME_URL = "http://app.test/home"


def _login_screen() -> FakeScreen:
    return FakeScreen(
        name="login",
        location=Location(kind="url", value=LOGIN_URL, title="Sign On"),
        nodes=[
            fake_node("text", "User ID", path="text[1]", bounds=Rect(x=10, y=10, width=60, height=20)),
            fake_node("textbox", label="User ID", path="textbox[1]", bounds=Rect(x=80, y=10, width=150, height=20)),
            fake_node("textbox", label="Password", path="textbox[2]", bounds=Rect(x=80, y=40, width=150, height=20)),
            fake_node("combobox", label="Branch", value="Main", path="combobox[1]"),
            fake_node("button", "Sign On", path="button[1]", bounds=Rect(x=80, y=70, width=70, height=24)),
            fake_node("link", "Help", path="link[1]", ref="help"),
        ],
        transitions={
            ("Sign On", "click"): lambda context: "home" if context.value("User ID") == "teller1" else SAME_SCREEN,
            ("Password", "press:Enter"): "home",
            ("Password", "press"): SAME_SCREEN,
            ("help", "click"): "help_popup",
            (WILDCARD, "press:F1"): "help_popup",
        },
        entry_points=[LOGIN_URL],
        select_options={"Branch": ["Main", "North"]},
        secret_fields=["Password"],
    )


def _home_screen() -> FakeScreen:
    return FakeScreen(
        name="home",
        location=Location(kind="url", value=HOME_URL, title="Home"),
        nodes=[fake_node("heading", "Welcome", path="heading[1]"), fake_node("link", "Sign Off", path="link[1]")],
        transitions={("Sign Off", "click"): "login", ("Welcome", "click"): "nowhere"},
        entry_points=[HOME_URL],
    )


def _help_popup() -> FakeScreen:
    return FakeScreen(
        name="help_popup",
        layer="overlay",
        nodes=[fake_node("dialog", "Help", path="dialog[1]"), fake_node("button", "Close", path="dialog[1]/button[1]")],
        dialogs=[Dialog(title="Help", text="Call the service desk")],
        transitions={("Close", "click"): PREVIOUS_SCREEN},
    )


def _surface(initial: str = "login") -> FakeSurface:
    fixed_time = datetime(2026, 1, 1, tzinfo=UTC)
    return FakeSurface(
        [_login_screen(), _home_screen(), _help_popup(), native_alert_screen("alert", "Printer offline")],
        initial=initial,
        clock=lambda: fixed_time,
    )


# ---------------------------------------------------------------- construction and observation


def test_fake_surface_satisfies_surface_protocol() -> None:
    assert isinstance(_surface(), Surface)
    assert _surface().kind == "fake"


async def test_observe_assigns_refs_location_and_time() -> None:
    surface = _surface()
    observation = await surface.observe()

    assert [node.ref for node in observation.nodes][:5] == ["n1", "n2", "n3", "n4", "n5"]
    assert find_node(observation, "link", name="Help").ref == "help"
    assert observation.location.value == LOGIN_URL
    assert observation.observed_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert observation.screenshot_png is not None and observation.screenshot_png.startswith(b"\x89PNG")
    assert (await surface.observe(include_screenshot=False)).screenshot_png is None
    assert surface.observation_count == 2


def test_unknown_initial_screen_raises() -> None:
    with pytest.raises(ValueError, match="unknown initial screen"):
        FakeSurface([_login_screen()], initial="missing")


def test_duplicate_refs_raise() -> None:
    with pytest.raises(ValueError, match="duplicate node refs"):
        FakeScreen(name="bad", nodes=[fake_node("button", "A", ref="x"), fake_node("button", "B", ref="x")])


def test_empty_screen_is_allowed() -> None:
    assert FakeScreen(name="empty").nodes == []


async def test_fingerprints_are_deterministic_and_structural() -> None:
    first, second = _surface(), _surface()
    login_a, login_b = await first.observe(), await second.observe()
    assert login_a.fingerprint == login_b.fingerprint

    await act_on(first, TypeAction(text="teller1"), "textbox", label="User ID")
    assert (await first.observe()).fingerprint == login_a.fingerprint  # values are not structure

    first.set_screen("home")
    assert (await first.observe()).fingerprint != login_a.fingerprint


# ---------------------------------------------------------------- typing and values


async def test_type_captures_value_and_respects_clear_first() -> None:
    surface = _surface()
    await act_on(surface, TypeAction(text="tell"), "textbox", label="User ID")
    await act_on(surface, TypeAction(text="er1", clear_first=False), "textbox", label="User ID")
    assert find_node(await surface.observe(), "textbox", label="User ID").value == "teller1"

    await act_on(surface, TypeAction(text="admin"), "textbox", label="User ID")
    assert surface.value_of("User ID") == "admin"


async def test_secret_fields_are_masked_in_observations_but_kept_for_routing() -> None:
    surface = _surface()
    await act_on(surface, TypeAction(text="s3cret"), "textbox", label="Password")

    assert find_node(await surface.observe(), "textbox", label="Password").value == "•" * 6
    assert surface.value_of("Password") == "s3cret"


async def test_typing_into_non_editable_node_is_a_no_op() -> None:
    surface = _surface()
    result = await act_on(surface, TypeAction(text="x"), "button", name="Sign On")
    assert result.ok
    assert find_node(await surface.observe(), "button", name="Sign On").value is None


async def test_select_validates_options() -> None:
    surface = _surface()
    assert (await act_on(surface, SelectAction(option="North"), "combobox", label="Branch")).ok
    assert surface.value_of("Branch") == "North"

    missing = await act_on(surface, SelectAction(option="South"), "combobox", label="Branch")
    assert not missing.ok and "South" in (missing.error or "")
    not_selectable = await act_on(surface, SelectAction(option="North"), "button", name="Sign On")
    assert not not_selectable.ok
    assert not (await surface.act(None, SelectAction(option="North"))).ok


# ---------------------------------------------------------------- transitions


async def test_routing_function_sees_typed_values() -> None:
    surface = _surface()
    await act_on(surface, TypeAction(text="nobody"), "textbox", label="User ID")
    await act_on(surface, ClickAction(), "button", name="Sign On")
    assert surface.current_screen == "login"

    await act_on(surface, TypeAction(text="teller1"), "textbox", label="User ID")
    await act_on(surface, ClickAction(), "button", name="Sign On")
    assert surface.current_screen == "home"


async def test_transition_by_ref_and_specific_press_key_wins() -> None:
    surface = _surface()
    await act_on(surface, PressAction(key="Tab"), "textbox", label="Password")
    assert surface.current_screen == "login"
    await act_on(surface, PressAction(key="Enter"), "textbox", label="Password")
    assert surface.current_screen == "home"

    other = _surface()
    await act_on(other, ClickAction(), "link", name="Help")  # keyed by definition ref 'help'
    assert other.current_screen == "help_popup"


async def test_wildcard_transition_with_no_target() -> None:
    surface = _surface()
    await surface.observe()
    assert (await surface.act(None, PressAction(key="F1"))).ok
    assert surface.current_screen == "help_popup"


async def test_press_without_target_uses_focused_node() -> None:
    surface = _surface()
    await act_on(surface, ClickAction(), "textbox", label="Password")
    assert (await surface.act(None, PressAction(key="Enter"))).ok
    assert surface.current_screen == "home"


async def test_navigation_resets_values_of_the_destination() -> None:
    surface = _surface()
    await act_on(surface, TypeAction(text="teller1"), "textbox", label="User ID")
    await act_on(surface, ClickAction(), "button", name="Sign On")
    await act_on(surface, ClickAction(), "link", name="Sign Off")
    assert find_node(await surface.observe(), "textbox", label="User ID").value is None


async def test_transition_to_unknown_screen_fails() -> None:
    surface = _surface("home")
    result = await act_on(surface, ClickAction(), "heading", name="Welcome")
    assert not result.ok and "nowhere" in (result.error or "")


async def test_previous_screen_without_underlay_fails() -> None:
    surface = FakeSurface([FakeScreen(name="solo", nodes=[fake_node("button", "Back")],
                                      transitions={("Back", "click"): PREVIOUS_SCREEN})], initial="solo")
    result = await act_on(surface, ClickAction(), "button", name="Back")
    assert not result.ok and "no previous screen" in (result.error or "")


async def test_routing_function_may_return_a_new_screen() -> None:
    def route(context: FakeContext) -> FakeScreen:
        return FakeScreen(name="echo", nodes=[fake_node("text", f"You typed {context.value('Query')}")])

    surface = FakeSurface([FakeScreen(
        name="search",
        nodes=[fake_node("textbox", label="Query"), fake_node("button", "Go")],
        transitions={("Go", "click"): route},
    )], initial="search")
    await act_on(surface, TypeAction(text="abc"), "textbox", label="Query")
    await act_on(surface, ClickAction(), "button", name="Go")

    assert surface.current_screen == "echo"
    assert "You typed abc" in texts_of(await surface.observe())


# ---------------------------------------------------------------- refs, points, failures


async def test_act_before_observe_and_unknown_ref_fail_without_raising() -> None:
    surface = _surface()
    before = await surface.act(NodeRef(ref="n1"), ClickAction())
    assert not before.ok and "observe" in (before.error or "")

    await surface.observe()
    unknown = await surface.act(NodeRef(ref="n404"), ClickAction())
    assert not unknown.ok and "unknown ref" in (unknown.error or "")


async def test_stale_ref_after_screen_change_fails() -> None:
    surface = _surface("home")
    observation = await surface.observe()
    sign_off = find_node(observation, "link", name="Sign Off")
    await surface.act(NodeRef(ref=sign_off.ref), ClickAction())

    stale = await surface.act(NodeRef(ref=sign_off.ref), ClickAction())
    assert not stale.ok and "stale" in (stale.error or "")


async def test_click_at_point_hits_the_smallest_node() -> None:
    surface = _surface()
    await surface.observe()
    assert (await surface.act(Point(x=100, y=80), ClickAction())).ok  # inside 'Sign On'
    assert surface.actions[-1].result.ok
    assert (await surface.act(Point(x=900, y=900), ClickAction())).ok  # empty space: no effect
    assert surface.current_screen == "login"


async def test_fail_next_act_fails_once_without_changing_state() -> None:
    surface = _surface()
    surface.fail_next_act("element detached")
    first = await act_on(surface, TypeAction(text="x"), "textbox", label="User ID")
    second = await act_on(surface, TypeAction(text="y"), "textbox", label="User ID")

    assert (first.ok, first.error) == (False, "element detached")
    assert second.ok and surface.value_of("User ID") == "y"


async def test_every_act_is_recorded() -> None:
    surface = _surface()
    await act_on(surface, TypeAction(text="teller1"), "textbox", label="User ID")
    await surface.act(NodeRef(ref="missing"), ClickAction())
    await surface.act(None, ScrollAction())

    assert [(record.action.kind, record.result.ok, record.screen, record.source) for record in surface.actions] == [
        ("type", True, "login", "automation"),
        ("click", False, "login", "automation"),
        ("scroll", True, "login", "automation"),
    ]


async def test_closed_surface_refuses_to_act() -> None:
    surface = _surface()
    await surface.close()
    assert surface.closed
    assert not (await surface.act(None, OpenAction(entry_point=LOGIN_URL))).ok


# ---------------------------------------------------------------- open


async def test_open_matches_full_url_or_path() -> None:
    surface = _surface("home")
    assert (await surface.act(None, OpenAction(entry_point=LOGIN_URL))).ok
    assert surface.current_screen == "login"
    assert (await surface.act(None, OpenAction(entry_point="http://other-host:8080/home"))).ok
    assert surface.current_screen == "home"
    missing = await surface.act(None, OpenAction(entry_point="http://app.test/nope"))
    assert not missing.ok and "no screen" in (missing.error or "")


# ---------------------------------------------------------------- interrupts


async def test_injected_overlay_shows_over_the_page_and_returns() -> None:
    surface = _surface()
    surface.inject_next("help_popup")
    observation = await surface.observe()

    assert [dialog.title for dialog in observation.dialogs] == ["Help"]
    assert find_node(observation, "button", name="Sign On")  # page underneath is still visible
    assert observation.location.value == LOGIN_URL  # overlay inherits the page location
    blocked = await surface.act(NodeRef(ref=find_node(observation, "button", name="Sign On").ref), ClickAction())
    assert blocked.ok and surface.current_screen == "help_popup"  # swallowed by the modal

    await act_on(surface, ClickAction(), "button", name="Close")
    assert surface.current_screen == "login"
    assert (await surface.observe()).dialogs == []


async def test_injected_native_dialog_hides_the_page() -> None:
    surface = _surface()
    surface.inject_next("alert")
    observation = await surface.observe()

    assert [(node.role, node.name) for node in observation.nodes] == [("dialog", "Printer offline"), ("button", "OK")]
    assert observation.dialogs == [Dialog(title="alert", text="Printer offline", native=True)]
    assert {node.container_path for node in observation.nodes} == {("dialog:native",)}
    assert (await surface.act(None, PressAction(key="Enter"))).ok
    assert surface.current_screen == "login"


async def test_interrupt_after_next_act() -> None:
    surface = _surface()
    surface.inject_next("alert", trigger="act")
    await surface.observe()
    assert surface.current_screen == "login"

    await act_on(surface, PressAction(key="Enter"), "textbox", label="Password")
    assert surface.current_screen == "alert"
    await surface.observe()
    await surface.act(None, PressAction(key="Escape"))
    assert surface.current_screen == "home"  # the act's own destination is underneath


async def test_interrupt_does_not_fire_after_a_failed_act() -> None:
    surface = _surface()
    surface.inject_next("alert", trigger="act")
    await surface.observe()
    await surface.act(NodeRef(ref="missing"), ClickAction())
    assert surface.current_screen == "login"


async def test_delay_observations_returns_loading_screen_n_times() -> None:
    surface = _surface()
    surface.delay_observations(2)
    first, second, third = await surface.observe(), await surface.observe(), await surface.observe()

    assert texts_of(first) == ["Loading..."] and texts_of(second) == ["Loading..."]
    assert first.location.value == LOGIN_URL
    assert find_node(third, "button", name="Sign On")
    surface.delay_observations(0)
    assert find_node(await surface.observe(), "button", name="Sign On")


async def test_acting_on_a_loading_observation_is_stale() -> None:
    surface = _surface()
    surface.delay_observations(1)
    loading = await surface.observe()
    result = await surface.act(NodeRef(ref=loading.nodes[0].ref), ClickAction())
    assert not result.ok and "stale" in (result.error or "")


def test_scripting_errors_raise_value_error() -> None:
    surface = _surface()
    with pytest.raises(ValueError):
        surface.inject_next("does_not_exist")
    with pytest.raises(ValueError):
        surface.delay_observations(-1)
    with pytest.raises(ValueError):
        surface.set_screen("does_not_exist")


async def test_overlay_ref_collisions_are_renamed() -> None:
    page = FakeScreen(name="page", location=Location(kind="url", value="http://x.test/"),
                      nodes=[fake_node("button", "A", ref="shared")])
    popup = FakeScreen(name="popup", layer="overlay", nodes=[fake_node("button", "B", ref="shared")],
                       transitions={("B", "click"): PREVIOUS_SCREEN})
    surface = FakeSurface([page, popup], initial="page")
    surface.inject_next("popup")
    refs = [node.ref for node in (await surface.observe()).nodes]

    assert refs == ["shared", "shared.1"]
    assert (await surface.act(NodeRef(ref="shared.1"), ClickAction())).ok
    assert surface.current_screen == "page"


# ---------------------------------------------------------------- small helpers


def test_node_keys_skip_empty_and_duplicates() -> None:
    node = fake_node("textbox", label="Name", ref="n1")
    assert node_keys(node) == ["n1", "Name"]
    assert node_keys(fake_node("button", "Go", ref="Go")) == ["Go"]


def test_fake_node_text_defaults() -> None:
    assert fake_node("button", "Go").text == "Go"
    assert fake_node("textbox", "Go").text == ""
    assert fake_node("text", "a", text="b").text == "b"


def test_blank_png_is_a_valid_png_of_any_size() -> None:
    image = blank_png(3, 2)
    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert int.from_bytes(image[16:20], "big") == 3 and int.from_bytes(image[20:24], "big") == 2
    assert int.from_bytes(blank_png(0, -5)[16:20], "big") == 1  # clamped to 1x1


def test_screen_accessors() -> None:
    surface = _surface()
    assert "home" in surface.screen_names
    assert surface.screen("home") is not None and surface.screen("nope") is None
    assert surface.value_of("Branch") == "Main"
    assert surface.value_of("No such field") is None
    assert surface.last_observation is None
