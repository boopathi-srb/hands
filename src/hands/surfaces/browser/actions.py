"""Perform surface-neutral actions on the live page. Never raises for UI errors: every failure is an
ActResult(ok=False, error=...) logged with context. Typed text is never logged, only its length.

Targets
- NodeRef: resolved through the latest observation's handle (CDP backend node id). Clicks scroll the
  node into view, re-read its border box, and click its center with page.mouse, which works across
  frames because box models are page-level.
- Point: page coordinates, clicked as-is.
- None: the currently focused element (type/press) or the viewport center (scroll).
While a native dialog is open only OK/Cancel clicks, prompt typing, and Enter/Escape are accepted.
"""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from typing import Any

from playwright.async_api import Page

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
from hands.surfaces.browser.cdp import CdpCaller
from hands.surfaces.browser.geometry import quad_to_rect
from hands.surfaces.browser.guard import Guarded, run_guarded
from hands.surfaces.browser.native_dialogs import NativeDialogKeeper
from hands.surfaces.browser.navigation import NavigationTracker
from hands.surfaces.browser.settle import SettleConfig
from hands.surfaces.browser.snapshot import NodeHandle

_LOGGER = get_logger(__name__)

WHEEL_PIXELS_PER_STEP = 100
_SELECT_OBJECT_GROUP = "hands-select"

# Selects an <option> by visible text (whitespace-collapsed, exact then case-insensitive). change/input
# are dispatched on a timer so an onchange alert() cannot block this CDP call.
SELECT_OPTION_JS = """function (optionText) {
  const normalize = (text) => (text || '').replace(/\\s+/g, ' ').trim();
  if (this.tagName !== 'SELECT') { return {status: 'not_select', options: []}; }
  const options = Array.from(this.options);
  const wanted = normalize(optionText);
  const match = options.find((option) => normalize(option.text) === wanted)
    || options.find((option) => normalize(option.text).toLowerCase() === wanted.toLowerCase());
  if (!match) { return {status: 'no_match', options: options.map((option) => normalize(option.text))}; }
  this.focus();
  match.selected = true;
  const select = this;
  setTimeout(() => {
    select.dispatchEvent(new Event('input', {bubbles: true}));
    select.dispatchEvent(new Event('change', {bubbles: true}));
  }, 0);
  return {status: 'selected', options: []};
}"""


@dataclass(frozen=True)
class ResolvedTarget:
    handle: NodeHandle | None = None
    point: Point | None = None
    error: str | None = None


def resolve_target(target: ActTarget, handles: Mapping[str, NodeHandle]) -> ResolvedTarget:
    """Map an ActTarget onto the latest observation's handles. Pure."""
    if isinstance(target, Point):
        return ResolvedTarget(point=target)
    if not isinstance(target, NodeRef):
        return ResolvedTarget()
    if not handles:
        return ResolvedTarget(error="no observation yet; call observe() before acting on a ref")
    handle = handles.get(target.ref)
    if handle is None:
        return ResolvedTarget(error=f"unknown ref '{target.ref}' in the latest observation")
    if handle.native_control is not None:
        return ResolvedTarget(error=f"ref '{target.ref}' belongs to a native dialog that is no longer open")
    return ResolvedTarget(handle=handle)


def _failure(message: str) -> ActResult:
    return ActResult(ok=False, error=message)


class BrowserActions:
    def __init__(
        self,
        page: Page,
        cdp: CdpCaller,
        dialogs: NativeDialogKeeper,
        config: SettleConfig,
        navigations: NavigationTracker | None = None,
    ) -> None:
        self._page = page
        self._cdp = cdp
        self._dialogs = dialogs
        self._config = config
        self._navigations = navigations

    async def perform(self, target: ActTarget, action: Action, handles: Mapping[str, NodeHandle]) -> ActResult:
        result = await self._dispatch(target, action, handles)
        if self._navigations is not None:
            self._navigations.mark_action()  # lets the next settle catch navigations this action starts
        if not result.ok:
            log_failure(_LOGGER, "BrowserActions.perform", result.error or "action failed",
                        target=target, action_kind=action.kind, url=self._page.url,
                        **_redacted_action_details(action))
        return result

    async def _dispatch(self, target: ActTarget, action: Action, handles: Mapping[str, NodeHandle]) -> ActResult:
        if self._dialogs.has_pending_dialog:
            return await self._act_on_native_dialog(target, action, handles)
        if isinstance(action, OpenAction):
            return await self._open(action)
        resolved = resolve_target(target, handles)
        if resolved.error:
            return _failure(resolved.error)
        if isinstance(action, ClickAction):
            return await self._click(resolved)
        if isinstance(action, TypeAction):
            return await self._type(resolved, action)
        if isinstance(action, PressAction):
            return await self._press(resolved, action)
        if isinstance(action, SelectAction):
            return await self._select(resolved, action)
        return await self._scroll(resolved, action)

    # ------------------------------------------------------------ individual actions

    async def _open(self, action: OpenAction) -> ActResult:
        navigation = self._page.goto(action.entry_point, wait_until="commit",
                                     timeout=self._config.navigation_timeout_ms)
        return await self._input("open", navigation, timeout_ms=self._config.navigation_timeout_ms + 1_000)

    async def _click(self, resolved: ResolvedTarget) -> ActResult:
        point = await self._point_for(resolved)
        if isinstance(point, str):
            return _failure(point)
        if point is None:
            return _failure("click needs a node ref or a point")
        return await self._input("click", self._page.mouse.click(point.x, point.y))

    async def _type(self, resolved: ResolvedTarget, action: TypeAction) -> ActResult:
        if resolved.handle is not None or resolved.point is not None:
            focused = await self._click(resolved)
            if not focused.ok:
                return focused
        if self._dialogs.has_pending_dialog:
            return _failure("a native dialog opened while focusing the field; nothing was typed")
        if action.clear_first:
            cleared = await self._clear_focused_field()
            if not cleared.ok:
                return cleared
        return await self._input("type", self._page.keyboard.type(action.text))

    async def _clear_focused_field(self) -> ActResult:
        selected = await self._input("select_all", self._page.keyboard.press("ControlOrMeta+A"))
        if not selected.ok:
            return selected
        return await self._input("clear", self._page.keyboard.press("Backspace"))

    async def _press(self, resolved: ResolvedTarget, action: PressAction) -> ActResult:
        focused = await self._focus(resolved)
        if not focused.ok:
            return focused
        return await self._input("press", self._page.keyboard.press(action.key))

    async def _focus(self, resolved: ResolvedTarget) -> ActResult:
        handle = resolved.handle
        if handle is not None and handle.backend_node_id is not None:
            focus = await self._cdp_guarded("DOM.focus", {"backendNodeId": handle.backend_node_id})
            if focus.ok and focus.value is not None:
                return ActResult(ok=True)
            return await self._click(resolved)
        if resolved.point is not None:
            return await self._click(resolved)
        return ActResult(ok=True)

    async def _select(self, resolved: ResolvedTarget, action: SelectAction) -> ActResult:
        handle = resolved.handle
        if handle is None or handle.backend_node_id is None:
            return _failure("select needs a node ref from the latest observation")
        selection = await self._select_by_script(handle.backend_node_id, action.option)
        if isinstance(selection, ActResult):
            return selection
        if selection["status"] == "selected":
            return ActResult(ok=True)
        if selection["status"] == "no_match":
            return _failure(f"option '{action.option}' not found; available: {selection['options']}")
        return await self._select_by_keyboard(resolved, action.option)

    async def _select_by_script(self, backend_node_id: int, option: str) -> dict[str, Any] | ActResult:
        resolved_object = await self._cdp_guarded(
            "DOM.resolveNode", {"backendNodeId": backend_node_id, "objectGroup": _SELECT_OBJECT_GROUP})
        if not resolved_object.ok or resolved_object.value is None:
            return _failure("select target no longer exists in the page")
        call = await self._cdp_guarded("Runtime.callFunctionOn", {
            "objectId": resolved_object.value["object"]["objectId"],
            "functionDeclaration": SELECT_OPTION_JS,
            "arguments": [{"value": option}],
            "returnByValue": True,
        })
        await self._cdp_guarded("Runtime.releaseObjectGroup", {"objectGroup": _SELECT_OBJECT_GROUP})
        if not call.ok or call.value is None:
            return _failure(call.error or "selecting the option by script failed")
        return dict(call.value["result"]["value"])

    async def _select_by_keyboard(self, resolved: ResolvedTarget, option: str) -> ActResult:
        """Fallback for custom (non-<select>) comboboxes: focus, type the option text, confirm."""
        focused = await self._click(resolved)
        if not focused.ok:
            return focused
        typed = await self._input("select_type", self._page.keyboard.type(option))
        if not typed.ok:
            return typed
        return await self._input("select_confirm", self._page.keyboard.press("Enter"))

    async def _scroll(self, resolved: ResolvedTarget, action: ScrollAction) -> ActResult:
        point = await self._point_for(resolved)
        if isinstance(point, str):
            return _failure(point)
        anchor = point or self._viewport_center()
        moved = await self._input("scroll_move", self._page.mouse.move(anchor.x, anchor.y))
        if not moved.ok:
            return moved
        direction = 1 if action.direction == "down" else -1
        delta_y = direction * action.amount * WHEEL_PIXELS_PER_STEP
        return await self._input("scroll", self._page.mouse.wheel(0, delta_y))

    # ------------------------------------------------------------ native dialogs

    async def _act_on_native_dialog(
        self, target: ActTarget, action: Action, handles: Mapping[str, NodeHandle]
    ) -> ActResult:
        handle = handles.get(target.ref) if isinstance(target, NodeRef) else None
        control = handle.native_control if handle is not None else None
        if isinstance(action, ClickAction) and control in ("accept", "dismiss"):
            return await self._dialogs.resolve(accept=control == "accept")
        if isinstance(action, TypeAction) and control == "prompt_input":
            return self._dialogs.set_prompt_text(action.text)
        if isinstance(action, PressAction) and action.key in ("Enter", "Escape"):
            return await self._dialogs.resolve(accept=action.key == "Enter")
        pending = self._dialogs.pending
        description = f"{pending.kind} ({pending.message!r})" if pending else "dialog"
        return _failure(f"a native {description} is open; click OK/Cancel or press Enter/Escape first")

    # ------------------------------------------------------------ helpers

    async def _point_for(self, resolved: ResolvedTarget) -> Point | str | None:
        """Click point for the target: fresh box center for nodes (scrolled into view first)."""
        if resolved.point is not None:
            return resolved.point
        handle = resolved.handle
        if handle is None:
            return None
        if handle.backend_node_id is not None:
            await self._cdp_guarded("DOM.scrollIntoViewIfNeeded", {"backendNodeId": handle.backend_node_id})
            box = await self._cdp_guarded("DOM.getBoxModel", {"backendNodeId": handle.backend_node_id})
            fresh_bounds = quad_to_rect(box.value["model"]["border"]) if box.ok and box.value else None
            if fresh_bounds is not None:
                return Point(x=fresh_bounds.center_x, y=fresh_bounds.center_y)
        if handle.bounds is not None:
            return Point(x=handle.bounds.center_x, y=handle.bounds.center_y)
        return f"node '{handle.ref}' has no box on screen (hidden or removed since the observation)"

    def _viewport_center(self) -> Point:
        viewport = self._page.viewport_size or {"width": 1280, "height": 800}
        return Point(x=viewport["width"] / 2, y=viewport["height"] / 2)

    async def _cdp_guarded(self, method: str, params: dict[str, Any]) -> Guarded[dict[str, Any] | None]:
        return await run_guarded(self._cdp.send(method, params), self._dialogs,
                                 timeout_s=self._config.cdp_timeout_ms / 1000, operation=method)

    async def _input(self, operation: str, awaitable: Awaitable[Any], timeout_ms: int | None = None) -> ActResult:
        """Run one input/navigation call. A dialog opened by it counts as success: the input landed."""
        timeout_s = (timeout_ms or self._config.action_timeout_ms) / 1000
        outcome = await run_guarded(awaitable, self._dialogs, timeout_s=timeout_s, operation=operation)
        if outcome.status in ("done", "dialog"):
            return ActResult(ok=True)
        return _failure(outcome.error or f"{operation} failed")


def _redacted_action_details(action: Action) -> dict[str, Any]:
    if isinstance(action, TypeAction):
        return {"text_length": len(action.text)}
    if isinstance(action, OpenAction):
        return {"entry_point": action.entry_point}
    if isinstance(action, PressAction):
        return {"key": action.key}
    return {}
