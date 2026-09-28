"""HumanInputChannel: the single path by which an operator's input reaches a live session.

Used by the console's websocket and by ScriptedEscalator, so both capture actions identically:

1. refuse unless the lease is held by `human` with this operator id and an intervention is open;
2. inject the raw event through the surface's LiveViewTransport (the SAME session automation used);
3. describe it as a HumanAction in artifact vocabulary: clicks are hit-tested against the most recent
   observation (node_role/node_name), typing is attributed to the last clicked node, and typed text is
   reduced to its length. Printable characters are never stored or logged;
4. write `human_action` evidence and accumulate the action on the InterventionBoard.

Pointer `down`/`up`/`move` and key `up` events are injected but not recorded as actions.
Key `down` with a single printable character counts as typing (length 1), never as a stored key.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from hands.core.control import HumanAction
from hands.core.log import get_logger, log_failure
from hands.core.observation import Node, Observation
from hands.core.ports import EvidenceSink, KeyEvent, LiveViewTransport, PointerEvent, Surface
from hands.session.board import InterventionBoard
from hands.session.hittest import node_at
from hands.session.lease import LeaseManager
from hands.session.support import Clock, utc_now

_logger: logging.Logger = get_logger(__name__)

InputRefusalCode = Literal[
    "not_in_control", "no_open_intervention", "no_live_view", "inject_failed"
]
FOCUS_MOVING_KEYS = frozenset({"Tab"})
PAGE_CHANGING_KEYS = frozenset({"Enter", "Escape"})


class InputAccepted(BaseModel):
    """The event reached the live session. `action` is None for events that are not recorded."""

    ok: Literal[True] = True
    action: HumanAction | None = None
    intervention_id: str


class InputRejected(BaseModel):
    ok: Literal[False] = False
    code: InputRefusalCode
    message: str


InputResult = InputAccepted | InputRejected


@dataclass(frozen=True)
class _Admission:
    transport: LiveViewTransport
    intervention_id: str


def is_printable_key(key: str) -> bool:
    """A single character key such as 'a' or '7' (as opposed to 'Enter' or 'ArrowDown')."""
    return len(key) == 1


def pointer_to_action(event: PointerEvent, node: Node | None, at: datetime) -> HumanAction | None:
    """A click or wheel as a HumanAction; None for down/up/move."""
    kind_by_type: dict[str, Literal["click", "scroll"]] = {"click": "click", "wheel": "scroll"}
    kind = kind_by_type.get(event.type)
    if kind is None:
        return None
    return HumanAction(
        at=at,
        kind=kind,
        x=event.x,
        y=event.y,
        node_role=None if node is None else node.role,
        node_name=None if node is None else node.name,
    )


def key_to_action(event: KeyEvent, focus_node: Node | None, at: datetime) -> HumanAction | None:
    """Typing (length only) or a named key press as a HumanAction; None for key up."""
    if event.type == "up":
        return None
    node_role = None if focus_node is None else focus_node.role
    node_name = None if focus_node is None else focus_node.name
    if event.type == "char":
        typed_length = len(event.text if event.text is not None else event.key)
        return HumanAction(
            at=at, kind="type", text_length=typed_length, node_role=node_role, node_name=node_name
        )
    if is_printable_key(event.key):
        return HumanAction(
            at=at, kind="type", text_length=1, node_role=node_role, node_name=node_name
        )
    return HumanAction(at=at, kind="press", key=event.key, node_role=node_role, node_name=node_name)


def human_action_evidence(action: HumanAction) -> dict[str, object]:
    """Evidence fields for a HumanAction; `kind` becomes `action_kind` (EvidenceSink.event owns `kind`)."""
    fields = action.model_dump(mode="json", exclude_none=True)
    fields["action_kind"] = fields.pop("kind")
    return fields


class HumanInputChannel:
    """Lease-checked operator input for one session, recorded as HumanActions."""

    def __init__(
        self,
        session_id: str,
        lease: LeaseManager,
        board: InterventionBoard,
        surface: Surface,
        evidence: EvidenceSink | None,
        clock: Clock = utc_now,
    ) -> None:
        self._session_id = session_id
        self._lease = lease
        self._board = board
        self._surface = surface
        self._evidence = evidence
        self._clock = clock
        self._latest_observation: Observation | None = None
        self._observation_stale = True
        self._focus_node: Node | None = None

    @property
    def latest_observation(self) -> Observation | None:
        return self._latest_observation

    async def refresh_observation(self) -> Observation | None:
        """Re-observe the surface (read-only) so clicks can be hit-tested; keeps the old one on failure."""
        try:
            observation = await self._surface.observe(include_screenshot=False)
        except Exception as error:  # noqa: BLE001 - surface adapter errors are adapter-specific
            log_failure(
                _logger,
                "HumanInputChannel.refresh_observation",
                repr(error),
                session_id=self._session_id,
            )
            return self._latest_observation
        self._latest_observation = observation
        self._observation_stale = False
        return observation

    async def send_pointer(self, operator_id: str, event: PointerEvent) -> InputResult:
        admission = self._admit(operator_id)
        if isinstance(admission, InputRejected):
            return admission
        node = await self._node_under(event) if event.type in ("click", "wheel") else None
        failure = await self._inject(admission.transport, event, operator_id)
        if failure is not None:
            return failure
        if event.type == "click":
            self._focus_node = node
            self._observation_stale = True
        action = pointer_to_action(event, node, self._clock())
        return self._record(admission.intervention_id, operator_id, action)

    async def send_key(self, operator_id: str, event: KeyEvent) -> InputResult:
        admission = self._admit(operator_id)
        if isinstance(admission, InputRejected):
            return admission
        failure = await self._inject(admission.transport, event, operator_id)
        if failure is not None:
            return failure
        action = key_to_action(event, self._focus_node, self._clock())
        self._track_focus_after_key(event)
        return self._record(admission.intervention_id, operator_id, action)

    # ------------------------------------------------------------ internals

    def _admit(self, operator_id: str) -> _Admission | InputRejected:
        if not self._lease.is_held_by("human", operator_id):
            return self._reject("not_in_control", "not in control", operator_id)
        intervention = self._board.open_for_session(self._session_id)
        if intervention is None:
            return self._reject("no_open_intervention", "no open intervention", operator_id)
        transport = self._surface.live_view()
        if transport is None:
            return self._reject("no_live_view", "surface has no live view", operator_id)
        return _Admission(transport=transport, intervention_id=intervention.intervention_id)

    async def _node_under(self, event: PointerEvent) -> Node | None:
        if self._observation_stale:
            await self.refresh_observation()
        return node_at(self._latest_observation, event.x, event.y)

    async def _inject(
        self, transport: LiveViewTransport, event: PointerEvent | KeyEvent, operator_id: str
    ) -> InputRejected | None:
        try:
            if isinstance(event, PointerEvent):
                await transport.inject_pointer(event)
            else:
                await transport.inject_key(event)
        except Exception as error:  # noqa: BLE001 - transport adapter errors are adapter-specific
            return self._reject("inject_failed", f"{type(error).__name__}: {error}", operator_id)
        return None

    def _track_focus_after_key(self, event: KeyEvent) -> None:
        if event.type != "down":
            return
        if event.key in FOCUS_MOVING_KEYS:
            self._focus_node = None
        if event.key in PAGE_CHANGING_KEYS or event.key in FOCUS_MOVING_KEYS:
            self._observation_stale = True

    def _record(
        self, intervention_id: str, operator_id: str, action: HumanAction | None
    ) -> InputAccepted:
        if action is None:
            return InputAccepted(action=None, intervention_id=intervention_id)
        self._board.record_human_action(intervention_id, action)
        if self._evidence is not None:
            self._evidence.event(
                "human_action",
                session_id=self._session_id,
                intervention_id=intervention_id,
                operator_id=operator_id,
                **human_action_evidence(action),
            )
        return InputAccepted(action=action, intervention_id=intervention_id)

    def _reject(self, code: InputRefusalCode, message: str, operator_id: str) -> InputRejected:
        log_failure(
            _logger,
            "HumanInputChannel.send",
            f"{code}: {message}",
            session_id=self._session_id,
            operator_id=operator_id,
        )
        return InputRejected(code=code, message=message)
