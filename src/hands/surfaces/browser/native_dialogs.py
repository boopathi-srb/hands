"""Native JS dialogs (alert/confirm/prompt/beforeunload): held open, reported, dismissed on request.

Playwright auto-dismisses dialogs only when nobody listens to page 'dialog' events. The keeper listens
and does NOT answer, so the dialog stays up exactly like it would for a human until an act() closes it.
While it is open the observation shows only synthetic nodes (the page underneath is frozen):

    container ('dialog:native',)
    dialog[1]              role dialog, name = message
    dialog[1]/textbox[1]   prompt() input only
    dialog[1]/button[1]    'OK'      -> accept
    dialog[1]/button[2]    'Cancel'  -> dismiss (confirm, prompt, beforeunload only)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal

from playwright.async_api import Dialog as PlaywrightDialog
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from hands.core.actions import ActResult
from hands.core.log import get_logger, log_failure
from hands.core.observation import Dialog, Node

_LOGGER = get_logger(__name__)

NATIVE_DIALOG_CONTAINER = ("dialog:native",)
_CANCELLABLE_KINDS = ("confirm", "prompt", "beforeunload")

NativeControl = Literal["accept", "dismiss", "prompt_input"]


@dataclass
class PendingDialog:
    dialog: PlaywrightDialog
    kind: str
    message: str
    default_value: str
    prompt_text: str | None = None


@dataclass(frozen=True)
class SyntheticNode:
    node: Node
    control: NativeControl | None


class NativeDialogKeeper:
    """Holds native dialogs until an explicit accept/dismiss. Implements guard.DialogSignal."""

    def __init__(self) -> None:
        self._pending: list[PendingDialog] = []
        self._appeared = asyncio.Event()
        self._parked: list[asyncio.Future[Any]] = []

    def attach(self, page: Page) -> None:
        page.on("dialog", self._on_dialog)

    @property
    def has_pending_dialog(self) -> bool:
        return bool(self._pending)

    @property
    def pending(self) -> PendingDialog | None:
        return self._pending[0] if self._pending else None

    async def wait_for_dialog(self) -> None:
        await self._appeared.wait()

    def park(self, task: asyncio.Future[Any]) -> None:
        """Keep a call that is blocked behind the dialog; it resolves once the dialog closes."""
        self._parked.append(task)
        task.add_done_callback(self._forget_parked)

    def set_prompt_text(self, text: str) -> ActResult:
        current = self.pending
        if current is None or current.kind != "prompt":
            return ActResult(ok=False, error="no prompt() dialog is open")
        current.prompt_text = text
        return ActResult(ok=True)

    async def resolve(self, accept: bool) -> ActResult:
        """Accept (OK / Enter) or dismiss (Cancel / Escape) the oldest pending dialog."""
        current = self.pending
        if current is None:
            return ActResult(ok=False, error="no native dialog is open")
        self._pending.pop(0)
        if not self._pending:
            self._appeared.clear()
        return await _answer(current, accept)

    async def close(self) -> None:
        for task in list(self._parked):
            task.cancel()
        self._parked.clear()

    def synthetic_nodes(self) -> list[SyntheticNode]:
        current = self.pending
        return synthetic_nodes_for(current.kind, current.message, current.default_value) if current else []

    def dialog_model(self) -> Dialog | None:
        current = self.pending
        return Dialog(title=current.kind, text=current.message, native=True) if current else None

    def _on_dialog(self, dialog: PlaywrightDialog) -> None:
        self._pending.append(
            PendingDialog(dialog=dialog, kind=dialog.type, message=dialog.message, default_value=dialog.default_value)
        )
        self._appeared.set()
        _LOGGER.info("native %s dialog opened and held: %r", dialog.type, dialog.message)

    def _forget_parked(self, task: asyncio.Future[Any]) -> None:
        if task in self._parked:
            self._parked.remove(task)
        if not task.cancelled() and task.exception() is not None:
            _LOGGER.debug("parked browser call finished with %r after the dialog closed", task.exception())


async def _answer(pending: PendingDialog, accept: bool) -> ActResult:
    try:
        if accept:
            await pending.dialog.accept(pending.prompt_text or pending.default_value or "")
        else:
            await pending.dialog.dismiss()
    except PlaywrightError as error:
        log_failure(_LOGGER, "NativeDialogKeeper.resolve", str(error), kind=pending.kind, accept=accept)
        return ActResult(ok=False, error=f"could not {'accept' if accept else 'dismiss'} {pending.kind}: {error}")
    return ActResult(ok=True)


def synthetic_nodes_for(kind: str, message: str, default_value: str) -> list[SyntheticNode]:
    """Nodes (without refs) that represent a native dialog in an observation."""
    nodes = [SyntheticNode(_synthetic("dialog", message, "dialog[1]", text=message), None)]
    if kind == "prompt":
        nodes.append(SyntheticNode(
            _synthetic("textbox", "", "dialog[1]/textbox[1]", value=default_value, label=message), "prompt_input"))
    nodes.append(SyntheticNode(_synthetic("button", "OK", "dialog[1]/button[1]", text="OK"), "accept"))
    if kind in _CANCELLABLE_KINDS:
        nodes.append(SyntheticNode(_synthetic("button", "Cancel", "dialog[1]/button[2]", text="Cancel"), "dismiss"))
    return nodes


def _synthetic(role: str, name: str, path: str, *, text: str = "", value: str | None = None,
               label: str | None = None) -> Node:
    return Node(ref="", role=role, name=name, text=text, value=value, label=label,
                container_path=NATIVE_DIALOG_CONTAINER, structural_path=path)
