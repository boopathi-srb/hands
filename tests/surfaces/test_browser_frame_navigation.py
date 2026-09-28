"""Regression: observe() right after an action must wait for child-frame navigations to finish.

A form inside the `content` frame POSTs, gets a 303, and the redirect target is served after a delay.
The very next observe() has to show the new page, not the old or a blank frame.
"""

from __future__ import annotations

import http.server
import threading
import time
from collections.abc import Iterator

import pytest

from hands.core.actions import ClickAction, NodeRef, OpenAction, PressAction, TypeAction
from hands.core.observation import Node, Observation
from hands.surfaces.browser import BrowserSurface

pytestmark = pytest.mark.browser

MEMBER_PAGE_DELAY_S = 0.3

FRAMESET_HTML = """<html><head><title>Nav Test</title></head>
<frameset rows="40,*"><frame name="top" src="/top"><frame name="content" src="/search"></frameset></html>"""
TOP_HTML = "<html><body>Signed on as teller1</body></html>"
SEARCH_HTML = """<html><body><form method="POST" action="/search">
<table><tr><td>Member Number</td><td><input type="text" name="member_number"></td></tr>
<tr><td colspan="2"><input type="submit" value="Search"></td></tr></table></form></body></html>"""
MEMBER_HTML = """<html><body><p>Member Detail {number}</p>
<table border="1"><tr><th>Share ID</th><th>Description</th></tr>
<tr><td>0001</td><td>Regular Savings</td></tr></table></body></html>"""


class _NavigationHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        routes = {"/": FRAMESET_HTML, "/top": TOP_HTML, "/search": SEARCH_HTML}
        if self.path.startswith("/member/"):
            time.sleep(MEMBER_PAGE_DELAY_S)
            self._send_html(MEMBER_HTML.format(number=self.path.rsplit("/", 1)[-1]))
            return
        body = routes.get(self.path)
        if body is None:
            self.send_error(404)
            return
        self._send_html(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        form = self.rfile.read(length).decode()
        member_number = form.partition("member_number=")[2] or "unknown"
        self.send_response(303)
        self.send_header("Location", f"/member/{member_number}")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_html(self, body: str) -> None:
        payload = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture(scope="module")
def navigation_site_url() -> Iterator[str]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _NavigationHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _find(observation: Observation, role: str, *, name: str | None = None, label: str | None = None) -> Node:
    return next(node for node in observation.nodes
                if node.role == role and (name is None or node.name == name)
                and (label is None or node.label == label))


def _texts(observation: Observation) -> list[str]:
    return [node.text for node in observation.nodes if node.text]


async def _search_form(surface: BrowserSurface, site_url: str, member_number: str) -> Observation:
    assert (await surface.act(None, OpenAction(entry_point=f"{site_url}/"))).ok
    form = await surface.observe(include_screenshot=False)
    textbox = _find(form, "textbox", label="Member Number")
    assert (await surface.act(NodeRef(ref=textbox.ref), TypeAction(text=member_number))).ok
    return form


@pytest.mark.parametrize("attempt", range(3))
async def test_observe_after_submit_click_waits_for_redirected_frame_navigation(
    browser_surface: BrowserSurface, navigation_site_url: str, attempt: int
) -> None:
    member_number = f"1000{attempt}"
    form = await _search_form(browser_surface, navigation_site_url, member_number)

    assert (await browser_surface.act(NodeRef(ref=_find(form, "button", name="Search").ref), ClickAction())).ok
    after = await browser_surface.observe(include_screenshot=False)

    assert f"Member Detail {member_number}" in _texts(after)
    assert _find(after, "columnheader", name="Share ID").container_path == ("frame:content",)


async def test_observe_after_enter_submit_waits_for_frame_navigation(
    browser_surface: BrowserSurface, navigation_site_url: str
) -> None:
    form = await _search_form(browser_surface, navigation_site_url, "20002")

    textbox = _find(form, "textbox", label="Member Number")
    assert (await browser_surface.act(NodeRef(ref=textbox.ref), PressAction(key="Enter"))).ok
    after = await browser_surface.observe(include_screenshot=False)

    assert "Member Detail 20002" in _texts(after)
