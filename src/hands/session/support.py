"""Small shared helpers for the session package: a UTC clock and exception-free event waiting."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


async def wait_for_event(event: asyncio.Event, timeout_s: float | None) -> bool:
    """Wait until `event` is set. Returns False on timeout instead of raising.

    `timeout_s=None` waits forever; `timeout_s <= 0` only checks the current state.
    """
    if event.is_set():
        return True
    if timeout_s is not None and timeout_s <= 0:
        return False
    waiter = asyncio.ensure_future(event.wait())
    try:
        done, _pending = await asyncio.wait({waiter}, timeout=timeout_s)
    finally:
        if not waiter.done():
            waiter.cancel()
    return bool(done)
