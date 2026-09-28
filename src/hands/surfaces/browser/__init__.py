"""Web surface: Playwright + CDP. The ONLY package in hands allowed to import playwright.

Observation pipeline (see each module):
    frames.py       Page.getFrameTree -> frames with container paths ('frame:content')
    ax_extract.py   Accessibility.getFullAXTree per frame -> kept nodes, text runs
    roles.py        Chrome role -> normalized role
    snapshot.py     page-level geometry (DOM.getBoxModel / DOM.getContentQuads), refs, Observation
    assemble.py     inline text merging, names, structural paths, label inference
    modals.py       in-page dialogs (role dialog + positioned-table heuristic)
    native_dialogs  JS alert/confirm/prompt held open and reported as Dialog(native=True)
Settling: settle.py + navigation.py (post-action grace, every frame's in-flight navigation committed and
loaded, network idle, DOM quiet with all documents 'complete').
Acting: actions.py (page.mouse / keyboard / CDP select), guarded against native dialogs (guard.py).
Live view: live_view.py (CDP screencast + Input.dispatch*), keys.py (event translation).
"""

from hands.surfaces.browser.live_view import CdpLiveView
from hands.surfaces.browser.settle import SettleConfig
from hands.surfaces.browser.surface import BrowserSurface, SurfaceLaunchError

__all__ = ["BrowserSurface", "CdpLiveView", "SettleConfig", "SurfaceLaunchError"]
