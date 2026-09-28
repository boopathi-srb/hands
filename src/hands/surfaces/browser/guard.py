"""Run browser calls so a native JS dialog can never hang the surface.

While an alert/confirm/prompt is open, Chrome's renderer is blocked: every CDP call that touches the
page (Accessibility, DOM, Runtime, screenshots, even Page.getFrameTree) and every input dispatch that
triggered the dialog waits until the dialog is closed. `run_guarded` races the call against
"a dialog appeared" and a timeout. When a dialog wins, the still-pending call is parked (it completes
once the dialog is dismissed) and the caller reports the dialog instead of hanging.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Generic, Literal, Protocol, TypeVar

from hands.core.log import get_logger, log_failure

_LOGGER = get_logger(__name__)

T = TypeVar("T")
GuardStatus = Literal["done", "dialog", "timeout", "failed"]


class DialogSignal(Protocol):
    """What the guard needs from the native dialog keeper."""

    @property
    def has_pending_dialog(self) -> bool: ...

    async def wait_for_dialog(self) -> None: ...

    def park(self, task: asyncio.Future[Any]) -> None: ...


@dataclass(frozen=True)
class Guarded(Generic[T]):
    status: GuardStatus
    value: T | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "done"


async def run_guarded(
    awaitable: Awaitable[T],
    dialogs: DialogSignal,
    timeout_s: float,
    operation: str,
    *,
    start_behind_open_dialog: bool = False,
) -> Guarded[T]:
    """Await `awaitable` unless a native dialog is (or becomes) open or `timeout_s` passes.

    With a dialog already open the call is normally not started at all. `start_behind_open_dialog`
    starts it anyway and parks it, for calls that must eventually happen (start/stop a screencast).
    """
    if dialogs.has_pending_dialog:
        if start_behind_open_dialog:
            dialogs.park(asyncio.ensure_future(awaitable))
        else:
            _discard(awaitable)
        return Guarded(status="dialog")
    work: asyncio.Future[T] = asyncio.ensure_future(awaitable)
    dialog_appeared = asyncio.ensure_future(dialogs.wait_for_dialog())
    racing: list[asyncio.Future[Any]] = [work, dialog_appeared]
    done, _ = await asyncio.wait(racing, timeout=timeout_s, return_when=asyncio.FIRST_COMPLETED)
    dialog_appeared.cancel()
    if work in done:
        return _outcome_of(work, operation)
    if dialog_appeared in done:
        dialogs.park(work)
        return Guarded(status="dialog")
    work.cancel()
    log_failure(_LOGGER, "run_guarded", "timed out", operation=operation, timeout_s=timeout_s)
    return Guarded(status="timeout", error=f"{operation} timed out after {timeout_s:.1f}s")


def _outcome_of(work: asyncio.Future[T], operation: str) -> Guarded[T]:
    error = work.exception()
    if error is not None:
        log_failure(_LOGGER, "run_guarded", f"{type(error).__name__}: {error}", operation=operation)
        return Guarded(status="failed", error=f"{operation} failed: {error}")
    return Guarded(status="done", value=work.result())


def _discard(awaitable: Awaitable[object]) -> None:
    """Close an un-started coroutine so Python does not warn that it was never awaited."""
    if inspect.iscoroutine(awaitable):
        awaitable.close()
