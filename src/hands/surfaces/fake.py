"""FakeSurface: an in-memory, scripted, deterministic Surface for tests. No browser, no OS.

A fake is a set of `FakeScreen`s plus transitions between them:

    login = FakeScreen(
        name="login",
        location=Location(kind="url", value="http://app.test/login"),
        nodes=[fake_node("textbox", label="User ID"), fake_node("button", "Sign On")],
        transitions={("Sign On", "click"): "home"},
        entry_points=["http://app.test/login"],
    )
    surface = FakeSurface([login, home], initial="login")

Semantics (kept close to the real browser surface so tests stay honest):
- `act(NodeRef)` resolves refs against the latest observation. Unknown refs, acting before any
  observation, and refs whose screen is no longer displayed return `ActResult(ok=False, ...)`.
- Typing into an editable node (textbox, combobox, ...) stores the text as that node's value, per screen.
  Selecting an option stores it as the value. Entering a screen through navigation resets its values.
- Transitions are keyed by (node key, action kind). Node keys are tried in order: definition ref, name,
  label, then `WILDCARD`. Press actions try `"press:<Key>"` before plain `"press"`. The target of a
  transition is a screen name, `SAME_SCREEN`, `PREVIOUS_SCREEN`, or a routing function that receives a
  `FakeContext` (typed values of the visible screen) and returns a screen name or a new `FakeScreen`.
- Screen layers: "page" replaces what is shown; "overlay" (in-page modal) is drawn over the screen
  underneath (both sets of nodes are observed, only the overlay reacts); "native" (JS alert, OS sheet)
  hides the page and shows only its own synthetic nodes. Overlay and native screens return to the screen
  underneath through `PREVIOUS_SCREEN`.
- Interrupts: `inject_next(name)` shows a screen on the next observe (or after the next successful act),
  `delay_observations(n)` returns a loading screen n times, `fail_next_act(error)` fails the next act.
- Every act is recorded in `surface.actions`; fingerprints hash roles and structural paths only.

`coreone_fake(tenant)` builds the CoreOne Member Services flow from PLAN.md with frame containers,
role-indexed structural paths, and page-level bounds shaped like the browser surface's output.
"""

from __future__ import annotations

import os
import struct
import zlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from hands.core.actions import (
    Action,
    ActResult,
    ActTarget,
    ClickAction,
    NodeRef,
    OpenAction,
    Point,
    PressAction,
    ScrollAction,
    SelectAction,
    TypeAction,
)
from hands.core.log import get_logger, log_failure
from hands.core.observation import Dialog, Location, Node, Observation, Rect
from hands.core.ports import FrameHandler, KeyEvent, PointerEvent, SurfaceKind
from hands.surfaces import TypedTextTracker, structural_fingerprint

_LOGGER = get_logger(__name__)

SAME_SCREEN = "<same>"
PREVIOUS_SCREEN = "<previous>"
WILDCARD = "*"
EDITABLE_ROLES = ("textbox", "searchbox", "combobox", "listbox", "spinbutton")
SECRET_MASK_CHAR = "•"
DEFAULT_VIEWPORT = (1280, 800)
BLANK_LOCATION = Location(kind="url", value="about:blank", title="")

ScreenLayer = Literal["page", "overlay", "native"]
ActSource = Literal["automation", "human"]
InterruptTrigger = Literal["observe", "act"]


# ================================================================ screen definitions


@dataclass(frozen=True)
class FakeContext:
    """What a routing function sees: the current screen name and typed values keyed by node key."""

    screen: str
    values: Mapping[str, str]

    def value(self, key: str, default: str = "") -> str:
        return self.values.get(key, default)


TransitionTarget = str | Callable[[FakeContext], "str | FakeScreen"]
TransitionKey = tuple[str, str]


@dataclass
class FakeScreen:
    """One scripted screen. Nodes with an empty ref get 'n1', 'n2', ... ('d1', ... on overlay/native
    layers, so they never collide with the page underneath). A None location inherits the location of
    the screen underneath (or the last known one)."""

    name: str
    nodes: list[Node] = field(default_factory=list)
    location: Location | None = None
    dialogs: list[Dialog] = field(default_factory=list)
    transitions: dict[TransitionKey, TransitionTarget] = field(default_factory=dict)
    entry_points: list[str] = field(default_factory=list)
    select_options: dict[str, list[str]] = field(default_factory=dict)
    secret_fields: list[str] = field(default_factory=list)
    layer: ScreenLayer = "page"

    def __post_init__(self) -> None:
        ref_prefix = "n" if self.layer == "page" else "d"
        self.nodes = _assign_missing_refs(self.nodes, ref_prefix)
        duplicate_refs = _duplicates([node.ref for node in self.nodes])
        if duplicate_refs:
            log_failure(_LOGGER, "FakeScreen", "duplicate node refs", screen=self.name, refs=duplicate_refs)
            raise ValueError(f"screen '{self.name}' has duplicate node refs: {duplicate_refs}")

    def node_by_key(self, key: str) -> Node | None:
        """Node whose ref, name, or label equals `key`; editable controls win over their label text."""
        matches = [node for node in self.nodes if key in node_keys(node)]
        editable = [node for node in matches if node.role in EDITABLE_ROLES]
        preferred = editable or matches
        return preferred[0] if preferred else None


def fake_node(
    role: str,
    name: str = "",
    *,
    text: str | None = None,
    value: str | None = None,
    label: str | None = None,
    container: tuple[str, ...] = (),
    path: str = "",
    bounds: Rect | None = None,
    enabled: bool = True,
    ref: str = "",
) -> Node:
    """Convenience Node constructor for fake screens. `text` defaults to `name` for non-editable roles."""
    default_text = "" if role in EDITABLE_ROLES else name
    return Node(
        ref=ref,
        role=role,
        name=name,
        text=default_text if text is None else text,
        value=value,
        label=label,
        container_path=container,
        structural_path=path,
        bounds=bounds,
        enabled=enabled,
    )


def node_keys(node: Node) -> list[str]:
    """Keys a transition, select option, or secret field may use to refer to a node."""
    keys: list[str] = []
    for key in (node.ref, node.name, node.label):
        if key and key not in keys:
            keys.append(key)
    return keys


def _assign_missing_refs(nodes: Sequence[Node], prefix: str) -> list[Node]:
    return [
        node if node.ref else node.model_copy(update={"ref": f"{prefix}{index}"})
        for index, node in enumerate(nodes, start=1)
    ]


def _duplicates(items: Sequence[str]) -> list[str]:
    seen: list[str] = []
    repeated: list[str] = []
    for item in items:
        if item in seen and item not in repeated:
            repeated.append(item)
        seen.append(item)
    return repeated


def default_loading_screen() -> FakeScreen:
    return FakeScreen(
        name="loading",
        nodes=[fake_node("text", "Loading...", path="text[1]", bounds=Rect(x=12, y=12, width=80, height=18))],
    )


# ================================================================ recorded acts


@dataclass(frozen=True)
class RecordedAct:
    """One act() call as the fake saw it. `screen` is the screen displayed when the act started."""

    target: ActTarget
    action: Action
    screen: str
    result: ActResult
    source: ActSource = "automation"


@dataclass(frozen=True)
class _ObservedNode:
    owner_screen: str
    definition: Node


@dataclass(frozen=True)
class _Resolution:
    owner_screen: str | None = None
    node: Node | None = None
    error: str | None = None


# ================================================================ the surface


class FakeSurface:
    """Scripted Surface implementation. See the module docstring for semantics."""

    kind: SurfaceKind = "fake"

    def __init__(
        self,
        screens: Sequence[FakeScreen],
        initial: str,
        *,
        loading_screen: FakeScreen | None = None,
        clock: Callable[[], datetime] | None = None,
        viewport: tuple[int, int] = DEFAULT_VIEWPORT,
    ) -> None:
        self._screens: dict[str, FakeScreen] = {}
        for screen in screens:
            self.add_screen(screen)
        if initial not in self._screens:
            log_failure(_LOGGER, "FakeSurface.__init__", "unknown initial screen", initial=initial)
            raise ValueError(f"unknown initial screen '{initial}'")
        self._current = initial
        self._underlays: list[str] = []
        self._values: dict[tuple[str, str], str] = {}
        self._focus: tuple[str, str] | None = None
        self._observe_interrupts: list[str] = []
        self._act_interrupts: list[str] = []
        self._act_failures: list[str] = []
        self._pending_loading_observations = 0
        self._loading_screen = loading_screen or default_loading_screen()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._viewport = viewport
        self._last_location = BLANK_LOCATION
        self._last_observation: Observation | None = None
        self._observed_nodes: dict[str, _ObservedNode] = {}
        self._live_view = FakeLiveView(self)
        self.actions: list[RecordedAct] = []
        self.observation_count = 0
        self.closed = False

    # ------------------------------------------------------------ inspection helpers for tests

    @property
    def current_screen(self) -> str:
        return self._current

    @property
    def last_observation(self) -> Observation | None:
        return self._last_observation

    @property
    def screen_names(self) -> list[str]:
        return list(self._screens)

    def screen(self, name: str) -> FakeScreen | None:
        return self._screens.get(name)

    def value_of(self, key: str, screen: str | None = None) -> str | None:
        """Current value of the node with this ref/name/label on `screen` (default: current screen)."""
        screen_name = screen or self._current
        definition = self._screens.get(screen_name)
        node = definition.node_by_key(key) if definition else None
        if node is None:
            return None
        return self._values.get((screen_name, node.ref), node.value)

    # ------------------------------------------------------------ scripting

    def add_screen(self, screen: FakeScreen) -> None:
        """Register (or replace) a screen."""
        self._screens[screen.name] = screen

    def set_screen(self, name: str) -> None:
        """Jump straight to a screen, as if it had been navigated to (or popped up, for overlays)."""
        self._require_screen("FakeSurface.set_screen", name)
        self._show(name)

    def inject_next(self, screen_name: str, *, trigger: InterruptTrigger = "observe") -> None:
        """Show `screen_name` on the next observe(), or right after the next successful act()."""
        self._require_screen("FakeSurface.inject_next", screen_name)
        queue = self._observe_interrupts if trigger == "observe" else self._act_interrupts
        queue.append(screen_name)

    def delay_observations(self, count: int) -> None:
        """Make the next `count` observations return the loading screen (a slow page load)."""
        if count < 0:
            log_failure(_LOGGER, "FakeSurface.delay_observations", "negative count", count=count)
            raise ValueError("count must be >= 0")
        self._pending_loading_observations += count

    def fail_next_act(self, error: str = "simulated action failure") -> None:
        """Make the next act() return ActResult(ok=False, error=error) without touching state."""
        self._act_failures.append(error)

    def _require_screen(self, function_name: str, name: str) -> None:
        if name not in self._screens:
            log_failure(_LOGGER, function_name, "unknown screen", screen=name)
            raise ValueError(f"unknown screen '{name}'")

    # ------------------------------------------------------------ Surface protocol

    async def observe(self, include_screenshot: bool = True) -> Observation:
        self.observation_count += 1
        if self._pending_loading_observations > 0:
            self._pending_loading_observations -= 1
            layers = [self._loading_screen]
        else:
            self._apply_interrupt(self._observe_interrupts)
            layers = self._visible_layers()
        observation, observed_nodes = self._render(layers, include_screenshot)
        self._last_observation = observation
        self._observed_nodes = observed_nodes
        return observation

    async def act(self, target: ActTarget, action: Action) -> ActResult:
        return self.perform(target, action, source="automation")

    async def close(self) -> None:
        self.closed = True
        await self._live_view.stop()

    def live_view(self) -> FakeLiveView:
        return self._live_view

    # ------------------------------------------------------------ acting

    def perform(self, target: ActTarget, action: Action, source: ActSource = "automation") -> ActResult:
        """Synchronous act(); also used by FakeLiveView to apply human input."""
        screen_at_start = self._current
        result = self._perform_checked(target, action)
        if result.ok:
            self._apply_interrupt(self._act_interrupts)
        else:
            log_failure(
                _LOGGER, "FakeSurface.act", result.error or "act failed",
                target=target, action_kind=action.kind, screen=screen_at_start, source=source,
            )
        self.actions.append(RecordedAct(target, action, screen_at_start, result, source))
        return result

    def _perform_checked(self, target: ActTarget, action: Action) -> ActResult:
        if self.closed:
            return ActResult(ok=False, error="surface is closed")
        if self._act_failures:
            return ActResult(ok=False, error=self._act_failures.pop(0))
        if isinstance(action, OpenAction):
            return self._open(action.entry_point)
        resolution = self._resolve_target(target)
        if resolution.error:
            return ActResult(ok=False, error=resolution.error)
        effect_error = self._apply_effect(resolution, action)
        if effect_error:
            return ActResult(ok=False, error=effect_error)
        return self._follow_transition(resolution, action)

    def _resolve_target(self, target: ActTarget) -> _Resolution:
        if isinstance(target, NodeRef):
            return self._resolve_ref(target.ref)
        if isinstance(target, Point):
            return self._hit_test(target)
        return self._focused_resolution()

    def _resolve_ref(self, ref: str) -> _Resolution:
        if self._last_observation is None:
            return _Resolution(error="no observation yet; call observe() before acting on a ref")
        observed = self._observed_nodes.get(ref)
        if observed is None:
            return _Resolution(error=f"unknown ref '{ref}' in the latest observation")
        if observed.owner_screen not in self._visible_layer_names():
            return _Resolution(
                error=f"stale ref '{ref}': screen '{observed.owner_screen}' is no longer displayed "
                f"(now '{self._current}'); observe again"
            )
        return _Resolution(owner_screen=observed.owner_screen, node=observed.definition)

    def _hit_test(self, point: Point) -> _Resolution:
        """Topmost layer first, then the smallest node whose bounds contain the point."""
        for screen in reversed(self._visible_layers()):
            hits = [node for node in screen.nodes if node.bounds and _contains(node.bounds, point)]
            if hits:
                smallest = min(hits, key=lambda node: _area(node.bounds))
                return _Resolution(owner_screen=screen.name, node=smallest)
        return _Resolution()

    def _focused_resolution(self) -> _Resolution:
        if self._focus is None or self._focus[0] not in self._visible_layer_names():
            return _Resolution()
        owner_screen, ref = self._focus
        node = next((node for node in self._screens[owner_screen].nodes if node.ref == ref), None)
        return _Resolution(owner_screen=owner_screen, node=node)

    def _apply_effect(self, resolution: _Resolution, action: Action) -> str | None:
        """Mutate typed values / focus. Returns an error message, or None."""
        owner_screen, node = resolution.owner_screen, resolution.node
        if node is None or owner_screen is None:
            return "select needs a target node" if isinstance(action, SelectAction) else None
        if isinstance(action, TypeAction | ClickAction | SelectAction):
            self._focus = (owner_screen, node.ref)
        if isinstance(action, TypeAction):
            self._type_into(owner_screen, node, action)
        if isinstance(action, SelectAction):
            return self._select_option(owner_screen, node, action.option)
        return None

    def _type_into(self, owner_screen: str, node: Node, action: TypeAction) -> None:
        if node.role not in EDITABLE_ROLES or not node.enabled:
            return
        previous = self._values.get((owner_screen, node.ref), node.value or "")
        self._values[(owner_screen, node.ref)] = action.text if action.clear_first else previous + action.text

    def _select_option(self, owner_screen: str, node: Node, option: str) -> str | None:
        if node.role not in ("combobox", "listbox"):
            return f"node '{node.ref}' with role '{node.role}' is not selectable"
        allowed_options = self._options_for(owner_screen, node)
        if allowed_options is not None and option not in allowed_options:
            return f"option '{option}' not found; available: {allowed_options}"
        self._values[(owner_screen, node.ref)] = option
        return None

    def _options_for(self, owner_screen: str, node: Node) -> list[str] | None:
        options_by_key = self._screens[owner_screen].select_options
        return next((options_by_key[key] for key in node_keys(node) if key in options_by_key), None)

    # ------------------------------------------------------------ transitions

    def _follow_transition(self, resolution: _Resolution, action: Action) -> ActResult:
        if resolution.owner_screen not in (None, self._current):
            return ActResult(ok=True)  # a node underneath a modal overlay: the click is swallowed
        target = self._find_transition(resolution.node, action)
        if target is None:
            return ActResult(ok=True)
        destination = self._evaluate_target(target)
        return self._go_to(destination)

    def _find_transition(self, node: Node | None, action: Action) -> TransitionTarget | None:
        transitions = self._screens[self._current].transitions
        candidate_node_keys = [*(node_keys(node) if node else []), WILDCARD]
        for node_key in candidate_node_keys:
            for action_key in _action_keys(action):
                if (node_key, action_key) in transitions:
                    return transitions[(node_key, action_key)]
        return None

    def _evaluate_target(self, target: TransitionTarget) -> str:
        if isinstance(target, str):
            return target
        routed = target(self._context())
        if isinstance(routed, FakeScreen):
            self.add_screen(routed)
            return routed.name
        return routed

    def _context(self) -> FakeContext:
        values: dict[str, str] = {}
        for screen in self._visible_layers():
            for node in screen.nodes:
                node_value = self._values.get((screen.name, node.ref), node.value)
                if node_value is not None:
                    values.update({key: node_value for key in node_keys(node)})
        return FakeContext(screen=self._current, values=values)

    def _go_to(self, destination: str) -> ActResult:
        if destination == SAME_SCREEN:
            return ActResult(ok=True)
        if destination == PREVIOUS_SCREEN:
            return self._return_to_underlay()
        if destination not in self._screens:
            return ActResult(ok=False, error=f"transition leads to unknown screen '{destination}'")
        self._show(destination)
        return ActResult(ok=True)

    def _return_to_underlay(self) -> ActResult:
        if not self._underlays:
            return ActResult(ok=False, error=f"screen '{self._current}' has no previous screen to return to")
        self._current = self._underlays.pop()
        return ActResult(ok=True)

    def _show(self, name: str) -> None:
        """Navigate to a page (clearing overlays and its typed values) or pop up an overlay/native screen."""
        if self._screens[name].layer == "page":
            self._underlays.clear()
            self._reset_values(name)
            self._focus = None
        else:
            self._underlays.append(self._current)
        self._current = name

    def _reset_values(self, screen_name: str) -> None:
        for key in [key for key in self._values if key[0] == screen_name]:
            del self._values[key]

    def _apply_interrupt(self, queue: list[str]) -> None:
        if queue:
            self._show(queue.pop(0))

    def _open(self, entry_point: str) -> ActResult:
        screen = next(
            (screen for screen in self._screens.values() if _matches_entry_point(entry_point, screen)), None
        )
        if screen is None:
            return ActResult(ok=False, error=f"no screen serves entry point '{entry_point}'")
        self._show(screen.name)
        return ActResult(ok=True)

    # ------------------------------------------------------------ rendering

    def _visible_layers(self) -> list[FakeScreen]:
        """Bottom-to-top screens that are drawn: a page, then any overlays stacked on it."""
        current = self._screens[self._current]
        if current.layer != "overlay":
            return [current]
        layers = [current]
        for underlay_name in reversed(self._underlays):
            underlay = self._screens[underlay_name]
            layers.insert(0, underlay)
            if underlay.layer != "overlay":
                break
        return layers

    def _visible_layer_names(self) -> list[str]:
        return [screen.name for screen in self._visible_layers()]

    def _resolve_location(self, layers: Sequence[FakeScreen]) -> Location:
        """Topmost screen with a location wins: drawn layers, the current screen, then underlays."""
        candidates = [
            *reversed(layers),
            self._screens[self._current],
            *(self._screens[name] for name in reversed(self._underlays)),
        ]
        location = next((screen.location for screen in candidates if screen.location), self._last_location)
        self._last_location = location
        return location

    def _render(
        self, layers: Sequence[FakeScreen], include_screenshot: bool
    ) -> tuple[Observation, dict[str, _ObservedNode]]:
        observed: dict[str, _ObservedNode] = {}
        rendered_nodes: list[Node] = []
        for layer_index, screen in enumerate(layers):
            for definition in screen.nodes:
                ref = definition.ref if definition.ref not in observed else f"{definition.ref}.{layer_index}"
                observed[ref] = _ObservedNode(owner_screen=screen.name, definition=definition)
                rendered_nodes.append(self._render_node(screen, definition, ref))
        observation = Observation(
            observed_at=self._clock(),
            location=self._resolve_location(layers),
            nodes=rendered_nodes,
            dialogs=[dialog for screen in layers for dialog in screen.dialogs],
            fingerprint=structural_fingerprint(rendered_nodes),
            screenshot_png=blank_png(*self._viewport) if include_screenshot else None,
        )
        return observation, observed

    def _render_node(self, screen: FakeScreen, definition: Node, ref: str) -> Node:
        stored_value = self._values.get((screen.name, definition.ref), definition.value)
        is_secret = any(key in screen.secret_fields for key in node_keys(definition))
        shown_value = SECRET_MASK_CHAR * len(stored_value) if is_secret and stored_value else stored_value
        return definition.model_copy(
            update={
                "ref": ref,
                "value": shown_value,
                "focused": self._focus == (screen.name, definition.ref),
            }
        )


def _action_keys(action: Action) -> list[str]:
    if isinstance(action, PressAction):
        return [f"press:{action.key}", "press"]
    return [action.kind]


def _matches_entry_point(entry_point: str, screen: FakeScreen) -> bool:
    requested_path = urlsplit(entry_point).path
    for candidate in screen.entry_points:
        if entry_point == candidate or (requested_path and requested_path == urlsplit(candidate).path):
            return True
    return False


def _contains(bounds: Rect, point: Point) -> bool:
    return bounds.x <= point.x <= bounds.x + bounds.width and bounds.y <= point.y <= bounds.y + bounds.height


def _area(bounds: Rect | None) -> float:
    return bounds.width * bounds.height if bounds else 0.0


# ================================================================ live view


class FakeLiveView:
    """LiveViewTransport double. Records injected input and emits frames on demand.

    When bound to a FakeSurface (the default for `surface.live_view()`), injected input also drives the
    fake the way a human would: pointer clicks click the node under the point, wheel events scroll,
    printable keys type into the focused node, and named keys (Enter, Escape, Tab, ...) are pressed.
    Such acts are recorded in `surface.actions` with source="human".
    """

    def __init__(self, surface: FakeSurface | None = None) -> None:
        self._surface = surface
        self._on_frame: FrameHandler | None = None
        self._typed_text = TypedTextTracker()
        self.pointer_events: list[PointerEvent] = []
        self.key_events: list[KeyEvent] = []
        self.frames_emitted = 0
        self.running = False

    async def start(self, on_frame: FrameHandler) -> None:
        self._on_frame = on_frame
        self.running = True

    async def stop(self) -> None:
        self._on_frame = None
        self.running = False

    async def emit_frame(self, frame: bytes | None = None) -> bool:
        """Push one frame (default: a blank PNG) to the handler. False if not started."""
        if not self.running or self._on_frame is None:
            log_failure(_LOGGER, "FakeLiveView.emit_frame", "live view is not started")
            return False
        await self._on_frame(frame if frame is not None else blank_png(*DEFAULT_VIEWPORT))
        self.frames_emitted += 1
        return True

    async def inject_pointer(self, event: PointerEvent) -> None:
        self.pointer_events.append(event)
        action = _pointer_action(event)
        if self._surface is not None and action is not None:
            self._surface.perform(Point(x=event.x, y=event.y), action, source="human")

    async def inject_key(self, event: KeyEvent) -> None:
        self.key_events.append(event)
        if self._surface is None:
            return
        action = self._key_action(event)
        if action is not None:
            self._surface.perform(None, action, source="human")

    def _key_action(self, event: KeyEvent) -> Action | None:
        if event.type == "up":
            self._typed_text.on_up(event)
            return None
        text = (
            self._typed_text.text_for_down(event, command_modifier=False)
            if event.type == "down"
            else self._typed_text.text_for_char(event, command_modifier=False)
        )
        if text:
            return TypeAction(text=text, clear_first=False)
        if event.type == "down" and len(event.key) > 1:
            return PressAction(key=event.key)
        return None


def _pointer_action(event: PointerEvent) -> Action | None:
    if event.type == "click":
        return ClickAction()
    if event.type == "wheel":
        return ScrollAction(direction="up" if event.delta_y < 0 else "down")
    return None



# ================================================================ blank screenshot


@lru_cache(maxsize=8)
def blank_png(width: int, height: int) -> bytes:
    """A valid white grayscale PNG of the given size, built without any imaging library."""
    width, height = max(1, width), max(1, height)
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    scanlines = (b"\x00" + b"\xff" * width) * height
    return b"".join(
        [b"\x89PNG\r\n\x1a\n", _png_chunk(b"IHDR", header), _png_chunk(b"IDAT", zlib.compress(scanlines, 9)),
         _png_chunk(b"IEND", b"")]
    )


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", checksum)


# ================================================================ CoreOne fake


@dataclass(frozen=True)
class CoreOneTenant:
    """Per-tenant UI differences of the CoreOne mock (PLAN.md tenant table)."""

    tenant_id: str
    brand: str
    member_label: str
    search_button: str
    savings_name: str
    share_columns: tuple[str, ...]


COREONE_TENANTS: dict[str, CoreOneTenant] = {
    "lakeside": CoreOneTenant(
        tenant_id="lakeside",
        brand="Lakeside Community CU",
        member_label="Member Number",
        search_button="Search",
        savings_name="Regular Savings",
        share_columns=("Share ID", "Description", "Balance", "Available"),
    ),
    "prairie": CoreOneTenant(
        tenant_id="prairie",
        brand="Prairie Federal CU",
        member_label="Account Number",
        search_button="Find",
        savings_name="Share Savings",
        share_columns=("Share ID", "Balance", "Description", "Available"),
    ),
}

COREONE_USER = "teller1"
COREONE_RESTRICTED_MEMBER = "40300"
COREONE_OPENED_SHARE_ID = "0007"
TOP_CONTAINER = ("frame:top",)
NAV_CONTAINER = ("frame:nav",)
CONTENT_CONTAINER = ("frame:content",)
NATIVE_DIALOG_CONTAINER = ("dialog:native",)
_SAVINGS = "<savings>"


@dataclass(frozen=True)
class _Share:
    share_id: str
    product: str
    balance: str


@dataclass(frozen=True)
class _Member:
    number: str
    name: str
    status: str
    shares: tuple[_Share, ...]


COREONE_MEMBERS: tuple[_Member, ...] = (
    _Member("10001", "Avery Quinn", "Active", (
        _Share("0001", _SAVINGS, "1,250.00"), _Share("0002", "Checking", "310.45"),
        _Share("0003", "Holiday Club", "85.00"),
    )),
    _Member("10002", "Jordan Lee", "Active", (
        _Share("0001", _SAVINGS, "9,870.12"), _Share("0002", "Checking", "0.00"),
    )),
)

# ---------------------------------------------------------------- layout helper

_ROW_HEIGHT = 26.0
_TEXT_HEIGHT = 18.0
_CHAR_WIDTH = 7.0
_PAGE_RECT = Rect(x=0, y=0, width=1280, height=800)
_TOP_RECT = Rect(x=0, y=0, width=1280, height=60)
_NAV_RECT = Rect(x=0, y=60, width=180, height=740)
_CONTENT_RECT = Rect(x=180, y=60, width=1100, height=740)


@dataclass(frozen=True)
class _Control:
    role: str
    name: str = ""
    value: str | None = None


@dataclass(frozen=True)
class _Cell:
    text: str = ""
    controls: tuple[_Control, ...] = ()
    header: bool = False


class _Canvas:
    """Lays out nodes top-to-bottom inside one frame, producing role-indexed structural paths and
    page-level bounds the way the browser surface reports them for legacy table layouts."""

    def __init__(self, container: tuple[str, ...], frame: Rect, *, first_table_index: int = 0) -> None:
        self.container = container
        self.frame = frame
        self.nodes: list[Node] = []
        self._cursor_y = frame.y + 12
        self._role_counts: dict[tuple[str, str], int] = {("", "table"): first_table_index}

    def text(self, content: str, *, at: tuple[float, float] | None = None) -> None:
        self._leaf("text", content, at, _text_width(content))

    def link(self, name: str, *, at: tuple[float, float] | None = None) -> None:
        self._leaf("link", name, at, _text_width(name))

    def table(self, rows: Sequence[Sequence[_Cell]], column_widths: Sequence[float]) -> None:
        table_path = self._next_path("", "table")
        left, top = self.frame.x + 12, self._cursor_y
        self._add("table", "", table_path, Rect(x=left, y=top, width=sum(column_widths),
                                                height=_ROW_HEIGHT * len(rows)))
        for row_index, row in enumerate(rows):
            self._table_row(table_path, row, column_widths, left, top + row_index * _ROW_HEIGHT)
        self._cursor_y = top + _ROW_HEIGHT * len(rows) + 12

    def _leaf(self, role: str, content: str, at: tuple[float, float] | None, width: float) -> None:
        x, y = (self.frame.x + at[0], self.frame.y + at[1]) if at else (self.frame.x + 12, self._cursor_y)
        self._add(role, content, self._next_path("", role), Rect(x=x, y=y, width=width, height=_TEXT_HEIGHT),
                  text=content)
        if at is None:
            self._cursor_y += _TEXT_HEIGHT + 10

    def _table_row(
        self, table_path: str, cells: Sequence[_Cell], column_widths: Sequence[float], left: float, top: float
    ) -> None:
        row_path = self._next_path(table_path, "row")
        self._add("row", "", row_path, Rect(x=left, y=top, width=sum(column_widths), height=_ROW_HEIGHT))
        cell_left, label_text = left, None
        for cell_index, cell in enumerate(cells):
            is_last = cell_index == len(cells) - 1
            width = sum(column_widths[cell_index:]) if is_last else column_widths[cell_index]
            role = "columnheader" if cell.header else "cell"
            cell_path = self._next_path(row_path, role)
            self._add(role, cell.text, cell_path, Rect(x=cell_left, y=top, width=width, height=_ROW_HEIGHT),
                      text=cell.text)
            self._cell_controls(cell_path, cell.controls, cell_left, top, label_text)
            label_text = cell.text or label_text
            cell_left += width

    def _cell_controls(
        self, cell_path: str, controls: Sequence[_Control], left: float, top: float, label: str | None
    ) -> None:
        control_left = left + 4
        for control in controls:
            width = _control_width(control)
            is_field = control.role in EDITABLE_ROLES
            self._add(control.role, control.name, self._next_path(cell_path, control.role),
                      Rect(x=control_left, y=top + 3, width=width, height=_ROW_HEIGHT - 6),
                      text="" if is_field else control.name, value=control.value,
                      label=label if is_field else None)
            control_left += width + 6

    def _next_path(self, parent: str, role: str) -> str:
        index = self._role_counts.get((parent, role), 0) + 1
        self._role_counts[(parent, role)] = index
        segment = f"{role}[{index}]"
        return f"{parent}/{segment}" if parent else segment

    def _add(self, role: str, name: str, path: str, bounds: Rect, *, text: str = "",
             value: str | None = None, label: str | None = None) -> None:
        self.nodes.append(Node(ref="", role=role, name=name, text=text, value=value, label=label,
                               container_path=self.container, structural_path=path, bounds=bounds))


def _text_width(content: str) -> float:
    return len(content) * _CHAR_WIDTH + 4


def _control_width(control: _Control) -> float:
    fixed_widths = {"textbox": 180.0, "combobox": 200.0}
    return fixed_widths.get(control.role, _text_width(control.name) + 20)


# ---------------------------------------------------------------- screens


@dataclass(frozen=True)
class _CoreOneSite:
    tenant: CoreOneTenant
    base_url: str
    password: str

    def url(self, path: str) -> str:
        return f"{self.base_url}/t/{self.tenant.tenant_id}{path}"

    @property
    def main_location(self) -> Location:
        return Location(kind="url", value=self.url("/main"),
                        title=f"CoreOne Member Services - {self.tenant.brand}")

    def product(self, product: str) -> str:
        return self.tenant.savings_name if product == _SAVINGS else product

    def share_types(self) -> list[str]:
        return [self.tenant.savings_name, "Money Market", "Share Certificate"]


def _frame_chrome_nodes(site: _CoreOneSite) -> list[Node]:
    top = _Canvas(TOP_CONTAINER, _TOP_RECT)
    top.text(site.tenant.brand, at=(12, 8))
    top.text(f"Signed on as {COREONE_USER}", at=(12, 34))
    top.link("Sign Off", at=(1190, 34))
    nav = _Canvas(NAV_CONTAINER, _NAV_RECT)
    for link_name in ("Member Inquiry", "Open Share Account", "Reports"):
        nav.link(link_name)
    return [*top.nodes, *nav.nodes]


def _frame_chrome_transitions() -> dict[TransitionKey, TransitionTarget]:
    return {
        ("Sign Off", "click"): "login",
        ("Member Inquiry", "click"): "inquiry",
        ("Open Share Account", "click"): "inquiry",
        ("Reports", "click"): SAME_SCREEN,
    }


def _main_screen(
    site: _CoreOneSite,
    name: str,
    content: _Canvas,
    transitions: dict[TransitionKey, TransitionTarget] | None = None,
    select_options: dict[str, list[str]] | None = None,
) -> FakeScreen:
    return FakeScreen(
        name=name,
        location=site.main_location,
        nodes=[*_frame_chrome_nodes(site), *content.nodes],
        transitions={**_frame_chrome_transitions(), **(transitions or {})},
        select_options=select_options or {},
    )


def _content() -> _Canvas:
    return _Canvas(CONTENT_CONTAINER, _CONTENT_RECT)


def _blank_screen() -> FakeScreen:
    return FakeScreen(name="blank", location=BLANK_LOCATION)


def _login_screen(site: _CoreOneSite, *, failed: bool) -> FakeScreen:
    page = _Canvas((), _PAGE_RECT)
    page.text("CoreOne Member Services")
    page.text(site.tenant.brand)
    if failed:
        page.text("Invalid User ID or Password.")
    page.table([
        [_Cell("User ID"), _Cell(controls=(_Control("textbox"),))],
        [_Cell("Password"), _Cell(controls=(_Control("textbox"),))],
        [_Cell(controls=(_Control("button", "Sign On"),))],
    ], (140, 220))
    page.text("Northwind Core Systems - CoreOne 7.4")
    route = _login_router(site)
    return FakeScreen(
        name="login_failed" if failed else "login",
        location=Location(kind="url", value=site.url("/login"), title=f"CoreOne Sign On - {site.tenant.brand}"),
        nodes=page.nodes,
        transitions={("Sign On", "click"): route, ("Password", "press:Enter"): route},
        entry_points=[] if failed else [site.url("/login")],
        secret_fields=["Password"],
    )


def _login_router(site: _CoreOneSite) -> Callable[[FakeContext], str]:
    def route(context: FakeContext) -> str:
        credentials_ok = context.value("User ID") == COREONE_USER and context.value("Password") == site.password
        return "main" if credentials_ok else "login_failed"

    return route


def _welcome_screen(site: _CoreOneSite) -> FakeScreen:
    content = _content()
    content.text("Select a function from the menu.")
    return _main_screen(site, "main", content)


def _inquiry_screen(site: _CoreOneSite, *, error: str | None = None, typed: str | None = None) -> FakeScreen:
    content = _content()
    content.text("Member Inquiry")
    if error:
        content.text(error)
    content.table([
        [_Cell(site.tenant.member_label), _Cell(controls=(_Control("textbox", value=typed),))],
        [_Cell(controls=(_Control("button", site.tenant.search_button),))],
    ], (160, 240))
    route = _inquiry_router(site)
    return _main_screen(site, "inquiry_invalid" if error else "inquiry", content, {
        (site.tenant.search_button, "click"): route,
        (site.tenant.member_label, "press:Enter"): route,
    })


def _inquiry_router(site: _CoreOneSite) -> Callable[[FakeContext], str | FakeScreen]:
    known_numbers = [member.number for member in COREONE_MEMBERS]

    def route(context: FakeContext) -> str | FakeScreen:
        member_number = context.value(site.tenant.member_label).strip()
        if not member_number.isdigit():
            return _inquiry_screen(site, error="Member number must be numeric.", typed=member_number)
        if member_number in known_numbers:
            return f"member_{member_number}"
        if member_number == COREONE_RESTRICTED_MEMBER:
            return "member_restricted"
        return _message_screen(site, "member_not_found", f"No member found for number {member_number}.")

    return route


def _member_screen(site: _CoreOneSite, member: _Member) -> FakeScreen:
    content = _content()
    content.text("Member Detail")
    content.table([
        [_Cell(site.tenant.member_label), _Cell(member.number)],
        [_Cell("Name"), _Cell(member.name)],
        [_Cell("Status"), _Cell(member.status)],
    ], (160, 240))
    content.text("Shares")
    content.table(
        [[_Cell(column, header=True) for column in site.tenant.share_columns],
         *(_share_row(site, share) for share in member.shares)],
        (100, 180, 120, 120),
    )
    content.table([[_Cell(controls=(_Control("button", "Open Share"), _Control("link", "New Inquiry")))]],
                  (400,))
    return _main_screen(site, f"member_{member.number}", content, {
        ("Open Share", "click"): f"open_share_{member.number}",
        ("New Inquiry", "click"): "inquiry",
    })


def _share_row(site: _CoreOneSite, share: _Share) -> list[_Cell]:
    values_by_column = {
        "Share ID": share.share_id,
        "Description": site.product(share.product),
        "Balance": share.balance,
        "Available": share.balance,
    }
    return [_Cell(values_by_column[column]) for column in site.tenant.share_columns]


def _message_screen(site: _CoreOneSite, name: str, message: str, *, link: str = "New Inquiry",
                    link_target: str = "inquiry") -> FakeScreen:
    content = _content()
    content.text(message)
    content.link(link)
    return _main_screen(site, name, content, {(link, "click"): link_target})


def _open_share_screen(site: _CoreOneSite, member: _Member) -> FakeScreen:
    content = _content()
    content.text(f"Open Share Account - Member {member.number}")
    content.table([
        [_Cell("Share Type"), _Cell(controls=(_Control("combobox", value=site.share_types()[0]),))],
        [_Cell("Initial Deposit"), _Cell(controls=(_Control("textbox"),))],
        [_Cell("Nickname"), _Cell(controls=(_Control("textbox"),))],
        [_Cell(controls=(_Control("button", "Continue"), _Control("button", "Cancel")))],
    ], (160, 240))
    return _main_screen(
        site, f"open_share_{member.number}", content,
        {("Continue", "click"): _review_router(site, member), ("Cancel", "click"): f"member_{member.number}"},
        select_options={"Share Type": site.share_types()},
    )


def _review_router(site: _CoreOneSite, member: _Member) -> Callable[[FakeContext], FakeScreen]:
    def route(context: FakeContext) -> FakeScreen:
        content = _content()
        content.text("Confirm New Share")
        content.table([
            [_Cell(site.tenant.member_label), _Cell(member.number)],
            [_Cell("Share Type"), _Cell(context.value("Share Type"))],
            [_Cell("Initial Deposit"), _Cell(context.value("Initial Deposit"))],
            [_Cell("Nickname"), _Cell(context.value("Nickname"))],
            [_Cell(controls=(_Control("button", "Submit"), _Control("button", "Cancel")))],
        ], (160, 240))
        return _main_screen(site, f"review_{member.number}", content, {
            ("Submit", "click"): f"share_opened_{member.number}",
            ("Cancel", "click"): f"member_{member.number}",
        })

    return route


def _maintenance_overlay() -> FakeScreen:
    notice_text = "Scheduled maintenance tonight 22:00-23:00. Some functions may be unavailable."
    overlay = _Canvas(CONTENT_CONTAINER, Rect(x=380, y=180, width=700, height=200), first_table_index=50)
    overlay.table([[_Cell("System Notice")], [_Cell(notice_text)],
                   [_Cell(controls=(_Control("button", "Acknowledge"),))]], (640,))
    return FakeScreen(
        name="maintenance_notice",
        layer="overlay",
        nodes=overlay.nodes,
        dialogs=[Dialog(title="System Notice", text=notice_text)],
        transitions={("Acknowledge", "click"): PREVIOUS_SCREEN},
    )


def _identity_check_overlay() -> FakeScreen:
    question = "Security question: What is the member's mother's maiden name?"
    box = Rect(x=380, y=180, width=600, height=160)
    nodes = [
        fake_node("dialog", "Verify Member Identity", text="", container=CONTENT_CONTAINER, path="dialog[1]",
                  bounds=box),
        fake_node("text", question, container=CONTENT_CONTAINER, path="dialog[1]/text[1]",
                  bounds=Rect(x=392, y=200, width=_text_width(question), height=_TEXT_HEIGHT)),
        fake_node("textbox", label="Answer", container=CONTENT_CONTAINER, path="dialog[1]/textbox[1]",
                  bounds=Rect(x=392, y=240, width=180, height=20)),
        fake_node("button", "Verify", container=CONTENT_CONTAINER, path="dialog[1]/button[1]",
                  bounds=Rect(x=392, y=290, width=62, height=22)),
        fake_node("button", "Cancel", container=CONTENT_CONTAINER, path="dialog[1]/button[2]",
                  bounds=Rect(x=462, y=290, width=62, height=22)),
    ]

    def verify(context: FakeContext) -> str:
        return PREVIOUS_SCREEN if context.value("Answer").strip() else SAME_SCREEN

    return FakeScreen(
        name="identity_check",
        layer="overlay",
        nodes=nodes,
        dialogs=[Dialog(title="Verify Member Identity", text=question)],
        transitions={("Verify", "click"): verify, ("Cancel", "click"): "inquiry"},
    )


def native_alert_screen(name: str, message: str) -> FakeScreen:
    """A JS alert() as the browser surface reports it: synthetic dialog + OK button, page hidden."""
    return FakeScreen(
        name=name,
        layer="native",
        nodes=[
            fake_node("dialog", message, container=NATIVE_DIALOG_CONTAINER, path="dialog[1]"),
            fake_node("button", "OK", container=NATIVE_DIALOG_CONTAINER, path="dialog[1]/button[1]"),
        ],
        dialogs=[Dialog(title="alert", text=message, native=True)],
        transitions={
            ("OK", "click"): PREVIOUS_SCREEN,
            (WILDCARD, "press:Enter"): PREVIOUS_SCREEN,
            (WILDCARD, "press:Escape"): PREVIOUS_SCREEN,
        },
    )


def _loading_screen(site: _CoreOneSite) -> FakeScreen:
    content = _content()
    content.text("Loading...")
    return FakeScreen(name="loading", nodes=[*_frame_chrome_nodes(site), *content.nodes])


def _coreone_screens(site: _CoreOneSite) -> list[FakeScreen]:
    screens = [
        _blank_screen(),
        _login_screen(site, failed=False),
        _login_screen(site, failed=True),
        _welcome_screen(site),
        _inquiry_screen(site),
        _message_screen(site, "member_restricted", "ACCESS DENIED: Member record is restricted (code 403-R)"),
        _message_screen(site, "session_expired", "Your session has expired. Please sign on again.",
                        link="Sign On", link_target="login"),
        _message_screen(site, "app_error", "Internal Error. Reference ID ERR-5521."),
        _maintenance_overlay(),
        _identity_check_overlay(),
        native_alert_screen("native_alert", "Printer queue offline"),
    ]
    for member in COREONE_MEMBERS:
        screens.append(_member_screen(site, member))
        screens.append(_open_share_screen(site, member))
        screens.append(_message_screen(
            site, f"share_opened_{member.number}",
            f"Share {COREONE_OPENED_SHARE_ID} opened for member {member.number}.",
        ))
    return screens


def coreone_fake(
    tenant: str = "lakeside",
    *,
    base_url: str = "http://coreone.test",
    password: str | None = None,
    initial: str = "blank",
    clock: Callable[[], datetime] | None = None,
) -> FakeSurface:
    """A FakeSurface modelling CoreOne Member Services (PLAN.md) for one tenant.

    Starts on about:blank; open `{base_url}/t/{tenant}/login` first. Sign on as `teller1` with the
    password from `password`, else env HANDS_DEMO_PASSWORD, else 'demo-only-password'.

    Screens: blank, login, login_failed, main (frameset), inquiry, inquiry_invalid (non-numeric input),
    member_10001, member_10002, member_restricted (40300), member_not_found (any other number),
    open_share_<n> -> review_<n> -> share_opened_<n>, plus injectable faults: session_expired,
    app_error, maintenance_notice (in-page overlay), identity_check (overlay, needs a human answer),
    native_alert (JS alert), and a 'loading' screen used by delay_observations().
    After sign-on the top-level URL stays at /main (it is a frameset); content changes inside
    container ('frame:content',), navigation links live in ('frame:nav',), the banner in ('frame:top',).
    """
    tenant_config = COREONE_TENANTS.get(tenant)
    if tenant_config is None:
        log_failure(_LOGGER, "coreone_fake", "unknown tenant", tenant=tenant)
        raise ValueError(f"unknown CoreOne tenant '{tenant}'; known: {sorted(COREONE_TENANTS)}")
    resolved_password = password or os.environ.get("HANDS_DEMO_PASSWORD") or "demo-only-password"
    site = _CoreOneSite(tenant=tenant_config, base_url=base_url.rstrip("/"), password=resolved_password)
    return FakeSurface(_coreone_screens(site), initial=initial, loading_screen=_loading_screen(site), clock=clock)
