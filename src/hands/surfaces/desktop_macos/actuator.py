"""Turns core actions into AX actions, falling back to synthetic CGEvent input.

Preference order is always "semantic first": AXPress / AXValue work even when the window is behind
others and do not move the user's mouse. CGEvent input is the fallback for custom-drawn controls
that expose no action or settable value; before it, the app is activated so input lands in it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from hands.core.actions import ActResult
from hands.core.log import get_logger, log_failure
from hands.surfaces.desktop_macos.ax import Action, Attr, AxBackend, AxElement, AxPoint
from hands.surfaces.desktop_macos.events import EventPoster, scroll_lines
from hands.surfaces.desktop_macos.mapping import collapse_whitespace

logger = get_logger(__name__)

Sleep = Callable[[float], Awaitable[None]]
Activate = Callable[[], ActResult]

MENU_AX_ROLE = "AXMenu"
MENU_ITEM_AX_ROLE = "AXMenuItem"
SELECT_ALL_KEY = "Cmd+A"
DELETE_KEY = "Delete"


@dataclass(frozen=True)
class ResolvedTarget:
    """An act() target after ref/point resolution. Either part may be missing."""

    element: AxElement | None
    screen_point: AxPoint | None
    description: str


@dataclass(frozen=True)
class MenuTimings:
    timeout_s: float = 1.0
    poll_s: float = 0.1


def _error(function_name: str, message: str, **inputs: object) -> ActResult:
    log_failure(logger, function_name, message, **inputs)
    return ActResult(ok=False, error=message)


class AxActuator:
    def __init__(
        self,
        backend: AxBackend,
        events: EventPoster,
        activate: Activate,
        sleep: Sleep,
        menu_timings: MenuTimings | None = None,
    ) -> None:
        self._backend = backend
        self._events = events
        self._activate = activate
        self._sleep = sleep
        self._menu_timings = menu_timings or MenuTimings()

    # ---------------------------------------------------- AX helpers

    def supports_action(self, element: AxElement, action: str) -> bool:
        action_names = self._backend.action_names(element)
        return action_names.ok and action in (action_names.value or [])

    def _press(self, element: AxElement) -> bool:
        return (
            self.supports_action(element, Action.PRESS)
            and self._backend.perform_action(element, Action.PRESS).ok
        )

    def _focus(self, element: AxElement) -> bool:
        return self._backend.set_attribute(element, Attr.FOCUSED, True).ok

    def _value_settable(self, element: AxElement) -> bool:
        settable = self._backend.is_settable(element, Attr.VALUE)
        return settable.ok and settable.value is True

    def _current_value(self, element: AxElement) -> str:
        current = self._backend.attribute(element, Attr.VALUE).value
        return current if isinstance(current, str) else ""

    def _activate_for_events(self, function_name: str, target: ResolvedTarget) -> None:
        activation = self._activate()
        if not activation.ok:
            log_failure(
                logger,
                function_name,
                f"activate before CGEvent failed: {activation.error}",
                target=target.description,
            )

    def _event_click(self, function_name: str, target: ResolvedTarget) -> ActResult:
        if target.screen_point is None:
            return _error(
                function_name, f"no AX action and no bounds to click for {target.description}"
            )
        self._activate_for_events(function_name, target)
        return self._events.click(target.screen_point.x, target.screen_point.y)

    # ---------------------------------------------------- click

    async def click(self, target: ResolvedTarget) -> ActResult:
        """AXPress when supported; otherwise a CGEvent click at the element (or point) center."""
        if target.element is not None and self._press(target.element):
            return ActResult(ok=True)
        return self._event_click("click", target)

    # ---------------------------------------------------- type

    async def type_text(self, target: ResolvedTarget, text: str, clear_first: bool) -> ActResult:
        """Focus + set AXValue (verified by read-back); else click, optionally select-all/delete, key-type."""
        if target.element is not None and self._set_value_semantically(
            target.element, text, clear_first
        ):
            return ActResult(ok=True)
        return self._type_with_events(target, text, clear_first)

    def _set_value_semantically(self, element: AxElement, text: str, clear_first: bool) -> bool:
        if not self._focus(element):
            logger.info("type: AXFocused not settable; continuing with AXValue")
        if not self._value_settable(element):
            return False
        new_value = text if clear_first else self._current_value(element) + text
        if not self._backend.set_attribute(element, Attr.VALUE, new_value).ok:
            return False
        return self._current_value(element) == new_value

    def _type_with_events(self, target: ResolvedTarget, text: str, clear_first: bool) -> ActResult:
        if target.screen_point is not None:
            focus_click = self._event_click("type_text", target)
            if not focus_click.ok:
                return focus_click
        elif target.element is not None:
            return _error(
                "type_text",
                f"cannot set value and no bounds to focus {target.description}",
                text_length=len(text),
            )
        else:
            self._activate_for_events("type_text", target)
        if clear_first:
            clear_result = self._clear_focused_field()
            if not clear_result.ok:
                return clear_result
        return self._events.type_text(text)

    def _clear_focused_field(self) -> ActResult:
        select_all = self._events.key(SELECT_ALL_KEY)
        return select_all if not select_all.ok else self._events.key(DELETE_KEY)

    # ---------------------------------------------------- press

    async def press(self, target: ResolvedTarget, key: str) -> ActResult:
        """Focus the target (if any), activate the app, and send the key combo as CGEvents."""
        if target.element is not None and not self._focus(target.element):
            logger.info(
                "press: could not focus %s; sending key to current focus", target.description
            )
        self._activate_for_events("press", target)
        return self._events.key(key)

    # ---------------------------------------------------- select

    async def select(self, target: ResolvedTarget, option: str) -> ActResult:
        """Open a popup/combobox with AXPress, then AXPress the menu item whose title matches `option`."""
        if target.element is None:
            return _error("select", "select needs a node target", option=option)
        opened = await self.click(target)
        if not opened.ok:
            return opened
        menu_item = await self._wait_for_menu_item(target.element, option)
        if menu_item is not None:
            if self._backend.perform_action(menu_item, Action.PRESS).ok:
                return ActResult(ok=True)
            return _error(
                "select", f"menu item {option!r} did not accept AXPress", target=target.description
            )
        self._close_menu(target.element)
        if (
            self._value_settable(target.element)
            and self._backend.set_attribute(target.element, Attr.VALUE, option).ok
        ):
            return ActResult(ok=True)
        return _error("select", f"option {option!r} not found in menu", target=target.description)

    async def _wait_for_menu_item(self, popup: AxElement, option: str) -> AxElement | None:
        elapsed_s = 0.0
        while True:
            menu_item = self.find_menu_item(popup, option)
            if menu_item is not None or elapsed_s >= self._menu_timings.timeout_s:
                return menu_item
            await self._sleep(self._menu_timings.poll_s)
            elapsed_s += self._menu_timings.poll_s

    def _children(self, element: AxElement) -> list[AxElement]:
        children = self._backend.attribute(element, Attr.CHILDREN).value
        return list(children) if isinstance(children, list) else []

    def _ax_role(self, element: AxElement) -> str:
        role = self._backend.attribute(element, Attr.ROLE).value
        return role if isinstance(role, str) else ""

    def _menu_items(self, popup: AxElement) -> list[AxElement]:
        menus = [child for child in self._children(popup) if self._ax_role(child) == MENU_AX_ROLE]
        return [
            item
            for menu in menus
            for item in self._children(menu)
            if self._ax_role(item) == MENU_ITEM_AX_ROLE
        ]

    def find_menu_item(self, popup: AxElement, option: str) -> AxElement | None:
        """The open menu's item titled `option` (exact first, then case-insensitive), or None."""
        titled_items = [
            (collapse_whitespace(str(self._backend.attribute(item, Attr.TITLE).value or "")), item)
            for item in self._menu_items(popup)
        ]
        wanted = collapse_whitespace(option)
        exact = next((item for title, item in titled_items if title == wanted), None)
        if exact is not None:
            return exact
        return next(
            (item for title, item in titled_items if title.casefold() == wanted.casefold()), None
        )

    def _close_menu(self, popup: AxElement) -> None:
        for menu in self._children(popup):
            if (
                self._ax_role(menu) == MENU_AX_ROLE
                and self._backend.perform_action(menu, Action.CANCEL).ok
            ):
                return
        escape_result = self._events.key("Escape")
        if not escape_result.ok:
            log_failure(logger, "_close_menu", f"Escape failed: {escape_result.error}")

    # ---------------------------------------------------- scroll

    async def scroll(
        self, target: ResolvedTarget, direction: Literal["up", "down"], amount: int
    ) -> ActResult:
        """Scroll-wheel CGEvent at the target center (wheel events go to the window under the cursor)."""
        if target.screen_point is None:
            return _error(
                "scroll", f"no point to scroll at for {target.description}", direction=direction
            )
        return self._events.scroll(
            target.screen_point.x, target.screen_point.y, scroll_lines(direction, amount)
        )
