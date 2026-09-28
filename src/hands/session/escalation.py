"""Escalators: raise an intervention, cede the SAME live session to a human, resume on hand-back.

Both escalators share one lifecycle (template method in `_EscalationLifecycle.escalate`):

1. open the intervention on the InterventionBoard (at most one open per session);
2. write `escalation_raised` evidence (with the request's screenshot path) and release the lease to
   `nobody`, so the operator can take it;
3. wait for a resolution (subclass-specific: a person at the console, or a script);
4. restore control: a human still holding the lease is force-released, then, unless the outcome is
   `abort`, the lease is re-granted to automation for the same run id;
5. write `escalation_resolved` evidence and return the resolution with the captured HumanActions.

Refusals (duplicate id, busy session, wrong session) resolve immediately as `abort` by `system`.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence

from hands.core.control import InterventionRequest, InterventionResolution
from hands.core.log import get_logger, log_failure
from hands.core.ports import EvidenceSink, KeyEvent, PointerEvent, Surface
from hands.session.board import (
    BoardRefused,
    BoardResult,
    InterventionBoard,
    InterventionRecord,
    ResolutionOutcome,
)
from hands.session.human_input import HumanInputChannel
from hands.session.lease import LeaseManager
from hands.session.support import Clock, utc_now

__all__ = [
    "SYSTEM_OPERATOR",
    "ConsoleEscalator",
    "InterventionBoard",
    "InterventionRecord",
    "ScriptedEscalator",
    "ScriptedInput",
    "operator_url",
]

_logger: logging.Logger = get_logger(__name__)

SYSTEM_OPERATOR = "system"
ScriptedInput = PointerEvent | KeyEvent
Announcer = Callable[[str], None]


def operator_url(console_url: str, intervention_id: str) -> str:
    """Link that opens the operator console focused on one intervention."""
    return f"{console_url.rstrip('/')}/?intervention={intervention_id}"


def _log_announcement(line: str) -> None:
    _logger.warning(line)


class _EscalationLifecycle(ABC):
    """Shared open -> release -> await -> restore -> record lifecycle."""

    def __init__(
        self,
        board: InterventionBoard,
        lease: LeaseManager,
        evidence: EvidenceSink,
        clock: Clock = utc_now,
    ) -> None:
        self._board = board
        self._lease = lease
        self._evidence = evidence
        self._clock = clock

    async def escalate(self, request: InterventionRequest) -> InterventionResolution:
        refusal = self._open(request)
        if refusal is not None:
            return refusal
        self._record_raised(request)
        self._release_for_human(request)
        resolution = await self._await_resolution(request)
        self._restore_control(request, resolution)
        self._record_resolved(request, resolution)
        return resolution

    @abstractmethod
    async def _await_resolution(self, request: InterventionRequest) -> InterventionResolution:
        """Block until the intervention is resolved and return the resolution."""

    # ------------------------------------------------------------ steps

    def _open(self, request: InterventionRequest) -> InterventionResolution | None:
        if request.session_id != self._lease.session_id:
            message = f"request session {request.session_id} is not lease session {self._lease.session_id}"
            return self._refused(request, message)
        opened = self._board.open(request)
        if isinstance(opened, BoardRefused):
            return self._refused(request, opened.message)
        return None

    def _record_raised(self, request: InterventionRequest) -> None:
        fields = request.model_dump(mode="json")
        fields["intervention_kind"] = fields.pop("kind")
        self._evidence.event("escalation_raised", **fields)

    def _release_for_human(self, request: InterventionRequest) -> None:
        reason = f"escalation {request.intervention_id}: {request.kind}"
        self._lease.release(reason=reason)

    def _restore_control(
        self, request: InterventionRequest, resolution: InterventionResolution
    ) -> None:
        if self._lease.current().holder == "human":
            self._lease.release(
                reason=f"intervention {request.intervention_id} closed by {resolution.operator_id}"
            )
        if resolution.outcome == "abort":
            return
        self._lease.grant_automation(
            request.run_id, reason=f"resumed after {request.intervention_id}: {resolution.outcome}"
        )

    def _record_resolved(
        self, request: InterventionRequest, resolution: InterventionResolution
    ) -> None:
        self._evidence.event(
            "escalation_resolved",
            intervention_id=request.intervention_id,
            session_id=request.session_id,
            run_id=request.run_id,
            outcome=resolution.outcome,
            operator_id=resolution.operator_id,
            note=resolution.note,
            human_action_count=len(resolution.human_actions),
            holder_after=self._lease.current().holder,
        )

    # ------------------------------------------------------------ helpers

    def _resolve(
        self, request: InterventionRequest, outcome: ResolutionOutcome, operator_id: str, note: str
    ) -> InterventionResolution:
        """Resolve on the board; if someone else resolved first, their resolution wins."""
        resolved = self._board.resolve_from_operator(
            request.intervention_id, outcome, operator_id, note
        )
        return self._resolution_from(request, resolved)

    def _resolution_from(
        self, request: InterventionRequest, resolved: BoardResult
    ) -> InterventionResolution:
        if isinstance(resolved, BoardRefused):
            record = self._board.get(request.intervention_id)
        else:
            record = resolved.record
        if record is None or record.resolution is None:
            return self._refused(request, "intervention vanished from the board")
        return record.resolution

    def _refused(self, request: InterventionRequest, message: str) -> InterventionResolution:
        log_failure(
            _logger,
            f"{type(self).__name__}.escalate",
            message,
            intervention_id=request.intervention_id,
            session_id=request.session_id,
        )
        return InterventionResolution(
            intervention_id=request.intervention_id,
            outcome="abort",
            operator_id=SYSTEM_OPERATOR,
            note=f"escalation refused: {message}",
            resolved_at=self._clock(),
        )


class ConsoleEscalator(_EscalationLifecycle):
    """Waits for a person at the operator console; aborts after `timeout_s` if nobody resolves."""

    def __init__(
        self,
        board: InterventionBoard,
        lease: LeaseManager,
        evidence: EvidenceSink,
        console_url: str,
        timeout_s: float | None = None,
        announce: Announcer = _log_announcement,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(board, lease, evidence, clock)
        self._console_url = console_url
        self._timeout_s = timeout_s
        self._announce = announce

    async def _await_resolution(self, request: InterventionRequest) -> InterventionResolution:
        self._announce(self._announcement(request))
        resolution = await self._board.wait_for_resolution(request.intervention_id, self._timeout_s)
        if resolution is not None:
            return resolution
        return self._time_out(request)

    def _announcement(self, request: InterventionRequest) -> str:
        return (
            f"INTERVENTION NEEDED [{request.kind}] session={request.session_id} run={request.run_id}: "
            f"{request.reason} -> take control at {operator_url(self._console_url, request.intervention_id)}"
        )

    def _time_out(self, request: InterventionRequest) -> InterventionResolution:
        note = f"no operator resolution within {self._timeout_s}s"
        log_failure(
            _logger,
            "ConsoleEscalator.escalate",
            note,
            intervention_id=request.intervention_id,
            session_id=request.session_id,
        )
        self._evidence.event(
            "escalation_timeout", intervention_id=request.intervention_id, timeout_s=self._timeout_s
        )
        return self._resolve(request, "abort", SYSTEM_OPERATOR, note)


class ScriptedEscalator(_EscalationLifecycle):
    """Headless stand-in for an operator: takes control, replays scripted input, hands back.

    Scripted input goes through the same HumanInputChannel as the console, so evidence shows real
    `human_action` events and lease transitions. Without a script or live view it simply resolves.
    """

    def __init__(
        self,
        board: InterventionBoard,
        lease: LeaseManager,
        evidence: EvidenceSink,
        outcome: ResolutionOutcome = "resume",
        operator_id: str = "scripted-operator",
        note: str = "",
        script: Sequence[ScriptedInput] = (),
        surface: Surface | None = None,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(board, lease, evidence, clock)
        self._outcome: ResolutionOutcome = outcome
        self._operator_id = operator_id
        self._note = note
        self._script = list(script)
        self._surface = surface

    async def _await_resolution(self, request: InterventionRequest) -> InterventionResolution:
        taken = self._lease.take_human(
            self._operator_id, reason=f"scripted operator for {request.intervention_id}"
        )
        if not taken.ok:
            return self._resolve(
                request, "abort", SYSTEM_OPERATOR, f"scripted take failed: {taken.code}"
            )
        await self._play_script(request)
        self._lease.hand_back(self._operator_id)
        return self._resolve(request, self._outcome, self._operator_id, self._note)

    async def _play_script(self, request: InterventionRequest) -> None:
        if not self._script or self._surface is None:
            return
        channel = HumanInputChannel(
            request.session_id, self._lease, self._board, self._surface, self._evidence, self._clock
        )
        await channel.refresh_observation()
        for scripted_input in self._script:
            await self._send(channel, scripted_input)

    async def _send(self, channel: HumanInputChannel, scripted_input: ScriptedInput) -> None:
        if isinstance(scripted_input, PointerEvent):
            await channel.send_pointer(self._operator_id, scripted_input)
        else:
            await channel.send_key(self._operator_id, scripted_input)
