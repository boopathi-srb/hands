"""BrowserSurface: the Surface port over Playwright (Chromium) + CDP accessibility extraction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from playwright.async_api import Error as PlaywrightError

from hands.core.actions import Action, ActResult, ActTarget
from hands.core.log import get_logger, log_failure
from hands.core.observation import Observation
from hands.core.ports import SurfaceKind
from hands.surfaces.browser.actions import BrowserActions
from hands.surfaces.browser.cdp import CdpCaller
from hands.surfaces.browser.live_view import CdpLiveView
from hands.surfaces.browser.native_dialogs import NativeDialogKeeper
from hands.surfaces.browser.navigation import NavigationTracker
from hands.surfaces.browser.settle import SettleConfig, wait_for_settle
from hands.surfaces.browser.snapshot import NodeHandle, SnapshotBuilder

_LOGGER = get_logger(__name__)

FINAL_TRACE_NAME = "trace.zip"


class SurfaceLaunchError(RuntimeError):
    """The browser could not be started; there is no surface to return a typed result from."""


@dataclass
class _BrowserSession:
    playwright: Playwright
    browser: Browser
    context: BrowserContext
    page: Page


class BrowserSurface:
    """One Chromium page. Observe via the accessibility tree of every frame; act via page-level input."""

    kind: SurfaceKind = "web"

    def __init__(
        self,
        session: _BrowserSession,
        cdp: CdpCaller,
        dialogs: NativeDialogKeeper,
        navigations: NavigationTracker,
        config: SettleConfig,
        trace_dir: str | None,
    ) -> None:
        self._session = session
        self._cdp = cdp
        self._dialogs = dialogs
        self._navigations = navigations
        self._config = config
        self._trace_dir = trace_dir
        self._tracing = trace_dir is not None
        self._snapshots = SnapshotBuilder(session.page, cdp, dialogs, config)
        self._actions = BrowserActions(session.page, cdp, dialogs, config, navigations)
        self._handles: dict[str, NodeHandle] = {}
        self._last_observation: Observation | None = None
        self._closed = False
        self._live_view: CdpLiveView | None = None

    # ------------------------------------------------------------ lifecycle

    @classmethod
    async def launch(
        cls,
        headless: bool = True,
        viewport: tuple[int, int] = (1280, 800),
        record_trace_dir: str | None = None,
        settle: SettleConfig | None = None,
    ) -> BrowserSurface:
        """Start Chromium with one page. Raises SurfaceLaunchError (logged) if the browser cannot start."""
        playwright = await async_playwright().start()
        try:
            session = await _open_session(playwright, headless, viewport)
            if record_trace_dir is not None:
                Path(record_trace_dir).mkdir(parents=True, exist_ok=True)
                await session.context.tracing.start(screenshots=True, snapshots=True)
                await session.context.tracing.start_chunk()
            cdp = CdpCaller(await session.context.new_cdp_session(session.page))
        except PlaywrightError as error:
            log_failure(_LOGGER, "BrowserSurface.launch", str(error), headless=headless, viewport=viewport)
            await playwright.stop()
            raise SurfaceLaunchError(f"could not launch Chromium: {error}") from error
        dialogs = NativeDialogKeeper()
        dialogs.attach(session.page)
        navigations = NavigationTracker()
        navigations.attach(session.page)
        return cls(session, cdp, dialogs, navigations, settle or SettleConfig(), record_trace_dir)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._dialogs.close()
        if self._tracing and self._trace_dir is not None:
            await self._stop_tracing(str(Path(self._trace_dir) / FINAL_TRACE_NAME))
        await self._cdp.detach()
        await _close_quietly("context", self._session.context.close())
        await _close_quietly("browser", self._session.browser.close())
        await _close_quietly("playwright", self._session.playwright.stop())

    # ------------------------------------------------------------ Surface protocol

    async def observe(self, include_screenshot: bool = True) -> Observation:
        await wait_for_settle(self._session.page, self._dialogs, self._config, self._navigations)
        snapshot = await self._snapshots.capture(include_screenshot)
        self._handles = snapshot.handles
        self._last_observation = snapshot.observation
        return snapshot.observation

    async def act(self, target: ActTarget, action: Action) -> ActResult:
        if self._closed:
            return ActResult(ok=False, error="surface is closed")
        return await self._actions.perform(target, action, self._handles)

    def live_view(self) -> CdpLiveView:
        """One transport per session: the console streams through it and the input channel injects through it."""
        if self._live_view is None:
            self._live_view = CdpLiveView(self._session.page, self._dialogs, self._navigations)
        return self._live_view

    # ------------------------------------------------------------ evidence

    @property
    def last_observation(self) -> Observation | None:
        return self._last_observation

    @property
    def playwright_page(self) -> Page:
        """Escape hatch for adapter-level tests and evidence tooling inside this package's callers."""
        return self._session.page

    async def save_trace(self, path: str) -> str | None:
        """Write the Playwright trace recorded so far to `path` and keep recording. None on failure."""
        if not self._tracing:
            log_failure(_LOGGER, "BrowserSurface.save_trace", "tracing is off (no record_trace_dir)", path=path)
            return None
        tracing = self._session.context.tracing
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            await tracing.stop_chunk(path=path)
            await tracing.start_chunk()
        except PlaywrightError as error:
            log_failure(_LOGGER, "BrowserSurface.save_trace", str(error), path=path)
            return None
        return path

    async def _stop_tracing(self, path: str) -> None:
        self._tracing = False
        tracing = self._session.context.tracing
        try:
            await tracing.stop_chunk(path=path)
            await tracing.stop()
        except PlaywrightError as error:
            log_failure(_LOGGER, "BrowserSurface.close", f"could not save final trace: {error}", path=path)


async def _open_session(playwright: Playwright, headless: bool, viewport: tuple[int, int]) -> _BrowserSession:
    browser = await playwright.chromium.launch(headless=headless)
    context = await browser.new_context(viewport={"width": viewport[0], "height": viewport[1]},
                                        device_scale_factor=1)
    page = await context.new_page()
    return _BrowserSession(playwright=playwright, browser=browser, context=context, page=page)


async def _close_quietly(what: str, closing: object) -> None:
    try:
        await closing  # type: ignore[misc]
    except PlaywrightError as error:
        log_failure(_LOGGER, "BrowserSurface.close", str(error), closing=what)
