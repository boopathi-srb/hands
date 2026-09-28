"""MacDesktopSurface over fake AX/app/event/capture backends: observe, launch and act() dispatch."""

from macos_ax_fakes import (
    BUNDLE_ID,
    CALC_ORIGIN,
    FORM_ORIGIN,
    PID,
    SurfaceKit,
    calculator_app,
    element,
    form_scenario,
    make_surface,
    tiny_png,
)

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
from hands.core.observation import Observation
from hands.core.ports import LiveViewTransport, Surface
from hands.surfaces.desktop_macos.ax import AX_ERROR_CANNOT_COMPLETE, Attr, AxResult
from hands.surfaces.desktop_macos.live_view import ScreenLiveView
from hands.surfaces.desktop_macos.surface import PERMISSION_HELP, MacDesktopSurface


def ref_of(observation: Observation, role: str, name: str) -> NodeRef:
    node = next(node for node in observation.nodes if node.role == role and node.name == name)
    return NodeRef(ref=node.ref)


async def observed_form() -> tuple[SurfaceKit, Observation]:
    kit = make_surface(form_scenario().app)
    return kit, await kit.surface.observe()


# ---------------------------------------------------------------- protocol + observe


def test_surface_satisfies_core_protocol() -> None:
    surface = MacDesktopSurface(BUNDLE_ID)
    assert isinstance(surface, Surface)
    assert surface.kind == "desktop"
    assert isinstance(surface.live_view(), LiveViewTransport)


async def test_observe_returns_core_observation_with_screenshot() -> None:
    kit = make_surface(calculator_app())
    observation = await kit.surface.observe()
    assert observation.location.value == BUNDLE_ID
    assert observation.location.title == "Calculator"
    assert observation.screenshot_png == tiny_png()
    assert kit.capturer.captured_ids == [kit.apps.window_id]
    assert "screenshot_png" not in observation.model_dump()


async def test_observe_without_screenshot() -> None:
    kit = make_surface(calculator_app())
    observation = await kit.surface.observe(include_screenshot=False)
    assert observation.screenshot_png is None
    assert kit.capturer.captured_ids == []


async def test_observe_waits_until_two_walks_match() -> None:
    app = calculator_app("1")
    kit = make_surface(app)
    display = app.attrs[Attr.FOCUSED_WINDOW].children[0].children[0].children[0]
    original_fetch = kit.backend.attributes
    values = iter(["1", "12", "123", "123", "123"])

    def mutating_fetch(target, names):
        if target is display:
            display.attrs[Attr.VALUE] = next(values, "123")
        return original_fetch(target, names)

    kit.backend.attributes = mutating_fetch
    observation = await kit.surface.observe(include_screenshot=False)
    assert next(node for node in observation.nodes if node.role == "text").text == "123"


async def test_observe_gives_up_after_settle_timeout_and_returns_latest() -> None:
    app = calculator_app("0")
    kit = make_surface(app)
    display = app.attrs[Attr.FOCUSED_WINDOW].children[0].children[0].children[0]
    original_fetch = kit.backend.attributes
    counter = iter(range(1000))

    def always_changing(target, names):
        if target is display:
            display.attrs[Attr.VALUE] = str(next(counter))
        return original_fetch(target, names)

    kit.backend.attributes = always_changing
    observation = await kit.surface.observe(include_screenshot=False)
    assert len(observation.nodes) == 5


async def test_observe_without_permission_is_empty_not_raising() -> None:
    kit = make_surface(calculator_app(), trusted=False)
    observation = await kit.surface.observe()
    assert observation.nodes == []
    assert observation.screenshot_png is None


async def test_observe_app_not_running_is_empty() -> None:
    kit = make_surface(calculator_app(), running=False)
    observation = await kit.surface.observe()
    assert observation.nodes == []
    assert observation.location.value == BUNDLE_ID


async def test_observe_empty_app_with_no_windows() -> None:
    kit = make_surface(element("AXApplication"))
    observation = await kit.surface.observe()
    assert observation.nodes == []
    assert observation.screenshot_png is None


async def test_observe_screenshot_missing_when_capture_fails() -> None:
    kit = make_surface(calculator_app())
    kit.capturer.error = "screen recording denied"
    assert (await kit.surface.observe()).screenshot_png is None


async def test_observe_screenshot_missing_when_window_id_unknown() -> None:
    kit = make_surface(calculator_app())
    kit.apps.window_id = None
    assert (await kit.surface.observe()).screenshot_png is None


# ---------------------------------------------------------------- launch / open


async def test_launch_starts_app_and_records_it_was_launched_by_us() -> None:
    kit = make_surface(calculator_app(), running=False)
    result = await kit.surface.act(None, OpenAction(entry_point=BUNDLE_ID))
    assert result.ok
    assert kit.apps.launched == [BUNDLE_ID]
    assert kit.surface.pid == PID
    assert kit.surface.launched_by_surface is True


async def test_launch_attaches_to_running_app() -> None:
    kit = make_surface(calculator_app())
    assert (await kit.surface.launch(BUNDLE_ID)).ok
    assert kit.surface.launched_by_surface is False


async def test_launch_fails_when_open_fails() -> None:
    kit = make_surface(calculator_app(), running=False)
    kit.apps.launch_ok = False
    result = await kit.surface.launch(BUNDLE_ID)
    assert not result.ok and "could not open" in (result.error or "")


async def test_launch_fails_when_process_never_appears() -> None:
    kit = make_surface(calculator_app(), running=False)
    kit.apps.pid_on_launch.clear()
    result = await kit.surface.launch(BUNDLE_ID)
    assert not result.ok and "did not start" in (result.error or "")


async def test_launch_succeeds_for_app_without_windows() -> None:
    kit = make_surface(element("AXApplication"), running=False)
    assert (await kit.surface.launch(BUNDLE_ID)).ok


async def test_launch_without_permission() -> None:
    kit = make_surface(calculator_app(), trusted=False)
    result = await kit.surface.launch(BUNDLE_ID)
    assert not result.ok and result.error == PERMISSION_HELP
    assert kit.apps.launched == []


async def test_quit_app_terminates_bundle() -> None:
    kit = make_surface(calculator_app())
    assert (await kit.surface.quit_app()).ok
    assert kit.apps.terminated == [BUNDLE_ID]
    assert (await MacDesktopSurface(apps=kit.apps).quit_app()).ok


# ---------------------------------------------------------------- click


async def test_click_prefers_ax_press() -> None:
    kit = make_surface(calculator_app())
    observation = await kit.surface.observe()
    result = await kit.surface.act(ref_of(observation, "button", "7"), ClickAction())
    assert result.ok
    assert [action for _, action in kit.backend.performed] == ["AXPress"]
    assert kit.events.calls == []


async def test_click_falls_back_to_cgevent_at_screen_center() -> None:
    kit, observation = await observed_form()
    result = await kit.surface.act(ref_of(observation, "button", "Signature Pad"), ClickAction())
    assert result.ok
    ox, oy = FORM_ORIGIN
    assert kit.events.calls == [("click", ox + 120, oy + 350, "left")]
    assert kit.apps.activated == [PID]


async def test_click_falls_back_when_ax_press_fails() -> None:
    kit, observation = await observed_form()
    kit.backend.perform_action = lambda target, action: AxResult.failure(AX_ERROR_CANNOT_COMPLETE)
    result = await kit.surface.act(ref_of(observation, "button", "Continue"), ClickAction())
    assert result.ok
    assert kit.events.calls[0][0] == "click"


async def test_click_point_is_window_relative() -> None:
    kit = make_surface(calculator_app())
    await kit.surface.observe()
    assert (await kit.surface.act(Point(x=5, y=6), ClickAction())).ok
    assert kit.events.calls == [("click", CALC_ORIGIN[0] + 5, CALC_ORIGIN[1] + 6, "left")]


async def test_click_point_before_observe_fails() -> None:
    kit = make_surface(calculator_app())
    result = await kit.surface.act(Point(x=5, y=6), ClickAction())
    assert not result.ok and "observe" in (result.error or "")


async def test_click_unknown_ref_fails() -> None:
    kit = make_surface(calculator_app())
    await kit.surface.observe()
    result = await kit.surface.act(NodeRef(ref="n999"), ClickAction())
    assert not result.ok and "unknown ref" in (result.error or "")


async def test_click_without_target_or_bounds_fails() -> None:
    kit = make_surface(calculator_app())
    await kit.surface.observe()
    result = await kit.surface.act(None, ClickAction())
    assert not result.ok and "no AX action" in (result.error or "")


async def test_act_without_permission_returns_help() -> None:
    kit = make_surface(calculator_app(), trusted=False)
    result = await kit.surface.act(NodeRef(ref="n1"), ClickAction())
    assert not result.ok and result.error == PERMISSION_HELP


async def test_act_never_raises_on_unexpected_backend_errors() -> None:
    kit = make_surface(calculator_app())
    observation = await kit.surface.observe()
    kit.backend.raise_on_actions = True
    result = await kit.surface.act(ref_of(observation, "button", "7"), ClickAction())
    assert not result.ok and "pyobjc exploded" in (result.error or "")


# ---------------------------------------------------------------- type


async def test_type_sets_ax_value_when_settable() -> None:
    kit, observation = await observed_form()
    result = await kit.surface.act(
        ref_of_label(observation, "Member Number"), TypeAction(text="10001")
    )
    assert result.ok
    assert (Attr.VALUE, "10001") in [(name, value) for _, name, value in kit.backend.writes]
    assert kit.events.calls == []


async def test_type_without_clear_appends_to_current_value() -> None:
    kit, observation = await observed_form()
    target = ref_of_label(observation, "Member Number")
    await kit.surface.act(target, TypeAction(text="100"))
    await kit.surface.act(target, TypeAction(text="01", clear_first=False))
    assert [value for _, name, value in kit.backend.writes if name == Attr.VALUE] == [
        "100",
        "10001",
    ]


async def test_type_falls_back_to_key_events_when_value_not_settable() -> None:
    kit, observation = await observed_form()
    result = await kit.surface.act(
        ref_of_label(observation, "First Name"), TypeAction(text="Avery")
    )
    assert result.ok
    assert [call[0] for call in kit.events.calls] == ["click", "key", "key", "type_text"]
    assert kit.events.calls[1][1] == "Cmd+A"
    assert kit.events.calls[-1] == ("type_text", "Avery")


async def test_type_falls_back_when_value_write_is_ignored() -> None:
    kit, observation = await observed_form()
    kit.backend.ignore_value_writes = True
    result = await kit.surface.act(
        ref_of_label(observation, "Member Number"), TypeAction(text="1", clear_first=False)
    )
    assert result.ok
    assert [call[0] for call in kit.events.calls] == ["click", "type_text"]


async def test_type_into_focus_without_target() -> None:
    kit, _ = await observed_form()
    assert (await kit.surface.act(None, TypeAction(text="hi", clear_first=False))).ok
    assert kit.events.calls == [("type_text", "hi")]
    assert kit.apps.activated == [PID]


async def test_type_reports_event_failure() -> None:
    kit, observation = await observed_form()
    kit.events.fail = True
    result = await kit.surface.act(ref_of_label(observation, "First Name"), TypeAction(text="x"))
    assert not result.ok


def ref_of_label(observation: Observation, label: str) -> NodeRef:
    return NodeRef(ref=next(node.ref for node in observation.nodes if node.label == label))


# ---------------------------------------------------------------- press / select / scroll


async def test_press_focuses_then_sends_key() -> None:
    kit, observation = await observed_form()
    assert (
        await kit.surface.act(ref_of_label(observation, "Member Number"), PressAction(key="Enter"))
    ).ok
    assert (Attr.FOCUSED, True) in [(name, value) for _, name, value in kit.backend.writes]
    assert kit.events.calls == [("key", "Enter", None)]


async def test_press_without_target() -> None:
    kit, _ = await observed_form()
    assert (await kit.surface.act(None, PressAction(key="Escape"))).ok
    assert kit.events.calls == [("key", "Escape", None)]


async def test_select_opens_popup_and_presses_menu_item() -> None:
    kit, observation = await observed_form()
    result = await kit.surface.act(
        ref_of(observation, "combobox", "Share Type"), SelectAction(option="money market")
    )
    assert result.ok
    after = await kit.surface.observe()
    assert next(node for node in after.nodes if node.role == "combobox").value == "Money Market"
    assert kit.events.calls == []


async def test_select_unknown_option_closes_menu_and_fails() -> None:
    kit, observation = await observed_form()
    result = await kit.surface.act(
        ref_of(observation, "combobox", "Share Type"), SelectAction(option="Gold Bars")
    )
    assert not result.ok and "not found" in (result.error or "")
    assert "AXCancel" in [action for _, action in kit.backend.performed]


async def test_select_falls_back_to_setting_value_on_combobox() -> None:
    combo = element(
        "AXComboBox",
        title="Branch",
        value="North",
        frame=(10, 10, 100, 20),
        actions=["AXPress"],
        settable=[Attr.VALUE],
    )
    window = element("AXWindow", combo, title="W", frame=(0, 0, 200, 200))
    kit = make_surface(element("AXApplication", AXWindows=[window], AXFocusedWindow=window))
    observation = await kit.surface.observe()
    assert (
        await kit.surface.act(
            ref_of(observation, "combobox", "Branch"), SelectAction(option="South")
        )
    ).ok
    assert combo.attrs[Attr.VALUE] == "South"
    assert ("key", "Escape", None) in kit.events.calls


async def test_select_requires_a_node() -> None:
    kit, _ = await observed_form()
    result = await kit.surface.act(None, SelectAction(option="x"))
    assert not result.ok and "node target" in (result.error or "")


async def test_scroll_at_node_center() -> None:
    kit, observation = await observed_form()
    table_ref = ref_of_path(observation, "table[1]")
    assert (await kit.surface.act(table_ref, ScrollAction(direction="down", amount=5))).ok
    ox, oy = FORM_ORIGIN
    assert kit.events.calls == [("scroll", ox + 170, oy + 440, -5)]


async def test_scroll_without_target_uses_window_center() -> None:
    kit = make_surface(calculator_app())
    await kit.surface.observe()
    assert (await kit.surface.act(None, ScrollAction(direction="up"))).ok
    assert kit.events.calls == [("scroll", CALC_ORIGIN[0] + 115, CALC_ORIGIN[1] + 200, 3)]


async def test_scroll_before_observe_fails() -> None:
    kit = make_surface(calculator_app())
    assert not (await kit.surface.act(None, ScrollAction())).ok


def ref_of_path(observation: Observation, structural_path: str) -> NodeRef:
    return NodeRef(
        ref=next(node.ref for node in observation.nodes if node.structural_path == structural_path)
    )


# ---------------------------------------------------------------- live view + lifecycle


async def test_live_view_is_cached_and_close_stops_it() -> None:
    kit = make_surface(calculator_app())
    view = kit.surface.live_view()
    assert isinstance(view, ScreenLiveView)
    assert kit.surface.live_view() is view
    frames: list[bytes] = []

    async def on_frame(frame: bytes) -> None:
        frames.append(frame)

    await view.start(on_frame)
    assert view.running
    await kit.surface.close()
    assert not view.running
    assert kit.surface.last_snapshot is None


async def test_capture_target_uses_fresh_window_frame() -> None:
    kit = make_surface(calculator_app())
    target = await kit.surface.capture_target()
    assert target is not None
    assert (target.window_id, target.origin.x, target.origin.y) == (
        kit.apps.window_id,
        *CALC_ORIGIN,
    )


async def test_capture_target_none_without_window() -> None:
    kit = make_surface(element("AXApplication"))
    assert await kit.surface.capture_target() is None
