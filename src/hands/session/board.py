"""InterventionBoard: in-memory registry of open and resolved interventions.

At most one intervention is open per session, so "which intervention is the human working on" and
"who is in control" always have a single answer. Human actions captured while an intervention is open
accumulate here and are attached to its resolution.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from hands.core.control import HumanAction, InterventionRequest, InterventionResolution
from hands.core.log import get_logger, log_failure
from hands.session.support import Clock, utc_now, wait_for_event

_logger: logging.Logger = get_logger(__name__)

InterventionStatus = Literal["open", "resolved"]
ResolutionOutcome = Literal["resume", "abort", "step_completed_by_human"]
BoardRefusalCode = Literal[
    "duplicate_intervention", "session_busy", "unknown_intervention", "already_resolved"
]


class InterventionRecord(BaseModel):
    """A snapshot of one intervention: request, status, captured human actions, resolution."""

    request: InterventionRequest
    status: InterventionStatus
    human_actions: list[HumanAction] = Field(default_factory=list)
    resolution: InterventionResolution | None = None


class BoardAccepted(BaseModel):
    ok: Literal[True] = True
    record: InterventionRecord


class BoardRefused(BaseModel):
    ok: Literal[False] = False
    code: BoardRefusalCode
    message: str


BoardResult = BoardAccepted | BoardRefused


@dataclass
class _Entry:
    request: InterventionRequest
    status: InterventionStatus = "open"
    human_actions: list[HumanAction] = field(default_factory=list)
    resolution: InterventionResolution | None = None
    resolved_event: asyncio.Event = field(default_factory=asyncio.Event)

    def snapshot(self) -> InterventionRecord:
        return InterventionRecord(
            request=self.request,
            status=self.status,
            human_actions=list(self.human_actions),
            resolution=self.resolution,
        )


def merge_typing(previous: HumanAction, current: HumanAction) -> HumanAction | None:
    """Merge consecutive typing into the same node into one action; None when they don't merge."""
    both_typing = previous.kind == "type" and current.kind == "type"
    same_node = (previous.node_role, previous.node_name) == (current.node_role, current.node_name)
    if not (both_typing and same_node):
        return None
    total_length = (previous.text_length or 0) + (current.text_length or 0)
    return previous.model_copy(update={"text_length": total_length, "at": current.at})


class InterventionBoard:
    """Registry of interventions with an asyncio event per intervention for its resolution."""

    def __init__(self, clock: Clock = utc_now) -> None:
        self._clock = clock
        self._entries: dict[str, _Entry] = {}

    # ------------------------------------------------------------ queries

    def list_open(self) -> list[InterventionRequest]:
        return [entry.request for entry in self._entries.values() if entry.status == "open"]

    def get(self, intervention_id: str) -> InterventionRecord | None:
        entry = self._entries.get(intervention_id)
        return None if entry is None else entry.snapshot()

    def has_open(self, session_id: str) -> bool:
        return self.open_for_session(session_id) is not None

    def open_for_session(self, session_id: str) -> InterventionRequest | None:
        open_requests = (
            request for request in self.list_open() if request.session_id == session_id
        )
        return next(open_requests, None)

    # ------------------------------------------------------------ lifecycle

    def open(self, request: InterventionRequest) -> BoardResult:
        if request.intervention_id in self._entries:
            return self._refuse("open", "duplicate_intervention", request.intervention_id)
        if self.has_open(request.session_id):
            return self._refuse("open", "session_busy", request.intervention_id)
        entry = _Entry(request=request)
        self._entries[request.intervention_id] = entry
        return BoardAccepted(record=entry.snapshot())

    def record_human_action(self, intervention_id: str, action: HumanAction) -> BoardResult:
        """Append a captured action; consecutive typing into the same node is merged."""
        entry = self._open_entry("record_human_action", intervention_id)
        if isinstance(entry, BoardRefused):
            return entry
        merged = merge_typing(entry.human_actions[-1], action) if entry.human_actions else None
        if merged is None:
            entry.human_actions.append(action)
        else:
            entry.human_actions[-1] = merged
        return BoardAccepted(record=entry.snapshot())

    def resolve(self, resolution: InterventionResolution) -> BoardResult:
        """Resolve with exactly this resolution and wake whoever is waiting on it."""
        entry = self._open_entry("resolve", resolution.intervention_id)
        if isinstance(entry, BoardRefused):
            return entry
        entry.status = "resolved"
        entry.resolution = resolution
        entry.resolved_event.set()
        return BoardAccepted(record=entry.snapshot())

    def resolve_from_operator(
        self, intervention_id: str, outcome: ResolutionOutcome, operator_id: str, note: str = ""
    ) -> BoardResult:
        """Resolve with the human actions captured so far attached."""
        entry = self._entries.get(intervention_id)
        captured_actions = [] if entry is None else list(entry.human_actions)
        resolution = InterventionResolution(
            intervention_id=intervention_id,
            outcome=outcome,
            operator_id=operator_id,
            note=note,
            human_actions=captured_actions,
            resolved_at=self._clock(),
        )
        return self.resolve(resolution)

    async def wait_for_resolution(
        self, intervention_id: str, timeout: float | None = None
    ) -> InterventionResolution | None:
        """The resolution once it exists; None on timeout or for an unknown id."""
        entry = self._entries.get(intervention_id)
        if entry is None:
            log_failure(
                _logger,
                "InterventionBoard.wait_for_resolution",
                "unknown intervention",
                intervention_id=intervention_id,
            )
            return None
        if not await wait_for_event(entry.resolved_event, timeout):
            return None
        return entry.resolution

    # ------------------------------------------------------------ internals

    def _open_entry(self, function_name: str, intervention_id: str) -> _Entry | BoardRefused:
        entry = self._entries.get(intervention_id)
        if entry is None:
            return self._refuse(function_name, "unknown_intervention", intervention_id)
        if entry.status != "open":
            return self._refuse(function_name, "already_resolved", intervention_id)
        return entry

    def _refuse(
        self, function_name: str, code: BoardRefusalCode, intervention_id: str
    ) -> BoardRefused:
        log_failure(
            _logger, f"InterventionBoard.{function_name}", code, intervention_id=intervention_id
        )
        return BoardRefused(code=code, message=f"{code}: {intervention_id}")
