"""macOS desktop surface: the core Surface protocol over the Accessibility (AX) API.

Proves the Surface seam is real: a native app produces the same Observation model (roles, names,
labels, container/structural paths, bounds) as the browser surface. This is the only package allowed
to import pyobjc (ApplicationServices, Quartz, AppKit); those imports are lazy so the package imports
anywhere and is fully testable with a fake AxBackend.

The async `observe_app` lives in the `observe_app` submodule (not re-exported here, so the package
attribute stays the module).
"""

from hands.surfaces.desktop_macos.live_view import ScreenLiveView
from hands.surfaces.desktop_macos.observe_app import ObserveOutcome, observe_app_to_json
from hands.surfaces.desktop_macos.surface import MacDesktopSurface

__all__ = ["MacDesktopSurface", "ObserveOutcome", "ScreenLiveView", "observe_app_to_json"]
