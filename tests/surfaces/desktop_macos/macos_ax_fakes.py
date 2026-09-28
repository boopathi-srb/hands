"""In-memory fakes for the macOS surface: an AX tree, an AxBackend, an event poster, apps, capturer.

The trees are modeled on Calculator (unlabeled groups, buttons named by AXDescription, a static-text
display) and on a legacy data-entry window with a sheet (adjacent-text labels, AXTitleUIElement,
a popup menu, a table, a confirmation sheet).
"""

from __future__ import annotations

import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from hands.core.actions import ActResult
from hands.surfaces.desktop_macos.ax import (
    AX_ERROR_ACTION_UNSUPPORTED,
    AX_ERROR_ATTRIBUTE_UNSUPPORTED,
    AX_ERROR_INVALID_UI_ELEMENT,
    AX_ERROR_NO_VALUE,
    Attr,
    AxPoint,
    AxResult,
    AxSize,
)
from hands.surfaces.desktop_macos.capture import CaptureResult
from hands.surfaces.desktop_macos.surface import MacDesktopSurface, SurfaceTimings

Frame = tuple[float, float, float, float]


@dataclass(eq=False)
class FakeElement:
    """One fake AX element. Identity equality, like distinct AXUIElementRefs."""

    role: str
    attrs: dict[str, Any] = field(default_factory=dict)
    children: list[FakeElement] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    settable: set[str] = field(default_factory=set)
    on_action: dict[str, Callable[[], None]] = field(default_factory=dict)
    invalid: bool = False

    def values(self) -> dict[str, Any]:
        merged = {Attr.ROLE: self.role, **self.attrs}
        if self.children:
            merged[Attr.CHILDREN] = list(self.children)
        return merged


def element(
    role: str,
    *children: FakeElement,
    title: str | None = None,
    description: str | None = None,
    value: Any = None,
    subrole: str | None = None,
    frame: Frame | None = None,
    actions: Sequence[str] = (),
    settable: Sequence[str] = (),
    **extra_attrs: Any,
) -> FakeElement:
    attrs: dict[str, Any] = dict(extra_attrs)
    optional_attrs = {
        Attr.TITLE: title,
        Attr.DESCRIPTION: description,
        Attr.VALUE: value,
        Attr.SUBROLE: subrole,
    }
    attrs.update(
        {name: attr_value for name, attr_value in optional_attrs.items() if attr_value is not None}
    )
    if frame is not None:
        attrs[Attr.POSITION] = AxPoint(frame[0], frame[1])
        attrs[Attr.SIZE] = AxSize(frame[2], frame[3])
    return FakeElement(
        role=role,
        attrs=attrs,
        children=list(children),
        actions=list(actions),
        settable=set(settable),
    )


def application(*windows: FakeElement, focused: FakeElement | None = None) -> FakeElement:
    app = element("AXApplication", title="App")
    app.attrs[Attr.WINDOWS] = list(windows)
    if focused is not None:
        app.attrs[Attr.FOCUSED_WINDOW] = focused
    return app


# ---------------------------------------------------------------- scenario trees

CALC_ORIGIN = (100.0, 200.0)


def calc_button(label: str, x: float, y: float) -> FakeElement:
    return element("AXButton", description=label, frame=(x, y, 40, 40), actions=["AXPress"])


def calculator_window(display_value: str = "0") -> FakeElement:
    ox, oy = CALC_ORIGIN
    display = element("AXStaticText", value=display_value, frame=(ox + 10, oy + 30, 210, 50))
    display_group = element("AXGroup", element("AXScrollArea", display))
    keypad = element(
        "AXGroup",
        calc_button("7", ox + 10, oy + 100),
        calc_button("8", ox + 60, oy + 100),
        calc_button("Add", ox + 110, oy + 100),
        calc_button("Clear", ox + 160, oy + 100),
    )
    return element(
        "AXWindow",
        display_group,
        keypad,
        title="Calculator",
        subrole="AXStandardWindow",
        frame=(ox, oy, 230, 400),
    )


def calculator_app(display_value: str = "0") -> FakeElement:
    window = calculator_window(display_value)
    return application(window, focused=window)


FORM_ORIGIN = (50.0, 60.0)


@dataclass
class FormScenario:
    app: FakeElement
    window: FakeElement
    dialog_window: FakeElement
    member_field: FakeElement
    first_name_field: FakeElement
    nickname_field: FakeElement
    share_popup: FakeElement
    joint_checkbox: FakeElement
    continue_button: FakeElement
    custom_canvas: FakeElement
    sheet: FakeElement


def _share_menu(popup: FakeElement, options: Sequence[str]) -> Callable[[], None]:
    def open_menu() -> None:
        items = [element("AXMenuItem", title=option, actions=["AXPress"]) for option in options]
        for item, option in zip(items, options, strict=True):
            item.on_action["AXPress"] = _choose(popup, option)
        menu = element("AXMenu", *items, actions=["AXCancel"])
        menu.on_action["AXCancel"] = lambda: popup.children.clear()
        popup.children[:] = [menu]

    return open_menu


def _choose(popup: FakeElement, option: str) -> Callable[[], None]:
    def choose() -> None:
        popup.attrs[Attr.VALUE] = option
        popup.children.clear()

    return choose


def form_scenario(with_sheet: bool = True) -> FormScenario:
    ox, oy = FORM_ORIGIN
    member_label = element("AXStaticText", value="Member Number", frame=(ox + 20, oy + 50, 100, 20))
    member_field = element(
        "AXTextField",
        value="",
        frame=(ox + 130, oy + 48, 160, 24),
        settable=[Attr.VALUE, Attr.FOCUSED],
    )
    first_name_label = element(
        "AXStaticText", value="First Name", frame=(ox + 20, oy + 90, 100, 20)
    )
    first_name_field = element(
        "AXTextField", value="", frame=(ox + 20, oy + 115, 160, 24), settable=[Attr.FOCUSED]
    )
    nickname_title = element("AXStaticText", value="Nickname", frame=(ox + 400, oy + 400, 60, 20))
    nickname_field = element(
        "AXTextField",
        value="",
        frame=(ox + 20, oy + 160, 160, 24),
        settable=[Attr.VALUE],
        AXTitleUIElement=nickname_title,
    )
    share_popup = element(
        "AXPopUpButton",
        value="Regular Savings",
        title="Share Type",
        frame=(ox + 20, oy + 200, 160, 24),
        actions=["AXPress"],
    )
    share_popup.on_action["AXPress"] = _share_menu(
        share_popup, ["Regular Savings", "Money Market", "Share Certificate"]
    )
    joint_checkbox = element(
        "AXCheckBox", title="Joint", value=0, frame=(ox + 20, oy + 240, 80, 20), actions=["AXPress"]
    )
    continue_button = element(
        "AXButton", title="Continue", frame=(ox + 200, oy + 280, 90, 30), actions=["AXPress"]
    )
    custom_canvas = element(
        "AXButton", description="Signature Pad", frame=(ox + 20, oy + 320, 200, 60)
    )
    table = element(
        "AXTable",
        element(
            "AXRow",
            element("AXCell", element("AXStaticText", value="S01")),
            element("AXCell", element("AXStaticText", value="Savings")),
        ),
        element(
            "AXRow",
            element("AXCell", element("AXStaticText", value="S02")),
            element("AXCell", element("AXStaticText", value="Checking")),
        ),
        frame=(ox + 20, oy + 400, 300, 80),
    )
    sheet = element(
        "AXSheet",
        element(
            "AXStaticText", value="Replace existing member?", frame=(ox + 30, oy + 30, 200, 20)
        ),
        element("AXButton", title="Replace", frame=(ox + 30, oy + 60, 80, 30), actions=["AXPress"]),
        element("AXButton", title="Cancel", frame=(ox + 120, oy + 60, 80, 30), actions=["AXPress"]),
        description="Confirm",
        frame=(ox + 10, oy + 20, 300, 120),
    )
    layout = element(
        "AXGroup",
        member_label,
        member_field,
        first_name_label,
        first_name_field,
        nickname_field,
        share_popup,
        joint_checkbox,
        continue_button,
        custom_canvas,
        table,
    )
    window_children = [layout, sheet] if with_sheet else [layout]
    window = element(
        "AXWindow",
        *window_children,
        title="New Member",
        subrole="AXStandardWindow",
        frame=(ox, oy, 600, 600),
    )
    dialog_window = element(
        "AXWindow",
        element("AXStaticText", value="Printer queue offline", frame=(410, 310, 150, 20)),
        element("AXButton", title="OK", frame=(500, 350, 60, 30), actions=["AXPress"]),
        title="Printer",
        subrole="AXDialog",
        frame=(400, 300, 200, 100),
    )
    app = application(dialog_window, window, focused=window)
    return FormScenario(
        app,
        window,
        dialog_window,
        member_field,
        first_name_field,
        nickname_field,
        share_popup,
        joint_checkbox,
        continue_button,
        custom_canvas,
        sheet,
    )


# ---------------------------------------------------------------- backend


class FakeAxBackend:
    """AxBackend over FakeElements. Records performed actions and attribute writes."""

    def __init__(
        self, apps_by_pid: dict[int, FakeElement] | None = None, trusted: bool = True
    ) -> None:
        self.apps_by_pid = apps_by_pid or {}
        self.trusted = trusted
        self.performed: list[tuple[FakeElement, str]] = []
        self.writes: list[tuple[FakeElement, str, Any]] = []
        self.ignore_value_writes = False
        self.raise_on_actions = False
        self.attribute_fetches = 0

    def is_process_trusted(self) -> bool:
        return self.trusted

    def application_element(self, pid: int) -> AxResult[Any]:
        app = self.apps_by_pid.get(pid)
        return (
            AxResult.success(app)
            if app is not None
            else AxResult.failure(AX_ERROR_INVALID_UI_ELEMENT)
        )

    def attribute(self, element: FakeElement, name: str) -> AxResult[Any]:
        if element.invalid:
            return AxResult.failure(AX_ERROR_INVALID_UI_ELEMENT)
        values = element.values()
        return (
            AxResult.success(values[name])
            if name in values
            else AxResult.failure(AX_ERROR_NO_VALUE)
        )

    def attributes(self, element: FakeElement, names: Sequence[str]) -> AxResult[dict[str, Any]]:
        self.attribute_fetches += 1
        if element.invalid:
            return AxResult.failure(AX_ERROR_INVALID_UI_ELEMENT)
        values = element.values()
        return AxResult.success({name: values[name] for name in names if name in values})

    def attribute_names(self, element: FakeElement) -> AxResult[list[str]]:
        return AxResult.success(list(element.values()))

    def action_names(self, element: FakeElement) -> AxResult[list[str]]:
        if self.raise_on_actions:
            raise RuntimeError("pyobjc exploded")
        return AxResult.success(list(element.actions))

    def is_settable(self, element: FakeElement, name: str) -> AxResult[bool]:
        return AxResult.success(name in element.settable)

    def set_attribute(self, element: FakeElement, name: str, value: Any) -> AxResult[None]:
        if name not in element.settable:
            return AxResult.failure(AX_ERROR_ATTRIBUTE_UNSUPPORTED)
        self.writes.append((element, name, value))
        if not (self.ignore_value_writes and name == Attr.VALUE):
            element.attrs[name] = value
        return AxResult.success(None)

    def perform_action(self, element: FakeElement, action: str) -> AxResult[None]:
        if action not in element.actions:
            return AxResult.failure(AX_ERROR_ACTION_UNSUPPORTED)
        self.performed.append((element, action))
        callback = element.on_action.get(action)
        if callback is not None:
            callback()
        return AxResult.success(None)


# ---------------------------------------------------------------- other fakes


class FakeEventPoster:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.fail = fail

    def _result(self) -> ActResult:
        return ActResult(ok=False, error="post failed") if self.fail else ActResult(ok=True)

    def move(self, x: float, y: float) -> ActResult:
        self.calls.append(("move", x, y))
        return self._result()

    def mouse_button(self, x: float, y: float, button: str, down: bool) -> ActResult:
        self.calls.append(("mouse_button", x, y, button, down))
        return self._result()

    def click(self, x: float, y: float, button: str = "left", click_count: int = 1) -> ActResult:
        self.calls.append(("click", x, y, button))
        return self._result()

    def key(self, key: str, down: bool | None = None) -> ActResult:
        self.calls.append(("key", key, down))
        return self._result()

    def type_text(self, text: str) -> ActResult:
        self.calls.append(("type_text", text))
        return self._result()

    def scroll(self, x: float, y: float, lines: int) -> ActResult:
        self.calls.append(("scroll", x, y, lines))
        return self._result()


class FakeAppController:
    def __init__(self, running: dict[str, int] | None = None, launch_ok: bool = True) -> None:
        self.running = dict(running or {})
        self.launch_ok = launch_ok
        self.pid_on_launch: dict[str, int] = {}
        self.launched: list[str] = []
        self.activated: list[int] = []
        self.terminated: list[str] = []
        self.window_id = 4242

    def find_pid(self, bundle_id: str) -> int | None:
        return self.running.get(bundle_id)

    async def launch(self, bundle_id: str) -> ActResult:
        self.launched.append(bundle_id)
        if not self.launch_ok:
            return ActResult(ok=False, error=f"could not open {bundle_id}")
        if bundle_id in self.pid_on_launch:
            self.running[bundle_id] = self.pid_on_launch[bundle_id]
        return ActResult(ok=True)

    def activate(self, pid: int) -> ActResult:
        self.activated.append(pid)
        return ActResult(ok=True)

    def terminate(self, bundle_id: str) -> ActResult:
        self.terminated.append(bundle_id)
        self.running.pop(bundle_id, None)
        return ActResult(ok=True)

    def window_id_for(self, pid: int, origin: AxPoint, size: AxSize) -> int | None:
        return self.window_id


def tiny_png(color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(output, format="PNG")
    return output.getvalue()


class FakeCapturer:
    def __init__(self, frames: Sequence[bytes] | None = None, error: str | None = None) -> None:
        self.frames = list(frames or [tiny_png()])
        self.error = error
        self.captured_ids: list[int] = []

    async def capture_window(self, window_id: int) -> CaptureResult:
        self.captured_ids.append(window_id)
        if self.error is not None:
            return CaptureResult(error=self.error)
        frame = self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]
        return CaptureResult(png=frame)


async def no_sleep(_seconds: float) -> None:
    return None


class FakeClock:
    """Advances by `step` every call, so deadline loops terminate without real time passing."""

    def __init__(self, step: float = 0.5) -> None:
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        self.now += self.step
        return self.now


BUNDLE_ID = "com.example.coreone"
PID = 777


@dataclass
class SurfaceKit:
    surface: MacDesktopSurface
    backend: FakeAxBackend
    events: FakeEventPoster
    apps: FakeAppController
    capturer: FakeCapturer


def make_surface(app: FakeElement | None, trusted: bool = True, running: bool = True) -> SurfaceKit:
    backend = FakeAxBackend({PID: app} if app is not None else {}, trusted=trusted)
    events = FakeEventPoster()
    apps = FakeAppController({BUNDLE_ID: PID} if running else {})
    apps.pid_on_launch[BUNDLE_ID] = PID
    capturer = FakeCapturer()
    surface = MacDesktopSurface(
        BUNDLE_ID,
        backend=backend,
        events=events,
        apps=apps,
        capturer=capturer,
        timings=SurfaceTimings(
            settle_timeout_s=2.0, settle_poll_s=0.01, launch_timeout_s=2.0, launch_poll_s=0.01
        ),
        sleep=no_sleep,
        clock=FakeClock(),
    )
    return SurfaceKit(surface, backend, events, apps, capturer)
