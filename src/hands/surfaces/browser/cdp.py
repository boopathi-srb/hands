"""Thin CDP session wrapper: the single I/O boundary where protocol errors become typed None results."""

from __future__ import annotations

from typing import Any

from playwright.async_api import CDPSession
from playwright.async_api import Error as PlaywrightError

from hands.core.log import get_logger, log_failure

_LOGGER = get_logger(__name__)


class CdpCaller:
    def __init__(self, session: CDPSession) -> None:
        self._session = session

    @property
    def session(self) -> CDPSession:
        return self._session

    async def send(
        self, method: str, params: dict[str, Any] | None = None, *, expected_failure: bool = False
    ) -> dict[str, Any] | None:
        """Send one command. Returns None on protocol errors, which are logged with context.

        `expected_failure` marks calls that routinely fail (box model of an invisible node) so they are
        logged at debug level instead of error level.
        """
        try:
            return await self._session.send(method, params or {})
        except PlaywrightError as error:
            if expected_failure:
                _LOGGER.debug("CDP %s failed (expected for some nodes): %s | params=%r", method, error, params)
            else:
                log_failure(_LOGGER, "CdpCaller.send", str(error), method=method, params=params)
            return None

    async def detach(self) -> None:
        try:
            await self._session.detach()
        except PlaywrightError as error:
            log_failure(_LOGGER, "CdpCaller.detach", str(error))
