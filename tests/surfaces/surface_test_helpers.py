"""Helpers shared by the surface tests (imported as a plain module; tests/surfaces is on sys.path)."""

from __future__ import annotations

from hands.core.actions import Action, ActResult, NodeRef
from hands.core.observation import Node, Observation
from hands.core.ports import Surface


def find_node(observation: Observation, role: str | None = None, *, name: str | None = None,
              label: str | None = None, text: str | None = None) -> Node:
    """First node matching every given criterion; fails the test with a readable listing otherwise."""
    for node in observation.nodes:
        if (
            (role is None or node.role == role)
            and (name is None or node.name == name)
            and (label is None or node.label == label)
            and (text is None or node.text == text)
        ):
            return node
    listing = [(node.role, node.name, node.label) for node in observation.nodes]
    raise AssertionError(f"no node role={role!r} name={name!r} label={label!r} text={text!r} in {listing}")


def texts_of(observation: Observation) -> list[str]:
    return [node.text for node in observation.nodes if node.text]


async def act_on(surface: Surface, action: Action, role: str | None = None, *, name: str | None = None,
                 label: str | None = None) -> ActResult:
    """Observe, find the node, act on it by ref (the way replay drives a surface)."""
    observation = await surface.observe(include_screenshot=False)
    node = find_node(observation, role, name=name, label=label)
    return await surface.act(NodeRef(ref=node.ref), action)
