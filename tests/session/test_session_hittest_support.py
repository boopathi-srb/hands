"""Hit-testing and the small async/clock helpers."""

from __future__ import annotations

import asyncio

from hands.core.observation import Node, Rect
from hands.session.doubles import make_observation
from hands.session.hittest import node_at, rect_contains
from hands.session.support import utc_now, wait_for_event

FORM = Node(
    ref="n1", role="group", name="Search form", bounds=Rect(x=0, y=0, width=400, height=200)
)
BUTTON = Node(ref="n2", role="button", name="Search", bounds=Rect(x=10, y=10, width=80, height=30))
NO_BOUNDS = Node(ref="n3", role="text", name="caption")


def test_rect_contains_inside_edges_and_outside() -> None:
    bounds = Rect(x=10, y=10, width=80, height=30)
    assert rect_contains(bounds, 50, 25)
    assert rect_contains(bounds, 10, 10)
    assert rect_contains(bounds, 90, 40)
    assert not rect_contains(bounds, 91, 25)


def test_rect_contains_rejects_zero_area() -> None:
    assert not rect_contains(Rect(x=0, y=0, width=0, height=10), 0, 5)


def test_node_at_prefers_innermost_node() -> None:
    observation = make_observation([FORM, BUTTON, NO_BOUNDS])
    assert node_at(observation, 20, 20) == BUTTON
    assert node_at(observation, 300, 150) == FORM


def test_node_at_returns_none_outside_and_for_empty_or_missing_observation() -> None:
    assert node_at(make_observation([FORM]), 900, 900) is None
    assert node_at(make_observation([]), 5, 5) is None
    assert node_at(None, 5, 5) is None


async def test_wait_for_event_set_zero_timeout_and_timeout() -> None:
    event = asyncio.Event()
    assert not await wait_for_event(event, 0)
    assert not await wait_for_event(event, 0.01)
    event.set()
    assert await wait_for_event(event, 0)


async def test_wait_for_event_wakes_when_set_later() -> None:
    event = asyncio.Event()
    asyncio.get_running_loop().call_later(0.01, event.set)
    assert await wait_for_event(event, None)


def test_utc_now_is_timezone_aware() -> None:
    assert utc_now().tzinfo is not None
