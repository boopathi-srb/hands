"""Shared fixtures for surface tests: a local static site (for BrowserSurface) and the `browser` marker."""

from __future__ import annotations

import functools
import http.server
import threading
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

BROWSER_SITE_DIR = Path(__file__).parent / "browser_site"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "browser: drives a real headless Chromium through Playwright")


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture(scope="session")
def browser_site_url() -> Iterator[str]:
    """Serve tests/surfaces/browser_site on a free local port for the whole session."""
    handler = functools.partial(_QuietHandler, directory=str(BROWSER_SITE_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
async def browser_surface() -> AsyncIterator[object]:
    """A fresh headless BrowserSurface per test (imported lazily so fake-only runs never load playwright)."""
    from hands.surfaces.browser import BrowserSurface

    surface = await BrowserSurface.launch(headless=True)
    yield surface
    await surface.close()
