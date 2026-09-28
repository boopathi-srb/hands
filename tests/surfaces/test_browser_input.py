"""Key/pointer translation, the dialog guard, target resolution, and native dialog bookkeeping (no browser)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from hands.core.actions import NodeRef, Point
from hands.core.observation import Rect
from hands.core.ports import KeyEvent, PointerEvent
from hands.surfaces.browser.actions import resolve_target
from hands.surfaces.browser.guard import run_guarded
from hands.surfaces.browser.keys import KeyTranslator, PointerTranslator, key_definition
from hands.surfaces.browser.native_dialogs import NativeDialogKeeper, synthetic_nodes_for
from hands.surfaces.browser.snapshot import NodeHandle

# ---------------------------------------------------------------- keys


def test_key_definitions() -> None:
    assert key_definition("Enter").text == "\r" and key_definition("Enter").key_code == 13
    assert (key_definition("a").code, key_definition("a").key_code) == ("KeyA", 65)
    assert (key_definition("7").code, key_definition("7").key_code) == ("Digit7", 55)
    assert key_definition("?").key_code == 0 and key_definition("?").text == "?"
    assert key_definition("F13").text is None


def test_printable_key_down_inserts_text_and_char_is_deduplicated() -> None:
    translator = KeyTranslator()
    down = translator.translate(KeyEvent(type="down", key="a"))
    char = translator.translate(KeyEvent(type="char", key="a", text="a"))
    up = translator.translate(KeyEvent(type="up", key="a"))

    assert down == [{"type": "keyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65,
                     "nativeVirtualKeyCode": 65, "modifiers": 0, "text": "a", "unmodifiedText": "a"}]
    assert char == []
    assert up[0]["type"] == "keyUp"


def test_char_only_events_insert_text() -> None:
    assert KeyTranslator().translate(KeyEvent(type="char", key="z", text="z"))[0]["type"] == "char"


def test_named_keys_use_raw_key_down_except_enter() -> None:
    translator = KeyTranslator()
    backspace = translator.translate(KeyEvent(type="down", key="Backspace"))[0]
    enter = translator.translate(KeyEvent(type="down", key="Enter"))[0]
    assert (backspace["type"], backspace["windowsVirtualKeyCode"], "text" in backspace) == ("rawKeyDown", 8, False)
    assert (enter["type"], enter["text"]) == ("keyDown", "\r")
    assert translator.translate(KeyEvent(type="char", key="Enter", text="\r")) == []


def test_modifiers_are_tracked_and_suppress_text_for_chords() -> None:
    translator = KeyTranslator()
    translator.translate(KeyEvent(type="down", key="Control"))
    chord = translator.translate(KeyEvent(type="down", key="a"))[0]
    assert (chord["type"], chord["modifiers"]) == ("rawKeyDown", 2)
    assert translator.modifiers == 2
    translator.translate(KeyEvent(type="up", key="Control"))
    assert translator.modifiers == 0
    translator.translate(KeyEvent(type="down", key="Shift"))
    assert translator.translate(KeyEvent(type="down", key="A"))[0]["modifiers"] == 8


def test_pointer_translation() -> None:
    pointer = PointerTranslator()
    click = pointer.translate(PointerEvent(type="click", x=10, y=20))
    assert [params["type"] for params in click] == ["mouseMoved", "mousePressed", "mouseReleased"]
    assert click[1]["buttons"] == 1 and click[2]["buttons"] == 0
    assert pointer.translate(PointerEvent(type="down", x=1, y=1, button="right"))[0]["buttons"] == 2
    assert pointer.translate(PointerEvent(type="move", x=2, y=2))[0]["buttons"] == 2
    assert pointer.translate(PointerEvent(type="up", x=2, y=2, button="right"))[0]["buttons"] == 0
    wheel = pointer.translate(PointerEvent(type="wheel", x=0, y=0, delta_y=-100), modifiers=8)[0]
    assert (wheel["type"], wheel["deltaY"], wheel["modifiers"]) == ("mouseWheel", -100, 8)


# ---------------------------------------------------------------- guard


class FakeDialogSignal:
    def __init__(self, pending: bool = False) -> None:
        self.pending = pending
        self.appeared = asyncio.Event()
        self.parked: list[asyncio.Future[Any]] = []

    @property
    def has_pending_dialog(self) -> bool:
        return self.pending

    async def wait_for_dialog(self) -> None:
        await self.appeared.wait()

    def park(self, task: asyncio.Future[Any]) -> None:
        self.parked.append(task)


async def _value(result: int, delay: float = 0.0) -> int:
    await asyncio.sleep(delay)
    return result


async def _boom() -> int:
    raise RuntimeError("renderer went away")


async def test_guard_returns_value() -> None:
    outcome = await run_guarded(_value(7), FakeDialogSignal(), timeout_s=1, operation="test")
    assert (outcome.status, outcome.value, outcome.ok) == ("done", 7, True)


async def test_guard_turns_exceptions_into_failed() -> None:
    outcome = await run_guarded(_boom(), FakeDialogSignal(), timeout_s=1, operation="test")
    assert outcome.status == "failed" and "renderer went away" in (outcome.error or "")


async def test_guard_times_out() -> None:
    outcome = await run_guarded(_value(1, delay=5), FakeDialogSignal(), timeout_s=0.05, operation="slow")
    assert outcome.status == "timeout" and "slow" in (outcome.error or "")


async def test_guard_does_not_start_calls_while_dialog_is_open() -> None:
    signal = FakeDialogSignal(pending=True)
    outcome = await run_guarded(_value(1), signal, timeout_s=1, operation="test")
    assert outcome.status == "dialog" and signal.parked == []


async def test_guard_can_start_and_park_calls_behind_open_dialog() -> None:
    signal = FakeDialogSignal(pending=True)
    outcome = await run_guarded(_value(3), signal, timeout_s=1, operation="test", start_behind_open_dialog=True)
    assert outcome.status == "dialog" and len(signal.parked) == 1
    assert await signal.parked[0] == 3


async def test_guard_parks_call_blocked_by_a_new_dialog() -> None:
    signal = FakeDialogSignal()
    asyncio.get_running_loop().call_later(0.02, signal.appeared.set)
    outcome = await run_guarded(_value(9, delay=0.3), signal, timeout_s=2, operation="click")
    assert outcome.status == "dialog"
    assert len(signal.parked) == 1 and await signal.parked[0] == 9


# ---------------------------------------------------------------- target resolution


def _handles() -> dict[str, NodeHandle]:
    return {
        "n1": NodeHandle(ref="n1", role="button", backend_node_id=11, frame_id="F", bounds=Rect(x=0, y=0, width=1,
                                                                                                 height=1)),
        "n2": NodeHandle(ref="n2", role="button", backend_node_id=None, frame_id=None, bounds=None,
                         native_control="accept"),
    }


def test_resolve_target_variants() -> None:
    handles = _handles()
    assert resolve_target(NodeRef(ref="n1"), handles).handle == handles["n1"]
    assert resolve_target(Point(x=3, y=4), handles).point == Point(x=3, y=4)
    assert resolve_target(None, handles) == resolve_target(None, {})
    assert "unknown ref" in (resolve_target(NodeRef(ref="n9"), handles).error or "")
    assert "observe" in (resolve_target(NodeRef(ref="n1"), {}).error or "")
    assert "no longer open" in (resolve_target(NodeRef(ref="n2"), handles).error or "")


# ---------------------------------------------------------------- native dialogs


class FakePlaywrightDialog:
    def __init__(self, kind: str, message: str, default_value: str = "", fail: bool = False) -> None:
        self.type = kind
        self.message = message
        self.default_value = default_value
        self.answers: list[tuple[str, str | None]] = []
        self._fail = fail

    async def accept(self, prompt_text: str | None = None) -> None:
        self._maybe_fail()
        self.answers.append(("accept", prompt_text))

    async def dismiss(self) -> None:
        self._maybe_fail()
        self.answers.append(("dismiss", None))

    def _maybe_fail(self) -> None:
        if self._fail:
            from playwright.async_api import Error as PlaywrightError

            raise PlaywrightError("dialog already handled")


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("alert", [("dialog", "Hi"), ("button", "OK")]),
        ("confirm", [("dialog", "Hi"), ("button", "OK"), ("button", "Cancel")]),
        ("prompt", [("dialog", "Hi"), ("textbox", ""), ("button", "OK"), ("button", "Cancel")]),
        ("beforeunload", [("dialog", "Hi"), ("button", "OK"), ("button", "Cancel")]),
    ],
)
def test_synthetic_nodes_per_dialog_kind(kind: str, expected: list[tuple[str, str]]) -> None:
    nodes = synthetic_nodes_for(kind, "Hi", "default")
    assert [(item.node.role, item.node.name) for item in nodes] == expected
    assert all(item.node.container_path == ("dialog:native",) for item in nodes)


async def test_keeper_holds_and_accepts_prompt_with_text() -> None:
    keeper = NativeDialogKeeper()
    assert keeper.pending is None and keeper.dialog_model() is None and keeper.synthetic_nodes() == []
    dialog = FakePlaywrightDialog("prompt", "Reason?", "none")
    keeper._on_dialog(dialog)  # type: ignore[arg-type]

    assert keeper.has_pending_dialog
    assert keeper.dialog_model() is not None and keeper.dialog_model().native  # type: ignore[union-attr]
    assert keeper.set_prompt_text("audit").ok
    assert (await keeper.resolve(accept=True)).ok
    assert dialog.answers == [("accept", "audit")]
    assert not keeper.has_pending_dialog


async def test_keeper_dismiss_and_errors() -> None:
    keeper = NativeDialogKeeper()
    assert not (await keeper.resolve(accept=False)).ok
    assert not keeper.set_prompt_text("x").ok

    keeper._on_dialog(FakePlaywrightDialog("alert", "Hello"))  # type: ignore[arg-type]
    assert not keeper.set_prompt_text("x").ok  # not a prompt
    failing = FakePlaywrightDialog("confirm", "Sure?", fail=True)
    keeper._on_dialog(failing)  # type: ignore[arg-type]
    assert (await keeper.resolve(accept=False)).ok
    result = await keeper.resolve(accept=True)
    assert not result.ok and "dialog already handled" in (result.error or "")


async def test_keeper_signals_and_cancels_parked_calls() -> None:
    keeper = NativeDialogKeeper()
    waiter = asyncio.ensure_future(keeper.wait_for_dialog())
    keeper._on_dialog(FakePlaywrightDialog("alert", "x"))  # type: ignore[arg-type]
    await asyncio.wait_for(waiter, timeout=1)

    parked = asyncio.ensure_future(asyncio.sleep(10))
    keeper.park(parked)
    await keeper.close()
    await asyncio.sleep(0)
    assert parked.cancelled()
