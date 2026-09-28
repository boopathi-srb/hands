"""Wait until the page has settled before observing.

Order (every step bounded, every step ends early when a native JS dialog is open, because nothing in
the page can progress until it is answered):
1. Post-action grace: if an action finished less than `post_action_grace_ms` ago, wait out the rest,
   so a navigation that the action triggers (form submit, onclick redirect) has time to start.
2. Frame navigations: wait until every in-flight navigation of ANY frame committed and fired 'load'
   (see navigation.py). This is what makes child-frame POST -> 303 -> slow GET observable.
3. Network idle on the main frame (short cap).
4. DOM quiet: two consecutive equal DOM signatures across all frames, with every document 'complete'.
Caps are best-effort: a page that never goes idle is observed anyway, and replay's postcondition waits
take it from there.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from hands.core.log import get_logger
from hands.surfaces.browser.guard import DialogSignal, run_guarded
from hands.surfaces.browser.navigation import NavigationTracker, wait_for_navigations

_LOGGER = get_logger(__name__)

# readyState, element count, and markup size of one document: changes whenever the DOM changes.
DOM_SIGNATURE_JS = """() => [
  document.readyState,
  document.getElementsByTagName('*').length,
  document.documentElement ? document.documentElement.innerHTML.length : 0,
].join(':')"""
_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class SettleConfig:
    post_action_grace_ms: int = 150
    navigation_max_ms: int = 10_000
    network_idle_timeout_ms: int = 1_500
    dom_quiet_interval_ms: int = 120
    dom_quiet_max_ms: int = 2_500
    cdp_timeout_ms: int = 8_000
    action_timeout_ms: int = 10_000
    navigation_timeout_ms: int = 15_000


async def wait_for_settle(
    page: Page, dialogs: DialogSignal, config: SettleConfig, navigations: NavigationTracker | None = None
) -> None:
    if dialogs.has_pending_dialog:
        return
    if navigations is not None:
        await _wait_out_post_action_grace(navigations, config)
        await wait_for_navigations(navigations, dialogs, max_wait_s=config.navigation_max_ms / 1000)
        if dialogs.has_pending_dialog:
            return
    network_wait = await run_guarded(
        _wait_for_network_idle(page, config.network_idle_timeout_ms),
        dialogs,
        timeout_s=config.network_idle_timeout_ms / 1000 + 1,
        operation="settle.network_idle",
    )
    if network_wait.status == "dialog":
        return
    await _wait_for_dom_quiet(page, dialogs, config)


async def _wait_out_post_action_grace(navigations: NavigationTracker, config: SettleConfig) -> None:
    elapsed_s = navigations.seconds_since_action()
    grace_s = config.post_action_grace_ms / 1000
    if elapsed_s is not None and elapsed_s < grace_s and not navigations.has_pending:
        await asyncio.sleep(grace_s - elapsed_s)


async def _wait_for_network_idle(page: Page, timeout_ms: int) -> bool:
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except PlaywrightError as error:
        _LOGGER.debug("network not idle within %sms on %s: %s", timeout_ms, page.url, error)
        return False
    return True


async def _wait_for_dom_quiet(page: Page, dialogs: DialogSignal, config: SettleConfig) -> bool:
    """True once two consecutive signatures are equal and every frame is 'complete'; False at the cap."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + config.dom_quiet_max_ms / 1000
    previous_signature: tuple[str, ...] | None = None
    while loop.time() < deadline:
        sample = await run_guarded(dom_signature(page), dialogs, timeout_s=1.0, operation="settle.dom_signature")
        if sample.status == "dialog":
            return True
        signature = sample.value if sample.ok else None
        if signature is not None and signature == previous_signature and all_frames_complete(signature):
            return True
        previous_signature = signature
        await asyncio.sleep(config.dom_quiet_interval_ms / 1000)
    _LOGGER.debug("DOM did not go quiet within %sms on %s", config.dom_quiet_max_ms, page.url)
    return False


async def dom_signature(page: Page) -> tuple[str, ...]:
    """One 'name=readyState:elements:size' entry per frame; a frame that cannot be evaluated
    (mid-navigation, detached) reports 'name=unavailable'."""
    frames = page.frames
    results = await asyncio.gather(*(frame.evaluate(DOM_SIGNATURE_JS) for frame in frames), return_exceptions=True)
    return tuple(
        f"{frame.name}={result}" if isinstance(result, str) else f"{frame.name}={_UNAVAILABLE}"
        for frame, result in zip(frames, results, strict=True)
    )


def all_frames_complete(signature: tuple[str, ...]) -> bool:
    return all(entry.partition("=")[2].startswith("complete:") for entry in signature)
